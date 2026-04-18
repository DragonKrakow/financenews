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
    lower_text = text.lower()
    return [keyword for keyword in KEYWORDS if keyword.lower() in lower_text]


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


def generate_news_data() -> list[dict]:
    analyzer = SentimentIntensityAnalyzer()
    news_items = []
    seen_links = set()

    for source_name, feed_url in RSS_FEEDS.items():
        parsed_feed = feedparser.parse(feed_url)
        for entry in parsed_feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            content_for_filtering = f"{title} {summary}".strip()

            matched = extract_keywords(content_for_filtering)
            if not matched:
                continue
            if not link or link in seen_links:
                continue

            score = analyzer.polarity_scores(content_for_filtering).get("compound", 0.0)
            published = normalize_published(
                entry.get("published") or entry.get("updated") or ""
            )

            news_items.append(
                {
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                    "summary": summary,
                    "matched_keywords": matched,
                    "sentiment_label": sentiment_label(score),
                    "sentiment_score": round(score, 4),
                }
            )
            seen_links.add(link)

    news_items.sort(key=lambda item: (item["published"], item["title"]), reverse=True)
    return news_items


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_file = repo_root / "data.json"
    news_items = generate_news_data()

    output_file.write_text(
        json.dumps(news_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(news_items)} news items to {output_file}")


if __name__ == "__main__":
    main()
