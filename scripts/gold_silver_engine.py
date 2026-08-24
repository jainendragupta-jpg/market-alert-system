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
# 1. LOGGING & SYSTEM SETUP
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Single Date Input via GitHub UI or Default Live Date
INPUT_SINGLE_DATE = os.getenv("INPUT_TEST_DATE", datetime.datetime.now().strftime("%Y-%m-%d"))

CONFIG = {
    "GOLD_SYMBOL": "GOLDBEES.NS",     # Real NSE Price in INR (Nippon Gold ETF)
    "SILVER_SYMBOL": "SILVERBEES.NS", # Real NSE Price in INR (Nippon Silver ETF)
    "GLOBAL_GOLD": "GC=F",            # Global Comex Gold Sentiment
    "STATE_FILE": "nippon_trade_state.json",
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    "CAPITAL_INR": 50000,
    "TRAILING_ATR_MULT": 2.0          # 2.0 Dynamic Trailing SL for 10-20% Gains
}

# -------------------------------------------------------------------
# 2. BEAUTIFUL FAIL-SAFE TELEGRAM NOTIFIER
# -------------------------------------------------------------------
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
        logging.error(f"Telegram Alert Delivery Error: {e}")

# -------------------------------------------------------------------
# 3. PERSISTENT STATE MANAGEMENT (Saves Open Trades & Dynamic SL)
# -------------------------------------------------------------------
def load_state():
    if os.path.exists(CONFIG["STATE_FILE"]):
        try:
            with open(CONFIG["STATE_FILE"], "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"State load error: {e}")
    return {"GOLDBEES.NS": {"in_pos": False, "buy_price": 0.0, "sl": 0.0, "qty": 0},
            "SILVERBEES.NS": {"in_pos": False, "buy_price": 0.0, "sl": 0.0, "qty": 0}}

def save_state(state):
    try:
        with open(CONFIG["STATE_FILE"], "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"State save error: {e}")

# -------------------------------------------------------------------
# 4. MACRO, GEOPOLITICAL WAR & FESTIVE SEASON ENGINE
# -------------------------------------------------------------------
def fetch_macro_context(eval_date):
    month = eval_date.month
    is_festive = month in [10, 11, 12, 1, 2]
    seasonal_tag = "🪔 HIGH DEMAND FESTIVE/WEDDING SEASON" if is_festive else "📆 REGULAR DEMAND SEASON"
    headline = "Technical Indicators Driving Trade Logic"
    sentiment = "🟢 BULLISH (SEASONAL)" if is_festive else "⚪ NEUTRAL"
    is_macro = False

    try:
        ticker = yf.Ticker(CONFIG["GLOBAL_GOLD"])
        news = ticker.news
        if news and len(news) > 0:
            headline = news[0].get("title", headline)
            keywords = ["war", "conflict", "attack", "strike", "fed", "rate cut", "cpi", "inflation", "jobs"]
            is_macro = any(w in str(headline).lower() for w in keywords)
            if is_macro:
                sentiment = "🚀 HIGHLY BULLISH (SAFE-HAVEN & FED ACTION)"
    except Exception as e:
        logging.warning(f"News API Fallback Active: {e}")

    return {"is_festive": is_festive, "seasonal_tag": seasonal_tag, "is_macro": is_macro, "news": headline, "sentiment": sentiment}

# -------------------------------------------------------------------
# 5. TECHNICAL INDICATORS & HOLIDAY TOLERANCE ENGINE
# -------------------------------------------------------------------
def compute_indicators(df_daily, df_weekly):
    if isinstance(df_weekly.columns, pd.MultiIndex): df_weekly.columns = df_weekly.columns.get_level_values(0)
    if isinstance(df_daily.columns, pd.MultiIndex): df_daily.columns = df_daily.columns.get_level_values(0)

    df_daily = df_daily.ffill().bfill().dropna().copy()
    df_weekly = df_weekly.ffill().bfill().dropna().copy()

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

    return df_daily, df_weekly

# -------------------------------------------------------------------
# 6. CORE PROCESSING ENGINE FOR GOLD AND SILVER
# -------------------------------------------------------------------
def process_etf(asset_name, ticker_symbol, input_date_str, allocation_inr):
    try:
        target_dt = datetime.datetime.strptime(input_date_str, "%Y-%m-%d")
    except ValueError:
        logging.error("Date format error. Use YYYY-MM-DD.")
        return

    pad_start = (target_dt - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    pad_end = (target_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")

    df_daily = yf.download(ticker_symbol, start=pad_start, end=pad_end, interval="1d", progress=False)
    df_weekly = yf.download(ticker_symbol, start=pad_start, end=pad_end, interval="1wk", progress=False)

    if df_daily.empty or df_weekly.empty:
        return

    df_daily, df_weekly = compute_indicators(df_daily, df_weekly)

    valid_daily = df_daily.loc[df_daily.index <= input_date_str]
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
    calculated_sl = price - (CONFIG["TRAILING_ATR_MULT"] * atr)
    target_price = price * 1.15
    qty = int(allocation_inr // price)

    state = load_state()
    asset_state = state.get(ticker_symbol, {"in_pos": False, "buy_price": 0.0, "sl": 0.0, "qty": 0})

    # STAGE VALIDATIONS
    s1 = macro['is_festive'] or macro['is_macro'] or (row['Close'] > row['EMA50'])
    s2 = weekly_uptrend
    s3 = ((45 <= row['RSI'] <= 68) or (prev_row['RSI'] < 50 and row['RSI'] >= 50)) and (row['MACD'] > row['Signal'])
    s4 = (row['Close'] > prev_row['High']) and (row['EMA9'] > row['EMA21']) and (row['Volume'] >= 0.80 * row['Vol_SMA20'])

    is_buy_signal = s1 and s2 and s3 and s4

    # POSITION SL TRAILING & EXIT MANAGEMENT
    if asset_state["in_pos"]:
        if calculated_sl > asset_state["sl"]:
            asset_state["sl"] = round(calculated_sl, 2)
            state[ticker_symbol] = asset_state
            save_state(state)
            send_telegram_alert(
                f"🏆 <b>DYNAMIC SL TRAILED HIGHER</b>\n"
                f"Asset: {asset_name}\nPrice: ₹{price:.2f}\nNew Dynamic SL: ₹{asset_state['sl']:.2f}"
            )

        if price <= asset_state["sl"]:
            pnl = (price - asset_state["buy_price"]) * asset_state["qty"]
            send_telegram_alert(
                f"🔴 <b>EXIT SIGNAL TRIGGERED</b>\n"
                f"Asset: {asset_name}\nSell Price: ₹{price:.2f}\nBuy Price: ₹{asset_state['buy_price']:.2f}\nTotal Profit/Loss: ₹{pnl:.2f}"
            )
            state[ticker_symbol] = {"in_pos": False, "buy_price": 0.0, "sl": 0.0, "qty": 0}
            save_state(state)
            return

    # NEW ENTRY SIGNAL GENERATION
    if is_buy_signal and not asset_state["in_pos"]:
        asset_state.update({"in_pos": True, "buy_price": round(price, 2), "sl": round(calculated_sl, 2), "qty": qty})
        state[ticker_symbol] = asset_state
        save_state(state)

        status_str = "🟢 HIGH-CONFIRMATION BUY SIGNAL"
    else:
        status_str = "🟢 POSITION ACTIVE (HOLDING)" if asset_state["in_pos"] else "🔴 NO BUY SIGNAL (HOLD / WAIT)"

    msg = (
        f"📊 <b>NIPPON ETF INSTITUTIONAL REPORT</b>\n"
        f"<b>Asset:</b> {asset_name} ({ticker_symbol})\n"
        f"<b>Evaluated Date:</b> {str(eval_dt.date())}\n"
        f"───────────────────────────────\n"
        f"<b>STATUS:</b> {status_str}\n"
        f"<b>Exact NSE Live Close:</b> ₹{price:.2f}\n"
        f"<b>Dynamic Trailing SL (ATR 2.0x):</b> ₹{calculated_sl:.2f}\n"
        f"<b>15% Profit Projection:</b> ₹{target_price:.2f}\n"
        f"<b>Allocated Capital:</b> ₹{allocation_inr:,.0f} ({qty} Units)\n"
        f"───────────────────────────────\n"
        f"📐 <b>STAGE CHECK STATUS:</b>\n"
        f"• Stage 1 (Macro/Festive): {'PASSED ✅' if s1 else 'FAILED ❌'}\n"
        f"• Stage 2 (Weekly Trend): {'PASSED ✅' if s2 else 'FAILED ❌'}\n"
        f"• Stage 3 (RSI/MACD Momentum): {'PASSED ✅' if s3 else 'FAILED ❌'}\n"
        f"• Stage 4 (Price Action Breakout): {'PASSED ✅' if s4 else 'FAILED ❌'}\n"
        f"───────────────────────────────\n"
        f"📰 <b>LIVE NEWS & MARKET CONTEXT:</b>\n"
        f"• Season: {macro['seasonal_tag']}\n"
        f"• Headline: {macro['news']}\n"
        f"• Sentiment: {macro['sentiment']}\n"
        f"───────────────────────────────\n"
        f"🧠 <b>SYSTEM DISCIPLINE NOTE:</b>\n"
        f"1. केवल 4 Stages PASS होने पर ही एंट्री लें।\n"
        f"2. Dynamic SL को स्वचालित रूप से ट्रेल होने दें और बड़े लाभ (12%-20%) के लिए ट्रेड को होल्ड रखें।"
    )
    send_telegram_alert(msg)

if __name__ == "__main__":
    # Splitting Capital 50-50 for Gold and Silver ETFs
    process_etf("Nippon India Gold BeES", CONFIG["GOLD_SYMBOL"], INPUT_SINGLE_DATE, CONFIG["CAPITAL_INR"] * 0.5)
    process_etf("Nippon India Silver BeES", CONFIG["SILVER_SYMBOL"], INPUT_SINGLE_DATE, CONFIG["CAPITAL_INR"] * 0.5)
