import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
NEGATIVE_SENTIMENT_THRESHOLD = -0.2
IMPACT_RULES = {
    "geopolitical_risk": {
        "keywords": ["war", "strike", "conflict"],
        "requires_negative_sentiment": True,
        "impact": {
            "LMT": "Bullish",
            "XLE": "Bullish",
        },
        "reasoning": "Negative geopolitical headlines can increase defense demand and energy risk premiums.",
    },
    "rate_cut_dovish": {
        "keywords": ["rate cut", "dovish"],
        "requires_negative_sentiment": False,
        "impact": {
            "QQQ": "Bullish",
            "TLT": "Bullish",
        },
        "reasoning": "Dovish policy expectations can support growth assets and longer-duration bonds.",
    },
    "trade_tariff_pressure": {
        "keywords": ["tariff", "trade war"],
        "requires_negative_sentiment": False,
        "impact": {
            "TSLA": "Bearish",
            "NVDA": "Bearish",
        },
        "reasoning": "Trade frictions can pressure globally exposed growth and supply-chain-dependent companies.",
    },
}


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


def load_watchlist(repo_root: Path) -> list[dict]:
    watchlist_path = repo_root / "watchlist.json"
    return json.loads(watchlist_path.read_text(encoding="utf-8"))


def confidence_from_count(count: int) -> str:
    if count >= 4:
        return "High"
    if count >= 2:
        return "Medium"
    return "Low"


def suggested_action_for_signal(signal: str) -> str:
    if signal == "Bullish":
        return "Educational prompt: research whether this theme improves the ticker's macro setup and define risk limits before any trade."
    if signal == "Bearish":
        return "Educational prompt: research downside scenarios, earnings sensitivity, and risk controls before any trade."
    return "Educational prompt: monitor for confirming headlines and update your research thesis before taking action."


def generate_news_data() -> list[dict]:
    analyzer = SentimentIntensityAnalyzer()

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
        return all_items[:30]
    return matched_items[:30]


def generate_signals(news_items: list[dict], watchlist: list[dict]) -> list[dict]:
    ticker_matches = defaultdict(list)
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        score = item.get("sentiment_score", 0.0)
        for rule in IMPACT_RULES.values():
            if rule["requires_negative_sentiment"] and score > NEGATIVE_SENTIMENT_THRESHOLD:
                continue
            if not any(keyword in text for keyword in rule["keywords"]):
                continue

            for ticker, signal in rule["impact"].items():
                ticker_matches[ticker].append(
                    {
                        "signal": signal,
                        "reasoning": rule["reasoning"],
                        "headline": {
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                        },
                    }
                )

    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    generic_reasoning = (
        "No specific impact-rule match was found in the latest headline set. Treat this as a neutral research starting point, not investment advice."
    )
    signals = []
    for instrument in watchlist:
        ticker = instrument["symbol"]
        matches = ticker_matches.get(ticker, [])
        if not matches:
            signals.append(
                {
                    "ticker": ticker,
                    "signal": "Neutral",
                    "confidence": "Low",
                    "reasoning": generic_reasoning,
                    "suggested_research_action": suggested_action_for_signal("Neutral"),
                    "top_related_headline": {"title": "No direct trigger in latest run", "link": ""},
                    "last_updated": last_updated,
                }
            )
            continue

        signal_counts = Counter(match["signal"] for match in matches)
        tie_reason = ""
        if signal_counts["Bullish"] > signal_counts["Bearish"]:
            signal = "Bullish"
        elif signal_counts["Bearish"] > signal_counts["Bullish"]:
            signal = "Bearish"
        else:
            signal = "Neutral"
            if signal_counts["Bullish"] or signal_counts["Bearish"]:
                tie_reason = " Mixed bullish and bearish triggers were balanced, so the net signal is Neutral."

        top_match = matches[0]["headline"]
        signals.append(
            {
                "ticker": ticker,
                "signal": signal,
                "confidence": confidence_from_count(len(matches)),
                "reasoning": f"{matches[0]['reasoning']} Triggered by {len(matches)} related headline(s) from the latest news run.{tie_reason} Educational use only.",
                "suggested_research_action": suggested_action_for_signal(signal),
                "top_related_headline": top_match,
                "last_updated": last_updated,
            }
        )

    return signals


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_file = repo_root / "data.json"
    signals_file = repo_root / "signals.json"
    news_items = generate_news_data()
    watchlist = load_watchlist(repo_root)
    signals = generate_signals(news_items, watchlist)

    output_file.write_text(json.dumps(news_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    signals_file.write_text(json.dumps(signals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(news_items)} news items to {output_file}")
    print(f"Wrote {len(signals)} signals to {signals_file}")


if __name__ == "__main__":
    main()
