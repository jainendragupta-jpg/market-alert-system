import time
import json
import logging
import os
import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import requests

# -------------------------------------------------------------------
# 1. LOGGING & SYSTEM CONFIGURATION
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("nippon_etf_expert.log"),
        logging.StreamHandler()
    ]
)

CONFIG = {
    "SYMBOL": "GOLDBEES.NS",          # Nippon India ETF Gold BeES (NSE)
    "SILVER_SYMBOL": "SILVERBEES.NS", # Nippon India ETF Silver BeES (NSE)
    "GLOBAL_GOLD_SYMBOL": "GC=F",      # Global Gold Futures for War/Macro Analysis
    
    # --- BACKTEST CUSTOM DATES INPUT ---
    "BACKTEST": False,                 # True: Runs historical backtest | False: Live Market Scan
    "BACKTEST_START": "2024-01-01",   # Custom Start Date (YYYY-MM-DD)
    "BACKTEST_END": "2026-08-24",     # Custom End Date (YYYY-MM-DD)
    
    "STATE_FILE": "nippon_trade_state.json",
    "TELEGRAM_BOT_TOKEN": "YOUR_TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID": "YOUR_TELEGRAM_CHAT_ID",
    "INVESTMENT_CAPITAL_INR": 50000,  # User Capital
    "TRAILING_ATR_MULT": 1.8          # Conservative ATR Multiplier for Positional Trades
}

# -------------------------------------------------------------------
# 2. TELEGRAM NOTIFIER SYSTEM
# -------------------------------------------------------------------
def send_telegram_message(message: str):
    token = CONFIG.get("TELEGRAM_BOT_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
        logging.info(f"\n================ [TELEGRAM ALERT] ================\n{message}\n==================================================")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logging.error(f"Telegram Notification Error: {e}")

# -------------------------------------------------------------------
# 3. STATE PERSISTENCE (Saves Buy Price, Qty, Dynamic SL)
# -------------------------------------------------------------------
def load_state():
    if os.path.exists(CONFIG["STATE_FILE"]):
        try:
            with open(CONFIG["STATE_FILE"], "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading state file: {e}")
    return {"in_position": False, "buy_price": 0.0, "current_sl": 0.0, "qty": 0, "symbol": CONFIG["SYMBOL"]}

def save_state(state: dict):
    try:
        with open(CONFIG["STATE_FILE"], "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving state file: {e}")

# -------------------------------------------------------------------
# 4. SEASONAL FESTIVAL & MACRO WAR NEWS ANALYZER
# -------------------------------------------------------------------
def get_seasonal_and_news_context(current_date=None):
    today = current_date if current_date else datetime.datetime.now()
    month = today.month
    
    is_festive_season = month in [10, 11, 12, 1, 2]
    seasonal_tag = "HIGH FESTIVE/WEDDING DEMAND SEASON" if is_festive_season else "REGULAR SEASON"

    try:
        ticker = yf.Ticker(CONFIG["GLOBAL_GOLD_SYMBOL"])
        news = ticker.news
        latest_title = news[0].get("title", "No critical news") if (news and len(news) > 0) else "Market Normal"
        
        war_keywords = ["war", "conflict", "attack", "strike", "geopolitical", "crisis", "sanction", "fed", "rate cut", "inflation"]
        is_high_risk_event = any(word in str(latest_title).lower() for word in war_keywords)
        
        sentiment = "BULLISH (SAFE HAVEN DEMAND)" if is_high_risk_event else ("BULLISH (SEASONAL)" if is_festive_season else "NEUTRAL")
        
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": is_high_risk_event,
            "news_title": latest_title,
            "sentiment": sentiment
        }
    except Exception as e:
        logging.error(f"News Fetch Fallback: {e}")
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": False,
            "news_title": "Technical Indicators Active",
            "sentiment": "NEUTRAL"
        }

# -------------------------------------------------------------------
# 5. TECHNICAL INDICATOR CALCULATION ENGINE
# -------------------------------------------------------------------
def calculate_indicators(df_daily, df_weekly):
    # Fix MultiIndex if present
    if isinstance(df_weekly.columns, pd.MultiIndex):
        df_weekly.columns = df_weekly.columns.get_level_values(0)
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.get_level_values(0)

    df_daily = df_daily.dropna().copy()
    df_weekly = df_weekly.dropna().copy()

    # Weekly Trend Indicator
    df_weekly['EMA20_W'] = df_weekly['Close'].ewm(span=20, adjust=False).mean()

    # Daily Moving Averages
    df_daily['EMA9'] = df_daily['Close'].ewm(span=9, adjust=False).mean()
    df_daily['EMA21'] = df_daily['Close'].ewm(span=21, adjust=False).mean()
    df_daily['EMA50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()

    # RSI Calculation
    delta = df_daily['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_daily['RSI'] = 100 - (100 / (1 + rs))

    # ATR Calculation for Dynamic Trailing SL
    high_low = df_daily['High'] - df_daily['Low']
    high_close = np.abs(df_daily['High'] - df_daily['Close'].shift())
    low_close = np.abs(df_daily['Low'] - df_daily['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df_daily['ATR'] = true_range.rolling(14).mean()

    return df_daily, df_weekly

# -------------------------------------------------------------------
# 6. STAGE 1 TO STAGE 4 VALIDATION RULES (NO GAPS)
# -------------------------------------------------------------------
def validate_stages(row, prev_row, weekly_uptrend, macro_info):
    # STAGE 1: Macro & Seasonal Alignment Filter
    stage1 = macro_info['is_festive'] or macro_info['is_war_event'] or (row['Close'] > row['EMA50'])
    if not stage1:
        return False, "Failed Stage 1: Macro/Seasonal conditions not aligned."

    # STAGE 2: Weekly Trend Confirmation
    if not weekly_uptrend:
        return False, "Failed Stage 2: Weekly trend is bearish."

    # STAGE 3: Daily Momentum & RSI Setup
    stage3_a = (45 <= row['RSI'] <= 65)  
    stage3_b = (prev_row['RSI'] < 50 and row['RSI'] >= 50) 
    if not (stage3_a or stage3_b):
        return False, "Failed Stage 3: Daily momentum / RSI condition not met."

    # STAGE 4: Price Action & Breakout Trigger
    if not ((row['Close'] > prev_row['High']) and (row['EMA9'] > row['EMA21'])):
        return False, "Failed Stage 4: Price Action breakout confirmation missing."

    return True, "ALL 4 STAGES PASSED SUCCESSFULLY"

# -------------------------------------------------------------------
# 7. BACKTEST ENGINE (Laps through every day in range)
# -------------------------------------------------------------------
def run_backtest():
    logging.info(f"=== RUNNING BACKTEST: {CONFIG['BACKTEST_START']} to {CONFIG['BACKTEST_END']} ===")
    df_daily = yf.download(CONFIG["SYMBOL"], start=CONFIG["BACKTEST_START"], end=CONFIG["BACKTEST_END"], interval="1d", progress=False)
    df_weekly = yf.download(CONFIG["SYMBOL"], start=CONFIG["BACKTEST_START"], end=CONFIG["BACKTEST_END"], interval="1wk", progress=False)

    df_daily, df_weekly = calculate_indicators(df_daily, df_weekly)

    in_pos = False
    buy_price = 0.0
    sl = 0.0
    qty = 0
    trades = []

    for i in range(30, len(df_daily)):
        curr_dt = df_daily.index[i]
        row = df_daily.iloc[i]
        prev_row = df_daily.iloc[i-1]

        # Get Weekly Trend for this date
        weekly_slice = df_weekly.loc[df_weekly.index <= curr_dt]
        weekly_uptrend = bool(weekly_slice.iloc[-1]['Close'] > weekly_slice.iloc[-1]['EMA20_W']) if not weekly_slice.empty else False

        macro_info = get_seasonal_and_news_context(curr_dt)
        curr_price = float(row['Close'])
        curr_atr = float(row['ATR'])

        if in_pos:
            new_sl = curr_price - (CONFIG["TRAILING_ATR_MULT"] * curr_atr)
            if new_sl > sl:
                sl = new_sl  # Dynamic Trailing Upwards

            if curr_price <= sl:
                pnl = (curr_price - buy_price) * qty
                trades.append({"Type": "EXIT", "Date": str(curr_dt.date()), "Price": round(curr_price,2), "PnL": round(pnl,2)})
                in_pos = False
        else:
            valid, _ = validate_stages(row, prev_row, weekly_uptrend, macro_info)
            if valid:
                buy_price = curr_price
                sl = curr_price - (CONFIG["TRAILING_ATR_MULT"] * curr_atr)
                qty = int(CONFIG["INVESTMENT_CAPITAL_INR"] // buy_price)
                in_pos = True
                trades.append({"Type": "BUY", "Date": str(curr_dt.date()), "Price": round(buy_price,2), "SL": round(sl,2), "Qty": qty})

    logging.info(f"BACKTEST COMPLETE. Total Signals Generated: {len(trades)}")
    for t in trades:
        print(t)

# -------------------------------------------------------------------
# 8. LIVE ENGINE SCANNER
# -------------------------------------------------------------------
def run_live_scan():
    logging.info("Starting Live Scan for Positional ETF Opportunities...")
    state = load_state()
    macro_info = get_seasonal_and_news_context()
    
    df_daily = yf.download(CONFIG["SYMBOL"], period="1y", interval="1d", progress=False)
    df_weekly = yf.download(CONFIG["SYMBOL"], period="2y", interval="1wk", progress=False)
    
    df_daily, df_weekly = calculate_indicators(df_daily, df_weekly)
    
    row = df_daily.iloc[-1]
    prev_row = df_daily.iloc[-2]
    weekly_uptrend = bool(df_weekly.iloc[-1]['Close'] > df_weekly.iloc[-1]['EMA20_W'])

    current_price = float(row['Close'])
    current_atr = float(row['ATR'])

    if state["in_position"]:
        buy_price = state["buy_price"]
        current_sl = state["current_sl"]
        new_calculated_sl = current_price - (CONFIG["TRAILING_ATR_MULT"] * current_atr)
        
        if new_calculated_sl > current_sl:
            state["current_sl"] = round(new_calculated_sl, 2)
            save_state(state)
            send_telegram_message(f"🏆 <b>NIPPON ETF: DYNAMIC TRAILING SL RAISED</b>\nSymbol: {CONFIG['SYMBOL']}\nLive Price: ₹{current_price:.2f}\nNew Dynamic SL: ₹{state['current_sl']:.2f}")

        if current_price <= state["current_sl"]:
            total_pnl = (current_price - buy_price) * state["qty"]
            send_telegram_message(f"🔴 <b>POSITIONAL EXIT SIGNAL</b>\nSymbol: {CONFIG['SYMBOL']}\nSell: ₹{current_price:.2f}\nPnL: ₹{total_pnl:.2f}")
            state = {"in_position": False, "buy_price": 0.0, "current_sl": 0.0, "qty": 0, "symbol": CONFIG["SYMBOL"]}
            save_state(state)

    else:
        signal_valid, reason = validate_stages(row, prev_row, weekly_uptrend, macro_info)
        if signal_valid:
            initial_sl = current_price - (CONFIG["TRAILING_ATR_MULT"] * current_atr)
            qty = int(CONFIG["INVESTMENT_CAPITAL_INR"] // current_price)
            
            state.update({"in_position": True, "buy_price": round(current_price, 2), "current_sl": round(initial_sl, 2), "qty": qty})
            save_state(state)

            msg = (
                f"🟢 <b>HIGH-CONFIRMATION BUY SIGNAL</b>\n"
                f"<b>Nippon India Gold BeES Positional Engine</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']} (NSE)\n"
                f"<b>Recommended Price:</b> ₹{current_price:.2f}\n"
                f"<b>Dynamic Stop Loss:</b> ₹{initial_sl:.2f}\n"
                f"<b>Qty (for ₹50k):</b> {qty} units\n"
                f"───────────────────────────────\n"
                f"<b>STAGE STATUS:</b> All 4 Stages Passed ✅\n"
                f"<b>News Sentiment:</b> {macro_info['sentiment']}\n"
                f"<b>Latest Macro Event:</b> {macro_info['news_title']}\n"
                f"───────────────────────────────\n"
                f"📌 <b>GUIDELINE:</b> Place Buy order for {qty} units. Bot will manage Dynamic SL."
            )
            send_telegram_message(msg)
        else:
            logging.info(f"Scan complete. No Buy Signal. Reason: {reason}")

# -------------------------------------------------------------------
# 9. EXECUTION ENTRY POINT
# -------------------------------------------------------------------
if __name__ == "__main__":
    if CONFIG["BACKTEST"]:
        run_backtest()
    else:
        run_live_scan()
