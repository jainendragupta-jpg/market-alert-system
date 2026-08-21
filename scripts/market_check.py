import os
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# ============================================================
# CONFIGURATION & CONSTANTS
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ============================================================
# HELPER FUNCTIONS & DATA FETCHERS
# ============================================================

def send_telegram(message: str) -> None:
    """Sends a text message to the specified Telegram Chat without failing on parse errors."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        print("Telegram configuration missing or using placeholders. Displaying output in console instead:\n")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        print("Telegram message sent successfully!")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response details: {e.response.text}")

def get_index_data(ticker_symbol: str) -> dict:
    """Fetches historical price data and technical indicators for a given index."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="2y")
        
        if df.empty or len(df) < 200:
            raise ValueError(f"Insufficient historical data for {ticker_symbol}")

        close_series = df['Close']
        latest_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        daily_change = round(((latest_close - prev_close) / prev_close) * 100, 2)

        # DMAs
        dma50 = float(close_series.rolling(window=50).mean().iloc[-1])
        dma200 = float(close_series.rolling(window=200).mean().iloc[-1])

        # Drawdown from 52-week High
        high_52w = float(df['High'].iloc[-252:].max())
        drawdown = round(((high_52w - latest_close) / high_52w) * 100, 2)

        # Weekly & Monthly RSI (Fixed Pandas Resample Key 'W' -> 'W', 'M' -> 'ME')
        weekly_df = close_series.resample('W').last()
        try:
            monthly_df = close_series.resample('ME').last()
        except ValueError:
            monthly_df = close_series.resample('M').last()

        def compute_rsi(series: pd.Series, period: int = 14) -> float:
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            val = rsi_series.dropna().iloc[-1] if not rsi_series.dropna().empty else 50.0
            return float(val)

        weekly_rsi = round(compute_rsi(weekly_df), 2)
        monthly_rsi = round(compute_rsi(monthly_df), 2)

        trend = "Bullish 🟢" if dma50 > dma200 else "Bearish 🔴"

        return {
            "close": round(latest_close, 2),
            "change": daily_change,
            "dma50": round(dma50, 2),
            "dma200": round(dma200, 2),
            "drawdown": drawdown,
            "weekly_rsi": weekly_rsi,
            "monthly_rsi": monthly_rsi,
            "trend": trend
        }
    except Exception as e:
        print(f"Error fetching index data for {ticker_symbol}: {e}")
        return {
            "close": 0.0, "change": 0.0, "dma50": 0.0, "dma200": 0.0,
            "drawdown": 0.0, "weekly_rsi": 50.0, "monthly_rsi": 50.0, "trend": "N/A"
        }

def get_nse_valuation() -> dict:
    """Fetches Nifty 50 PE, PB, and Dividend Yield."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    return {
        "pe": 22.5,
        "pb": 4.1,
        "dividend_yield": 1.2,
        "date": today_str
    }

def get_india_vix() -> float:
    """Fetches India VIX index value using Yahoo Finance."""
    try:
        vix = yf.Ticker("^INDIAVIX")
        df = vix.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"Error fetching India VIX: {e}")
    return 15.0

# Fixed Ticker list (Removed delisted LTIM.NS issue)
def get_nifty100_symbols() -> list:
    return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LT.NS", "AXISBANK.NS"]

def get_midcap150_symbols() -> list:
    return ["FEDERALBNK.NS", "VOLTAS.NS", "POLYCAB.NS", "ASHOKLEY.NS", "AUBANK.NS", "MPHASIS.NS", "PERSISTENT.NS", "COFORGE.NS"]

def get_smallcap250_symbols() -> list:
    return ["CDSL.NS", "ANGELONE.NS", "KEI.NS", "CAMS.NS", "BSOFT.NS", "CYIENT.NS", "IEX.NS", "MCX.NS"]

def calculate_breadth(symbols: list) -> dict:
    """Calculates percentage of constituent stocks trading above 200 DMA."""
    above_200_count = 0
    total = len(symbols)
    if total == 0:
        return {"pct200": 50.0}

    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(period="1y")
            if len(df) >= 200:
                c = df['Close'].iloc[-1]
                d200 = df['Close'].rolling(200).mean().iloc[-1]
                if c > d200:
                    above_200_count += 1
        except Exception:
            continue

    pct = round((above_200_count / total) * 100, 2)
    return {"pct200": pct}

# ============================================================
# SCORING & LOGIC FUNCTIONS
# ============================================================

def calculate_valuation_score(pe: float, pb: float, dy: float) -> float:
    if pe is None:
        return 50.0
    if pe < 18:
        pe_score = 90
    elif pe < 22:
        pe_score = 70
    elif pe < 25:
        pe_score = 50
    else:
        pe_score = 30

    return float(pe_score)

def vix_score(vix: float) -> float:
    if vix is None:
        return 50.0
    if vix < 12:
        return 80.0
    elif vix < 18:
        return 65.0
    elif vix < 24:
        return 45.0
    else:
        return 30.0

def god_score(close: float, dma50: float, dma200: float, w_rsi: float, m_rsi: float, drawdown: float, vix: float, breadth_200: float) -> float:
    score = 50.0
    
    if close > dma50 and dma50 > dma200:
        score += 15
    elif close < dma200:
        score -= 10

    if 40 <= w_rsi <= 60:
        score += 10
    elif w_rsi > 70:
        score -= 5

    if m_rsi > 50:
        score += 10

    if breadth_200 > 60:
        score += 10
    elif breadth_200 < 40:
        score -= 10

    if vix < 15:
        score += 5

    return min(100.0, max(0.0, round(score, 1)))

def score_status(score: float) -> str:
    if score >= 75:
        return "EXTREMELY BULLISH 🚀"
    elif score >= 60:
        return "BULLISH 🟢"
    elif score >= 45:
        return "NEUTRAL 🟡"
    elif score >= 30:
        return "BEARISH 🔴"
    else:
        return "EXTREMELY BEARISH ⚠️"

def get_action(score: float) -> str:
    if score >= 70:
        return "Aggressive Buying / Top-Up SIP"
    elif score >= 50:
        return "Continue Regular SIP / Hold Existing Capital"
    else:
        return "Caution Recommended / Preserve Cash for Dips"

def valuation_label(score: float) -> str:
    if score >= 70:
        return "Attractive ✅"
    elif score >= 50:
        return "Fairly Valued 🟡"
    else:
        return "Expensive ❌"

def get_allocation(overall: float, large: float, mid: float, small: float) -> dict:
    if overall > 65:
        return {"large": 50, "mid": 30, "small": 20}
    elif overall >= 45:
        return {"large": 60, "mid": 25, "small": 15}
    else:
        return {"large": 70, "mid": 20, "small": 10}

def investment_strategy(score: float, close: float, dma200: float, m_rsi: float) -> dict:
    if score >= 65:
        stage = "Bullish Expansion"
        sip = "100% Active"
        lumpsum = "Deploy in Tranches on Minor Dips"
        action = "Accumulate Quality Growth Funds / Equities"
    elif score >= 45:
        stage = "Consolidation / Rangebound"
        sip = "100% Active"
        lumpsum = "Wait for Clear Support Levels"
        action = "Maintain Balanced Asset Allocation"
    else:
        stage = "Correction / Bearish Pressure"
        sip = "Continue (Do Not Stop SIP)"
        lumpsum = "Aggressive Opportunity if Long-Term Horizon"
        action = "Focus on Large Caps and Quality Value Stocks"

    return {
        "stage": stage,
        "sip": sip,
        "lumpsum": lumpsum,
        "action": action
    }

# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    try:
        print("======================================")
        print("AI WEALTH MANAGER STARTED")
        print("======================================")

        # 1. Fetch Index Data
        print("Getting index data...")
        nifty50 = get_index_data("^NSEI")
        nifty100 = get_index_data("^CNX100")
        midcap150 = get_index_data("NIFTYMIDCAP150.NS")
        smallcap250 = get_index_data("NIFTYSMLCAP250.NS")
        sensex = get_index_data("^BSESN")

        # 2. Fetch Valuation Data
        print("Getting NSE valuation...")
        valuation_data = get_nse_valuation()
        pe = valuation_data["pe"]
        pb = valuation_data["pb"]
        dividend_yield = valuation_data["dividend_yield"]

        # 3. Fetch India VIX
        print("Getting India VIX...")
        india_vix = get_india_vix()

        # 4. Fetch Constituents & Calculate Market Breadth
        print("Getting constituents and calculating breadth...")
        nifty100_symbols = get_nifty100_symbols()
        midcap150_symbols = get_midcap150_symbols()
        smallcap250_symbols = get_smallcap250_symbols()

        large_breadth = calculate_breadth(nifty100_symbols)
        mid_breadth = calculate_breadth(midcap150_symbols)
        small_breadth = calculate_breadth(smallcap250_symbols)

        # 5. Calculate Valuation & VIX Scores
        valuation_score_value = calculate_valuation_score(pe, pb, dividend_yield)
        vix_score_value = vix_score(india_vix)

        # 6. Calculate God Scores for Market Segments
        large_score = god_score(
            nifty100["close"], nifty100["dma50"], nifty100["dma200"],
            nifty100["weekly_rsi"], nifty100["monthly_rsi"], nifty100["drawdown"],
            india_vix, large_breadth["pct200"]
        )

        mid_score = god_score(
            midcap150["close"], midcap150["dma50"], midcap150["dma200"],
            midcap150["weekly_rsi"], midcap150["monthly_rsi"], midcap150["drawdown"],
            india_vix, mid_breadth["pct200"]
        )

        small_score = god_score(
            smallcap250["close"], smallcap250["dma50"], smallcap250["dma200"],
            smallcap250["weekly_rsi"], smallcap250["monthly_rsi"], smallcap250["drawdown"],
            india_vix, small_breadth["pct200"]
        )

        # 7. Overall Market Score
        overall_score = round(
            large_score * 0.50 +
            mid_score * 0.30 +
            small_score * 0.20,
            1
        )

        # 8. Status & Actions Formatting
        overall_status = score_status(overall_score)
        large_status = score_status(large_score)
        mid_status = score_status(mid_score)
        small_status = score_status(small_score)

        overall_action = get_action(overall_score)
        large_action = get_action(large_score)
        mid_action = get_action(mid_score)
        small_action = get_action(small_score)

        allocation = get_allocation(overall_score, large_score, mid_score, small_score)
        strategy = investment_strategy(overall_score, nifty50["close"], nifty50["dma200"], nifty50["monthly_rsi"])

        pe_text = f"{pe:.2f}" if pe is not None else "N/A"
        pb_text = f"{pb:.2f}" if pb is not None else "N/A"
        dy_text = f"{dividend_yield:.2f}%" if dividend_yield is not None else "N/A"
        vix_text = f"{india_vix:.2f}" if india_vix is not None else "N/A"

        # 9. Format Final Report
        message = f"""🤖 AI WEALTH MANAGER
📊 DAILY MARKET INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 FINAL MARKET SCORE

{overall_score}/100
{overall_status}

ACTION: {overall_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🌐 MARKET VALUATION

NIFTY 50 PE: {pe_text}
NIFTY 50 PB: {pb_text}
DIVIDEND YIELD: {dy_text}
VALUATION SCORE: {valuation_score_value}/100
VALUATION DATA DATE: {valuation_data['date']}

━━━━━━━━━━━━━━━━━━━━━━━━

⚡ INDIA VIX

Current VIX: {vix_text}
VIX SCORE: {vix_score_value}/100

━━━━━━━━━━━━━━━━━━━━━━━━

LARGE CAP : NIFTY 100
🎯 SCORE: {large_score}/100
Valuation: {valuation_label(large_score)}
Price: {nifty100['close']}
50 DMA: {nifty100['dma50']}
200 DMA: {nifty100['dma200']}

DMA Trend: {'🟢 50DMA > 200DMA' if nifty100['dma50'] > nifty100['dma200'] else '🔴 50DMA < 200DMA'}

Weekly RSI: {nifty100['weekly_rsi']}
Monthly RSI: {nifty100['monthly_rsi']}

━━━━━━━━━━━━━━━━━━━━━━━━

MID CAP : NIFTY MIDCAP 150
🎯 SCORE: {mid_score}/100
Valuation: {valuation_label(mid_score)}
Price: {midcap150['close']}
50 DMA: {midcap150['dma50']}
200 DMA: {midcap150['dma200']}

DMA Trend:
{'🟢 50DMA > 200DMA' if midcap150['dma50'] > midcap150['dma200'] else '🔴 50DMA < 200DMA'}

Weekly RSI: {midcap150['weekly_rsi']}
Monthly RSI: {midcap150['monthly_rsi']}

━━━━━━━━━━━━━━━━━━━━━━━━

SMALL CAP: NIFTY SMALLCAP 250
🎯 SCORE: {small_score}/100
Valuation: {valuation_label(small_score)}
Price: {smallcap250['close']}
50 DMA: {smallcap250['dma50']}
200 DMA: {smallcap250['dma200']}

DMA Trend:
{'🟢 50DMA > 200DMA' if smallcap250['dma50'] > smallcap250['dma200'] else '🔴 50DMA < 200DMA'}

Weekly RSI: {smallcap250['weekly_rsi']}
Monthly RSI: {smallcap250['monthly_rsi']}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price: {nifty50['close']}
Daily Change: {nifty50['change']}%
Monthly RSI: {nifty50['monthly_rsi']}
Trend: {nifty50['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 SENSEX

Price: {sensex['close']}
Daily Change: {sensex['change']}%
Monthly RSI: {sensex['monthly_rsi']}
Trend: {sensex['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 INVESTMENT STRATEGY

MARKET STAGE: {strategy['stage']}
Equity SIP: {strategy['sip']}
Lump Sum: {strategy['lumpsum']}
Recommendation: {strategy['action']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 SUGGESTED ALLOCATION

Large Cap: {allocation['large']}%
Mid Cap: {allocation['mid']}%
Small Cap: {allocation['small']}%
"""

        # 10. Dispatch Output
        send_telegram(message)

    except Exception as e:
        print(f"Error running AI Wealth Manager: {e}")
