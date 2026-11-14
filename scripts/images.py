"""PoliDesk image pipeline.

Feeds give photos of very different sizes (a 300 px Toronto Star thumbnail, a
7000 px CBC original, portrait NPR crops) and some give none at all (Al Jazeera,
Good News Network). For every story this module:

1. collects candidates: the feed's photo, plus the article page's own share
   image (og:image / twitter:image / JSON-LD) when the feed photo is missing or weak;
2. asks the outlet's image CDN for a standard width (1200 px, plus 640 px for
   small screens) using each CDN's resize parameters;
3. measures the real pixel size by reading only the image header;
4. keeps the best landscape photo and drops logos and tiny images.

Photos stay on the outlets' servers (hotlinked exactly as before); we only choose
which copy and size to show. Results are cached in data/images.json by story id,
so each story's page is read once. Standard library only.
"""
import html
import json
import re
import struct
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

BIG = 1200            # main photo width
SMALL = 640           # srcset width for phones and list thumbnails
WEAK_W = 640          # a feed photo narrower than this sends us to the article page
MIN_W = 360           # narrower than this is a thumbnail or icon: not shown
MAX_PAGES = 60        # article pages read per run (the rest wait for the next run)
DEADLINE = 100        # seconds this step may take per run
RETRY_AFTER = timedelta(hours=2)
MAX_TRIES = 3
KEEP_DAYS = 35
UA = "Mozilla/5.0 (compatible; PoliDesk/1.0; +https://polidesk.ca/about/)"
BAD_URL = re.compile(r"logo|placeholder|default[-_]?(image|share|og)|1x1|pixel|spacer|\.gif(\?|$)|\.svg(\?|$)|overlay-", re.I)


# ---------------------------------------------------------------- CDN size rules
def _set_query(url, **params):
    p = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k not in params]
    q += [(k, str(v)) for k, v in params.items()]
    return urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(q)))


def sized(url, w):
    """The same photo at about `w` px wide, or None when we don't know this CDN."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    if "ichef.bbci.co.uk" in host:
        u = re.sub(r"(/(?:ace|news)/(?:standard|ws)/)\d+/", rf"\g<1>{w}/", url)
        return u if u != url or f"/{w}/" in url else None
    if host == "i.cbc.ca" and "/ais/" in url:
        # Akamai Image Manager: append a Resize step to the crop the feed already asks for.
        p = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
        steps = re.sub(r";?Resize=\(\d+\);?", ";", q.get("im", "")).strip(";")
        q["im"] = (steps + ";" if steps else "") + f"Resize=({w})"
        return urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(q)))
    if host.endswith("brightspotcdn.com") and "/dims3/" in url:
        m = re.search(r"/crop/(\d+)x\d+", url)
        if m and int(m.group(1)) < w:
            w = int(m.group(1))  # never ask for more pixels than the crop has
        u = re.sub(r"/resize/[^/]+/", f"/resize/{w}/", url)
        if u == url and "/resize/" not in url:
            u = url.replace("/quality/", f"/resize/{w}/quality/", 1)
        return u
    if host.endswith("townnews.com"):
        return _set_query(url, resize=f"{w},")
    if host in ("globalnews.ca", "www.aljazeera.com", "policyoptions.irpp.org", "www.goodnewsnetwork.org") and "/wp-content/uploads/" in url:
        if "globalnews.ca" in host:
            return _set_query(url, w=w, h=round(w * 2 / 3), crop=1, quality=70, strip="all")
        return _set_query(url, resize=f"{w},{round(w * 2 / 3)}")
    if host == "images.theconversation.com":
        return _set_query(url, w=w, fit="clip")
    if host == "cdnph.upi.com":
        m = re.match(r"(https://cdnph\.upi\.com)/ph/st/th/(\d+)/(\d{4})/i/(\d+)/v[\d.]+/(.+)$", url)
        if m:
            return f"{m.group(1)}/svc/sv/i/{m.group(2)}/{m.group(3)}/1/{m.group(4)}/{m.group(5)}"
        return None
    # The Guardian signs its image URLs (changing the width breaks them); unknown CDNs stay as they are.
    return None


# ---------------------------------------------------------------- reading images and pages
def _get(url, limit, accept, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Range": f"bytes=0-{limit - 1}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get("Content-Type", "")


def dimensions(data):
    """(width, height) from the first bytes of a JPEG, PNG, WebP or GIF, or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8 " and len(data) >= 30:
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if kind == b"VP8L" and len(data) >= 25:
            b = data[21:25]
            return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        if kind == b"VP8X" and len(data) >= 30:
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        return None
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg
    return None


def probe(url):
    """Real pixel size of an image URL: (w, h), or None if it didn't load or isn't an image."""
    try:
        data, ctype = _get(url, 96 * 1024, "image/webp,image/jpeg,image/png,image/*;q=0.8")
    except Exception:
        return None
    if ctype and not ctype.startswith("image") and "octet-stream" not in ctype:
        return None
    return dimensions(data)


META_RX = [
    re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:og:image(?::secure_url)?|og:image:url)[\"'][^>]*content=[\"']([^\"']+)", re.I),
    re.compile(r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*(?:property|name)=[\"']og:image[\"']", re.I),
    re.compile(r"<meta[^>]+name=[\"']twitter:image(?::src)?[\"'][^>]*content=[\"']([^\"']+)", re.I),
]
LD_RX = re.compile(r"\"image\"\s*:\s*(?:\[\s*)?(?:\{[^{}]*?\"url\"\s*:\s*)?\"(https?:[^\"]+)\"", re.I)


def page_images(url):
    """Share images the article page itself declares, best first."""
    try:
        data, ctype = _get(url, 400 * 1024, "text/html,application/xhtml+xml", timeout=10)
    except Exception:
        return []
    text = data.decode("utf-8", "replace")
    head = text.split("</head>", 1)[0] if "</head>" in text else text
    found = []
    for rx in META_RX:
        found += rx.findall(head)
    found += [u.replace("\\/", "/") for u in LD_RX.findall(text)[:3]]
    out = []
    for u in found:
        u = urllib.parse.urljoin(url, html.unescape(u.strip()))
        if u.startswith("http") and not BAD_URL.search(u) and u not in out:
            out.append(u)
    return out[:3]


# ---------------------------------------------------------------- choosing the photo
def _score(w, h):
    ratio = w / h if h else 0
    s = min(w, 1600)
    if ratio < 0.9:
        s *= 0.45          # portrait: the cards are landscape, faces get cut
    elif ratio > 2.4:
        s *= 0.5           # banners
    return s


def measure(url):
    """Best verified version of one candidate: dict with url, w, h, small (or None if it failed)."""
    big = sized(url, BIG)
    if big:
        d = probe(big)
        if d:
            small = sized(url, SMALL)
            return {"url": big, "w": d[0], "h": d[1], "small": small if small and small != big else None}
    d = probe(url)
    if d:
        return {"url": url, "w": d[0], "h": d[1], "small": None}
    return None


def resolve(item, read_page=True):
    """Pick the photo for one story. Returns (image or None, verified: bool)."""
    feed = item.get("image") if isinstance(item.get("image"), dict) else ({"url": item["image"]} if item.get("image") else None)
    credit = (feed or {}).get("credit", "")
    caption = (feed or {}).get("caption", "")
    best, tried_any = None, False
    if feed and feed.get("url") and not BAD_URL.search(feed["url"]):
        best = measure(feed["url"])
        tried_any = True
    weak = best is None or best["w"] < WEAK_W or best["w"] / max(best["h"], 1) < 0.9
    page_used = False
    if weak and read_page:
        for u in page_images(item["url"]):
            m = measure(u)
            tried_any = True
            if m and (best is None or _score(m["w"], m["h"]) > _score(best["w"], best["h"])):
                best, page_used = m, True
                break
    if best is None:
        # Nothing could be measured. If the feed had a photo, keep it unchanged rather than
        # lose it because our server couldn't reach the outlet's CDN.
        if feed and feed.get("url") and not BAD_URL.search(feed["url"]):
            return dict(feed), False
        return None, tried_any
    if best["w"] < MIN_W:
        return None, True
    out = {"url": best["url"], "w": best["w"], "h": best["h"]}
    if best.get("small"):
        out["small"] = best["small"]
    if credit and not page_used:
        out["credit"] = credit
    if caption and not page_used:
        out["caption"] = caption
    return out, True


# ---------------------------------------------------------------- cache + batch
def load_cache(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(path, cache, now):
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("at", "") >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cache, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def _feed(it):
    """The photo the feed itself gave this run ("_feed"), falling back to the stored one."""
    im = it["_feed"] if "_feed" in it else it.get("image")
    if isinstance(im, dict) and im.get("file"):
        return None  # our own file photo from an earlier run, not the outlet's
    if isinstance(im, str):
        im = {"url": im}
    return im or None


def enrich(items, cache_path, now, log=print):
    """Give every item its chosen photo (in place). Items are processed newest first."""
    cache = load_cache(cache_path)
    todo, seen = [], set()
    for it in sorted(items, key=lambda x: x.get("date") or "", reverse=True):
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        c = cache.get(it["id"])
        feed_url = (_feed(it) or {}).get("url", "")
        if c:
            changed = "_feed" in it and c.get("feed", "") != feed_url
            settled = (c.get("img") is not None and c.get("ok", True)) or c.get("n", 0) >= MAX_TRIES or now - datetime.fromisoformat(c["at"]) < RETRY_AFTER
            if settled and not changed:
                continue
        todo.append(it)
    todo = todo[:MAX_PAGES]
    start = time.monotonic()

    def work(it):
        if time.monotonic() - start > DEADLINE:
            return it, None, None
        img, verified = resolve(dict(it, image=_feed(it)))
        return it, img, verified

    done = found = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for it, img, verified in pool.map(work, todo):
            if verified is None:
                continue  # out of time; next run
            done += 1
            prev = cache.get(it["id"], {})
            cache[it["id"]] = {"img": img, "feed": (_feed(it) or {}).get("url", ""), "at": now.isoformat(),
                               "n": 0 if img and verified else prev.get("n", 0) + 1, "ok": bool(verified)}
            found += bool(img)
    for it in items:
        c = cache.get(it["id"])
        if c is None:
            continue
        if c.get("img"):
            it["image"] = c["img"]
        elif c.get("ok"):
            it["image"] = None  # checked: no usable photo (tiny, a logo, or none anywhere)
    save_cache(cache_path, cache, now)
    try:
        add_file_photos(items, cache_path.parent / "commons.json", now, log)
    except Exception as e:  # file photos are a bonus
        log(f"[warn] file photos: {e}")
    have = sum(1 for i in items if i.get("image"))
    log(f"images: {done} checked this run, {found} with a photo; {have}/{len(items)} stories have one")
    return cache


# ---------------------------------------------------------------- layer 2: file photos (Wikimedia Commons)
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_REFRESH = timedelta(days=30)


def _strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _short_artist(a):
    a = _strip_tags(a)
    a = re.sub(r"^(No machine-readable author provided\.\s*)?", "", a)
    a = re.sub(r"\s*assumed \(based on.*$", "", a)
    a = re.sub(r"^(Autor:|Immediate source:)\s*", "", a)
    a = re.sub(r"^This image or media was taken or created by ([^.]+)\..*$", r"\1", a)
    a = re.sub(r"~commonswiki\b", "", a)
    return a[:60].rstrip(" ,;") if a else ""


def commons_info(files, log=print):
    """Size, thumbnail URLs, author and licence for Commons files: {file: info}. One API call per 40 files."""
    out = {}
    for i in range(0, len(files), 40):
        chunk = files[i:i + 40]
        for width in (1280, 960):
            q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "iiurlwidth": width,
                                        "iiprop": "url|size|extmetadata", "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
                                        "titles": "|".join("File:" + f for f in chunk)})
            req = urllib.request.Request(f"{COMMONS_API}?{q}", headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            back = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
            for page in data.get("query", {}).get("pages", {}).values():
                name = back.get(page.get("title"), page.get("title", ""))[5:]
                ii = (page.get("imageinfo") or [None])[0]
                if name not in chunk or not ii:
                    continue
                o = out.setdefault(name, {})
                thumb = (ii.get("thumburl") or ii.get("url") or "").split("?")[0]
                meta = ii.get("extmetadata") or {}
                if width == 1280:
                    o.update({"url": thumb, "w": ii.get("thumbwidth") or ii.get("width"), "h": ii.get("thumbheight") or ii.get("height"),
                              "page": ii.get("descriptionurl", ""),
                              "artist": _short_artist((meta.get("Artist") or {}).get("value")),
                              "license": _strip_tags((meta.get("LicenseShortName") or {}).get("value"))})
                else:
                    o["small"] = thumb
    return out


def add_file_photos(items, cache_path, now, log=print):
    """Stories still without a photo get a labelled file photo of the person or place in their headline."""
    import entities
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    files = sorted(set(entities.FILES.values()))
    fresh = cache.get("at") and now - datetime.fromisoformat(cache["at"]) < COMMONS_REFRESH
    if not fresh or any(f not in cache.get("files", {}) for f in files):
        try:
            info = commons_info(files, log)
            if info:
                cache = {"at": now.isoformat(), "files": info}
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        except Exception as e:  # keep using the old list; try again next run
            log(f"[warn] commons: {e}")
    info = cache.get("files", {})
    added = 0
    for it in items:
        if it.get("image") or it.get("kind") == "light":
            continue
        key = entities.match(it.get("title", ""), it.get("topic"))
        f = entities.FILES.get(key)
        c = info.get(f) if f else None
        if not c or not c.get("url") or not c.get("license"):
            continue
        img = {"url": c["url"], "w": c["w"], "h": c["h"], "file": True, "page": c.get("page", ""),
               "credit": " · ".join(x for x in (c.get("artist"), c.get("license")) if x)}
        if c.get("small") and c["small"] != c["url"]:
            img["small"] = c["small"]
        it["image"] = img
        added += 1
    log(f"file photos: {added} stories")
