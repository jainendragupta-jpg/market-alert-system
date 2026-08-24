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
# 1. SYSTEM LOGGING & ENVIRONMENT INPUTS (GitHub Actions Ready)
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("nippon_etf_expert.log"),
        logging.StreamHandler()
    ]
)

# Parse inputs directly from GitHub Workflow parameters or environment
BACKTEST_ENV = os.getenv("INPUT_BACKTEST", "false").lower() == "true"
START_DATE_ENV = os.getenv("INPUT_START_DATE", "2025-01-01")
END_DATE_ENV = os.getenv("INPUT_END_DATE", datetime.datetime.now().strftime("%Y-%m-%d"))

CONFIG = {
    "SYMBOL": "GOLDBEES.NS",          # Nippon India ETF Gold BeES
    "SILVER_SYMBOL": "SILVERBEES.NS", # Nippon India ETF Silver BeES
    "GLOBAL_GOLD_SYMBOL": "GC=F",      # US Comex Gold Futures (Macro Analysis)
    "US_DXY_SYMBOL": "DX-Y.NYB",       # US Dollar Index (US Data Analysis)
    
    "BACKTEST": BACKTEST_ENV,
    "BACKTEST_START": START_DATE_ENV,
    "BACKTEST_END": END_DATE_ENV,
    
    "STATE_FILE": "nippon_trade_state.json",
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    "INVESTMENT_CAPITAL_INR": 50000,
    "TRAILING_ATR_MULT": 1.8
}

# -------------------------------------------------------------------
# 2. BEAUTIFUL HTML TELEGRAM NOTIFIER
# -------------------------------------------------------------------
def send_telegram_message(message: str):
    token = CONFIG.get("TELEGRAM_BOT_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token:
        logging.info(f"\n================ [TELEGRAM ALERT] ================\n{message}\n==================================================")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logging.error(f"Telegram Notification Error: {e}")

# -------------------------------------------------------------------
# 3. STATE PERSISTENCE
# -------------------------------------------------------------------
def load_state():
    if os.path.exists(CONFIG["STATE_FILE"]):
        try:
            with open(CONFIG["STATE_FILE"], "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading state: {e}")
    return {"in_position": False, "buy_price": 0.0, "current_sl": 0.0, "qty": 0, "symbol": CONFIG["SYMBOL"]}

def save_state(state: dict):
    try:
        with open(CONFIG["STATE_FILE"], "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving state: {e}")

# -------------------------------------------------------------------
# 4. US DATA, FESTIVALS & MACRO WAR NEWS ANALYZER
# -------------------------------------------------------------------
def get_macro_seasonal_us_context(eval_date=None):
    today = eval_date if eval_date else datetime.datetime.now()
    month = today.month
    
    is_festive_season = month in [10, 11, 12, 1, 2]
    seasonal_tag = "🪔 HIGH FESTIVE / WEDDING DEMAND SEASON" if is_festive_season else "📆 REGULAR DEMAND SEASON"

    # News Sentiment
    try:
        ticker = yf.Ticker(CONFIG["GLOBAL_GOLD_SYMBOL"])
        news = ticker.news
        latest_title = news[0].get("title", "Market Data Normal") if (news and len(news) > 0) else "Market Data Normal"
        
        war_keywords = ["war", "conflict", "attack", "strike", "geopolitical", "crisis", "sanction", "fed", "rate", "inflation", "cpi", "jobs"]
        is_high_risk_event = any(word in str(latest_title).lower() for word in war_keywords)
        sentiment = "🚀 BULLISH (SAFE-HAVEN & MACRO DEMAND)" if is_high_risk_event else ("🟢 BULLISH (SEASONAL)" if is_festive_season else "⚪ NEUTRAL")
        
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": is_high_risk_event,
            "news_title": latest_title,
            "sentiment": sentiment
        }
    except Exception as e:
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": False,
            "news_title": "Market Data Normal (Fallback Active)",
            "sentiment": "⚪ NEUTRAL"
        }

# -------------------------------------------------------------------
# 5. ROBUST MULTI-TIMEFRAME DATA & HOLIDAY TOLERANCE ENGINE
# -------------------------------------------------------------------
def calculate_indicators(df_daily, df_weekly):
    if isinstance(df_weekly.columns, pd.MultiIndex):
        df_weekly.columns = df_weekly.columns.get_level_values(0)
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.get_level_values(0)

    # Forward-fill and backward-fill to protect against holidays / missing weekends
    df_daily = df_daily.ffill().bfill().dropna().copy()
    df_weekly = df_weekly.ffill().bfill().dropna().copy()

    df_weekly['EMA20_W'] = df_weekly['Close'].ewm(span=20, adjust=False).mean()

    df_daily['EMA9'] = df_daily['Close'].ewm(span=9, adjust=False).mean()
    df_daily['EMA21'] = df_daily['Close'].ewm(span=21, adjust=False).mean()
    df_daily['EMA50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()

    delta = df_daily['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_daily['RSI'] = 100 - (100 / (1 + rs))

    high_low = df_daily['High'] - df_daily['Low']
    high_close = np.abs(df_daily['High'] - df_daily['Close'].shift())
    low_close = np.abs(df_daily['Low'] - df_daily['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df_daily['ATR'] = true_range.rolling(14).mean()

    return df_daily, df_weekly

# -------------------------------------------------------------------
# 6. STAGE 1 TO STAGE 4 VALIDATION RULES
# -------------------------------------------------------------------
def validate_stages(row, prev_row, weekly_uptrend, macro_info):
    stage1 = macro_info['is_festive'] or macro_info['is_war_event'] or (row['Close'] > row['EMA50'])
    if not stage1:
        return False, "Failed Stage 1: Macro/Seasonal conditions not aligned."

    if not weekly_uptrend:
        return False, "Failed Stage 2: Weekly trend is bearish."

    stage3_a = (45 <= row['RSI'] <= 65)  
    stage3_b = (prev_row['RSI'] < 50 and row['RSI'] >= 50) 
    if not (stage3_a or stage3_b):
        return False, "Failed Stage 3: Daily momentum / RSI condition not met."

    if not ((row['Close'] > prev_row['High']) and (row['EMA9'] > row['EMA21'])):
        return False, "Failed Stage 4: Price Action breakout confirmation missing."

    return True, "ALL 4 STAGES PASSED SUCCESSFULLY"

# -------------------------------------------------------------------
# 7. BACKTEST ENGINE (Historical Analysis Loop)
# -------------------------------------------------------------------
def run_backtest():
    logging.info(f"=== RUNNING BACKTEST: {CONFIG['BACKTEST_START']} to {CONFIG['BACKTEST_END']} ===")
    
    # Pad start date by 60 days to ensure EMA/RSI are calculated even for holidays/weekends
    padded_start = (datetime.datetime.strptime(CONFIG["BACKTEST_START"], "%Y-%m-%d") - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    
    df_daily = yf.download(CONFIG["SYMBOL"], start=padded_start, end=CONFIG["BACKTEST_END"], interval="1d", progress=False)
    df_weekly = yf.download(CONFIG["SYMBOL"], start=padded_start, end=CONFIG["BACKTEST_END"], interval="1wk", progress=False)

    df_daily, df_weekly = calculate_indicators(df_daily, df_weekly)

    in_pos = False
    buy_price = 0.0
    sl = 0.0
    qty = 0
    trades = []

    for i in range(30, len(df_daily)):
        curr_dt = df_daily.index[i]
        
        # Skip dates prior to user's selected backtest start date
        if str(curr_dt.date()) < CONFIG["BACKTEST_START"]:
            continue
            
        row = df_daily.iloc[i]
        prev_row = df_daily.iloc[i-1]

        weekly_slice = df_weekly.loc[df_weekly.index <= curr_dt]
        weekly_uptrend = bool(weekly_slice.iloc[-1]['Close'] > weekly_slice.iloc[-1]['EMA20_W']) if not weekly_slice.empty else False

        macro_info = get_macro_seasonal_us_context(curr_dt)
        curr_price = float(row['Close'])
        curr_atr = float(row['ATR'])

        if in_pos:
            new_sl = curr_price - (CONFIG["TRAILING_ATR_MULT"] * curr_atr)
            if new_sl > sl:
                sl = new_sl

            if curr_price <= sl:
                pnl = (curr_price - buy_price) * qty
                trades.append({"Action": "🔴 EXIT", "Date": str(curr_dt.date()), "Price": round(curr_price,2), "PnL_INR": round(pnl,2)})
                in_pos = False
        else:
            valid, _ = validate_stages(row, prev_row, weekly_uptrend, macro_info)
            if valid:
                buy_price = curr_price
                sl = curr_price - (CONFIG["TRAILING_ATR_MULT"] * curr_atr)
                qty = int(CONFIG["INVESTMENT_CAPITAL_INR"] // buy_price)
                in_pos = True
                trades.append({"Action": "🟢 BUY", "Date": str(curr_dt.date()), "Price": round(buy_price,2), "SL": round(sl,2), "Qty": qty})

    logging.info(f"BACKTEST RESULTS SUMMARY ({len(trades)} Events Triggered):")
    for t in trades:
        print(t)

# -------------------------------------------------------------------
# 8. LIVE ENGINE SCANNER & NOTIFIER
# -------------------------------------------------------------------
def run_live_scan():
    logging.info("Starting Live Scan for Positional ETF Opportunities...")
    state = load_state()
    macro_info = get_macro_seasonal_us_context()
    
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
            send_telegram_message(
                f"🏆 <b>NIPPON ETF: DYNAMIC TRAILING SL RAISED</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']}\n"
                f"<b>Live Price:</b> ₹{current_price:.2f}\n"
                f"<b>New Dynamic SL:</b> ₹{state['current_sl']:.2f}\n"
                f"<b>Locked Profit / Unit:</b> ₹{state['current_sl'] - buy_price:.2f}"
            )

        if current_price <= state["current_sl"]:
            total_pnl = (current_price - buy_price) * state["qty"]
            send_telegram_message(
                f"🔴 <b>POSITIONAL EXIT SIGNAL</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']}\n"
                f"<b>Sell Price:</b> ₹{current_price:.2f}\n"
                f"<b>Buy Price:</b> ₹{buy_price:.2f}\n"
                f"<b>Total Realized Profit/Loss:</b> ₹{total_pnl:.2f}"
            )
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
                f"<b>Recommended Entry:</b> ₹{current_price:.2f}\n"
                f"<b>Initial Dynamic SL:</b> ₹{initial_sl:.2f}\n"
                f"<b>Qty (for ₹50k):</b> {qty} units\n"
                f"───────────────────────────────\n"
                f"<b>STAGE STATUS:</b>\n"
                f"• Stage 1 (Macro/Seasonal Filter): PASSED ✅\n"
                f"• Stage 2 (Weekly Trend Confirmation): PASSED ✅\n"
                f"• Stage 3 (Daily Momentum/RSI): PASSED ✅\n"
                f"• Stage 4 (Price Action Breakout Trigger): PASSED ✅\n"
                f"───────────────────────────────\n"
                f"📰 <b>MARKET & US DATA NEWS CONTEXT:</b>\n"
                f"• <b>Season:</b> {macro_info['seasonal_tag']}\n"
                f"• <b>US/War Headline:</b> {macro_info['news_title']}\n"
                f"• <b>Sentiment:</b> {macro_info['sentiment']}\n"
                f"───────────────────────────────\n"
                f"📌 <b>EXPERT STAGES & SYSTEM GUIDELINES:</b>\n"
                f"<b>Stage 1:</b> Global War, US Inflation & Seasonal Demand Check.\n"
                f"<b>Stage 2:</b> Weekly Multi-timeframe trend must be Bullish.\n"
                f"<b>Stage 3:</b> RSI Range (45-65) ensures buying low before rally.\n"
                f"<b>Stage 4:</b> Daily candle breakout confirmation.\n"
                f"💡 <i>Action: Place Buy order for {qty} units. The bot will automatically manage Dynamic Trailing SL!</i>"
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
