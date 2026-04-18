import feedparser
import re
import json
import os

# Keywords for matching
keywords = ["stock", "equity", "investment", "interest rate", "rates", "inflation", "CPI", "jobs", "payrolls", "tariffs", "trade", "regulation", "SEC", "FTC", "antitrust", "election", "congress", "senate", "white house", "budget", "deficit", "debt ceiling", "shutdown", "geopolitics", "sanctions", "OPEC", "oil", "China"]

# Abbreviations to match, case-insensitive
abbreviations = ["cpi", "sec", "ftc", "opec"]

# Fetch data from various feeds
feed_urls = [...]  # List of feed URLs

matched_items = []
for url in feed_urls:
    parsed_feed = feedparser.parse(url)
    if parsed_feed.bozo or parsed_feed.get('status') not in (200, None):
        print(f"Warning: {url} returned an error status.")
        continue

    for entry in parsed_feed.entries:
        title = entry.title.lower()
        content = entry.content[0].value.lower()
        link = entry.link
        matched_keywords = [kw for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', title) or re.search(r'\b' + re.escape(kw) + r'\b', content)]
        matched_abbr = [abbr for abbr in abbreviations if re.search(r'\b' + re.escape(abbr) + r'\b', title) or re.search(r'\b' + re.escape(abbr) + r'\b', content)]
        matched_keywords.extend(matched_abbr)

        if matched_keywords:
            matched_items.append({'title': title, 'link': link, 'matched_keywords': matched_keywords})

# Fallback mode if fewer than 10 items are matched
if len(matched_items) < 10:
    all_items = []
    for url in feed_urls:
        parsed_feed = feedparser.parse(url)
        all_items.extend([{'title': entry.title.lower(), 'link': entry.link} for entry in parsed_feed.entries])
    # Deduplicate by link
    unique_links = set()
    recent_items = []
    for item in all_items:
        if item['link'] not in unique_links:
            unique_links.add(item['link'])
            recent_items.append(item)
            if len(recent_items) == 30:
                break
    matched_items.extend(recent_items)

# Save results to data.json
with open('./data.json', 'w') as json_file:
    json.dump(matched_items, json_file)
