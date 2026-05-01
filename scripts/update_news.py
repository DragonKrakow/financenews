import csv
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
    "Telegram: geopolitics_prime (RSS.app)": "https://rss.app/r/feed/PNtcWNxuZCdoI4fa",
    "Telegram: market_briefing_italia (RSS.app)": "https://rss.app/r/feed/lBa4vy39mNxqvI7b",
}

KEYWORDS = [
    "Interest Rates",
    "Election",
    "Trade War",
    "Fed",
    "Regulation",
    # Expanded themes
    "Defense",
    "Aerospace",
    "Commodities",
    "Oil",
    "Natural Gas",
    "Gold",
    "Silver",
    "Mining",
    "Metals",
    "Semiconductors",
    "Chips",
    "AI",
    "Artificial Intelligence",
    "Robotics",
    "Clean Energy",
    "Renewables",
    "Supply Chain",
    "Logistics",
    "Shipping",
    "Transport",
]

NEGATIVE_SENTIMENT_THRESHOLD = -0.2
IMPACT_RULES = {
    "geopolitical_risk": {
        "keywords": ["war", "strike", "conflict", "missile", "drone", "nato", "sanctions"],
        "requires_negative_sentiment": True,
        "impact": {
            "LMT": "Bullish",
            "XLE": "Bullish",
            "ITA": "Bullish",
            "XAR": "Bullish",
            "VANECK_DEFENSE_UCITS": "Bullish",
            "WTEU_DEFENCE_UCITS": "Bullish",
            "GLD": "Bullish",
        },
        "reasoning": "Geopolitical headlines can increase defense demand, energy risk premiums, and risk-off flows into gold.",
    },
    "rate_cut_dovish": {
        "keywords": ["rate cut", "dovish", "soft landing", "disinflation"],
        "requires_negative_sentiment": False,
        "impact": {
            "QQQ": "Bullish",
            "TLT": "Bullish",
            "XLK": "Bullish",
            "VGT": "Bullish",
        },
        "reasoning": "Dovish policy expectations can support growth assets and longer-duration bonds.",
    },
    "trade_tariff_pressure": {
        "keywords": ["tariff", "trade war", "export controls", "chip ban"],
        "requires_negative_sentiment": False,
        "impact": {
            "TSLA": "Bearish",
            "NVDA": "Bearish",
            "SOXX": "Bearish",
            "SMH": "Bearish",
        },
        "reasoning": "Trade frictions can pressure globally exposed growth and supply-chain-dependent companies.",
    },
    "oil_supply_shock": {
        "keywords": ["opec", "oil", "brent", "wti", "pipeline", "refinery", "hormuz"],
        "requires_negative_sentiment": False,
        "impact": {
            "XLE": "Bullish",
            "VDE": "Bullish",
            "USO": "Bullish",
        },
        "reasoning": "Oil supply disruptions and geopolitics can raise crude prices and support traditional energy exposures.",
    },
    "gas_supply_shock": {
        "keywords": ["natural gas", "lng", "ttf", "storage", "pipeline"],
        "requires_negative_sentiment": False,
        "impact": {
            "UNG": "Bullish",
        },
        "reasoning": "Gas supply/demand shocks can drive natural gas volatility and influence gas-linked exposures.",
    },
    "semis_ai_boom": {
        "keywords": ["semiconductor", "chip", "chips", "gpu", "ai", "artificial intelligence", "data center"],
        "requires_negative_sentiment": False,
        "impact": {
            "NVDA": "Bullish",
            "SOXX": "Bullish",
            "SMH": "Bullish",
            "VVSM": "Bullish",
        },
        "reasoning": "AI/data-center demand can support semiconductor revenue and capex cycles.",
    },
    "transport_supply_chain": {
        "keywords": ["shipping", "freight", "port", "red sea", "suez", "logistics", "supply chain"],
        "requires_negative_sentiment": False,
        "impact": {
            "IYT": "Bullish",
            "XTN": "Bullish",
            "SUPL": "Bullish",
        },
        "reasoning": "Supply-chain disruptions and freight rate moves can affect transport/logistics exposures.",
    },
    "precious_metals_riskoff": {
        "keywords": ["risk-off", "safe haven", "gold", "silver", "bank stress"],
        "requires_negative_sentiment": False,
        "impact": {
            "GLD": "Bullish",
            "PHYS_GOLD_ETC": "Bullish",
            "WT_PHYSICAL_SILVER": "Bullish",
        },
        "reasoning": "Risk-off sentiment can support precious metals demand.",
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


def load_csv_tickers(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        tickers = []
        for row in reader:
            ticker = (row.get("Ticker") or "").strip()
            if not ticker:
                continue
            tickers.append(ticker)

    seen = set()
    out = []
    for t in tickers:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def merge_watchlist(base: list[dict], extra_tickers: list[str]) -> list[dict]:
    existing = {item.get("symbol") for item in base}
    merged = list(base)
    for t in extra_tickers:
        if t in existing:
            continue
        merged.append({"symbol": t, "name": t, "type": "Ticker", "tags": ["Imported", "Database"]})
        existing.add(t)
    return merged


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

    def sort_key(it):
        return (it.get("published") or "", it.get("title") or "")

    matched_items.sort(key=sort_key, reverse=True)
    all_items.sort(key=sort_key, reverse=True)

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

    base_watchlist = load_watchlist(repo_root)
    imported_tickers = load_csv_tickers(repo_root / "data" / "ETF_Azioni_Mega_Database (1).xlsx - Francoforte.csv")
    watchlist = merge_watchlist(base_watchlist, imported_tickers)

    signals = generate_signals(news_items, watchlist)

    output_file.write_text(json.dumps(news_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    signals_file.write_text(json.dumps(signals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(news_items)} news items to {output_file}")
    print(f"Wrote {len(signals)} signals to {signals_file}")


if __name__ == "__main__":
    main()
