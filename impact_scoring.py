import re
from typing import List, Dict

class ImpactScorer:
    """Calculates rule-based priority score before passing articles to LLM."""

    HIGH_IMPACT_KEYWORDS = [
        "war", "conflict", "fed", "federal reserve", "interest rate", "inflation",
        "cpi", "rbi", "gdp", "recession", "sanction", "crude oil", "opec", "tariff",
        "trade war", "bank collapse", "liquidity", "earthquake", "tsunami", "default",
        "bond yield", "treasury", "monetary policy", "stimulus", "geopolitical"
    ]

    CREDIBLE_SOURCES = [
        "Reuters", "Bloomberg", "Financial Times", "Wall Street Journal", 
        "US Federal Reserve", "Reserve Bank of India (RBI)", "IMF News"
    ]

    @classmethod
    def calculate_score(cls, article: Dict) -> float:
        score = 40.0  # Base Score
        
        text = f"{article['headline']} {article['summary_raw']}".lower()

        # Keyword matching (+5 per match, max +35)
        matches = sum(1 for kw in cls.HIGH_IMPACT_KEYWORDS if kw in text)
        score += min(matches * 5, 35)

        # Source credibility bonus (+15)
        if any(src.lower() in article["source"].lower() for src in cls.CREDIBLE_SOURCES):
            score += 15

        # Cap score at 100
        return min(score, 100.0)

    @classmethod
    def filter_articles(cls, articles: List[Dict], threshold: float) -> List[Dict]:
        scored_articles = []
        for art in articles:
            score = cls.calculate_score(art)
            art["heuristics_score"] = score
            if score >= (threshold - 20):  # Pass pre-filtered list to LLM
                scored_articles.append(art)
        
        # Sort descending by preliminary score
        scored_articles.sort(key=lambda x: x["heuristics_score"], reverse=True)
        return scored_articles[:20]  # Take top 20 for AI LLM deep analysis
