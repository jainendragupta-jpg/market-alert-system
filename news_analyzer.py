import json
import logging
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Define Pydantic Schemas for Enforced JSON Structure
class ImpactDetail(BaseModel):
    asset: str = Field(description="Affected asset e.g., Nifty, Sensex, S&P 500, Gold, Crude Oil, USD, INR")
    direction: str = Field(description="Bullish, Bearish, or Neutral")

class HighImpactNews(BaseModel):
    headline: str = Field(description="Concise, clear headline")
    summary: str = Field(description="Maximum 2-3 lines short narrative or bullet summary")
    impact_score: int = Field(description="AI Impact Score from 0 to 100")
    impact_details: List[ImpactDetail]
    link: str = Field(description="Direct URL to news item")

class InvestorActionSummary(BaseModel):
    what_to_watch: str = Field(description="Key global & domestic Indian events to watch")
    indian_sectors_benefiting: str = Field(description="Indian sectors that will benefit (e.g., IT, Banking, Auto, Metals)")
    indian_sectors_pressured: str = Field(description="Indian sectors under pressure")
    nifty_sensex_impact: str = Field(description="Direct impact on Nifty 50, Sensex & Large Caps")
    indian_mid_smallcap_impact: str = Field(description="Direct impact on Indian MidCap and SmallCap indices")
    indian_mutual_funds_impact: str = Field(description="Strategy for Equity MF, Debt MF, and SIP investors")
    us_markets_impact: str = Field(description="Impact on S&P 500, Nasdaq, and US Equities")
    gold_silver_impact: str = Field(description="Impact on Gold (MCX/INR) & Silver")
    crude_oil_inr_impact: str = Field(description="Impact on Crude Oil price & USD/INR currency exchange")

class MarketOutlook(BaseModel):
    nifty_outlook_1m: str = Field(description="Indian Market Nifty 50 1-Month Outlook: Bullish / Bearish / Neutral")
    nifty_outlook_3m: str = Field(description="Indian Market Nifty 50 3-Month Outlook: Bullish / Bearish / Neutral")
    nifty_outlook_6m: str = Field(description="Indian Market Nifty 50 6-Month Outlook: Bullish / Bearish / Neutral")
    us_market_outlook_3m: str = Field(description="US Market S&P 500 3-Month Outlook: Bullish / Bearish / Neutral")
    key_risks_india: List[str] = Field(description="Major risks for Indian market & investors")
    key_opportunities_india: List[str] = Field(description="Major opportunities for Indian market & investors")
    investor_action_summary: InvestorActionSummary

class AnalysisResult(BaseModel):
    high_impact_news: List[HighImpactNews]
    market_outlook: Optional[MarketOutlook] = None


class NewsAnalyzer:
    """Analyses and evaluates global financial impact using Gemini AI."""

    def __init__(self, api_key: str, language: str = 'en'):
        self.client = genai.Client(api_key=api_key)
        self.language = language
        # Updated candidate list prioritized by the latest active models
        self.candidate_models = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-flash-latest"]

    def analyze_and_rank(self, articles: List[Dict], threshold: float) -> Dict[str, Any]:
        if not articles:
            return {"high_impact_news": [], "market_outlook": None}

        lang_instruction = "English" if self.language == 'en' else "Hindi (using clear Devanagari script)"

system_instruction = f"""
        You are an elite Senior Financial Market Strategist, Quant Research Expert, and Indian Market Specialist.
        Analyze global news through the lens of an Indian Investor holding Indian Stocks, Mutual Funds, Gold, and US Equities.
        Language of output fields MUST be in {lang_instruction}.

        Evaluation Criteria:
        1. Calculate AI Market Impact Score (0 to 100) based on economic significance, market sensitivity, and RBI/Fed policies.
        2. Identify affected assets: Nifty 50, Sensex, Nifty Midcap, Nifty Smallcap, S&P 500, Nasdaq, Gold (MCX), Crude Oil, USD/INR.
        3. Give explicit directional impact on the Indian stock market alongside US markets.
        4. Include ONLY news items with AI Market Impact Score >= {threshold}.
        5. Provide 1-Month, 3-Month, and 6-Month outlooks specifically, key risks, key opportunities, and an investor action summary for Nifty/Indian Market and S&P 500.
        6. Detail specific strategies for Indian Mutual Funds (SIPs, Equity, Debt), Indian Large/Mid/Small-caps, Gold, Crude Oil, and INR.
        """
        prompt = f"Analyze the following pre-filtered global news items:\n{json.dumps(articles, indent=2)}"

 # Attempt API generation with automatic 503 retry backoff
        for target_model in self.candidate_models:
            for attempt in range(1, 4):
                try:
                    logging.info(f"Attempting news analysis with Gemini model: {target_model} (Attempt {attempt}/3)...")
                    response = self.client.models.generate_content(
                        model=target_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json",
                            response_schema=AnalysisResult,
                            temperature=0.2
                        )
                    )

                    if response.parsed:
                        logging.info(f"Successfully processed analysis using model: {target_model}")
                        return response.parsed.model_dump()
                    elif response.text:
                        logging.info(f"Successfully processed raw text analysis using model: {target_model}")
                        return json.loads(response.text)

                except Exception as e:
                    err_msg = str(e)
                    logging.warning(f"Model {target_model} attempt {attempt} failed: {err_msg}")
                    
                    # Retry if server returns a 503 temporary overload error
                    if "503" in err_msg and attempt < 3:
                        time.sleep(3)
                        continue
                    
                    # If 404 or other non-retriable error, break attempt loop to move to next candidate model
                    break

        logging.error("All Gemini candidate models failed to generate a response.")
        return {"high_impact_news": [], "market_outlook": None}
