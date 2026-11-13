"""Static pages for search engines and AI search.

The app in docs/index.html builds everything with JavaScript, so a crawler that
doesn't run JavaScript (and Google, before its render step) sees an empty page.
This module writes plain HTML that needs no JavaScript:

- docs/index.html: today's headlines are written into the start screen
  (the app replaces them with the same content when it loads)
- docs/briefing/<date>/index.html: a permanent page for every daily briefing
- docs/briefing/index.html: the list of past briefings
- docs/about/index.html: what PoliDesk is and where the news comes from
- docs/sitemap.xml

Files are only rewritten when their content changes, so the repository
doesn't get a commit every ten minutes.
Uses only the Python standard library.
"""
import html
import json
import re
from datetime import date
from pathlib import Path

SITE = "https://polidesk.ca"
NAME = "PoliDesk"

esc = lambda s: html.escape(str(s or ""), quote=True)


def write_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"


def whole(text):
    """Drop a trailing cut-off fragment ("…") so text ends on a full sentence when possible."""
    t = (text or "").strip()
    if not re.search(r"(…|\.\.\.)$", t):
        return t
    body = re.sub(r"\s*(…|\.\.\.)$", "", t)
    ends = [m.end() for m in re.finditer(r"[.!?][\"'”’)]?(?=\s|$)", body) if m.end() >= 60]
    return body[:ends[-1]] if ends else t


def safe_url(u):
    return u if re.match(r"^https?://", u or "", re.I) else "#"


# ---------------------------------------------------------------- shared page shell
STYLE = """
:root{--ink:#142238;--paper:#F6F5F1;--text:#2B3545;--muted:#5B6577;--soft:#EEF1F5;--pill:#D9DEE6;--flame:#E0646A;
--serif:'Source Serif 4',Georgia,serif;--sans:Inter,system-ui,-apple-system,'Segoe UI',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit}
header{background:var(--ink);color:#fff}
.wrap{max-width:760px;margin:0 auto;padding:0 22px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0}
.brand{display:flex;align-items:center;gap:8px;font-family:var(--serif);font-weight:700;font-size:22px;text-decoration:none}
.cta{display:inline-flex;align-items:center;min-height:40px;padding:0 16px;border-radius:12px;background:#fff;color:var(--ink);font-weight:700;font-size:15px;text-decoration:none}
.hero{padding:26px 0 30px}
.kicker{margin:0 0 8px;font-size:15px;color:#AFBBD0}
h1{margin:0;font-family:var(--serif);font-weight:700;font-size:clamp(32px,7vw,48px);line-height:1.05;letter-spacing:-.02em}
.lede{margin:12px 0 0;font-size:18px;line-height:1.45;color:#D3DAE6}
main.wrap{padding-top:26px;padding-bottom:40px}
article{background:#fff;border-radius:20px;padding:22px;margin:0 0 16px}
.meta{margin:0 0 6px;font-size:13px;font-weight:600;color:var(--muted)}
h2{margin:0;font-family:var(--serif);font-weight:700;font-size:24px;line-height:1.18;letter-spacing:-.01em}
h2 a{text-decoration:none}
h2 a:hover{text-decoration:underline}
p.sum{margin:10px 0 0;font-size:17px;line-height:1.55;color:var(--text)}
.takes{margin:14px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px}
.takes li{padding:12px 14px;border-radius:14px;background:var(--soft);font-size:15px;line-height:1.45;color:var(--text)}
.takes b{display:block;font-size:13px;color:var(--ink)}
.src{margin:14px 0 0;font-size:13px;font-weight:600;color:var(--muted)}
.src a{display:inline-block;margin:6px 6px 0 0;padding:5px 10px;border:1px solid var(--pill);border-radius:999px;color:#3A4556;text-decoration:none;font-size:12px}
.list{margin:0;padding:0;list-style:none;background:#fff;border-radius:20px;overflow:hidden}
.list li{border-bottom:1px solid #E7EAEF}
.list li:last-child{border-bottom:0}
.list a{display:block;padding:16px 20px;text-decoration:none}
.list a b{display:block;font-family:var(--serif);font-size:19px}
.list a span{display:block;margin-top:4px;font-size:14px;color:var(--muted);line-height:1.4}
.pager{display:flex;justify-content:space-between;gap:12px;margin:22px 0 0;font-size:15px;font-weight:600}
.prose{background:#fff;border-radius:20px;padding:24px;font-size:17px;line-height:1.6;color:var(--text)}
.prose h2{margin:22px 0 8px;font-size:22px}
.prose h2:first-child{margin-top:0}
.pk-kicker{margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--flame)}
.pk-meta{margin:14px 0 0;font-size:13px;color:#AFBBD0}
.why{background:#fff;border-radius:20px;padding:20px 22px;margin:0 0 16px;font-size:17px;line-height:1.55;color:var(--text)}
.why b{color:var(--ink)}
.facts{background:#fff;border-radius:20px;padding:20px 22px 20px 44px;margin:0 0 16px;font-size:17px;line-height:1.55;color:var(--text)}
.facts li{margin:0 0 8px}
.ref{font-size:12px;vertical-align:super;line-height:0;text-decoration:none;color:var(--muted);margin-left:2px}
.sec{background:#fff;border-radius:20px;padding:20px 22px;margin:0 0 16px}
.sec p{margin:10px 0 0;font-size:17px;line-height:1.6;color:var(--text)}
.h3{font-family:var(--sans);margin:0 0 4px;font-size:12px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.srcs{background:#fff;border-radius:20px;padding:20px 22px 20px 44px;margin:0 0 16px;font-size:15px;line-height:1.5}
.srcs li{margin:0 0 8px}
.note{border:1px solid var(--pill);border-radius:16px;padding:14px 16px;font-size:14px;line-height:1.5;color:var(--muted)}
.quick{background:#fff;border-radius:20px;padding:20px 22px 8px;margin:0 0 12px}
.tldr{list-style:none;margin:10px 0 0;padding:0}
.tldr li{display:flex;gap:14px;align-items:flex-start;padding:0 0 14px}
.tldr li span{flex-shrink:0;width:28px;height:28px;border-radius:14px;background:var(--ink);color:#fff;font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:center;margin-top:1px}
.tldr li p{margin:0;font-size:18px;line-height:1.45;color:var(--ink);font-weight:500}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 12px}
.stat{background:var(--ink);color:#fff;border-radius:18px;padding:16px 16px 14px;display:flex;flex-direction:column;gap:6px}
.stat b{font-family:var(--serif);font-size:30px;line-height:1;letter-spacing:-.02em}
.stat span{font-size:13px;line-height:1.35;color:#D3DAE6}
.stat .ref{color:#AFBBD0}
.foryou{background:#fff;border-radius:20px;padding:18px 22px 6px;margin:0 0 12px;border-left:0}
.foryou p{margin:8px 0 12px;font-size:16px;line-height:1.55;color:var(--text)}
.more-h{margin:22px 0 8px 4px}
.fold{background:#fff;border-radius:16px;margin:0 0 8px;overflow:hidden}
.fold summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;font-weight:700;font-size:16px;color:var(--ink)}
.fold summary::-webkit-details-marker{display:none}
.fold summary i{width:10px;height:10px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform 200ms ease;margin-top:-4px;flex-shrink:0}
.fold[open] summary i{transform:rotate(-135deg);margin-top:4px}
.fold-body{padding:0 20px 16px}
.fold-body p{margin:0 0 12px;font-size:16px;line-height:1.6;color:var(--text)}
.facts-in,.srcs-in{margin:0;padding:0 0 0 20px;font-size:15px;line-height:1.55;color:var(--text)}
.facts-in li,.srcs-in li{margin:0 0 8px}
.why{font-size:16px}
footer{padding:0 0 40px;font-size:14px;color:var(--muted)}
footer a{margin-right:14px}
"""

LOGO = ('<svg width="28" height="28" viewBox="0 0 160 160" aria-hidden="true"><rect width="160" height="160" rx="36" fill="#fff"/>'
        '<path transform="translate(45.60 118) scale(0.09987 -0.09987)" d="M45 708 140 699C141 597 141 496 141 394V346C141 243 141 141 140 42L45 33V0H395V33L285 43L284 299H329C557 299 644 398 644 522C644 660 555 741 341 741H45ZM284 335V394C284 498 284 602 285 704H339C453 704 510 642 510 523C510 412 453 335 326 335Z" fill="#15191f"/>'
        '<circle cx="118" cy="44" r="13" fill="#c0262d"/></svg>')


def page(*, path, title, description, hero, body, root="../", jsonld=None):
    """A complete static page in PoliDesk's look. `root` is the relative path back to the site root."""
    url = f"{SITE}/{path}"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{NAME}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<meta name="theme-color" content="#142238">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>{STYLE}</style>
{ld}</head>
<body>
<header>
  <div class="wrap">
    <div class="top"><a class="brand" href="{root}">{LOGO}{NAME}</a><a class="cta" href="{root}">Today's briefing</a></div>
    <div class="hero">{hero}</div>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="wrap"><a href="{root}">Today's briefing</a><a href="{root}pick/">Editor's pick</a><a href="{root}briefing/">Past briefings</a><a href="{root}about/">About</a></footer>
</body>
</html>
"""


# ---------------------------------------------------------------- daily briefing pages
def story_html(st, n):
    sources = [s for s in st.get("sources") or [] if s.get("name")]
    cov = max(st.get("coverage") or 0, len(sources))
    text = whole(st.get("detail") or st.get("summary") or "")
    if text.endswith("…") and _ITEMS:
        # Another outlet's complete summary of the same story, if we have one.
        urls = {st.get("url")} | {s.get("url") for s in sources}
        alts = [whole(i.get("summary")) for i in _ITEMS if i.get("url") in urls]
        alts = [a for a in alts if len(a) >= 60 and not a.endswith("…")]
        if alts:
            text = max(alts, key=len)
    takes = [t for t in st.get("details") or [] if t.get("summary") and whole(t["summary"]) != text and not whole(t["summary"]).endswith("…")][:3]
    takes_html = ""
    if takes:
        takes_html = '<ul class="takes">' + "".join(
            f'<li><b>{esc(t["source"])}</b>{esc(whole(t["summary"]))}</li>' for t in takes) + "</ul>"
    links = "".join(f'<a href="{esc(safe_url(s.get("url")))}" rel="noopener">{esc(s["name"])}</a>' for s in sources)
    label = f"Reported by {cov} outlets" if cov > 1 else "Source"
    return f"""<article id="story-{n}">
  <p class="meta">{n} · {esc(st.get("place") or "World")}</p>
  <h2><a href="{esc(safe_url(st.get("url")))}" rel="noopener">{esc(st.get("title"))}</a></h2>
  <p class="sum">{esc(text)}</p>
  {takes_html}
  <p class="src">{label}:<br>{links}</p>
</article>"""


def edition_page(ed, prev_date=None, next_date=None):
    d = ed["date"]
    places = list(dict.fromkeys(s.get("place") for s in ed["stories"] if s.get("place")))
    title = f"Daily political briefing, {long_date(d)} · {NAME}"
    desc = (f"The {len(ed['stories'])} most-covered political stories on {long_date(d)}"
            + (f" — {', '.join(places)}" if places else "") + ": " + "; ".join(s["title"] for s in ed["stories"][:3]) + ".")
    desc = desc[:300]
    hero = (f'<p class="kicker">{esc(long_date(d))}</p><h1>Daily briefing</h1>'
            f'<p class="lede">The {len(ed["stories"])} political stories most outlets covered'
            + (f' — {esc(", ".join(places))}' if places else "") + ".</p>")
    pager = '<nav class="pager">' + (f'<a href="../{prev_date}/">← {esc(long_date(prev_date))}</a>' if prev_date else "<span></span>") \
        + (f'<a href="../{next_date}/">{esc(long_date(next_date))} →</a>' if next_date else "<span></span>") + "</nav>"
    body = "\n".join(story_html(st, i + 1) for i, st in enumerate(ed["stories"])) + "\n" + pager
    jsonld = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": f"Daily political briefing, {long_date(d)}", "datePublished": ed.get("publishedAt") or d,
        "url": f"{SITE}/briefing/{d}/", "isPartOf": {"@type": "WebSite", "name": NAME, "url": f"{SITE}/"},
        "mainEntity": {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": st["title"], "url": safe_url(st.get("url"))}
            for i, st in enumerate(ed["stories"])]},
    }
    return page(path=f"briefing/{d}/", title=title, description=desc, hero=hero, body=body, root="../../", jsonld=jsonld)


def archive_index_page(editions):
    items = "".join(
        f'<li><a href="{e["date"]}/"><b>{esc(long_date(e["date"]))}</b>'
        f'<span>{esc(" · ".join(s["title"] for s in e["stories"][:3]))}</span></a></li>'
        for e in editions)
    hero = ('<h1>Past briefings</h1><p class="lede">Every daily briefing: the five political stories most outlets covered that morning, '
            'from Canada, Ontario, Toronto and the world.</p>')
    return page(path="briefing/", title=f"Past briefings · {NAME}",
                description="Archive of PoliDesk daily political briefings: the five most-covered political stories each day from Canada, Ontario, Toronto and the world.",
                hero=hero, body=f'<ul class="list">{items}</ul>', root="../")


def about_page(feed_names):
    sources = ", ".join(sorted(set(feed_names)))
    hero = '<h1>About PoliDesk</h1><p class="lede">Five political stories a day, in a few minutes. Then you\'re done.</p>'
    body = f"""<div class="prose">
<h2>What it is</h2>
<p>PoliDesk is a free daily political briefing for Canada, Ontario, Toronto and the world. Every morning at 7:00 (Toronto time) it picks the five political stories that the most news outlets are covering, and shows each one in a short card with links to the original reporting.</p>
<h2>How stories are chosen</h2>
<p>About every ten minutes PoliDesk reads public news feeds, keeps the political stories and groups reports about the same event. At 7:00 it ranks those groups by how many different outlets covered them, how recent they are and whether they have a photo, keeps a mix of regions, and makes sure at least one Canadian story is included. Nothing is written by hand and nothing is paid for.</p>
<h2>Where the news comes from</h2>
<p>{esc(sources)}. Every card links to the original articles; PoliDesk shows only headlines and short summaries.</p>
<h2>Why it's short</h2>
<p>Many people avoid the news because it feels endless and draining. A briefing with a clear end, a streak for showing up, and a one-question check at the end is meant to keep you informed without the doom-scrolling.</p>
<h2>More</h2>
<p>Browse every story from the last three days under “All stories” in the app, or read <a href="../briefing/">past briefings</a>.</p>
</div>"""
    jsonld = {"@context": "https://schema.org", "@type": "AboutPage", "name": f"About {NAME}", "url": f"{SITE}/about/"}
    return page(path="about/", title=f"About · {NAME}",
                description="PoliDesk is a free daily political briefing: the five most-covered political stories each morning from Canada, Ontario, Toronto and the world.",
                hero=hero, body=body, root="../", jsonld=jsonld)


# ---------------------------------------------------------------- editor's pick
# docs/pick/<date>/pick.json is written by the nightly Editor's Pick task and merged
# by the editor after review. Shape:
# {date, topic, title, dek, why, readMinutes, reviewPasses,
#  facts: [{text, sources: [1-based source numbers]}],
#  sections: [{heading, paragraphs: [..]}],
#  sources: [{name, title, url}]}
def _refs(nums, n_sources):
    return "".join(f'<a class="ref" href="#src-{i}">[{i}]</a>' for i in nums or [] if isinstance(i, int) and 1 <= i <= n_sources)


def pick_page(pk, prev_date=None, next_date=None):
    """Quick format first (short version, key numbers, why it matters, what it means for you);
    the longer sections and sources fold away for readers who want more."""
    d = pk["date"]
    srcs = [x for x in pk.get("sources") or [] if x.get("url")]
    n = len(srcs)
    topic = pk.get("topic") or "World"
    secs = pk.get("sections") or []
    find = lambda word: next((x for x in secs if word in (x.get("heading") or "").lower()), None)
    for_you = find("for you")
    # The short version: 3 lines. Older picks without "tldr" fall back to their first facts.
    tldr = pk.get("tldr") or [f["text"] for f in (pk.get("facts") or [])[:3]]
    tldr_html = "".join(f"<li><span>{i + 1}</span><p>{esc(t)}</p></li>" for i, t in enumerate(tldr[:3]))
    stats = "".join(f'<div class="stat"><b>{esc(x.get("value"))}</b><span>{esc(x.get("label"))}{_refs(x.get("sources"), n)}</span></div>'
                    for x in (pk.get("numbers") or [])[:4])
    hero = (f'<p class="pk-kicker">Today\'s Editor\'s Pick · {esc(topic)}</p>'
            f'<h1>{esc(pk["title"])}</h1><p class="lede">{esc(pk.get("dek"))}</p>'
            f'<p class="pk-meta">{esc(long_date(d))} · {int(pk.get("quickMinutes") or 1)} min · {n} sources</p>')
    fold = lambda title, inner, open_=False: (f'<details class="fold"{" open" if open_ else ""}><summary>{esc(title)}<i aria-hidden="true"></i></summary>'
                                              f'<div class="fold-body">{inner}</div></details>')
    paras = lambda sec: "".join(f"<p>{esc(p)}</p>" for p in sec.get("paragraphs") or [])
    more = "".join(fold(sec.get("heading"), paras(sec)) for sec in secs if sec is not for_you)
    facts = "".join(f'<li>{esc(f["text"])}{_refs(f.get("sources"), n)}</li>' for f in pk.get("facts") or [])
    if facts:
        more = fold("Key facts", f'<ol class="facts-in">{facts}</ol>') + more
    sources = "".join(
        f'<li id="src-{i + 1}"><a href="{esc(safe_url(x["url"]))}" rel="noopener">{esc(x.get("title") or x["url"])}</a>'
        f'{" — " + esc(x["name"]) if x.get("name") else ""}</li>' for i, x in enumerate(srcs))
    pager = '<nav class="pager">' + (f'<a href="../{prev_date}/">← Previous pick</a>' if prev_date else "<span></span>") \
        + (f'<a href="../{next_date}/">Next pick →</a>' if next_date else "<span></span>") + "</nav>"
    body = (f'<section class="quick"><h2 class="h3">The short version</h2><ol class="tldr">{tldr_html}</ol></section>'
            + (f'<div class="stats">{stats}</div>' if stats else "")
            + f'<div class="why"><b>Why it matters.</b> {esc(pk.get("why"))}</div>'
            + (f'<div class="foryou"><h2 class="h3">What it means for you</h2>{paras(for_you)}</div>' if for_you else "")
            + (f'<h2 class="h3 more-h">Want the full story?</h2>{more}' if more else "")
            + fold(f"Sources ({n})", f'<ol class="srcs-in">{sources}</ol>')
            + '<p class="note">Researched and written by AI and checked several times against its sources before publishing. It can still contain mistakes, so follow the sources for the full picture. Not medical, legal or financial advice.</p>'
            + pager)
    jsonld = {"@context": "https://schema.org", "@type": "Article", "headline": pk["title"], "description": pk.get("dek"),
              "datePublished": pk.get("publishedAt") or d, "url": f"{SITE}/pick/{d}/",
              "publisher": {"@type": "Organization", "name": NAME, "url": f"{SITE}/"},
              "citation": [x["url"] for x in srcs]}
    return page(path=f"pick/{d}/", title=f"{pk['title']} · Editor's Pick · {NAME}", description=(pk.get("dek") or "")[:300],
                hero=hero, body=body, root="../../", jsonld=jsonld)


def pick_index_page(picks):
    items = "".join(f'<li><a href="{p["date"]}/"><b>{esc(p["title"])}</b><span>{esc(long_date(p["date"]))} · {esc(p.get("topic") or "")}</span></a></li>' for p in picks)
    hero = ('<p class="pk-kicker">Editor\'s Pick</p><h1>The story that matters most</h1><p class="lede">Each day, one story with the widest impact on people\'s lives — '
            'health, science, climate, the economy or anything else — researched across several sources.</p>')
    body = f'<ul class="list">{items}</ul>' if items else '<p class="note">The first Editor\'s Pick is on its way.</p>'
    return page(path="pick/", title=f"Editor's Pick · {NAME}",
                description="PoliDesk's daily Editor's Pick: one story with the widest impact on people's lives, researched across several sources.",
                hero=hero, body=body, root="../")


def build_picks(docs):
    """Pages for every approved pick, plus pick/latest.json for the app."""
    changed, picks = [], []
    folder = docs / "pick"
    for f in sorted(folder.glob("*/pick.json"), reverse=True):
        try:
            pk = json.loads(f.read_text(encoding="utf-8"))
            if pk.get("title") and pk.get("date") == f.parent.name:
                picks.append(pk)
        except (ValueError, OSError):
            pass
    dates = [p["date"] for p in picks]
    for i, pk in enumerate(picks):
        nxt = dates[i - 1] if i > 0 else None
        prv = dates[i + 1] if i + 1 < len(dates) else None
        if write_if_changed(folder / pk["date"] / "index.html", pick_page(pk, prv, nxt)):
            changed.append(f"pick/{pk['date']}/")
    if write_if_changed(folder / "index.html", pick_index_page(picks)):
        changed.append("pick/")
    if picks:
        p = picks[0]
        latest = {"date": p["date"], "topic": p.get("topic"), "title": p["title"], "dek": p.get("dek"),
                  "readMinutes": p.get("quickMinutes") or p.get("readMinutes") or 4, "sources": len(p.get("sources") or []), "url": f"pick/{p['date']}/"}
        if write_if_changed(folder / "latest.json", json.dumps(latest, ensure_ascii=False, indent=1)):
            changed.append("pick/latest.json")
    return changed, dates


# ---------------------------------------------------------------- home page prerender
def prerender_home(index_path, ed):
    """Write today's headlines into the app's start screen so they're in the HTML itself."""
    s = index_path.read_text(encoding="utf-8")
    items = "".join(f"<li><span>{i + 1}</span><b>{esc(st['title'])}</b></li>" for i, st in enumerate(ed["stories"]))
    places = "".join(f"<span>{esc(p)}</span>" for p in dict.fromkeys(st.get("place") for st in ed["stories"] if st.get("place")))
    s2 = re.sub(r'(<ol class="today-list" id="startList">).*?(</ol>)', lambda m: m.group(1) + items + m.group(2), s, count=1, flags=re.S)
    s2 = re.sub(r'(<div class="places" id="startPlaces">).*?(</div>)', lambda m: m.group(1) + places + m.group(2), s2, count=1, flags=re.S)
    s2 = re.sub(r'(<p class="kicker-dark" id="startDate">).*?(</p>)', lambda m: m.group(1) + esc(long_date(ed["date"])) + m.group(2), s2, count=1, flags=re.S)
    return write_if_changed(index_path, s2)


# ---------------------------------------------------------------- sitemap
def sitemap(paths_with_dates):
    rows = "".join(f"<url><loc>{SITE}/{p}</loc><lastmod>{d}</lastmod></url>\n" for p, d in paths_with_dates)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


# ---------------------------------------------------------------- entry point
_ITEMS = []


def build(docs, ed, feed_names, items=None):
    """Called after edition.json is up to date. Returns the list of files that changed."""
    global _ITEMS
    _ITEMS = items or []
    changed = []
    archive = docs / "briefing"
    if ed and ed.get("stories") and re.match(r"^\d{4}-\d{2}-\d{2}$", ed.get("date", "")):
        # Keep a copy of every edition's data next to its page, so pages can be rebuilt later.
        if write_if_changed(archive / ed["date"] / "edition.json", json.dumps(ed, ensure_ascii=False, indent=1)):
            changed.append(f"briefing/{ed['date']}/edition.json")
    editions = []
    for f in sorted(archive.glob("*/edition.json"), reverse=True):
        try:
            editions.append(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    dates = [e["date"] for e in editions]
    for i, e in enumerate(editions):
        nxt = dates[i - 1] if i > 0 else None
        prv = dates[i + 1] if i + 1 < len(dates) else None
        if write_if_changed(archive / e["date"] / "index.html", edition_page(e, prv, nxt)):
            changed.append(f"briefing/{e['date']}/")
    if write_if_changed(archive / "index.html", archive_index_page(editions)):
        changed.append("briefing/")
    if write_if_changed(docs / "about" / "index.html", about_page(feed_names)):
        changed.append("about/")
    if ed and ed.get("stories") and prerender_home(docs / "index.html", ed):
        changed.append("index.html")
    pick_changed, pick_dates = build_picks(docs)
    changed += pick_changed
    latest = dates[0] if dates else date.today().isoformat()
    urls = [("", latest), ("briefing/", latest), ("about/", "2026-11-13")] + [(f"briefing/{d}/", d) for d in dates]
    urls += [("pick/", pick_dates[0] if pick_dates else latest)] + [(f"pick/{d}/", d) for d in pick_dates]
    if write_if_changed(docs / "sitemap.xml", sitemap(urls)):
        changed.append("sitemap.xml")
    return changed
