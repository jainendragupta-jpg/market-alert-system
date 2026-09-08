import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Define Pydantic Models for Strict JSON Enforcements
class ImpactDetail(BaseModel):
    asset: str = Field(description="Affected asset like Nifty, S&P 500, Gold, Crude Oil, USD")
    direction: str = Field(description="Bullish, Bearish, or Neutral")

class HighImpactNews(BaseModel):
    headline: str
    summary: str
    impact_score: int
    impact_details: List[ImpactDetail]
    link: str

class InvestorActionSummary(BaseModel):
    what_to_watch: str
    benefiting_sectors: str
    pressured_sectors: str
    equities_impact: str
    mutual_funds_impact: str
    gold_impact: str
    crude_oil_impact: str

class MarketOutlook(BaseModel):
    outlook_1m: str
    outlook_3m: str
    outlook_6m: str
    key_risks: List[str]
    key_opportunities: List[str]
    investor_action_summary: InvestorActionSummary

class AnalysisResult(BaseModel):
    high_impact_news: List[HighImpactNews]
    market_outlook: Optional[MarketOutlook] = None


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
        Analyze the input news items and populate the required output schema.
        Language of output fields MUST be in {lang_instruction}.

        Evaluate each news item against these criteria:
        1. Calculate AI Market Impact Score (0 to 100).
        2. Identify affected asset classes: Nifty, Sensex, S&P 500, Nasdaq, Gold, Silver, Crude Oil, USD, INR.
        3. Sentiment: Bullish, Bearish, or Neutral per affected asset class.
        4. Include ONLY items with AI Market Impact Score >= {threshold}.
        5. Provide market outlooks (1, 3, 6 Months), Key Risks, Key Opportunities, and Investor Action Summaries.
        """

        prompt = f"Analyze these global financial news items:\n{articles}"

        try:
            logging.info("Sending requests to Gemini API with Structured Output Schema...")
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AnalysisResult,
                    temperature=0.2
                )
            )

            # Response is automatically parsed into the Pydantic structure
            if response.parsed:
                return response.parsed.model_dump()
            
            return {"high_impact_news": [], "market_outlook": None}

        except Exception as e:
            logging.error(f"Error calling Gemini API: {e}")
            return {"high_impact_news": [], "market_outlook": None}
