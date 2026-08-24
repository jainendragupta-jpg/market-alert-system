import os
import sys
import json
import logging
import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import requests

# -------------------------------------------------------------------
# SYSTEM & ENVIRONMENT SETUP
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
INPUT_SINGLE_DATE = os.getenv("INPUT_TEST_DATE", datetime.datetime.now().strftime("%Y-%m-%d"))

CONFIG = {
    "GOLD_SYMBOL": "GOLDBEES.NS",     # Exact Nippon India ETF Gold BeES (NSE Price in INR)
    "SILVER_SYMBOL": "SILVERBEES.NS", # Exact Nippon India ETF Silver BeES (NSE Price in INR)
    "GLOBAL_GOLD": "GC=F",            # Global Sentiment Trigger
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    "CAPITAL_INR": 50000,
    "TRAILING_ATR_MULT": 2.0          # Swing Dynamic SL Multiplier
}

def send_telegram_alert(message: str):
    token = CONFIG.get("TELEGRAM_BOT_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token:
        logging.info(f"\n================ [TELEGRAM ALERT] ================\n{message}\n==================================================")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=8)
    except Exception as e:
        logging.error(f"Telegram Delivery Error: {e}")

def fetch_macro_context(eval_date):
    month = eval_date.month
    is_festive = month in [10, 11, 12, 1, 2]
    seasonal_tag = "🪔 HIGH DEMAND FESTIVE/WEDDING SEASON" if is_festive else "📆 REGULAR SEASON"
    headline = "Technical Indicators Driving Analysis"
    sentiment = "🟢 BULLISH (SEASONAL)" if is_festive else "⚪ NEUTRAL"
    is_macro = False

    try:
        ticker = yf.Ticker(CONFIG["GLOBAL_GOLD"])
        news = ticker.news
        if news and len(news) > 0:
            headline = news[0].get("title", headline)
            keywords = ["war", "conflict", "attack", "strike", "fed", "rate cut", "cpi", "inflation"]
            is_macro = any(w in str(headline).lower() for w in keywords)
            if is_macro: sentiment = "🚀 HIGHLY BULLISH (SAFE-HAVEN / FED ACTION)"
    except Exception:
        pass

    return {"is_festive": is_festive, "seasonal_tag": seasonal_tag, "is_macro": is_macro, "news": headline, "sentiment": sentiment}

def process_etf_symbol(symbol_name, ticker_symbol, target_date_str):
    target_dt = datetime.datetime.strptime(target_date_str, "%Y-%m-%d")
    pad_start = (target_dt - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    pad_end = (target_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")

    df_daily = yf.download(ticker_symbol, start=pad_start, end=pad_end, interval="1d", progress=False)
    df_weekly = yf.download(ticker_symbol, start=pad_start, end=pad_end, interval="1wk", progress=False)

    if df_daily.empty or df_weekly.empty:
        return

    if isinstance(df_weekly.columns, pd.MultiIndex): df_weekly.columns = df_weekly.columns.get_level_values(0)
    if isinstance(df_daily.columns, pd.MultiIndex): df_daily.columns = df_daily.columns.get_level_values(0)

    df_daily = df_daily.ffill().bfill().dropna().copy()
    df_weekly = df_weekly.ffill().bfill().dropna().copy()

    # Calculations
    df_weekly['EMA20_W'] = df_weekly['Close'].ewm(span=20, adjust=False).mean()
    df_daily['EMA9'] = df_daily['Close'].ewm(span=9, adjust=False).mean()
    df_daily['EMA21'] = df_daily['Close'].ewm(span=21, adjust=False).mean()
    df_daily['EMA50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()

    delta = df_daily['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df_daily['RSI'] = 100 - (100 / (1 + (gain / loss)))

    exp1 = df_daily['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df_daily['Close'].ewm(span=26, adjust=False).mean()
    df_daily['MACD'] = exp1 - exp2
    df_daily['Signal'] = df_daily['MACD'].ewm(span=9, adjust=False).mean()

    high_low = df_daily['High'] - df_daily['Low']
    high_close = np.abs(df_daily['High'] - df_daily['Close'].shift())
    low_close = np.abs(df_daily['Low'] - df_daily['Close'].shift())
    df_daily['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    df_daily['Vol_SMA20'] = df_daily['Volume'].rolling(20).mean()

    valid_daily = df_daily.loc[df_daily.index <= target_date_str]
    if valid_daily.empty: return

    idx = len(valid_daily) - 1
    eval_dt = valid_daily.index[idx]
    row = valid_daily.iloc[idx]
    prev_row = valid_daily.iloc[idx - 1]

    weekly_slice = df_weekly.loc[df_weekly.index <= eval_dt]
    weekly_uptrend = bool(weekly_slice.iloc[-1]['Close'] > weekly_slice.iloc[-1]['EMA20_W']) if not weekly_slice.empty else False

    macro = fetch_macro_context(eval_dt)
    price = float(row['Close'])
    atr = float(row['ATR'])
    initial_sl = price - (CONFIG["TRAILING_ATR_MULT"] * atr)
    target_price = price * 1.15
    qty = int(CONFIG["CAPITAL_INR"] // price)

    # 4-Stage Strict Verification
    s1 = macro['is_festive'] or macro['is_macro'] or (row['Close'] > row['EMA50'])
    s2 = weekly_uptrend
    s3 = ((45 <= row['RSI'] <= 68) or (prev_row['RSI'] < 50 and row['RSI'] >= 50)) and (row['MACD'] > row['Signal'])
    s4 = (row['Close'] > prev_row['High']) and (row['EMA9'] > row['EMA21']) and (row['Volume'] >= 0.80 * row['Vol_SMA20'])

    is_buy = s1 and s2 and s3 and s4
    status_str = "🟢 HIGH-CONFIRMATION BUY SIGNAL" if is_buy else "🔴 NO BUY SIGNAL (HOLD / WAIT)"

    msg = (
        f"📊 <b>NIPPON ETF INSTITUTIONAL REPORT</b>\n"
        f"<b>Asset:</b> {symbol_name} ({ticker_symbol})\n"
        f"<b>Evaluated Market Date:</b> {str(eval_dt.date())}\n"
        f"───────────────────────────────\n"
        f"<b>STATUS:</b> {status_str}\n"
        f"<b>Exact NSE Live Close:</b> ₹{price:.2f}\n"
        f"<b>Dynamic Trailing SL (ATR):</b> ₹{initial_sl:.2f}\n"
        f"<b>15% Profit Target:</b> ₹{target_price:.2f}\n"
        f"<b>Capital Qty (for ₹50,000):</b> {qty} Units\n"
        f"───────────────────────────────\n"
        f"📐 <b>STAGE CHECK STATUS:</b>\n"
        f"• Stage 1 (Macro/Seasonal): {'PASSED ✅' if s1 else 'FAILED ❌'}\n"
        f"• Stage 2 (Weekly Trend): {'PASSED ✅' if s2 else 'FAILED ❌'}\n"
        f"• Stage 3 (RSI/MACD Momentum): {'PASSED ✅' if s3 else 'FAILED ❌'}\n"
        f"• Stage 4 (Price Action Breakout): {'PASSED ✅' if s4 else 'FAILED ❌'}\n"
        f"───────────────────────────────\n"
        f"📰 <b>HEADLINES & CONTEXT:</b>\n"
        f"• Season: {macro['seasonal_tag']}\n"
        f"• Headline: {macro['news']}\n"
        f"• Sentiment: {macro['sentiment']}\n"
        f"───────────────────────────────\n"
        f"🧠 <b>SYSTEM DISCIPLINE NOTE:</b>\n"
        f"अपनी तरफ से कोई अनुमान न लगाएं। सिस्टम जब 4 Stages Pass करे, तभी ऑर्डर प्लेस करें और Dynamic SL को ट्रेल होने दें।"
    )
    send_telegram_alert(msg)

if __name__ == "__main__":
    process_etf_symbol("Nippon India Gold BeES", CONFIG["GOLD_SYMBOL"], INPUT_SINGLE_DATE)
