import os
import sys

# Configuration settings for Global Market Impact AI Agent

# Language: 'en' for English, 'hi' for Hindi
PREFERRED_LANGUAGE = os.getenv("PREFERRED_LANGUAGE", "en").lower()

# Minimum score threshold (0-100) to trigger alert inclusion
IMPACT_THRESHOLD = float(os.getenv("IMPACT_THRESHOLD", "70"))

# Maximum news items per Telegram message
MAX_NEWS_ITEMS = int(os.getenv("MAX_NEWS_ITEMS", "8"))

# Telegram Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Gemini AI API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Trusted Global News RSS Feeds
NEWS_FEEDS = [
    # Top International & Financial Outlets
    {"name": "Reuters Business", "url": "https://news.google.com/rss/search?q=site:reuters.com+when:1d&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bloomberg Markets", "url": "https://news.google.com/rss/search?q=site:bloomberg.com+when:1d&hl=en-US&gl=US&ceid=US:en"},
    {"name": "CNBC Global", "url": "https://search.cnbc.com/rs/search/combined:ftpsimple?partnerId=2000&keywords=markets&target=all"},
    {"name": "Financial Times", "url": "https://news.google.com/rss/search?q=site:ft.com+when:1d&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWSJ.xml"},
    {"name": "Investing.com News", "url": "https://www.investing.com/rss/news.rss"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    
    # Major Central Banks & Global Regulatory Institutions
    {"name": "US Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"name": "Reserve Bank of India (RBI)", "url": "https://news.google.com/rss/search?q=site:rbi.org.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "IMF News", "url": "https://www.imf.org/en/News/rss"},
    {"name": "World Bank", "url": "https://www.worldbank.org/en/news/rss.xml"},

    # Trusted Indian Outlets
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/markets-106.rss"},
    {"name": "Moneycontrol", "url": "https://www.moneycontrol.com/rss/MCtopnews.xml"}
]

def validate_config():
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
        
    if missing:
        print(f"❌ Configuration Error: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
