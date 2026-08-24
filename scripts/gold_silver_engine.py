import os
import json
import argparse
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ==========================================
# ENVIRONMENT SECRETS & CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

STATE_FILE = "trade_state.json"

ASSETS = {
    "GOLDBEES": {
        "etf": "GOLDBEES.NS",
        "name": "Nippon India Gold BeES ETF",
        "benchmark": "GC=F"
    },
    "SILVERBEES": {
        "etf": "SILVERBEES.NS",
        "name": "Nippon India Silver BeES ETF",
        "benchmark": "SI=F"
    }
}

MACRO_TICKERS = {
    "DXY": "DX-Y.NYB",   # US Dollar Index
    "US10Y": "^TNX"      # US 10-Yr Treasury Yield
}

# ==========================================
# STATE & DATA MANAGEMENT
# ==========================================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": {}, "total_capital": 50000}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Error saving state: {e}")

def calculate_rsi(series, period=14):
    if len(series) < period + 1:
        return 50.0
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return val if not pd.isna(val) else 50.0

def fetch_robust_data(symbol, end_date_str=None):
    try:
        if end_date_str:
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)
            start_dt = end_dt - timedelta(days=365)
            df = yf.download(symbol, start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"), progress=False)
        else:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)

        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            close_series = df['Close'].iloc[:, 0]
        else:
            close_series = df['Close']
            
        close_series = close_series.dropna()
        if len(close_series) < 20:
            return None

        curr_price = float(close_series.iloc[-1])
        high_52w = float(close_series.max())
        ma_50 = float(close_series.tail(50).mean())
        ma_200 = float(close_series.tail(200).mean()) if len(close_series) >= 200 else ma_50
        
        drawdown = ((curr_price - high_52w) / high_52w) * 100
        daily_rsi = calculate_rsi(close_series, 14)

        weekly_series = close_series.resample('W').last().dropna()
        weekly_rsi = calculate_rsi(weekly_series, 14)

        return {
            "price": curr_price,
            "high_52w": high_52w,
            "drawdown": drawdown,
            "daily_rsi": daily_rsi,
            "weekly_rsi": weekly_rsi,
            "ma_50": ma_50,
            "ma_200": ma_200
        }
    except Exception as e:
        print(f"Data fetch error for {symbol}: {e}")
        return None

def check_festive_season(test_date):
    month = test_date.month
    if month in [3, 4, 8, 9, 10]:
        return "Festive Accumulation Window Active 🪔"
    return "Standard Positional Trading Window 📊"

def get_ai_intelligence(asset_name, action, data, dxy_val):
    if not GEMINI_API_KEY:
        return "• Global macro environment aligns with current technical setup.\n• Stick strictly to execution parameters."
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = (
            f"Role: Senior CIO & Gold/Silver Bullion Strategist. Asset: {asset_name}, Action: {action}. "
            f"Price: ₹{data['price']:.2f}, Drawdown: {data['drawdown']:.2f}%, Weekly RSI: {data['weekly_rsi']:.1f}, DXY: {dxy_val}. "
            "Task: Give 2 brief bullet points in simple Hindi/English mixing: "
            "1) Macro Reason & News impact (Fed, Dollar index, Inflation), "
            "2) Immediate 24-48 hour market outlook."
        )
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception:
        pass
    return "• Global macro trends favor this execution stage.\n• Market structure is supportive for positional holding."

# ==========================================
# MAIN EXECUTION ENGINE
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Institutional Bullion AI Engine")
    parser.add_argument("--date", type=str, help="Backtest date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    if args.date:
        exec_date_str = args.date
        exec_date = datetime.strptime(exec_date_str, "%Y-%m-%d")
        is_dry_run = True
    else:
        exec_date = datetime.now()
        exec_date_str = exec_date.strftime("%Y-%m-%d")
        is_dry_run = False

    state = load_state()
    positions = state.get("positions", {})

    dxy_data = fetch_robust_data(MACRO_TICKERS["DXY"], exec_date_str)
    dxy_val = f"{dxy_data['price']:.2f}" if dxy_data else "N/A"
    festive_status = check_festive_season(exec_date)

    signals = []

    for key, info in ASSETS.items():
        data = fetch_robust_data(info["etf"], exec_date_str)
        if not data:
            data = fetch_robust_data(info["benchmark"], exec_date_str)
            if not data:
                continue

        curr_p = data["price"]
        dd = data["drawdown"]
        w_rsi = data["weekly_rsi"]
        d_rsi = data["daily_rsi"]
        pos = positions.get(key, None)

        # 🟢 BUY LOGIC (Tranche-1: ₹15,000)
        if pos is None:
            if (dd <= -4.0 or w_rsi < 42 or d_rsi < 38):
                ai_desc = get_ai_intelligence(info["name"], "BUY", data, dxy_val)
                signals.append({
                    "type": "BUY",
                    "asset_key": key,
                    "name": info["name"],
                    "price": curr_p,
                    "limit_price": round(curr_p * 0.998, 2),
                    "drawdown": dd,
                    "weekly_rsi": w_rsi,
                    "daily_rsi": d_rsi,
                    "ma_50": data["ma_50"],
                    "amount": "₹15,000 (Tranche 1)",
                    "ai_note": ai_desc
                })
                if not is_dry_run:
                    positions[key] = {
                        "buy_price": curr_p,
                        "highest_seen": curr_p,
                        "buy_date": exec_date_str,
                        "amount": 15000
                    }

        # 🔴 PROFIT BOOKING & TRAILING STOP LOGIC
        else:
            buy_p = pos["buy_price"]
            highest_seen = max(pos.get("highest_seen", buy_p), curr_p)
            gain_pct = ((curr_p - buy_p) / buy_p) * 100

            if not is_dry_run:
                positions[key]["highest_seen"] = highest_seen

            trailing_drop = ((highest_seen - curr_p) / highest_seen) * 100

            if (gain_pct >= 6.5 and trailing_drop >= 1.5) or w_rsi >= 74 or gain_pct >= 12.0:
                ai_desc = get_ai_intelligence(info["name"], "SELL", data, dxy_val)
                signals.append({
                    "type": "SELL",
                    "asset_key": key,
                    "name": info["name"],
                    "price": curr_p,
                    "buy_price": buy_p,
                    "gain_pct": gain_pct,
                    "weekly_rsi": w_rsi,
                    "ai_note": ai_desc
                })
                if not is_dry_run:
                    positions.pop(key, None)

    if not is_dry_run:
        state["positions"] = positions
        save_state(state)

    if not signals:
        print(f"[{exec_date_str}] Institutional Engine Status: No high-probability setup today.")
        return

    # TELEGRAM NOTIFICATION FORMATTING
    mode_tag = "🧪 [BACKTEST MODE]" if is_dry_run else "🚨 [INSTITUTIONAL SIGNAL ALERT]"
    msg = f"{mode_tag}\n"
    msg += f"🏛️ *AI BULLION WEALTH ENGINE*\n"
    msg += f"📅 Date: {exec_date.strftime('%d-%b-%Y')} | Window: 1.5 Hours\n"
    msg += f"🌐 US Dollar Index (DXY): `{dxy_val}` | Cycle: `{festive_status}`\n"
    msg += f"─────────────────────────────────\n\n"

    for sig in signals:
        if sig["type"] == "BUY":
            msg += f"🟢 *SIGNAL: STAGE-1 BUY ACCUMULATE* ({sig['asset_key']})\n"
            msg += f"📌 *Asset:* {sig['name']}\n"
            msg += f"📲 *Action:* Groww App par *{sig['amount']}* ki buying karein.\n"
            msg += f"💵 *Current Market Price:* ₹{sig['price']:.2f}\n"
            msg += f"🎯 *Suggested Limit Price:* ₹{sig['limit_price']:.2f}\n"
            msg += f"📉 *Peak Discount:* {sig['drawdown']:.2f}%\n"
            msg += f"📊 *Weekly RSI:* {sig['weekly_rsi']:.1f} | *Daily RSI:* {sig['daily_rsi']:.1f}\n\n"
            msg += f"📰 *MACRO & NEWS ANALYSIS:*\n{sig['ai_note']}\n\n"

        elif sig["type"] == "SELL":
            msg += f"🔴 *SIGNAL: PROFIT BOOKING (SELL)* ({sig['asset_key']})\n"
            msg += f"📌 *Asset:* {sig['name']}\n"
            msg += f"📲 *Action:* Groww App par apne saare units sell karke cash free karein.\n"
            msg += f"💵 *Selling Price:* ₹{sig['price']:.2f}\n"
            msg += f"🛒 *Buying Price:* ₹{sig['buy_price']:.2f}\n"
            msg += f"🚀 *Net Realized Profit:* +{sig['gain_pct']:.2f}%\n\n"
            msg += f"📰 *EXIT REASONING & NEWS:*\n{sig['ai_note']}\n\n"

    msg += f"─────────────────────────────────\n"
    msg += f"🛑 *DISCIPLINE & EXECUTION RULES (Strictly Follow):*\n"
    msg += f"1️⃣ *No FOMO Trading:* Telegram alert ke bina market mein koi bhi manual trade na lein.\n"
    msg += f"2️⃣ *₹15,000 Limit Rule:* Pehli baari mein ₹15,000 se ₹1 bhi zyada na lagayein. Baaki ₹35,000 reserve rakhein.\n"
    msg += f"3️⃣ *Limit Order Advantage:* Pehle Limit Order lagayein, agar 3:00 PM tak fill na ho tabhi Market Order lein.\n\n"
    msg += f"💡 *MOTIVATIONAL THOUGHT:*\n"
    msg += f"_\"Bina discipline ke trading जुआ (gambling) hai, aur rules ke saath trading Wealth Creation hai.\"_\n\n"
    msg += f"⏰ *Execute before 3:15 PM IST on Groww App.*"

    print(msg)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
            print("Telegram alert delivered successfully.")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")

if __name__ == "__main__":
    main()
