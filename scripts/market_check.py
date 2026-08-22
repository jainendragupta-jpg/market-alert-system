import os
import re
import argparse
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

def send_telegram(message: str, is_test_mode: bool = False) -> None:
    """Sends formatted plain-text alert to Telegram with fail-safe error handling."""
    if is_test_mode:
        print("\n=== [TEST MODE OUTPUT: TELEGRAM SKIPPED] ===")
        print(message)
        print("===========================================\n")
        return

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
# SAFE MARKET & INDEX DATA FETCHING ENGINE
# ============================================================

def get_index_data(ticker_symbol: str, target_date: str = None) -> dict:
    """Fetches historical price data, DMA trends, RSI, and Drawdowns."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="2y")
        
        if df.empty or len(df) < 50:
            raise ValueError(f"Insufficient historical price data for {ticker_symbol}")

        if target_date:
            df = df.loc[:target_date]
            if df.empty:
                raise ValueError(f"No data available up to target date: {target_date}")

        close_series = df['Close'].dropna()
        
        latest_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else latest_close
        
        daily_change = round(((latest_close - prev_close) / prev_close) * 100, 2) if prev_close > 0 else 0.0

        dma50 = float(close_series.rolling(window=min(50, len(close_series))).mean().iloc[-1])
        dma200 = float(close_series.rolling(window=min(200, len(close_series))).mean().iloc[-1])

        high_52w = float(df['High'].iloc[-252:].max()) if len(df) >= 252 else float(df['High'].max())
        drawdown = round(((high_52w - latest_close) / high_52w) * 100, 2) if high_52w > 0 else 0.0

        weekly_df = close_series.resample('W').last().dropna()
        try:
            monthly_df = close_series.resample('ME').last().dropna()
        except Exception:
            monthly_df = close_series.resample('M').last().dropna()

        def compute_rsi(series: pd.Series, period: int = 14) -> float:
            if len(series) < period:
                return 50.0
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            valid_rsi = rsi_series.dropna()
            return float(valid_rsi.iloc[-1]) if not valid_rsi.empty else 50.0

        weekly_rsi = round(compute_rsi(weekly_df), 2)
        monthly_rsi = round(compute_rsi(monthly_df), 2)

        trend_status = "BEARISH_DISCOUNT" if close_series.iloc[-1] < dma50 else "BULLISH_STRENGTH"

        return {
            "close": round(latest_close, 2),
            "change": daily_change,
            "dma50": round(dma50, 2),
            "dma200": round(dma200, 2),
            "drawdown": drawdown,
            "weekly_rsi": weekly_rsi,
            "monthly_rsi": monthly_rsi,
            "trend_status": trend_status,
            "is_below_200dma": latest_close < dma200
        }
    except Exception as e:
        print(f"Warning: Fallback applied for {ticker_symbol} due to: {e}")
        return {
            "close": 0.0, "change": 0.0, "dma50": 0.0, "dma200": 0.0,
            "drawdown": 0.0, "weekly_rsi": 50.0, "monthly_rsi": 50.0,
            "trend_status": "NEUTRAL", "is_below_200dma": False
        }

def get_screener_index_pe(index_slug: str, fallback_pe: float) -> float:
    url = f"https://www.screener.in/company/{index_slug}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            match = re.search(r'Stock P/E.*?>\s*([\d\.]+)\s*<', res.text, re.DOTALL | re.IGNORECASE)
            if match:
                return float(match.group(1))
    except Exception as e:
        print(f"Failed fetching Screener PE for {index_slug}, fallback used: {e}")
    return fallback_pe

def get_category_pe_ratios(override_date: str = None) -> dict:
    today_str = override_date if override_date else datetime.now().strftime("%d-%b-%Y")
    return {
        "large_pe": get_screener_index_pe("Nifty+100", 20.3),
        "mid_pe": get_screener_index_pe("Nifty+Midcap+150", 29.5),
        "small_pe": get_screener_index_pe("Nifty+Smallcap+250", 27.8),
        "date": today_str
    }

def get_india_vix() -> float:
    try:
        vix = yf.Ticker("^INDIAVIX")
        df = vix.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception:
        pass
    return 15.0

# ============================================================
# INSTITUTIONAL MULTI-FACTOR STAGE DECISION MATRIX
# ============================================================

def get_category_stage(drawdown_52w: float, weekly_rsi: float, pe_ratio: float, vix: float, is_below_200dma: bool) -> dict:
    """
    Evaluates 8 Stages using Strict Multi-Factor Confluence:
    Primary Anchor: Drawdown
    Secondary Modifiers: RSI, PE, VIX, 200 DMA Position
    """
    # STAGE 8: Panic Market Crash (30%+ Drop OR 25%+ Drop with Extreme Fear/Crash RSI)
    if drawdown_52w >= 30.0 or (drawdown_52w >= 25.0 and weekly_rsi < 28.0 and vix > 25.0):
        return {
            "stage_num": 8,
            "stage": "🛑 Market Crash (Stg 8)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + Max Lumpsum Buy 🚀",
            "short_action": "SIP + Max Lumpsum Buy 🚀"
        }
    
    # STAGE 7: Heavy Discount (22%+ Drop AND (RSI < 32 OR Deep Value PE OR Below 200DMA))
    elif drawdown_52w >= 22.0 and (weekly_rsi < 35.0 or pe_ratio < 18.0 or is_below_200dma):
        return {
            "stage_num": 7,
            "stage": "📉 Heavy Discount (Stg 7)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 75% Extra Lumpsum 🟢",
            "short_action": "SIP + 75% Extra Lumpsum 🟢"
        }
    
    # STAGE 6: Big Discount (15%+ Drop AND (RSI < 40 OR VIX > 22))
    elif drawdown_52w >= 15.0 and (weekly_rsi < 42.0 or vix > 20.0):
        return {
            "stage_num": 6,
            "stage": "⚠️ Big Discount (Stg 6)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 50% Extra Lumpsum 🟢",
            "short_action": "SIP + 50% Extra Lumpsum 🟢"
        }
    
    # STAGE 5: Good Discount (10%+ Drop AND (RSI < 45 OR Reasonable PE))
    elif drawdown_52w >= 10.0 and (weekly_rsi < 48.0 or pe_ratio < 22.0):
        return {
            "stage_num": 5,
            "stage": "🟡 Good Discount (Stg 5)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "SIP + 25% Extra Lumpsum 🟢",
            "short_action": "SIP + 25% Extra Lumpsum 🟢"
        }
    
    # STAGE 4: Small Discount (6.0% to 9.99% Drop) -> NO LUMPSUM, PREPAY LOAN
    elif 6.0 <= drawdown_52w < 10.0:
        return {
            "stage_num": 4,
            "stage": "📊 Small Discount (Stg 4)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "Normal SIP Only (0% Lumpsum - Prepay Loan 🏦)",
            "short_action": "Normal SIP Only (Prepay Loan) 🏦"
        }
    
    # STAGE 1: Peak Market Overbought (Near Peak AND High RSI)
    elif drawdown_52w < 1.5 and weekly_rsi >= 70.0:
        return {
            "stage_num": 1,
            "stage": "🔥 Extreme High (Stg 1)",
            "sip_status": "Stop This Month 🔴",
            "lumpsum_pct": "Book Small Profit 💰 & Prepay Loan 🏦",
            "short_action": "Book Profit 💰 -> Prepay Loan 🏦"
        }
    
    # STAGE 2: Strong Bull Trend (Low Drop < 3.0% AND Strong RSI)
    elif drawdown_52w < 3.0 and weekly_rsi >= 60.0:
        return {
            "stage_num": 2,
            "stage": "🚀 Bull Run (Stg 2)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "Normal SIP Only (Prepay Loan 🏦)",
            "short_action": "Normal SIP Only (Prepay Loan) 🏦"
        }
    
    # STAGE 3: Normal Market (Safety Catch-All Block)
    else:
        return {
            "stage_num": 3,
            "stage": "🟢 Normal Market (Stg 3)",
            "sip_status": "Active 🟢",
            "lumpsum_pct": "Normal SIP Only (0% Lumpsum) 🟡",
            "short_action": "Normal SIP Only 🟡"
        }

# ============================================================
# MAIN EXECUTION CONTROLLER
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Institutional Wealth Manager")
    parser.add_argument("--date", type=str, default=None, help="Back-date test YYYY-MM-DD")
    parser.add_argument("--test", action="store_true", help="Dry run mode")
    args = parser.parse_args()

    is_test_mode = args.test or (args.date is not None)
    target_date = args.date

    try:
        nifty50 = get_index_data("^NSEI", target_date)
        nifty100 = get_index_data("^CNX100", target_date)
        midcap150 = get_index_data("NIFTYMIDCAP150.NS", target_date)
        smallcap250 = get_index_data("NIFTYSMLCAP250.NS", target_date)

        pe_data = get_category_pe_ratios(target_date)
        vix_val = get_india_vix()

        large_stage = get_category_stage(nifty100["drawdown"], nifty100["weekly_rsi"], pe_data["large_pe"], vix_val, nifty100["is_below_200dma"])
        mid_stage = get_category_stage(midcap150["drawdown"], midcap150["weekly_rsi"], pe_data["mid_pe"], vix_val, midcap150["is_below_200dma"])
        small_stage = get_category_stage(smallcap250["drawdown"], smallcap250["weekly_rsi"], pe_data["small_pe"], vix_val, smallcap250["is_below_200dma"])

        # Alert triggers ON ONLY for Stage 1 (Peak) and Stages 5, 6, 7, 8 (Discounts)
        target_alert_stages = [1, 5, 6, 7, 8]

        large_alert = large_stage["stage_num"] in target_alert_stages
        mid_alert = mid_stage["stage_num"] in target_alert_stages
        small_alert = small_stage["stage_num"] in target_alert_stages

        if not (large_alert or mid_alert or small_alert) and not is_test_mode:
            print("Market is in Stage 2, 3, or 4. Automation execution finished silently.")
        else:
            msg = [
                "🚨 ACTION ALERT: INSTITUTIONAL WEALTH ENGINE",
                f"Date: {pe_data['date']}",
                "──────────────────────────",
                f"• Nifty 50: {nifty50['close']} ({nifty50['change']}%)",
                f"• India VIX: {vix_val} | Nifty PE: {pe_data['large_pe']:.2f}",
                "──────────────────────────\n"
            ]

            if large_alert or is_test_mode:
                msg.append(f"🏛️ LARGE CAP: {large_stage['stage']}\n Action: {large_stage['lumpsum_pct']}\n Drop: -{nifty100['drawdown']}% | RSI: {nifty100['weekly_rsi']}\n")
            if mid_alert or is_test_mode:
                msg.append(f"📈 MID CAP: {mid_stage['stage']}\n Action: {mid_stage['lumpsum_pct']}\n Drop: -{midcap150['drawdown']}% | RSI: {midcap150['weekly_rsi']}\n")
            if small_alert or is_test_mode:
                msg.append(f"🚀 SMALL CAP: {small_stage['stage']}\n Action: {small_stage['lumpsum_pct']}\n Drop: -{smallcap250['drawdown']}% | RSI: {smallcap250['weekly_rsi']}\n")

            send_telegram("\n".join(msg), is_test_mode)

    except Exception as e:
        print(f"Engine Execution Error: {e}")
