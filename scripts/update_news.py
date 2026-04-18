import json
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

RSS_FEEDS = {
    "Reuters Politics": "http://feeds.reuters.com/Reuters/PoliticsNews",
    "CNBC Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "MarketWatch Top Stories": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "The Guardian Economics": "https://www.theguardian.com/business/economics/rss",
}

KEYWORDS = ["Interest Rates", "Election", "Trade War", "Fed", "Regulation"]


def extract_keywords(text: str) -> list[str]:
    lower = (text or "").lower()
    return [k for k in KEYWORDS if k.lower() in lower]


def sentiment_label(score: float) -> str:
    if score >= 0.2:
        return "Bullish"
    if score <= -0.2:
        return "Bearish"
    return "Neutral"


def normalize_published(raw_value: str) -> str:
    if not raw_value:
        return ""
    try:
        dt = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError):
        return raw_value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def main() -> None:
    analyzer = SentimentIntensityAnalyzer()
    repo_root = Path(__file__).resolve().parents[1]
    output_file = repo_root / "data.json"

    matched_items = []
    all_items = []
    seen = set()

    for source_name, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)

        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            published = normalize_published(entry.get("published") or entry.get("updated") or "")

            if not link or link in seen:
                continue
            seen.add(link)

            text = f"{title} {summary}".strip()
            kws = extract_keywords(text)
            score = analyzer.polarity_scores(text).get("compound", 0.0)

            item = {
                "title": title,
                "link": link,
                "source": source_name,
                "published": published,
                "summary": summary,
                "matched_keywords": kws,
                "sentiment_label": sentiment_label(score),
                "sentiment_score": round(score, 4),
            }

            all_items.append(item)
            if kws:
                matched_items.append(item)

    # Sort newest first
    def sort_key(it):
        return (it.get("published") or "", it.get("title") or "")

    matched_items.sort(key=sort_key, reverse=True)
    all_items.sort(key=sort_key, reverse=True)

    # Fallback: if too few keyword matches, still publish recent items
    if len(matched_items) < 10:
        output = all_items[:30]
    else:
        output = matched_items[:30]

    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} news items to {output_file}")


if __name__ == "__main__":
    main()
