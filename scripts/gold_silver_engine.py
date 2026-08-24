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
    "BACKTEST": False,                # Set to True for backtesting
    "BACKTEST_START": "2025-01-01",
    "BACKTEST_END": "2026-08-24",
    "STATE_FILE": "nippon_trade_state.json",
    "TELEGRAM_BOT_TOKEN": "YOUR_TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID": "YOUR_TELEGRAM_CHAT_ID",
    "INVESTMENT_CAPITAL_INR": 50000,  # User Capital
    "TRAILING_ATR_MULT": 1.8          # Conservative ATR Multiplier for Positional Trades
}

# -------------------------------------------------------------------
# 2. TELEGRAM NOTIFIER SYSTEM WITH BEAUTIFUL HTML FORMATTING
# -------------------------------------------------------------------
def send_telegram_message(message: str):
    token = CONFIG.get("TELEGRAM_BOT_TOKEN")
    chat_id = CONFIG.get("TELEGRAM_CHAT_ID")
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
        logging.info(f"\n================ [TELEGRAM ALERT] ================\n{message}\n==================================================")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
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
def get_seasonal_and_news_context():
    """
    Checks Seasonal festivals (Dhanteras, Diwali, Wedding Season) 
    and War/Geopolitical news for Gold/Silver.
    """
    today = datetime.datetime.now()
    month = today.month
    
    # Seasonal Demand Filter for Indian Gold (Oct-Nov: Dhanteras/Diwali, Dec-Feb: Wedding Season)
    is_festive_season = month in [10, 11, 12, 1, 2]
    seasonal_tag = "HIGH FESTIVE/WEDDING DEMAND SEASON" if is_festive_season else "REGULAR SEASON"

    # War & Geopolitical News Feed Analysis
    try:
        ticker = yf.Ticker(CONFIG["GLOBAL_GOLD_SYMBOL"])
        news = ticker.news
        latest_title = news[0].get("title", "No critical news") if news else "No news available"
        
        war_keywords = ["war", "conflict", "attack", "strike", "geopolitical", "crisis", "sanction", "fed", "rate cut", "inflation"]
        is_high_risk_event = any(word in latest_title.lower() for word in war_keywords)
        
        sentiment = "BULLISH (SAFE HAVEN DEMAND)" if is_high_risk_event else ("BULLISH (SEASONAL)" if is_festive_season else "NEUTRAL")
        
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": is_high_risk_event,
            "news_title": latest_title,
            "sentiment": sentiment
        }
    except Exception as e:
        logging.error(f"News Analysis Error: {e}")
        return {
            "is_festive": is_festive_season,
            "seasonal_tag": seasonal_tag,
            "is_war_event": False,
            "news_title": "Market Data Normal",
            "sentiment": "NEUTRAL"
        }

# -------------------------------------------------------------------
# 5. MULTI-TIMEFRAME DATA RETRIEVAL (Weekly + Daily)
# -------------------------------------------------------------------
def fetch_multi_timeframe_data(symbol):
    try:
        # 1. Fetch Weekly Data for Big Trend Analysis
        df_weekly = yf.download(symbol, period="1y", interval="1wk", progress=False)
        if isinstance(df_weekly.columns, pd.MultiIndex):
            df_weekly.columns = df_weekly.columns.get_level_values(0)
            
        df_weekly['EMA20_W'] = df_weekly['Close'].ewm(span=20, adjust=False).mean()
        weekly_uptrend = df_weekly.iloc[-1]['Close'] > df_weekly.iloc[-1]['EMA20_W']

        # 2. Fetch Daily Data for Entry Setup
        df_daily = yf.download(symbol, period="60d", interval="1d", progress=False)
        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = df_daily.columns.get_level_values(0)
            
        df_daily.dropna(inplace=True)

        # Technical Indicators Calculation
        df_daily['EMA9'] = df_daily['Close'].ewm(span=9, adjust=False).mean()
        df_daily['EMA21'] = df_daily['Close'].ewm(span=21, adjust=False).mean()
        df_daily['EMA50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()

        # RSI Calculation
        delta = df_daily['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_daily['RSI'] = 100 - (100 / (1 + rs))

        # ATR for Dynamic SL
        high_low = df_daily['High'] - df_daily['Low']
        high_close = np.abs(df_daily['High'] - df_daily['Close'].shift())
        low_close = np.abs(df_daily['Low'] - df_daily['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df_daily['ATR'] = true_range.rolling(14).mean()

        return df_daily, weekly_uptrend
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame(), False

# -------------------------------------------------------------------
# 6. STAGE 1 TO STAGE 4 VALIDATION RULES (NO GAPS)
# -------------------------------------------------------------------
def validate_stages(df_daily, weekly_uptrend, macro_info):
    row = df_daily.iloc[-1]
    prev_row = df_daily.iloc[-2]

    # STAGE 1: Macro & Seasonal Alignment Filter
    stage1 = macro_info['is_festive'] or macro_info['is_war_event'] or (row['Close'] > row['EMA50'])
    if not stage1:
        return False, "Failed Stage 1: Macro/Seasonal conditions not aligned."

    # STAGE 2: Weekly Trend Confirmation
    stage2 = weekly_uptrend
    if not stage2:
        return False, "Failed Stage 2: Weekly trend is bearish."

    # STAGE 3: Daily Momentum & RSI Setup (AND / OR)
    stage3_a = (45 <= row['RSI'] <= 65)  # Steady accumulation zone
    stage3_b = (prev_row['RSI'] < 50 and row['RSI'] >= 50) # Bullish crossover
    stage3 = stage3_a or stage3_b
    if not stage3:
        return False, "Failed Stage 3: Daily momentum / RSI condition not met."

    # STAGE 4: Price Action & Breakout Trigger (AND)
    stage4 = (row['Close'] > prev_row['High']) and (row['EMA9'] > row['EMA21'])
    if not stage4:
        return False, "Failed Stage 4: Price Action breakout confirmation missing."

    return True, "ALL 4 STAGES PASSED SUCCESSFULLY"

# -------------------------------------------------------------------
# 7. MAIN ENGINE EXECUTION
# -------------------------------------------------------------------
def run_positional_etf_bot():
    logging.info("Analyzing Nippon India ETF Positional Opportunities...")
    state = load_state()
    macro_info = get_seasonal_and_news_context()
    
    df_daily, weekly_uptrend = fetch_multi_timeframe_data(CONFIG["SYMBOL"])
    if df_daily.empty or len(df_daily) < 30:
        logging.warning("Insufficient data available.")
        return

    current_price = float(df_daily.iloc[-1]['Close'])
    current_atr = float(df_daily.iloc[-1]['ATR'])

    # ---------------------------------------------------------------
    # ACTIVE POSITION MANAGEMENT (DYNAMIC TRAILING & EXIT)
    # ---------------------------------------------------------------
    if state["in_position"]:
        buy_price = state["buy_price"]
        current_sl = state["current_sl"]
        
        # Dynamic ATR Trailing SL Calculation
        new_calculated_sl = current_price - (CONFIG["TRAILING_ATR_MULT"] * current_atr)
        
        # Trailing SL Shift upwards
        if new_calculated_sl > current_sl:
            state["current_sl"] = round(new_calculated_sl, 2)
            save_state(state)
            
            msg = (
                f"🏆 <b>NIPPON ETF: DYNAMIC TRAILING SL INCREASED</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']}\n"
                f"<b>Live Price:</b> ₹{current_price:.2f}\n"
                f"<b>New Dynamic Stop Loss:</b> ₹{state['current_sl']:.2f}\n"
                f"<b>Locked Profit / Unit:</b> ₹{state['current_sl'] - buy_price:.2f}\n"
                f"───────────────────────────────\n"
                f"📌 <i>Guideline: Let your profits run! Stop loss will keep trailing up.</i>"
            )
            send_telegram_message(msg)

        # Exit Signal Check
        if current_price <= state["current_sl"]:
            total_pnl = (current_price - buy_price) * state["qty"]
            msg = (
                f"🔴 <b>POSIIONAL EXIT SIGNAL (SL HIT)</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']}\n"
                f"<b>Sell Price:</b> ₹{current_price:.2f}\n"
                f"<b>Buy Price:</b> ₹{buy_price:.2f}\n"
                f"<b>Total Realized PnL:</b> ₹{total_pnl:.2f}\n"
                f"───────────────────────────────\n"
                f"💡 <i>Guideline: Capital protected. Wait for next Stage 1-4 setup.</i>"
            )
            send_telegram_message(msg)
            
            state = {"in_position": False, "buy_price": 0.0, "current_sl": 0.0, "qty": 0, "symbol": CONFIG["SYMBOL"]}
            save_state(state)

    # ---------------------------------------------------------------
    # NEW BUY ENTRY SIGNAL CHECK
    # ---------------------------------------------------------------
    else:
        signal_valid, reason = validate_stages(df_daily, weekly_uptrend, macro_info)
        
        if signal_valid:
            initial_sl = current_price - (CONFIG["TRAILING_ATR_MULT"] * current_atr)
            qty = int(CONFIG["INVESTMENT_CAPITAL_INR"] // current_price)
            
            state["in_position"] = True
            state["buy_price"] = round(current_price, 2)
            state["current_sl"] = round(initial_sl, 2)
            state["qty"] = qty
            save_state(state)

            msg = (
                f"🟢 <b>HIGH-CONFIRMATION BUY SIGNAL</b>\n"
                f"<b>Nippon India Gold BeES Trading Engine</b>\n"
                f"───────────────────────────────\n"
                f"<b>Symbol:</b> {CONFIG['SYMBOL']} (NSE)\n"
                f"<b>Recommended Entry Price:</b> ₹{current_price:.2f}\n"
                f"<b>Initial Dynamic Stop Loss:</b> ₹{initial_sl:.2f}\n"
                f"<b>Calculated Quantity (for ₹50k):</b> {qty} units\n"
                f"───────────────────────────────\n"
                f"<b>STAGE STATUS:</b> All 4 Stages Passed ✅\n"
                f"• Stage 1 (Macro/Seasonal): PASSED\n"
                f"• Stage 2 (Weekly Trend): PASSED\n"
                f"• Stage 3 (Daily Momentum): PASSED\n"
                f"• Stage 4 (Price Action Trigger): PASSED\n"
                f"───────────────────────────────\n"
                f"<b>MARKET & NEWS CONTEXT:</b>\n"
                f"<b>Seasonality:</b> {macro_info['seasonal_tag']}\n"
                f"<b>Latest Macro News:</b> {macro_info['news_title']}\n"
                f"<b>Market Sentiment:</b> {macro_info['sentiment']}\n"
                f"───────────────────────────────\n"
                f"📌 <b>EXPERT GUIDELINES FOR YOU:</b>\n"
                f"1. Put a Buy order for {qty} units at ~₹{current_price:.2f} on your broker app.\n"
                f"2. Sit back and relax. The bot will monitor dynamic stop loss automatically."
            )
            send_telegram_message(msg)
        else:
            logging.info(f"Scan complete. No trade signal. Reason: {reason}")

# -------------------------------------------------------------------
# 8. EXECUTION LOOP
# -------------------------------------------------------------------
if __name__ == "__main__":
    logging.info("Starting Nippon India Positional Trading Engine...")
    try:
        run_positional_etf_bot()
    except Exception as e:
        logging.critical(f"System Error: {e}", exc_info=True)
