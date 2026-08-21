import os
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# ============================================================
# CONFIGURATION & TELEGRAM MESSAGING
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

def send_telegram(message: str) -> None:
    """Sends formatted plain-text alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        print("Telegram configuration missing. Displaying output in console:\n")
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
        print("Telegram notification delivered successfully!")
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

# ============================================================
# DYNAMIC MARKET & P/E DATA FETCHING
# ============================================================

def get_index_data(ticker_symbol: str) -> dict:
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="2y")
        
        if df.empty or len(df) < 200:
            raise ValueError(f"Insufficient historical price data for {ticker_symbol}")

        close_series = df['Close']
        latest_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        daily_change = round(((latest_close - prev_close) / prev_close) * 100, 2)

        dma50 = float(close_series.rolling(window=50).mean().iloc[-1])
        dma200 = float(close_series.rolling(window=200).mean().iloc[-1])

        high_52w = float(df['High'].iloc[-252:].max())
        drawdown = round(((high_52w - latest_close) / high_52w) * 100, 2)

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

        trend = "🟢 50 DMA < 200 DMA (Discount Opportunity)" if dma50 < dma200 else "🔴 50 DMA > 200 DMA"

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
        print(f"Error retrieving index data for {ticker_symbol}: {e}")
        return {
            "close": 0.0, "change": 0.0, "dma50": 0.0, "dma200": 0.0,
            "drawdown": 0.0, "weekly_rsi": 50.0, "monthly_rsi": 50.0, "trend": "N/A"
        }

def get_dynamic_category_pe(symbols: list, default_pe: float) -> float:
    pe_list = []
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            info = t.info
            pe = info.get("trailingPE") or info.get("forwardPE")
            if pe and pe > 0:
                pe_list.append(pe)
        except Exception:
            continue
    return round(float(np.mean(pe_list)), 2) if pe_list else default_pe

def get_category_pe_ratios() -> dict:
    today_str = datetime.now().strftime("%d-%b-%Y")
    large_symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS"]
    mid_symbols = ["FEDERALBNK.NS", "VOLTAS.NS", "POLYCAB.NS", "PERSISTENT.NS", "COFORGE.NS", "AUBANK.NS"]
    small_symbols = ["CDSL.NS", "ANGELONE.NS", "KEI.NS", "CYIENT.NS", "BSOFT.NS"]

    large_pe = get_dynamic_category_pe(large_symbols, 22.5)
    mid_pe = get_dynamic_category_pe(mid_symbols, 30.0)
    small_pe = get_dynamic_category_pe(small_symbols, 28.0)

    return {
        "large_pe": large_pe,
        "mid_pe": mid_pe,
        "small_pe": small_pe,
        "date": today_str
    }

def get_pe_status(cap_type: str, pe: float) -> str:
    if cap_type == "large":
        if pe < 18: return "Discount Price"
        elif pe <= 24: return "Fair Price"
        else: return "High Price"
    elif cap_type == "mid":
        if pe < 24: return "Discount Price"
        elif pe <= 32: return "Growth Zone"
        else: return "Overvalued"
    elif cap_type == "small":
        if pe < 20: return "Deep Value"
        elif pe <= 28: return "Healthy Growth"
        else: return "High Risk"
    return ""

def get_india_vix() -> float:
    try:
        vix = yf.Ticker("^INDIAVIX")
        df = vix.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"Error fetching India VIX: {e}")
    return 15.0

def calculate_breadth(symbols: list) -> dict:
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
    if score >= 75: return "Bullish 🚀"
    elif score >= 60: return "Bullish 🟢"
    elif score >= 45: return "Neutral 🟡"
    elif score >= 30: return "Bearish 🔴"
    else: return "Ext. Bearish ⚠️"

# ============================================================
# CATEGORY STAGE EVALUATION ENGINE
# ============================================================

def get_category_stage(drawdown_52w: float, weekly_rsi: float, pe_ratio: float, vix: float) -> dict:
    if drawdown_52w < 1.5 or weekly_rsi >= 72.0:
        return {
            "stage_num": 1,
            "stage": "🔥 Extreme High (Stg 1)",
            "sip_status": "Stop This Month 🔴",
            "lumpsum_pct": "Book Small Profit 💰 & Prepay Loan 🏦",
            "short_action": "Book Profit 💰 -> Prepay Loan 🏦"
        }
    elif drawdown_52w >= 25.0 or weekly_rsi < 30:
        return {
            "stage_num": 8,
            "stage": "🛑 Market Crash (Stg 8)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + Max Lumpsum Buy 🚀",
            "short_action": "SIP + Max Lumpsum Buy 🚀"
        }
    elif drawdown_52w >= 15.0 or weekly_rsi < 35 or pe_ratio < 19:
        return {
            "stage_num": 7,
            "stage": "📉 Heavy Discount (Stg 7)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 75% Extra Lumpsum 🟢",
            "short_action": "SIP + 75% Extra Lumpsum 🟢"
        }
    elif drawdown_52w >= 10.0 or weekly_rsi < 40 or vix > 20:
        return {
            "stage_num": 6,
            "stage": "⚠️ Big Discount (Stg 6)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 50% Extra Lumpsum 🟢",
            "short_action": "SIP + 50% Extra Lumpsum 🟢"
        }
    elif drawdown_52w >= 4.5 or (40 <= weekly_rsi < 48):
        return {
            "stage_num": 5,
            "stage": "🟡 Good Discount (Stg 5)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 25% Extra Lumpsum 🟢",
            "short_action": "SIP + 25% Extra Lumpsum 🟢"
        }
    elif drawdown_52w >= 2.5 or (48 <= weekly_rsi < 58):
        return {
            "stage_num": 4,
            "stage": "📊 Small Discount (Stg 4)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 10% Extra Lumpsum 🟢",
            "short_action": "SIP + 10% Extra Lumpsum 🟢"
        }
    elif 58 <= weekly_rsi < 68:
        return {
            "stage_num": 3,
            "stage": "🟢 Normal Market (Stg 3)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "Normal SIP Only (0% Lumpsum) 🟡",
            "short_action": "Normal SIP Only 🟡"
        }
    else:
        return {
            "stage_num": 2,
            "stage": "🚀 Bull Run (Stg 2)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "Normal SIP Only (Loan Prepay) 🔴",
            "short_action": "Normal SIP Only (Prepay Loan) 🏦"
        }

# ============================================================
# MAIN EXECUTION WITH SCHEDULE FILTER
# ============================================================

if __name__ == "__main__":
    try:
        print("Fetching real-time market data...")

        nifty50 = get_index_data("^NSEI")
        nifty100 = get_index_data("^CNX100")
        midcap150 = get_index_data("NIFTYMIDCAP150.NS")
        smallcap250 = get_index_data("NIFTYSMLCAP250.NS")

        pe_data = get_category_pe_ratios()
        india_vix = get_india_vix()

        large_symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
        mid_symbols = ["FEDERALBNK.NS", "VOLTAS.NS", "POLYCAB.NS"]
        small_symbols = ["CDSL.NS", "ANGELONE.NS", "KEI.NS"]

        large_breadth = calculate_breadth(large_symbols)
        mid_breadth = calculate_breadth(mid_symbols)
        small_breadth = calculate_breadth(small_symbols)

        large_score = god_score(nifty100["close"], nifty100["dma50"], nifty100["dma200"], nifty100["weekly_rsi"], nifty100["monthly_rsi"], nifty100["drawdown"], india_vix, large_breadth["pct200"])
        mid_score = god_score(midcap150["close"], midcap150["dma50"], midcap150["dma200"], midcap150["weekly_rsi"], midcap150["monthly_rsi"], midcap150["drawdown"], india_vix, mid_breadth["pct200"])
        small_score = god_score(smallcap250["close"], smallcap250["dma50"], smallcap250["dma200"], smallcap250["weekly_rsi"], smallcap250["monthly_rsi"], smallcap250["drawdown"], india_vix, small_breadth["pct200"])

        overall_score = round(large_score * 0.55 + mid_score * 0.28 + small_score * 0.17, 1)

        large_stage = get_category_stage(nifty100["drawdown"], nifty100["weekly_rsi"], pe_data["large_pe"], india_vix)
        mid_stage = get_category_stage(midcap150["drawdown"], midcap150["weekly_rsi"], pe_data["mid_pe"], india_vix)
        small_stage = get_category_stage(smallcap250["drawdown"], smallcap250["weekly_rsi"], pe_data["small_pe"], india_vix)

        # TRIGGER SCHEDULE FILTER: STAGE 1 OR STAGES 4, 5, 6, 7, 8
        target_stages = [1, 4, 5, 6, 7, 8]
        action_needed = any([
            large_stage["stage_num"] in target_stages,
            mid_stage["stage_num"] in target_stages,
            small_stage["stage_num"] in target_stages
        ])

        if not action_needed:
            print("Market in Normal/Bull Zone (Stage 2 or 3). Notification skipped.")
        else:
            print("Actionable condition met (Stage 1 or Stage 4-8). Dispatching Telegram alert...")

            large_pe_status = get_pe_status("large", pe_data["large_pe"])
            mid_pe_status = get_pe_status("mid", pe_data["mid_pe"])
            small_pe_status = get_pe_status("small", pe_data["small_pe"])

            message = f"""🚨 ACTION ALERT: AI WEALTH MANAGER
{pe_data['date']}
─────────────────────
🌡️ MARKET METRICS
• Score: {overall_score}/100 ({score_status(overall_score)})
• Nifty PE (Live): {pe_data['large_pe']:.2f} | VIX: {india_vix:.2f}
• Nifty 50: {nifty50['close']} ({nifty50['change']}%)
• Monthly RSI: {nifty50['monthly_rsi']}

─────────────────────
📊 LARGE CAP: NIFTY 100
• Stage: {large_stage['stage']}
• SIP Status: {large_stage['sip_status']}
• Action: {large_stage['lumpsum_pct']}
• Live PE: {pe_data['large_pe']:.2f} ({large_pe_status})
• Price: {nifty100['close']} (-{nifty100['drawdown']}%)
• Weekly RSI: {nifty100['weekly_rsi']:.2f} | Monthly RSI: {nifty100['monthly_rsi']:.2f}
• DMA Trend: {nifty100['trend']}

📊 MID CAP:NIFTY MIDCAP150
• Stage: {mid_stage['stage']}
• SIP Status: {mid_stage['sip_status']}
• Action: {mid_stage['lumpsum_pct']}
• Live PE: {mid_pe_status} ({pe_data['mid_pe']:.2f})
• Price: {midcap150['close']} (-{midcap150['drawdown']}%)
• Weekly RSI: {midcap150['weekly_rsi']:.2f} | Monthly RSI: {midcap150['monthly_rsi']:.2f}
• DMA Trend: {midcap150['trend']}

📊 SMALL CAP:NIFTY SMALLCAP250
• Stage: {small_stage['stage']}
• SIP Status: {small_stage['sip_status']}
• Action: {small_stage['lumpsum_pct']}
• Live PE: {pe_data['small_pe']:.2f} ({small_pe_status})
• Price: {smallcap250['close']} (-{smallcap250['drawdown']}%)
• Weekly RSI: {smallcap250['weekly_rsi']:.2f} | Monthly RSI: {smallcap250['monthly_rsi']:.2f}
• DMA Trend: {smallcap250['trend']}

─────────────────────
💡 SUMMARY ACTION
• Large: {large_stage['short_action']}
• Mid: {mid_stage['short_action']}
• Small: {small_stage['short_action']}

─────────────────────
📖 8-STAGE QUICK GUIDE

1. 🔥 Extreme High (All-Time Peak)
   └ 🔴 Stop SIP | Book Small Profit -> Prepay Loan
2. 🚀 Bull Run (High Zone)
   └ 🔴 Normal SIP | Prepay Loan
3. 🟢 Normal Market (Fair Price)
   └ 🟡 Normal SIP Only (0% Lumpsum)
4. 📊 Small Discount (2-3% Dip)
   └ 🟢 SIP + 10% Extra
5. 🟡 Good Discount (5% Dip)
   └ 🟢 SIP + 25% Extra
6. ⚠️ Big Discount (10% Drop - Buy)
   └ 🟢 SIP + 50% Extra
7. 📉 Heavy Discount (15%+ - Mega Buy)
   └ 🟢 SIP + 75% Extra
8. 🛑 Market Crash (25%+ - JackPot Buy)
   └ 🚀 SIP + Max Lumpsum Buy

─────────────────────
📌 IMPORTANT NOTES & RULES

• NOTE: Extra Lumpsum% (10% to 100%) in Stages 4-8 applies strictly to your allocated Monthly Extra Lumpsum Capital Buffer.
• RSI (<30 Cheap | >70 High)
• DMA (50<200 Discount 🟢 | 50>200 High 🔴)
• Drawdown (% Drop from 52W High)

📊 PE RATIO GUIDE:
• Large Cap: <19 Cheap | >24 High
• Mid Cap:   <24 Cheap | >32 High
• Small Cap: <20 Cheap | >28 High
"""
            send_telegram(message)

    except Exception as e:
        print(f"Error executing AI Wealth Manager: {e}")
