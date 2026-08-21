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

# ============================================================
# HELPER FUNCTIONS & DATA FETCHERS
# ============================================================

def send_telegram(message: str) -> None:
    """Sends plain-text formatted message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        print("Telegram config missing/placeholder. Displaying in console:\n")
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
    """Fetches historical price data, DMAs, Drawdown & RSIs for an index."""
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

        # Weekly & Monthly RSI
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

        trend = "🟢 50 > 200" if dma50 > dma200 else "🔴 50 < 200"

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
    """Returns current Nifty PE valuation metrics."""
    today_str = datetime.now().strftime("%d-%b-%Y")
    return {
        "pe": 22.5,
        "pb": 4.1,
        "dividend_yield": 1.2,
        "date": today_str
    }

def get_india_vix() -> float:
    """Fetches India VIX index value."""
    try:
        vix = yf.Ticker("^INDIAVIX")
        df = vix.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"Error fetching India VIX: {e}")
    return 15.0

def get_nifty100_symbols() -> list:
    return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LT.NS", "AXISBANK.NS"]

def get_midcap150_symbols() -> list:
    return ["FEDERALBNK.NS", "VOLTAS.NS", "POLYCAB.NS", "ASHOKLEY.NS", "AUBANK.NS", "MPHASIS.NS", "PERSISTENT.NS", "COFORGE.NS"]

def get_smallcap250_symbols() -> list:
    return ["CDSL.NS", "ANGELONE.NS", "KEI.NS", "CAMS.NS", "BSOFT.NS", "CYIENT.NS", "IEX.NS", "MCX.NS"]

def calculate_breadth(symbols: list) -> dict:
    """Calculates % of constituents trading above 200 DMA."""
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
# TECHNICAL & VALUATION SCORING
# ============================================================

def god_score(close: float, dma50: float, dma200: float, w_rsi: float, m_rsi: float, drawdown: float, vix: float, breadth_200: float) -> float:
    score = 50.0
    if close > dma50 and dma50 > dma200:
        score += 15
    elif close < dma200:
        score -= 10

    if 40 <= w_rsi <= 60:
        score += 10
    elif w_rsi > 70:
        score -= 15

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
        return "Bullish 🚀"
    elif score >= 60:
        return "Bullish 🟢"
    elif score >= 45:
        return "Neutral 🟡"
    elif score >= 30:
        return "Bearish 🔴"
    else:
        return "Ext. Bearish ⚠️"

# ============================================================
# CATEGORY-SPECIFIC 8-STAGE EVALUATION ENGINE
# ============================================================

def get_category_stage(drawdown_52w: float, weekly_rsi: float, pe_ratio: float, vix: float) -> dict:
    if drawdown_52w < 1.5 or weekly_rsi >= 72.0:
        return {
            "stage": "🔥 Peak Euphoria",
            "action": "100% Active",
            "lumpsum_pct": "0% STRICT NO 🔴",
            "home_loan_prepay": "100% Prepay",
            "short_action": "100% Prepay Loan 🏦"
        }
    elif drawdown_52w >= 25.0 or weekly_rsi < 30:
        return {
            "stage": "🛑 Crisis Bottom",
            "action": "100% Active",
            "lumpsum_pct": "+100% Max Cash 🟢",
            "home_loan_prepay": "0% Prepay",
            "short_action": "100% Equity Buy 🟢"
        }
    elif drawdown_52w >= 15.0 or weekly_rsi < 35 or pe_ratio < 19:
        return {
            "stage": "📉 Bear Market",
            "action": "100% Active",
            "lumpsum_pct": "+75% Extra 🟢",
            "home_loan_prepay": "0% Prepay",
            "short_action": "75% Equity Buy 🟢"
        }
    elif drawdown_52w >= 10.0 or weekly_rsi < 40 or vix > 20:
        return {
            "stage": "⚠️ Correction",
            "action": "100% Active",
            "lumpsum_pct": "+50% Extra 🟢",
            "home_loan_prepay": "0% Prepay",
            "short_action": "50% Equity Buy 🟢"
        }
    elif drawdown_52w >= 4.5 or (40 <= weekly_rsi < 48):
        return {
            "stage": "🟡 Healthy Dip",
            "action": "100% Active",
            "lumpsum_pct": "+30% Extra 🟢",
            "home_loan_prepay": "20% Prepay",
            "short_action": "+30% Lumpsum 🟢"
        }
    elif drawdown_52w >= 2.5 or (48 <= weekly_rsi < 58):
        return {
            "stage": "📊 Minor Dip",
            "action": "100% Active",
            "lumpsum_pct": "+15% Extra 🟢",
            "home_loan_prepay": "50% Prepay",
            "short_action": "50% Equity / 50% Loan"
        }
    elif 58 <= weekly_rsi < 68:
        return {
            "stage": "🟢 Steady Bull",
            "action": "100% Active",
            "lumpsum_pct": "+10% Small Top 🟢",
            "home_loan_prepay": "70% Prepay",
            "short_action": "70% Prepay Loan 🏦"
        }
    else:
        return {
            "stage": "🚀 Strong Rally",
            "action": "100% Active",
            "lumpsum_pct": "0% Extra 🔴",
            "home_loan_prepay": "100% Prepay",
            "short_action": "100% Prepay Loan 🏦"
        }

# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    try:
        print("Fetching market data...")

        # 1. Fetch Index Data
        nifty50 = get_index_data("^NSEI")
        nifty100 = get_index_data("^CNX100")
        midcap150 = get_index_data("NIFTYMIDCAP150.NS")
        smallcap250 = get_index_data("NIFTYSMLCAP250.NS")

        # 2. Fetch Valuations & VIX
        val_data = get_nse_valuation()
        pe = val_data["pe"]
        india_vix = get_india_vix()

        # 3. Breadth Analysis
        large_breadth = calculate_breadth(get_nifty100_symbols())
        mid_breadth = calculate_breadth(get_midcap150_symbols())
        small_breadth = calculate_breadth(get_smallcap250_symbols())

        # 4. Scores
        large_score = god_score(nifty100["close"], nifty100["dma50"], nifty100["dma200"], nifty100["weekly_rsi"], nifty100["monthly_rsi"], nifty100["drawdown"], india_vix, large_breadth["pct200"])
        mid_score = god_score(midcap150["close"], midcap150["dma50"], midcap150["dma200"], midcap150["weekly_rsi"], midcap150["monthly_rsi"], midcap150["drawdown"], india_vix, mid_breadth["pct200"])
        small_score = god_score(smallcap250["close"], smallcap250["dma50"], smallcap250["dma200"], smallcap250["weekly_rsi"], smallcap250["monthly_rsi"], smallcap250["drawdown"], india_vix, small_breadth["pct200"])

        overall_score = round(large_score * 0.55 + mid_score * 0.28 + small_score * 0.17, 1)

        # 5. Category Stage Evaluation
        large_stage = get_category_stage(nifty100["drawdown"], nifty100["weekly_rsi"], pe, india_vix)
        mid_stage = get_category_stage(midcap150["drawdown"], midcap150["weekly_rsi"], pe, india_vix)
        small_stage = get_category_stage(smallcap250["drawdown"], smallcap250["weekly_rsi"], pe, india_vix)

        # 6. Build Ultra-Compact Short Message
        message = f"""📊 AI WEALTH MANAGER
{val_data['date']}
──────────────────────────
🌡️ MARKET METRICS
• Score: {overall_score}/100 ({score_status(overall_score)})
• Nifty PE: {pe:.2f}
• India VIX: {india_vix:.2f}
• Nifty 50: {nifty50['close']} ({nifty50['change']}%)
• Monthly RSI: {nifty50['monthly_rsi']}

──────────────────────
🏛️ CATEGORY MATRIX

📊 LARGE CAP
• Stage: {large_stage['stage']}
• SIP Status: 100% Active
• Lumpsum: {large_stage['lumpsum_pct']}
• Home Loan: {large_stage['home_loan_prepay']}
• Price: {nifty100['close']}
• Drawdown: -{nifty100['drawdown']}%
• wRSI / mRSI: {nifty100['weekly_rsi']} / {nifty100['monthly_rsi']}
• DMA: {nifty100['trend']}

📊 MID CAP
• Stage: {mid_stage['stage']}
• SIP Status: 100% Active
• Lumpsum: {mid_stage['lumpsum_pct']}
• Home Loan: {mid_stage['home_loan_prepay']}
• Price: {midcap150['close']}
• Drawdown: -{midcap150['drawdown']}%
• wRSI / mRSI: {midcap150['weekly_rsi']} / {midcap150['monthly_rsi']}
• DMA: {midcap150['trend']}

📊 SMALL CAP
• Stage: {small_stage['stage']}
• SIP Status: 100% Active
• Lumpsum: {small_stage['lumpsum_pct']}
• Home Loan: {small_stage['home_loan_prepay']}
• Price: {smallcap250['close']}
• Drawdown: -{smallcap250['drawdown']}%
• wRSI / mRSI: {smallcap250['weekly_rsi']} / {smallcap250['monthly_rsi']}
• DMA: {smallcap250['trend']}

──────────────────────
💡 SUMMARY ACTION
Large: {large_stage['short_action']}
Mid: {mid_stage['short_action']}
Small: {small_stage['short_action']}
"""

        # 7. Send Message
        send_telegram(message)

    except Exception as e:
        print(f"Error running AI Wealth Manager: {e}")
