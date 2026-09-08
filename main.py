import logging
from config import (
    validate_config, 
    NEWS_FEEDS, 
    IMPACT_THRESHOLD, 
    PREFERRED_LANGUAGE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    GEMINI_API_KEY
)
from news_fetcher import NewsFetcher
from impact_scoring import ImpactScorer
from news_analyzer import NewsAnalyzer
from telegram_sender import TelegramReporter

def run_pipeline():
    logging.info("Starting Global Market Impact AI Agent Pipeline...")
    validate_config()

    # Step 1: Fetch Articles
    fetcher = NewsFetcher(NEWS_FEEDS)
    raw_articles = fetcher.fetch_all()
    if not raw_articles:
        logging.info("No raw articles extracted. Terminating execution.")
        return

    # Step 2: Heuristic Filtering
    filtered_articles = ImpactScorer.filter_articles(raw_articles, IMPACT_THRESHOLD)
    logging.info(f"Filtered down to {len(filtered_articles)} candidates for LLM analysis.")

    if not filtered_articles:
        logging.info("No articles met initial heuristics threshold. Exiting without alert.")
        return

    # Step 3: AI Scoring & Synthesis
    analyzer = NewsAnalyzer(api_key=GEMINI_API_KEY, language=PREFERRED_LANGUAGE)
    analysis_results = analyzer.analyze_and_rank(filtered_articles, IMPACT_THRESHOLD)

    # Step 4: Dispatch Telegram Alert
    reporter = TelegramReporter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    formatted_msg = reporter.format_message(analysis_results)

    if formatted_msg:
        reporter.send_notification(formatted_msg)
    else:
        logging.info("No high-impact news surpassed final threshold. Telegram message skipped.")

if __name__ == "__main__":
    run_pipeline()
