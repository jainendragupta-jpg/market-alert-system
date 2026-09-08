import json
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types

class NewsAnalyzer:
    """Analyses and evaluates global financial impact using Gemini AI."""

    def __init__(self, api_key: str, language: str = 'en'):
        self.client = genai.Client(api_key=api_key)
        self.language = language

    def analyze_and_rank(self, articles: List[Dict], threshold: float) -> Dict[str, Any]:
        if not articles:
            return {"high_impact_news": [], "market_outlook": None}

        lang_instruction = "English" if self.language == 'en' else "Hindi (using clear Devanagari script)"

        system_instruction = f"""
        You are an elite Senior Financial Market Strategist and Quantitative Research Expert.
        Analyze the input news items and return a JSON output analyzing market impact.
        Language of output fields MUST be in {lang_instruction}.

        Evaluate each news item against these criteria:
        1. Calculate AI Market Impact Score (0 to 100).
        2. Identify affected asset classes: Nifty, Sensex, S&P 500, Nasdaq, Gold, Silver, Crude Oil, USD, INR.
        3. Sentiment: Bullish, Bearish, or Neutral per affected asset class.
        4. Include ONLY items with AI Market Impact Score >= {threshold}.
        5. Provide market outlooks (1, 3, 6 Months), Key Risks, Key Opportunities, and Investor Action Summaries.

        CRITICAL: Return ONLY raw, valid JSON. No Markdown formatting block tags like ```json.
        """

        prompt = f"""
        Analyze the following global financial news items:
        {json.dumps(articles, indent=2)}

        Return JSON matching this exact structure:
        {{
          "high_impact_news": [
            {{
              "headline": "Concise title",
              "summary": "2-3 line bulleted or crisp narrative summary (under 15s reading time)",
              "impact_score": 85,
              "impact_details": [
                {{"asset": "Nifty / Sensex", "direction": "Bearish / Bullish / Neutral"}},
                {{"asset": "Crude Oil", "direction": "Bullish"}}
              ],
              "link": "Original URL"
            }}
          ],
          "market_outlook": {{
            "outlook_1m": "Bullish / Bearish / Neutral",
            "outlook_3m": "Bullish / Bearish / Neutral",
            "outlook_6m": "Bullish / Bearish / Neutral",
            "key_risks": ["Risk 1", "Risk 2"],
            "key_opportunities": ["Opportunity 1", "Opportunity 2"],
            "investor_action_summary": {{
              "what_to_watch": "Details...",
              "benefiting_sectors": "Details...",
              "pressured_sectors": "Details...",
              "equities_impact": "Details...",
              "mutual_funds_impact": "Details...",
              "gold_impact": "Details...",
              "crude_oil_impact": "Details..."
            }}
          }}
        }}
        """

        try:
            logging.info("Sending requests to Gemini 2.5 Flash API...")
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            result = json.loads(response.text)
            return result

        except Exception as e:
            logging.error(f"Error calling Gemini API: {e}")
            return {"high_impact_news": [], "market_outlook": None}
