# Finance News Dashboard

A static GitHub Pages dashboard that aggregates finance/politics-relevant news from free RSS feeds, filters by market-impact keywords, and assigns lightweight sentiment labels (Bullish/Bearish/Neutral) using VADER.

## Data pipeline

The updater script lives at:

- `/home/runner/work/financenews/financenews/scripts/update_news.py`

It reads these RSS feeds:

- Reuters Politics: `http://feeds.reuters.com/Reuters/PoliticsNews`
- CNBC Finance: `https://www.cnbc.com/id/10000664/device/rss/rss.html`
- MarketWatch Top Stories: `http://feeds.marketwatch.com/marketwatch/topstories/`
- The Guardian Economics: `https://www.theguardian.com/business/economics/rss`

It filters for keywords (case-insensitive):

- `Interest Rates`
- `Election`
- `Trade War`
- `Fed`
- `Regulation`

Then it writes root-level `data.json` with:

- `title`
- `link`
- `source`
- `published`
- `summary`
- `matched_keywords`
- `sentiment_label`
- `sentiment_score`

## Local setup and run

From repo root (`/home/runner/work/financenews/financenews`):

```bash
python -m pip install --upgrade pip
python -m pip install feedparser vaderSentiment
python scripts/update_news.py
```

Open `index.html` (via a local web server) to view the dashboard:

```bash
python -m http.server 8000
```

Then browse to `http://localhost:8000`.

## GitHub Action automation

Workflow file:

- `/home/runner/work/financenews/financenews/.github/workflows/update_news.yml`

Behavior:

- Runs every 6 hours (`cron: "0 */6 * * *"`)
- Supports manual trigger (`workflow_dispatch`)
- Installs Python dependencies (`feedparser`, `vaderSentiment`)
- Runs `scripts/update_news.py`
- Commits and pushes `data.json` only if it changed (using bot identity)

## GitHub Pages

This repository is structured for simple Pages hosting from the repo root:

- `index.html`
- `data.json`

In repository settings, set Pages source to:

- Branch: `main`
- Folder: `/(root)`

## Disclaimer

This project is for informational and educational purposes only and does **not** constitute financial advice, investment advice, or trading recommendations.
