import os
import argparse
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

CATEGORIES_TICKERS = {
    "LARGE CAP": ["NIFTYBEES.NS", "^NSEI"],
    "MID CAP": ["MID150BEES.NS", "MIDCAPETF.NS"],
    "SMALL CAP": ["HDFCSML250.NS", "SMLCAPBEES.NS"]
}

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    return 100 - (100 / (1 + rs))

def extract_safe_series(df, col_name='Close'):
    if df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        try:
            series = df[col_name].iloc[:, 0]
        except Exception:
            series = df.xs(col_name, axis=1, level=0).iloc[:, 0]
    else:
        series = df[col_name]
    return series.dropna()

def parse_input_date(date_str):
    if not date_str:
        return datetime.now()
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.now()

def get_market_data(ticker_list, target_dt):
    for ticker in ticker_list:
        try:
            df = yf.download(ticker, period="3y", interval="1d", progress=False)
            close = extract_safe_series(df, 'Close')
            close = close[close.index <= pd.Timestamp(target_dt)]
            if len(close) < 50:
                continue

            current_price = float(close.iloc[-1])
            high_52w = float(close.rolling(window=min(len(close), 252), min_periods=1).max().iloc[-1])
            drawdown = ((current_price - high_52w) / high_52w) * 100

            weekly_close = close.resample('W').last().dropna()
            weekly_rsi = calculate_rsi(weekly_close, 14)
            cur_w_rsi = float(weekly_rsi.iloc[-1]) if not weekly_rsi.empty else 50.0

            return {
                'price': current_price,
                'drawdown': drawdown,
                'weekly_rsi': cur_w_rsi,
                'dma_50': float(close.rolling(50, min_periods=1).mean().iloc[-1]),
                'dma_200': float(close.rolling(200, min_periods=1).mean().iloc[-1])
            }
        except Exception:
            continue
    raise RuntimeError(f"Data fetch failed for {ticker_list}")

def evaluate_stage(data):
    dd = abs(data['drawdown'])
    w_rsi = data['weekly_rsi']

    if dd >= 25 or (dd >= 20 and w_rsi < 30):
        return 8, "🚨 STAGE 8: MARKET CRASH", "🚀 JACKPOT BUY", 100
    elif dd >= 15 or (dd >= 12 and w_rsi < 35):
        return 7, "🟢 STAGE 7: HEAVY DISCOUNT", "🟢 MEGA BUY", 75
    elif dd >= 10 or (dd >= 8 and w_rsi < 40):
        return 6, "🟢 STAGE 6: BIG DISCOUNT", "🟢 BIG BUY", 50
    elif dd >= 5 or (dd >= 4 and w_rsi < 45):
        return 5, "🟡 STAGE 5: GOOD DISCOUNT", "🟢 BUY", 25
    elif dd >= 2.5:
        return 4, "📊 STAGE 4: SMALL DISCOUNT", "🟡 SMALL BUY", 10
    elif w_rsi > 70:
        return 1, "🔴 STAGE 1: EXTREME HIGH", "🔴 STOP LUMPSUM / PREPAY LOAN", 0
    elif w_rsi > 60:
        return 2, "🚀 STAGE 2: BULL RUN", "🟢 NORMAL SIP ONLY", 0
    else:
        return 3, "🟢 STAGE 3: NORMAL MARKET", "🟢 NORMAL SIP ONLY", 0

def generate_and_send_alert():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str)
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    target_dt = parse_input_date(args.date)
    formatted_date_str = target_dt.strftime("%d-%b-%Y")

    cat_data = {k: get_market_data(v, target_dt) for k, v in CATEGORIES_TICKERS.items()}

    try:
        vix_df = yf.download("^INDIAVIX", period="3y", progress=False)
        vix_series = extract_safe_series(vix_df, 'Close')
        vix_series = vix_series[vix_series.index <= pd.Timestamp(target_dt)]
        vix_val = float(vix_series.iloc[-1]) if not vix_series.empty else 15.0
    except Exception:
        vix_val = 15.0

    # Calculate max stage across categories
    stages = [evaluate_stage(cat_data[k])[0] for k in cat_data]

    # TRIGGER RULE: Stage 2 aur Stage 3 par message SUPPRESS hoga (Baki sab par aayega)
    should_send_telegram = any(s in [1, 4, 5, 6, 7, 8] for s in stages) or (vix_val >= 22.0)

    if not should_send_telegram and not args.test:
        print(f"[{formatted_date_str}] Market in Stage 2/3 (Normal/Bull). Message suppressed for zero noise.")
        return

    # Message Construction
    weighted_dd = sum([abs(cat_data[k]['drawdown']) for k in cat_data]) / 3
    weighted_rsi = sum([cat_data[k]['weekly_rsi'] for k in cat_data]) / 3
    score = max(0, min(100, (weighted_rsi * 0.6) + (vix_val * 0.4) - (weighted_dd * 1.8)))

    msg = f"🚨 AI WEALTH MANAGER REPORT\n{formatted_date_str}\n"
    msg += f"──────────────────────\n"
    msg += f"🌡️ MARKET METRICS\n"
    msg += f"• Score: {score:.1f}/100\n"
    msg += f"• India VIX: {vix_val:.2f}\n"
    msg += f"• Avg Market Drop: -{weighted_dd:.1f}%\n\n"
    msg += f"──────────────────────\n"
    msg += f"🏛️ CATEGORY ACTION MATRIX\n\n"

    stage_weights = {}
    for cat_name in CATEGORIES_TICKERS.keys():
        data = cat_data[cat_name]
        s_num, s_title, s_action, l_weight = evaluate_stage(data)
        stage_weights[cat_name] = l_weight

        msg += f"🎯 {cat_name}\n"
        msg += f"• Stage: {s_title}\n"
        msg += f"• Action: {s_action}\n"
        msg += f"• Dip: {data['drawdown']:.1f}% | RSI: {data['weekly_rsi']:.1f}\n\n"

    # Allocation Plan
    total_w = sum(stage_weights.values())
    msg += f"──────────────────────\n"
    msg += f"💡 LUMPSUM CAPITAL ALLOCATION\n"
    if total_w > 0:
        for k, v in stage_weights.items():
            alloc_pct = round((v / total_w) * 100)
            msg += f"• {k.split()[0].capitalize()}: {alloc_pct}%\n"
    else:
        msg += "• 0% Lumpsum Equity | Redirect Buffer to Home Loan Prepayment (7.75%-7.85% ROI)\n"

    msg += f"\n──────────────────────\n"
    msg += f"📊 INDIA VIX RISK GUIDE\n"
    msg += f"(VIX = Market Fear Index)\n"
    msg += f"• VIX < 15 : Low Volatility 🟡\n"
    msg += f"• VIX 15-22: Moderate Volatility 🟡\n"
    msg += f"• VIX 22-30: High Fear / Buy Zone 🟢\n"
    msg += f"• VIX > 30 : Extreme Panic / Jackpot 🚀\n"

    if args.test or not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("\n=== [TELEGRAM MESSAGE PREVIEW] ===")
        print(msg)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        print("Telegram Alert Sent Successfully!")

if __name__ == "__main__":
    generate_and_send_alert()
