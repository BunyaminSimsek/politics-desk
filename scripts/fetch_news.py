"""Politics Desk news fetcher.

Reads public RSS/Atom feeds, keeps political stories, sorts them into beats,
flags breaking stories, and writes docs/news.json for the website.
Uses only the Python standard library.
"""
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "news.json"
EDITION = ROOT / "docs" / "edition.json"
EDITION_HOUR = 7          # the daily briefing appears at 7:00 a.m. Toronto time
EDITION_SIZE = 5
KEEP_HOURS = 72
MAX_ITEMS = 400
SUMMARY_CHARS = 260
DETAIL_CHARS = 700        # longest text kept for a briefing story's "More detail" view

# (source name, feed url, region hint, topic hint, politics_feed)
# politics_feed=True means every story in the feed is already political.
FEEDS = [
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-politics", "local", "federal", True),
    ("CBC Toronto", "https://www.cbc.ca/webfeed/rss/rss-canada-toronto", "local", "toronto", False),
    ("CBC World", "https://www.cbc.ca/webfeed/rss/rss-world", "world", None, False),
    ("Global News", "https://globalnews.ca/politics/feed/", "local", "federal", True),
    ("Global News Toronto", "https://globalnews.ca/toronto/feed/", "local", "toronto", False),
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-politics-public-rss-1.822302", "local", "federal", True),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "world", None, False),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "world", None, False),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/europe/rss.xml", "world", "europe", False),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "world", "mideast", False),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "world", "asia", False),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "world", None, False),
    ("The Guardian", "https://www.theguardian.com/world/rss", "world", None, False),
    ("The Guardian", "https://www.theguardian.com/us-news/us-politics/rss", "world", "us", True),
    ("NPR", "https://feeds.npr.org/1014/rss.xml", "world", "us", True),
    # Local politics, from topic pages that only carry political stories.
    ("Global News", "https://globalnews.ca/tag/ontario-politics/feed/", "local", "ontario", True),
    ("Global News", "https://globalnews.ca/tag/doug-ford/feed/", "local", "ontario", True),
    ("Global News", "https://globalnews.ca/tag/toronto-city-council/feed/", "local", "toronto", True),
    ("Global News", "https://globalnews.ca/tag/olivia-chow/feed/", "local", "toronto", True),
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=politics*&l=50&s=start_time&sd=desc", "local", "federal", True),
    # More world regions.
    ("BBC News", "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml", "world", "latam", False),
    ("BBC News", "https://feeds.bbci.co.uk/news/world/africa/rss.xml", "world", "africa", False),
    ("The Guardian", "https://www.theguardian.com/world/turkey/rss", "world", "turkey", False),
    ("The Guardian", "https://www.theguardian.com/world/americas/rss", "world", None, False),
    ("The Guardian", "https://www.theguardian.com/world/africa/rss", "world", "africa", False),
    # Analysis and explainers.
    ("The Conversation", "https://theconversation.com/ca/politics/articles.atom", "local", "federal", True),
    ("Policy Options", "https://policyoptions.irpp.org/feed/", "local", "federal", True),
]

# "Lighter side" feeds for the Keep exploring feed: odd, good and curious news.
# They never enter news.json or the daily briefing; they only go to the 30-day archive.
LIGHT_FEEDS = [
    ("UPI Odd News", "https://rss.upi.com/news/odd_news.rss", "odd"),
    ("Good News Network", "https://www.goodnewsnetwork.org/feed/", "good"),
    ("The Guardian", "https://www.theguardian.com/world/series/the-upside/rss", "good"),
    ("BBC News", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "curious"),
]

ANALYSIS_SOURCES = {"The Conversation", "Policy Options"}
ANALYSIS_RX = re.compile(r"\b(analysis|explainer|explained|what it means|what to know|why it matters|opinion|column|commentary|fact check)\b", re.I)


def kind_of(source, title):
    return "analysis" if source in ANALYSIS_SOURCES or ANALYSIS_RX.search(title or "") else "news"

LOCAL_TOPICS = {"federal", "ontario", "toronto"}

# Keywords per beat. Matched as whole words, case-insensitive.
TOPIC_WORDS = {
    "toronto": ["toronto city council", "city council", "olivia chow", "mayor chow", "chow",
                "city hall", "ttc", "toronto budget", "councillor", "toronto mayor", "bylaw"],
    "ontario": ["queen's park", "doug ford", "premier ford", "ford government", "ontario government",
                "mpp", "mpps", "marit stiles", "bonnie crombie", "ontario ndp", "ontario liberal",
                "ontario pc", "bethlenfalvy", "ontario premier", "province of ontario", "ontario"],
    "federal": ["carney", "poilievre", "parliament hill", "house of commons", "ottawa", "federal government",
                "champagne", "blanchet", "ndp", "bloc québécois", "bloc quebecois", "liberals", "conservatives",
                "senate of canada", "canadian government", "prime minister of canada", "canada's"],
    "ukraine": ["ukraine", "ukrainian", "russia", "russian", "kremlin", "putin", "zelensky", "zelenskyy",
                "kyiv", "moscow", "donbas", "crimea"],
    "mideast": ["israel", "israeli", "gaza", "hamas", "hezbollah", "iran", "iranian", "tehran", "lebanon",
                "syria", "west bank", "netanyahu", "saudi", "yemen", "houthi", "iraq", "qatar", "palestinian"],
    "us": ["trump", "white house", "congress", "senate", "republican", "republicans", "democrat", "democrats",
           "vance", "supreme court", "hegseth", "rubio", "u.s. president", "us president", "capitol hill"],
    "turkey": ["turkey", "türkiye", "turkiye", "turkish", "erdogan", "erdoğan", "ankara", "istanbul",
               "imamoglu", "imamoğlu", "chp", "akp", "kurdish", "pkk"],
    "latam": ["brazil", "lula", "mexico", "sheinbaum", "argentina", "milei", "venezuela", "maduro",
              "colombia", "petro", "chile", "peru", "cuba", "ecuador", "bolivia", "latin america", "haiti",
              "panama", "guatemala", "honduras", "nicaragua"],
    "africa": ["africa", "african", "nigeria", "south africa", "ramaphosa", "kenya", "ethiopia", "sudan",
               "egypt", "congo", "drc", "sahel", "mali", "niger", "somalia", "ghana", "uganda", "tanzania",
               "morocco", "algeria", "libya", "tunisia", "zimbabwe", "senegal", "rwanda"],
    "europe": ["european union", "eu", "brussels", "nato", "starmer", "britain", "uk", "british", "france",
               "macron", "germany", "german", "merz", "spain", "italy", "meloni", "poland", "hungary",
               "orban", "netherlands", "europe", "european", "ireland", "greece", "sweden", "denmark"],
    "asia": ["china", "chinese", "xi jinping", "beijing", "japan", "japanese", "takaichi", "india", "modi",
             "pakistan", "korea", "taiwan", "philippines", "indonesia", "australia", "vietnam",
             "bangladesh", "myanmar", "thailand", "afghanistan"],
}

# Issue beats: a story can carry several of these on top of its region.
ISSUE_WORDS = {
    "trade": ["tariff", "tariffs", "trade deal", "trade war", "trade talks", "cusma", "usmca", "free trade",
              "exports", "imports", "duties", "wto", "trade minister", "trade agreement"],
    "elections": ["election", "elections", "by-election", "byelection", "referendum", "ballot", "polls",
                  "poll", "campaign", "voters", "vote count", "runoff", "candidate", "candidates"],
    "immigration": ["immigration", "immigrants", "migrants", "migrant", "asylum", "refugee", "refugees",
                    "deportation", "deportations", "border", "visa", "visas", "international students",
                    "temporary residents", "ice raids"],
    "economy": ["budget", "deficit", "economy", "economic", "inflation", "interest rate", "interest rates",
                "recession", "gdp", "jobs report", "unemployment", "taxes", "tax cut", "spending",
                "bank of canada", "federal reserve", "fiscal"],
    "defence": ["defence", "defense", "military", "nato", "troops", "army", "missile", "missiles", "drone",
                "drones", "pentagon", "national security", "espionage", "spy", "warship", "ceasefire",
                "armed forces"],
    "climate": ["climate", "emissions", "carbon", "pipeline", "pipelines", "oil and gas", "renewable",
                "clean energy", "net zero", "cop33", "cop32", "wildfire", "lng", "energy policy"],
    "housing": ["housing", "rent", "rents", "renters", "homelessness", "affordability", "cost of living",
                "home prices", "mortgage", "mortgages", "affordable homes", "encampment", "encampments"],
}

# Stories that are mostly crime, accidents or sport are dropped unless clearly political.
NOISE_WORDS = ["shooting", "shot dead", "stabbing", "stabbed", "murder", "homicide", "crash", "collision",
               "fire crews", "missing person", "arrested", "charged with", "hockey", "soccer", "football",
               "basketball", "baseball", "world juniors", "tournament", "olympic", "olympics", "nhl", "nba",
               "nfl", "concert", "celebrity", "weather warning", "snowfall", "second world war",
               "first world war", "museum", "opens to public", "obituary", "dies aged", "recipe", "tourism"]

STRONG_POLITICS = ["government", "minister", "president", "prime minister", "premier", "parliament",
                   "legislature", "council", "mayor", "senator", "congress", "election", "policy", "bill"]

POLITICS_WORDS = [
    "government", "minister", "president", "prime minister", "premier", "election", "elections", "vote",
    "voters", "parliament", "legislature", "council", "mayor", "senator", "senate", "congress", "policy",
    "bill", "law", "budget", "tariff", "tariffs", "sanctions", "diplomat", "diplomatic", "summit", "talks",
    "ceasefire", "war", "treaty", "protest", "protests", "party", "leader", "opposition", "campaign",
    "referendum", "coalition", "cabinet", "ambassador", "military", "troops", "peace", "negotiations",
    "court", "ruling", "impeachment", "minister's", "mp", "mpp", "politics", "political",
]

STOP = set("""a an the of to in on for and or but with at by from as is are was were be been it its this that
these those after over into about amid says said say new will would could can may more than up out not no
his her their they he she we you i our us after before what who how why when where""".split())


def compile_words(words):
    return [re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.I) for w in words]


TOPIC_RX = {t: compile_words(ws) for t, ws in TOPIC_WORDS.items()}
ISSUE_RX = {t: compile_words(ws) for t, ws in ISSUE_WORDS.items()}
POLITICS_RX = compile_words(POLITICS_WORDS)
NOISE_RX = compile_words(NOISE_WORDS)
STRONG_RX = compile_words(STRONG_POLITICS)


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


NEWSLETTER_RX = re.compile(r"\s*\b(Sign up for|Sign up to|Subscribe to) [^.]*?(newsletter|email)\b.*$", re.I | re.S)
SENTENCE_END_RX = re.compile(r"[.!?][\"'”’)]?(?=\s|$)")


def whole_sentences(text, min_len=60):
    """Text up to its last complete sentence, or None if that would be too short."""
    ends = [m.end() for m in SENTENCE_END_RX.finditer(text)]
    ends = [e for e in ends if e >= min_len]
    return text[:ends[-1]].strip() if ends else None


def shorten(text, n=SUMMARY_CHARS):
    """Keep summaries to whole sentences, so a story never stops mid-thought.

    Feeds often send summaries that are already cut ("…", "[…]"); those are
    trimmed back to their last full sentence too. Only when no sentence of a
    useful length exists do we fall back to a word cut with an ellipsis.
    """
    text = NEWSLETTER_RX.sub("", text).strip()
    truncated = bool(re.search(r"(…|\.\.\.|\[…\]|\[\.\.\.\])$", text))
    if len(text) <= n and not truncated:
        return text
    head = text[:n + 1] if len(text) > n else re.sub(r"\s*(…|\.\.\.|\[…\]|\[\.\.\.\])$", "", text)
    sentences = whole_sentences(head)
    if sentences:
        return sentences
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:.") + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(el, *names):
    for c in el:
        if local_name(c.tag) in names and (c.text or "").strip():
            return c.text
    return ""


MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def find_image(el, raw_html):
    """The outlet's own photo for this item, with credit and caption when the feed gives them."""
    best = None
    item_credit = ""

    def consider(url, w=0, credit="", caption=""):
        nonlocal best
        url = (url or "").strip()
        if not url.startswith("http") or re.search(r"logo|\.gif(\?|$)|pixel|1x1", url, re.I):
            return
        w = int(w) if str(w).isdigit() else 0
        if 0 < w < 200:
            return
        if best is None or w > best["w"]:
            best = {"url": url, "w": w, "credit": credit, "caption": caption}

    for c in el:
        if c.tag.startswith(MEDIA_NS) and local_name(c.tag) == "credit" and (c.text or "").strip():
            item_credit = clean(c.text)
    for c in el.iter():
        name = local_name(c.tag)
        if c.tag.startswith(MEDIA_NS) and name in ("content", "thumbnail"):
            typ, medium = c.get("type", ""), c.get("medium", "")
            if name == "content" and (typ or medium) and not (typ.startswith("image") or medium == "image"):
                continue
            credit = caption = ""
            for g in c:
                ln = local_name(g.tag)
                if ln == "credit":
                    credit = clean(g.text)
                elif ln in ("description", "title") and not caption:
                    caption = clean(g.text)
            consider(c.get("url"), c.get("width", 0), credit, caption)
        elif name == "enclosure" and c.get("type", "").startswith("image"):
            consider(c.get("url"))
    if best is None:
        m = re.search(r"<img[^>]+src=[\"']([^\"']+)", raw_html or "")
        if m:
            consider(html.unescape(m.group(1)))
    if best is None:
        return None
    url = re.sub(r"(ichef\.bbci\.co\.uk/(?:ace|news)/(?:standard|ws)/)\d+/", r"\g<1>800/", best["url"])
    caption = best["caption"]
    if caption and len(caption) > 160:
        caption = shorten(caption, 160)
    return {"url": url, "credit": best["credit"] or item_credit, "caption": caption}


def parse_feed(xml_bytes):
    """Return list of dicts with title, link, summary, date from RSS or Atom."""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        name = local_name(el.tag)
        if name not in ("item", "entry"):
            continue
        title = clean(child_text(el, "title"))
        link = child_text(el, "link").strip()
        if not link:
            for c in el:
                if local_name(c.tag) == "link" and c.get("href"):
                    if c.get("rel", "alternate") == "alternate":
                        link = c.get("href")
                        break
        raw = child_text(el, "description", "summary", "content") + " " + child_text(el, "encoded")
        summary = clean(child_text(el, "description", "summary", "content"))
        date = parse_date(child_text(el, "pubDate", "published", "updated", "date"))
        if title and link.startswith("http"):
            out.append({"title": title, "link": link, "summary": summary, "date": date,
                        "image": find_image(el, raw)})
    return out


def count_hits(rxs, text):
    return sum(1 for rx in rxs if rx.search(text))


def issues_for(title, summary):
    text = title + " " + summary
    tags = []
    for t, rxs in ISSUE_RX.items():
        if count_hits(rxs, title) >= 1 or count_hits(rxs, summary) >= 2:
            tags.append(t)
    return tags


def classify(title, summary, region_hint, topic_hint, politics_feed):
    """Return (topic, region, issue_tags) or None if the story isn't political/relevant."""
    text = title + " " + summary
    politics_hits = count_hits(POLITICS_RX, text)
    if not politics_feed and politics_hits == 0:
        return None
    if count_hits(NOISE_RX, title) and count_hits(STRONG_RX, text) == 0:
        return None
    candidates = LOCAL_TOPICS if region_hint == "local" else TOPIC_RX.keys()
    scores = {t: count_hits(TOPIC_RX[t], title) * 2 + count_hits(TOPIC_RX[t], summary) for t in candidates}
    # A Canadian politician in the headline makes it a Canadian story, wherever it happens.
    local_title = {t: count_hits(TOPIC_RX[t], title) for t in LOCAL_TOPICS if t in scores}
    if any(local_title.values()):
        best = max(local_title, key=lambda t: (local_title[t], scores[t]))
        best_score = scores[best]
    else:
        best = max(scores, key=scores.get) if scores else None
        best_score = scores.get(best, 0) if best else 0
        if best_score == 0:
            best = None
    if best is None:
        if topic_hint:
            best = topic_hint
        else:
            return None
    # Local feeds that aren't politics-only need a local politics signal to avoid crime/weather noise.
    if region_hint == "local" and not politics_feed and best_score == 0:
        return None
    return best, ("local" if best in LOCAL_TOPICS else "world"), issues_for(title, summary)


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if w not in STOP and len(w) > 2}


def mark_breaking(items, now):
    for it in items:
        it["breaking"] = False
    recent = [it for it in items if it["date"] and now - datetime.fromisoformat(it["date"]) < timedelta(hours=6)]
    toks = [tokens(it["title"]) for it in recent]
    clusters = []
    for i, it in enumerate(recent):
        sources = {it["source"]}
        for j, other in enumerate(recent):
            if i == j:
                continue
            shared = toks[i] & toks[j]
            union = toks[i] | toks[j]
            if len(shared) >= 2 and union and len(shared) / len(union) >= 0.25:
                sources.add(other["source"])
        if len(sources) >= 4 or re.search(r"\bbreaking\b", it["title"], re.I):
            clusters.append((len(sources), it))
    clusters.sort(key=lambda x: (x[0], x[1]["date"]), reverse=True)
    picked, seen = 0, []
    for _, it in clusters:
        t = tokens(it["title"])
        if any(len(t & s) >= 2 for s in seen):
            continue
        it["breaking"] = True
        seen.append(t)
        picked += 1
        if picked == 3:
            break


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (PoliticsDesk personal news reader)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def item_id(link):
    norm = re.sub(r"[?#].*$", "", link.strip().lower())
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def build(feed_results, previous, now):
    """feed_results: list of (feed_tuple, parsed_items or None)."""
    prev_by_id = {it["id"]: it for it in previous}
    merged = {}
    for iid, it in prev_by_id.items():
        # Re-check saved stories against the current filters each run.
        if count_hits(NOISE_RX, it["title"]) and count_hits(STRONG_RX, it["title"] + " " + it["summary"]) == 0:
            continue
        if "tags" not in it:
            it = dict(it, tags=issues_for(it["title"], it["summary"]))
        if "kind" not in it:
            it = dict(it, kind=kind_of(it["source"], it["title"]))
        merged[iid] = it
    report = []
    for (name, url, region_hint, topic_hint, politics_feed), parsed in feed_results:
        if parsed is None:
            report.append({"source": name, "url": url, "ok": False, "kept": 0})
            continue
        kept = 0
        for p in parsed:
            c = classify(p["title"], p["summary"], region_hint, topic_hint, politics_feed)
            if not c:
                continue
            topic, region, tags = c
            iid = item_id(p["link"])
            date = p["date"] or (datetime.fromisoformat(prev_by_id[iid]["date"]) if iid in prev_by_id and prev_by_id[iid].get("date") else now)
            if date > now + timedelta(hours=1):
                date = now
            merged[iid] = {
                "id": iid,
                "title": p["title"],
                "summary": shorten(p["summary"]),
                # Longer text for the briefing's "More detail" view. Kept in memory only:
                # it is used to build edition.json and stripped before news.json is written.
                "_detail": shorten(p["summary"], DETAIL_CHARS),
                "source": name,
                "url": p["link"],
                "date": date.isoformat(),
                "topic": topic,
                "region": region,
                "tags": tags,
                "kind": kind_of(name, p["title"]),
                "image": p.get("image") or prev_by_id.get(iid, {}).get("image"),
                "breaking": False,
                "addedAt": prev_by_id.get(iid, {}).get("addedAt", now.isoformat()),
            }
            kept += 1
        report.append({"source": name, "url": url, "ok": True, "kept": kept})

    cutoff = now - timedelta(hours=KEEP_HOURS)
    items = [it for it in merged.values() if datetime.fromisoformat(it["date"]) >= cutoff]
    items.sort(key=lambda it: it["date"], reverse=True)
    items = items[:MAX_ITEMS]
    mark_breaking(items, now)
    return {"generatedAt": now.isoformat(), "feeds": report, "items": items}


# ---------------------------------------------------------------- daily edition
try:
    from zoneinfo import ZoneInfo
    TORONTO = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - zoneinfo data missing
    TORONTO = timezone(timedelta(hours=-5))

PLACE = {
    "us": "US", "ukraine": "Ukraine", "mideast": "Middle East", "europe": "Europe",
    "asia": "Asia", "africa": "Africa", "latam": "Latin America", "turkey": "Türkiye",
    "federal": "Canada", "ontario": "Ontario", "toronto": "Toronto",
}
LOCAL_TOPICS = {"federal", "ontario", "toronto"}
MEDIA_URL_RX = re.compile(r"/(video|videos|audio|live|podcasts?)/", re.I)
SKIP_RX = re.compile(r"\b(live|podcast|as it happened|video|watch|quiz|newsletter|in pictures)\b", re.I)


def tidy_title(t):
    t = re.sub(r"\s+[–—-]\s+(live|podcast|as it happened|video|the latest)$", "", t, flags=re.I)
    return t.strip()


def make_edition(items, now, old):
    """Pick the day's five most-covered stories. Built once a day, at 7:00 Toronto time."""
    local = now.astimezone(TORONTO)
    today = local.date().isoformat()
    after_seven = local.hour >= EDITION_HOUR
    if old and old.get("date") == today and (not old.get("early") or not after_seven):
        return None  # today's edition already exists; keep it fixed for the day
    if old and old.get("date") != today and not after_seven:
        return None  # before 7:00, keep showing yesterday's edition
    # Never repeat an article from the previous edition, so every day brings new reading.
    seen_before = set()
    for st in (old or {}).get("stories", []):
        seen_before.add(st.get("id"))
        seen_before.add(st.get("url"))
        seen_before.update(x.get("url") for x in st.get("sources", []))
    for fresh_only in (True, False):
        edition = _pick_edition(items, now, today, after_seven, seen_before if fresh_only else set())
        if edition:
            return edition
    return None


def _complete(t):
    return bool(t) and len(t) >= 60 and not t.endswith("…")


def _detail_for(cluster, rep):
    """The longest complete text any outlet gave for this story (for "More detail")."""
    texts = [i.get("_detail") or i["summary"] for i in [rep] + cluster]
    good = [t for t in texts if _complete(t)]
    best = max(good or texts, key=len)
    return best if len(best) > len(rep["summary"]) + 40 else None


def _outlet_takes(cluster):
    """One short, complete summary per outlet, so readers can see how each covered it."""
    seen, out = set(), []
    for i in cluster:
        if i["source"] in seen or not _complete(i["summary"]):
            continue
        seen.add(i["source"])
        out.append({"source": i["source"], "url": i["url"], "summary": i["summary"]})
    return out[:4]


def _pick_edition(items, now, today, after_seven, seen_before):
    pool = []
    for it in items:
        if it["id"] in seen_before or it["url"] in seen_before:
            continue
        if it.get("kind") == "analysis" or SKIP_RX.search(it["title"]) or " | " in it["title"] or MEDIA_URL_RX.search(it["url"]):
            continue
        if not it.get("date") or now - datetime.fromisoformat(it["date"]) > timedelta(hours=24):
            continue
        pool.append(it)
    pool.sort(key=lambda it: it["date"], reverse=True)
    clusters = []
    for it in pool:
        t = tokens(it["title"])
        for c in clusters:
            shared = t & c["tokens"]
            union = t | c["tokens"]
            if len(shared) >= 2 and union and len(shared) / len(union) >= 0.25:
                c["items"].append(it)
                break
        else:
            clusters.append({"tokens": t, "items": [it]})
    def score(c):
        srcs = {i["source"] for i in c["items"]}
        img = any(i.get("image") for i in c["items"])
        newest = max(datetime.fromisoformat(i["date"]) for i in c["items"])
        hours = (now - newest).total_seconds() / 3600
        return len(srcs) * 3 + (1 if img else 0) - hours / 12
    clusters.sort(key=score, reverse=True)
    picked, per_topic = [], {}
    for c in clusters:
        topic = c["items"][0]["topic"]
        if per_topic.get(topic, 0) >= (2 if topic == "us" else 1):
            continue
        picked.append(c)
        per_topic[topic] = per_topic.get(topic, 0) + 1
        if len(picked) == EDITION_SIZE:
            break
    if picked and not any(c["items"][0]["topic"] in LOCAL_TOPICS for c in picked):
        best_local = next((c for c in clusters if c["items"][0]["topic"] in LOCAL_TOPICS and c not in picked), None)
        if best_local:
            picked[-1] = best_local
    stories = []
    for c in picked:
        with_img = [i for i in c["items"] if i.get("image")]
        rep = with_img[0] if with_img else c["items"][0]
        # Prefer the representative's own summary if it is complete; otherwise the
        # longest complete summary in the cluster; only then a cut-off one.
        complete = [i["summary"] for i in c["items"] if len(i["summary"]) >= 80 and not i["summary"].endswith("…")]
        best_summary = max(complete, key=len) if complete else max((i["summary"] for i in c["items"]), key=len)
        seen, sources = set(), []
        for i in c["items"]:
            if i["source"] not in seen:
                seen.add(i["source"])
                sources.append({"name": i["source"], "url": i["url"]})
        stories.append({
            "id": rep["id"],
            "title": tidy_title(rep["title"]),
            "summary": rep["summary"] if len(rep["summary"]) >= 80 and not rep["summary"].endswith("…") else best_summary,
            "place": PLACE.get(rep["topic"], "World"),
            "topic": rep["topic"],
            "url": rep["url"],
            "image": rep.get("image"),
            "sources": sources[:4],
            "coverage": len(sources),  # how many outlets reported it (shown on the card)
            "detail": _detail_for(c["items"], rep),
            "details": _outlet_takes(c["items"]),
            "why": None,       # filled in by the AI editor in phase 2
        })
    if len(stories) < 3:
        return None
    return {
        "date": today,
        "publishedAt": now.isoformat(),
        "editionHour": EDITION_HOUR,  # the page reads this for its "next briefing at" times
        "early": not after_seven,
        "stories": stories,
        "question": None,  # phase 2
    }


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    previous = []
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8")).get("items", [])
        except (ValueError, OSError):
            previous = []
    results = []
    for feed in FEEDS:
        try:
            results.append((feed, parse_feed(fetch(feed[1]))))
        except Exception as e:  # one bad feed must not stop the others
            print(f"[warn] {feed[0]} {feed[1]}: {e}", file=sys.stderr)
            results.append((feed, None))
    data = build(results, previous, now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    public = dict(data, items=[{k: v for k, v in it.items() if not k.startswith("_")} for it in data["items"]])
    OUT.write_text(json.dumps(public, ensure_ascii=False, indent=1), encoding="utf-8")
    old = None
    if EDITION.exists():
        try:
            old = json.loads(EDITION.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            old = None
    edition = make_edition(data["items"], now, old)
    if edition:
        EDITION.write_text(json.dumps(edition, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"edition {edition['date']}: {len(edition['stories'])} stories")
    # Rolling 30-day archive for the "Keep exploring" feed (old days are deleted).
    try:
        import archive
        light_results = []
        for feed in LIGHT_FEEDS:
            try:
                light_results.append((feed, parse_feed(fetch(feed[1]))))
            except Exception as e:
                print(f"[warn] light {feed[0]} {feed[1]}: {e}", file=sys.stderr)
                light_results.append((feed, None))
        lighter = archive.light_items(light_results, now, shorten, item_id)
        changed = archive.update(ROOT / "docs", data["items"], lighter, now)
        print(f"archive: {len(lighter)} lighter stories; {len(changed)} files changed")
    except Exception as e:  # the archive is a bonus; never let it break the news update
        print(f"[warn] archive: {e}", file=sys.stderr)
    # Static pages for search engines (briefing archive, about, sitemap, headlines in index.html).
    try:
        import site_pages
        current = edition or old
        changed = site_pages.build(ROOT / "docs", current, [f[0] for f in FEEDS], data["items"])
        if changed:
            print("pages updated: " + ", ".join(changed))
    except Exception as e:  # pages are a bonus; never let them break the news update
        print(f"[warn] static pages: {e}", file=sys.stderr)
    ok = sum(1 for r in data["feeds"] if r["ok"])
    print(f"{len(data['items'])} stories, {ok}/{len(data['feeds'])} feeds OK")


if __name__ == "__main__":
    main()
