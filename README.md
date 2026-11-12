# Politics Desk

A personal news page for world and local (Canada, Ontario, Toronto) politics.

- `scripts/fetch_news.py` reads public news feeds, keeps political stories, sorts them into beats and flags breaking stories. It writes `docs/news.json`.
- `.github/workflows/update-news.yml` runs that script every 30 minutes on GitHub and publishes the `docs` folder as the website.
- `docs/index.html` is the page. It reloads the news every 5 minutes while open.

To add or remove a news source, edit the `FEEDS` list at the top of `scripts/fetch_news.py`.
To run an update right away: **Actions** tab → **Update news** → **Run workflow**.
