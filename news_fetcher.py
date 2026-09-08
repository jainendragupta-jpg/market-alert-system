import feedparser
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO)

class NewsFetcher:
    """Fetches and deduplicates news articles from trusted RSS sources."""
    
    def __init__(self, feeds: List[Dict[str, str]]):
        self.feeds = feeds
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def fetch_all(()) -> List[Dict]:
        articles = []
        seen_titles = set()

        for feed_info in self.feeds:
            feed_name = feed_info["name"]
            url = feed_info["url"]
            try:
                logging.info(f"Fetching RSS: {feed_name}...")
                resp = requests.get(url, headers=self.headers, timeout=10)
                feed = feedparser.parse(resp.content)

                for entry in feed.entries[:15]:  # Process top 15 from each source
                    title = entry.get('title', '').strip()
                    link = entry.get('link', '').strip()
                    summary = entry.get('summary', '') or entry.get('description', '')

                    # Clean html tags from summary
                    clean_summary = BeautifulSoup(summary, "html.parser").get_text()

                    # Deduplication key using lower-case normalized title
                    norm_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
                    if norm_title in seen_titles or len(title) < 15:
                        continue
                    
                    seen_titles.add(norm_title)
                    articles.append({
                        "headline": title,
                        "summary_raw": clean_summary[:500],
                        "link": link,
                        "source": feed_name
                    })
            except Exception as e:
                logging.warning(f"Failed to fetch feed {feed_name}: {e}")

        logging.info(f"Total deduplicated articles fetched: {len(articles)}")
        return articles
