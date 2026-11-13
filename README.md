# PoliDesk

A daily political briefing for world and local (Canada, Ontario, Toronto) news, live at **https://polidesk.ca**.

Every morning at 7:00 (Toronto time) the site picks the five most-covered stories of the last day. You read them in about three minutes, keep a streak and earn badges. After that, **All stories** lets you browse, search and filter every political story the site has collected, and keep the ones you want under **Saved**.

## How it works

| File | What it does |
|---|---|
| `scripts/fetch_news.py` | Reads ~27 public news feeds, keeps political stories, sorts them into beats and flags breaking ones. Writes `docs/news.json` (all stories, last 72 hours) and, once a day, `docs/edition.json` (the five-story briefing). Standard library only. |
| `.github/workflows/update-news.yml` | Runs the script about every 10 minutes and publishes the `docs` folder to GitHub Pages. |
| `docs/index.html` | The whole site: one page, no build step. |
| `docs/sw.js` | Service worker, so the briefing still opens without a connection. |
| `docs/manifest.webmanifest`, icons | Lets the site be added to a phone's home screen. |
| `docs/og-image.png` | Preview image shown when the link is shared. |

## Common changes

- **Add or remove a news source:** edit the `FEEDS` list at the top of `scripts/fetch_news.py`.
- **Change the briefing time:** change `EDITION_HOUR` in `scripts/fetch_news.py`. The page reads it from `edition.json`.
- **Update right away:** Actions tab → **Update news** → **Run workflow**.
- **After changing `index.html` in a way that must reach offline users quickly:** bump `CACHE` in `docs/sw.js`.
