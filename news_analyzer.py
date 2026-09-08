import json
import logging
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
    what_to_watch: str
    benefiting_sectors: str
    pressured_sectors: str
    equities_impact: str
    mutual_funds_impact: str
    gold_impact: str
    crude_oil_impact: str

class MarketOutlook(BaseModel):
    outlook_1m: str = Field(description="Bullish / Bearish / Neutral")
    outlook_3m: str = Field(description="Bullish / Bearish / Neutral")
    outlook_6m: str = Field(description="Bullish / Bearish / Neutral")
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

    def _get_active_model(self) -> str:
        """Dynamically retrieves the first available flash model supporting generateContent."""
        # Hardcoded candidates in order of preference
        candidate_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]
        
        try:
            # Query active models directly from Google API
            available_models = [m.name.replace("models/", "") for m in self.client.models.list() if "generateContent" in getattr(m, 'supported_actions', []) or "generateContent" in getattr(m, 'supported_generation_methods', [])]
            for model_id in candidate_models:
                if model_id in available_models:
                    logging.info(f"Dynamically selected active Gemini model: {model_id}")
                    return model_id
        except Exception as err:
            logging.warning(f"Failed to fetch model list automatically: {err}")

        # Fallback to standard robust endpoint string
        return "gemini-1.5-flash"

    def analyze_and_rank(self, articles: List[Dict], threshold: float) -> Dict[str, Any]:
        if not articles:
            return {"high_impact_news": [], "market_outlook": None}

        lang_instruction = "English" if self.language == 'en' else "Hindi (using clear Devanagari script)"

        system_instruction = f"""
        You are an elite Senior Financial Market Strategist and Quantitative Research Expert with 30+ years of global experience.
        Analyze the input news items and populate the required output schema accurately.
        Language of output fields MUST be in {lang_instruction}.

        Evaluation Criteria:
        1. Calculate AI Market Impact Score (0 to 100) based on economic significance, geographic importance, market sensitivity, urgency, and reliability.
        2. Identify affected asset classes strictly: Nifty, Sensex, S&P 500, Nasdaq, Gold, Silver, Crude Oil, USD, INR.
        3. Assign directional sentiment per asset: Bullish, Bearish, or Neutral.
        4. Include ONLY news items with AI Market Impact Score >= {threshold}.
        5. Provide concise, clear 1-month, 3-month, and 6-month market outlooks, key risks, key opportunities, and an investor action summary.
        """

        prompt = f"Analyze the following pre-filtered global news items:\n{json.dumps(articles, indent=2)}"

        target_model = self._get_active_model()

        try:
            logging.info(f"Sending request to Gemini API model ({target_model}) with Structured Output Schema...")
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

            # Automatically convert structured response into a dictionary
            if response.parsed:
                return response.parsed.model_dump()
            elif response.text:
                return json.loads(response.text)
            
            logging.warning("Response returned empty content.")
            return {"high_impact_news": [], "market_outlook": None}

        except Exception as e:
            logging.error(f"Error calling Gemini API on {target_model}: {e}")
            return {"high_impact_news": [], "market_outlook": None}
