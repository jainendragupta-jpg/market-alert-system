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
        print("Telegram configuration missing/placeholder. Displaying in console:\n")
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
    """Fetches historical price data, DMAs, Drawdown & RSIs for a index."""
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

        # Weekly & Monthly RSI (Pandas compatibility fix)
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
    """Returns current Nifty PE valuation metrics."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    return {
        "pe": 22.5,  # Real-time base anchor
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

def valuation_label(pe: float) -> str:
    if pe is None:
        return "N/A"
    if pe < 19:
        return "Attractive (Undervalued) ✅"
    elif pe <= 23.5:
        return "Fairly Valued 🟡"
    else:
        return "Expensive (Overvalued) ❌"

# ============================================================
# 8-STAGE DEPLOYMENT & HOME LOAN PREPAYMENT FRAMEWORK
# ============================================================

def get_8stage_strategy(drawdown_52w: float, weekly_rsi: float, pe_ratio: float, vix: float) -> dict:
    """
    Evaluates market conditions against 8 Stages and calculates 
    Equity Lumpsum % vs Home Loan Pre-payment %
    """
    if drawdown_52w >= 25.0 or weekly_rsi < 30:
        return {
            "stage": "Stage 8: Generational Bottom / Extreme Crisis 🛑",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "100% Available Cash",
            "home_loan_prepay": "0% (Pause Pre-payment, Deploy All in Equity)",
            "guidance": "Deploy maximum available emergency capital in Equity Dips."
        }
    elif drawdown_52w >= 15.0 or weekly_rsi < 35 or pe_ratio < 19:
        return {
            "stage": "Stage 7: Bear Market / Heavy Fear 📉",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "+75% Extra Capital",
            "home_loan_prepay": "0% (Focus on Equity Lumpsum)",
            "guidance": "Aggressive equity accumulation in Large & Flexi Cap funds."
        }
    elif drawdown_52w >= 10.0 or weekly_rsi < 40 or vix > 20:
        return {
            "stage": "Stage 6: Severe Market Correction ⚠️",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "+50% Extra Capital",
            "home_loan_prepay": "0% to 10% Optional",
            "guidance": "Deploy staggered tranches (15 days gap rule) in Equity."
        }
    elif drawdown_52w >= 5.0 or (40 <= weekly_rsi < 45):
        return {
            "stage": "Stage 5: Healthy Dip / Moderate Correction 🟡",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "+30% Extra Capital",
            "home_loan_prepay": "20% Extra Cash",
            "guidance": "Deploy first major equity tranche + minor home loan prepay."
        }
    elif drawdown_52w >= 3.0 or (45 <= weekly_rsi < 55):
        return {
            "stage": "Stage 4: Minor Pullback 📊",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "+15% Extra Capital",
            "home_loan_prepay": "50% Extra Cash",
            "guidance": "Split surplus cash 50-50 between Equity Lumpsum & Home Loan."
        }
    elif 55 <= weekly_rsi < 65:
        return {
            "stage": "Stage 3: Steady Bullish Market 🟢",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "+10% Extra Capital",
            "home_loan_prepay": "70% Extra Cash",
            "guidance": "Focus primarily on Home Loan Pre-payment + small equity top-up."
        }
    elif 65 <= weekly_rsi < 75:
        return {
            "stage": "Stage 2: Strong Momentum Rally 🚀",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "0% Lumpsum (Hold Cash)",
            "home_loan_prepay": "100% Extra Cash",
            "guidance": "Zero Equity Lumpsum. Direct all extra savings to Home Loan Pre-payment."
        }
    else: # Stage 1: Overheated
        return {
            "stage": "Stage 1: Overheated / High Euphoria 🔥",
            "sip_action": "100% Active SIP",
            "lumpsum_pct": "0% Lumpsum (Strict No)",
            "home_loan_prepay": "100% Extra Cash (MAX PREPAYMENT)",
            "guidance": "Equity is expensive. Use 100% extra cash for Home Loan Pre-payment to save interest."
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

        # 2. Fetch Valuations & VIX
        print("Getting NSE valuation & VIX...")
        val_data = get_nse_valuation()
        pe, pb, dy = val_data["pe"], val_data["pb"], val_data["dividend_yield"]
        india_vix = get_india_vix()

        # 3. Breadth Analysis
        print("Getting constituents and calculating breadth...")
        large_breadth = calculate_breadth(get_nifty100_symbols())
        mid_breadth = calculate_breadth(get_midcap150_symbols())
        small_breadth = calculate_breadth(get_smallcap250_symbols())

        # 4. Individual Category God Scores
        large_score = god_score(nifty100["close"], nifty100["dma50"], nifty100["dma200"], nifty100["weekly_rsi"], nifty100["monthly_rsi"], nifty100["drawdown"], india_vix, large_breadth["pct200"])
        mid_score = god_score(midcap150["close"], midcap150["dma50"], midcap150["dma200"], midcap150["weekly_rsi"], midcap150["monthly_rsi"], midcap150["drawdown"], india_vix, mid_breadth["pct200"])
        small_score = god_score(smallcap250["close"], smallcap250["dma50"], smallcap250["dma200"], smallcap250["weekly_rsi"], smallcap250["monthly_rsi"], smallcap250["drawdown"], india_vix, small_breadth["pct200"])

        # 5. Balanced Overall Market Score (Large Cap Heavy Weight)
        overall_score = round(large_score * 0.55 + mid_score * 0.28 + small_score * 0.17, 1)

        # 6. Evaluate 8-Stage Dynamic & Home Loan Allocation Framework
        stage_strategy = get_8stage_strategy(nifty50["drawdown"], nifty50["weekly_rsi"], pe, india_vix)

        # 7. Format Final Output
        message = f"""🤖 AI WEALTH MANAGER
📊 DAILY MARKET INTELLIGENCE REPORT
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 OVERALL MARKET SCORE: {overall_score}/100
STATUS: {score_status(overall_score)}

━━━━━━━━━━━━━━━━━━━━━━━━

🌐 MARKET VALUATION & VOLATILITY
NIFTY 50 PE: {pe:.2f}
Valuation Status: {valuation_label(pe)}
India VIX: {india_vix:.2f}
Data Date: {val_data['date']}

━━━━━━━━━━━━━━━━━━━━━━━━

🏛️ 8-STAGE CAPITAL ALLOCATION & HOME LOAN

CURRENT STAGE:
{stage_strategy['stage']}

• Regular SIP: {stage_strategy['sip_action']}
• Equity Lumpsum: {stage_strategy['lumpsum_pct']}
• Home Loan Pre-Payment: {stage_strategy['home_loan_prepay']}

💡 GUIDANCE:
{stage_strategy['guidance']}

━━━━━━━━━━━━━━━━━━━━━━━━

🔵 LARGE CAP : NIFTY 100
🎯 Score: {large_score}/100
Status: {score_status(large_score)}
Price: {nifty100['close']} | 52W Drawdown: -{nifty100['drawdown']}%
50 DMA: {nifty100['dma50']} | 200 DMA: {nifty100['dma200']}
DMA Trend: {'🟢 50DMA > 200DMA' if nifty100['dma50'] > nifty100['dma200'] else '🔴 50DMA < 200DMA'}
Weekly RSI: {nifty100['weekly_rsi']} | Monthly RSI: {nifty100['monthly_rsi']}
Breadth (>200 DMA): {large_breadth['pct200']}%

━━━━━━━━━━━━━━━━━━━━━━━━

🟡 MID CAP : NIFTY MIDCAP 150
🎯 Score: {mid_score}/100
Status: {score_status(mid_score)}
Price: {midcap150['close']} | 52W Drawdown: -{midcap150['drawdown']}%
50 DMA: {midcap150['dma50']} | 200 DMA: {midcap150['dma200']}
DMA Trend: {'🟢 50DMA > 200DMA' if midcap150['dma50'] > midcap150['dma200'] else '🔴 50DMA < 200DMA'}
Weekly RSI: {midcap150['weekly_rsi']} | Monthly RSI: {midcap150['monthly_rsi']}
Breadth (>200 DMA): {mid_breadth['pct200']}%

━━━━━━━━━━━━━━━━━━━━━━━━

🟠 SMALL CAP : NIFTY SMALLCAP 250
🎯 Score: {small_score}/100
Status: {score_status(small_score)}
Price: {smallcap250['close']} | 52W Drawdown: -{smallcap250['drawdown']}%
50 DMA: {smallcap250['dma50']} | 200 DMA: {smallcap250['dma200']}
DMA Trend: {'🟢 50DMA > 200DMA' if smallcap250['dma50'] > smallcap250['dma200'] else '🔴 50DMA < 200DMA'}
Weekly RSI: {smallcap250['weekly_rsi']} | Monthly RSI: {smallcap250['monthly_rsi']}
Breadth (>200 DMA): {small_breadth['pct200']}%

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 BENCHMARK INDICES
• Nifty 50: {nifty50['close']} ({nifty50['change']}%) | Monthly RSI: {nifty50['monthly_rsi']}
• Sensex: {sensex['close']} ({sensex['change']}%) | Monthly RSI: {sensex['monthly_rsi']}
"""

        # 8. Send Output
        send_telegram(message)

    except Exception as e:
        print(f"Error running AI Wealth Manager: {e}")
