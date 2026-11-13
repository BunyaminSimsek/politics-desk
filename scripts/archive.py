"""Rolling 30-day story archive for the app's "Keep exploring" feed.

docs/archive/YYYY-MM-DD.json holds one Toronto day of stories: political stories from
news.json plus "lighter side" stories (odd and good news) from a few extra feeds.
Same-story duplicates are folded into one entry that remembers how many outlets ran it.
Day files older than ARCHIVE_DAYS are deleted on every run.
docs/archive/index.json lists the days the app can load, newest first.
Standard library only.
"""
import json
import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TORONTO = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover
    TORONTO = timezone(timedelta(hours=-5))

ARCHIVE_DAYS = 30
DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
KEEP = ("id", "title", "summary", "source", "url", "date", "topic", "region", "kind", "image")

STOP = set("""a an the of to in on for and or but with at by from as is are was were be been it its this that
these those after over into about amid says said say new will would could can may more than up out not no
his her their they he she we you i our us before what who how why when where""".split())

# Lighter-side stories must not be about harm: no one should be laughing next to a tragedy.
LIGHT_SKIP = re.compile(
    r"\b(die[sd]?|dead|death|deaths|dying|kill(s|ed|ing)?|murder\w*|shoot\w*|shot|stab\w*|crash\w*|"
    r"abuse\w*|assault\w*|sexual|rape\w*|suicide|cancer|overdose\w*|funeral|tragic|tragedy|war|attack\w*|"
    r"injur\w*|wounded|victim\w*|missing|hostage\w*|bomb\w*|terror\w*|arrest\w*|charged|police|"
    r"subscribe|newsletter|podcast|quiz|good news in history|what went right)\b", re.I)


def toronto_day(iso):
    return datetime.fromisoformat(iso).astimezone(TORONTO).date().isoformat()


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", (title or "").lower()) if w not in STOP and len(w) > 2}


def light_items(feed_results, now, shorten, item_id):
    """Turn parsed lighter-side feeds into archive items. feed_results: [((name, url, kind), parsed|None)]."""
    out = []
    week_ago = now - timedelta(days=7)
    for (name, _url, sub), parsed in feed_results:
        for p in parsed or []:
            text = f"{p['title']} {p['summary']}"
            if LIGHT_SKIP.search(text) or not p.get("date") or p["date"] < week_ago:
                continue
            date = min(p["date"], now)
            out.append({
                "id": item_id(p["link"]), "title": p["title"], "summary": shorten(p["summary"]),
                "source": name, "url": p["link"], "date": date.isoformat(), "topic": "lighter",
                "region": "world", "kind": "light", "sub": sub, "image": p.get("image"),
            })
    return out


def _fold(items):
    """Fold same-story duplicates. Keeps the entry with a photo and the fullest summary."""
    items = sorted(items, key=lambda it: it["date"])
    groups = []
    for it in items:
        t = tokens(it["title"])
        home = None
        for g in groups:
            if g["kind"] != it.get("kind"):
                continue
            shared = t & g["tok"]
            if len(shared) >= 3 and len(shared) / max(1, len(t | g["tok"])) >= 0.3:
                home = g
                break
        if home is None:
            groups.append({"kind": it.get("kind"), "tok": t, "members": [it]})
        else:
            home["members"].append(it)
            home["tok"] |= t
    out = []
    for g in groups:
        ms = g["members"]
        rep = max(ms, key=lambda m: (bool(m.get("image")), len(m.get("summary") or ""), m["date"]))
        names = []
        for m in ms:
            for n in [m["source"]] + list(m.get("also") or []):
                if n and n not in names:
                    names.append(n)
        e = dict(rep)
        e["also"] = [n for n in names if n != rep["source"]][:6]
        e["cov"] = len(names)
        e["date"] = min(m["date"] for m in ms)  # first reported
        out.append(e)
    out.sort(key=lambda e: (e["cov"], e["date"]), reverse=True)
    return out


def _write_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def update(docs, news_items, lighter, now):
    """Merge this run's stories into the day files, drop old days, rewrite the index. Returns changed names."""
    folder = docs / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    today = now.astimezone(TORONTO).date()
    oldest = (today - timedelta(days=ARCHIVE_DAYS - 1)).isoformat()
    changed = []

    fresh = {}
    for it in list(news_items) + list(lighter):
        e = {k: it.get(k) for k in KEEP}
        if it.get("sub"):
            e["sub"] = it["sub"]
        e["kind"] = e.get("kind") or "news"
        day = toronto_day(e["date"])
        if day >= oldest:
            fresh.setdefault(day, {})[e["id"]] = e

    for day, by_id in fresh.items():
        path = folder / f"{day}.json"
        old = []
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8")).get("items", [])
            except (ValueError, OSError):
                old = []
        merged = {e["id"]: e for e in old}
        for iid, e in by_id.items():
            if iid in merged:
                e = dict(e, also=list(dict.fromkeys((merged[iid].get("also") or []) + (e.get("also") or []))))
                e["date"] = min(e["date"], merged[iid]["date"])
            merged[iid] = e
        # Entries folded earlier keep their outlet list in "also", so folding again loses nothing.
        items = _fold(list(merged.values()))
        if _write_if_changed(path, json.dumps({"date": day, "items": items}, ensure_ascii=False, separators=(",", ":"))):
            changed.append(f"archive/{day}.json")

    days = []
    for f in sorted(folder.iterdir(), reverse=True):
        if not DAY_FILE.match(f.name):
            continue
        day = f.name[:-5]
        if day < oldest:
            f.unlink()  # older than 30 days: gone for good
            changed.append(f"archive/{day}.json (deleted)")
            continue
        try:
            items = json.loads(f.read_text(encoding="utf-8")).get("items", [])
        except (ValueError, OSError):
            continue
        days.append({"date": day, "count": len(items), "light": sum(1 for x in items if x.get("kind") == "light")})
    if _write_if_changed(folder / "index.json", json.dumps({"keepDays": ARCHIVE_DAYS, "days": days}, ensure_ascii=False, indent=1)):
        changed.append("archive/index.json")
    return changed
