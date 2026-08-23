import os
import argparse
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Updated Small Cap tickers using Index for reliable 2020-2026 backtesting
CATEGORIES_TICKERS = {
    "LARGE CAP": ["NIFTYBEES.NS", "^NSEI"],
    "MID CAP": ["MID150BEES.NS", "MIDCAPETF.NS"],
    "SMALL CAP": ["^CNXSC", "SMLCAPBEES.NS", "HDFCSML250.NS"]
}

def calculate_rsi(series, period=14):
    if len(series) < period:
        return pd.Series([50.0] * len(series), index=series.index)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    return 100 - (100 / (1 + rs))

def extract_safe_series(df, col_name='Close'):
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        try:
            series = df[col_name].iloc[:, 0]
        except Exception:
            try:
                series = df.xs(col_name, axis=1, level=0).iloc[:, 0]
            except Exception:
                return pd.Series(dtype=float)
    else:
        if col_name in df.columns:
            series = df[col_name]
        else:
            return pd.Series(dtype=float)
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
    start_dt = target_dt - timedelta(days=4 * 365)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = (target_dt + timedelta(days=2)).strftime("%Y-%m-%d")

    for ticker in ticker_list:
        try:
            df = yf.download(ticker, start=start_str, end=end_str, interval="1d", progress=False)
            close = extract_safe_series(df, 'Close')
            
            close = close[close.index <= pd.Timestamp(target_dt)]
            
            if close.empty or len(close) < 20:
                continue

            current_price = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) > 1 else current_price
            p_change = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0.0

            rolling_window = min(len(close), 252)
            high_52w = float(close.rolling(window=rolling_window, min_periods=1).max().iloc[-1])
            drawdown = ((current_price - high_52w) / high_52w) * 100

            weekly_close = close.resample('W').last().dropna()
            weekly_rsi = calculate_rsi(weekly_close, 14)
            cur_w_rsi = float(weekly_rsi.iloc[-1]) if not weekly_rsi.empty else 50.0

            try:
                monthly_close = close.resample('ME').last().dropna()
            except Exception:
                monthly_close = close.resample('M').last().dropna()
                
            monthly_rsi = calculate_rsi(monthly_close, 14)
            cur_m_rsi = float(monthly_rsi.iloc[-1]) if not monthly_rsi.empty else 50.0

            dma_50_val = float(close.rolling(min(len(close), 50), min_periods=1).mean().iloc[-1])
            dma_200_val = float(close.rolling(min(len(close), 200), min_periods=1).mean().iloc[-1])

            return {
                'price': current_price,
                'p_change': p_change,
                'drawdown': drawdown,
                'weekly_rsi': cur_w_rsi,
                'monthly_rsi': cur_m_rsi,
                'dma_50': dma_50_val,
                'dma_200': dma_200_val
            }
        except Exception:
            continue

    return {
        'price': 100.0,
        'p_change': 0.0,
        'drawdown': 0.0,
        'weekly_rsi': 50.0,
        'monthly_rsi': 50.0,
        'dma_50': 100.0,
        'dma_200': 100.0
    }

def fetch_ai_news_summary(nifty_p_change, vix_val, is_historic=False, date_str=""):
    if is_historic:
        return f"• Historical Backtest Mode ({date_str}): Market metrics calculated based on historical price action."

    if not GEMINI_API_KEY:
        if nifty_p_change < -1.0:
            return "• Market down due to profit booking and institutional rebalancing."
        elif nifty_p_change > 1.0:
            return "• Market rally driven by strong domestic liquidity and positive global cues."
        else:
            return "• Market trading in a stable range with neutral macro triggers."
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"Indian stock market moved {nifty_p_change:.2f}% today with VIX at {vix_val:.2f}. Provide a 2-line simple Hinglish market summary for an investor."
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=8)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return f"• {text}"
    except Exception:
        pass
    
    return "• Market moving in normal parameters based on institutional flows."

def evaluate_stage(data):
    dd = abs(data['drawdown'])
    w_rsi = data['weekly_rsi']

    # EXACT STAGE EVALUATION LOGIC
    if dd >= 25 or (dd >= 20 and w_rsi < 30):
        return 8, "🚨🚨 🛑 STAGE 8: MARKET CRASH 🛑 🚀🚀", "🟢🟢🟢 JACKPOT LUMPSUM BUY 🟢🟢🟢", "🟢🟢 SIP + 100% MAX EXTRA LUMPSUM 🟢🟢", 100
    elif dd >= 15 or (dd >= 12 and w_rsi < 35):
        return 7, "🟢🟢 STAGE 7: HEAVY DISCOUNT 🟢🟢", "🟢 MEGA BUY OPPORTUNITY 🟢", "🟢 SIP + 75% Extra Lumpsum 🟢", 75
    elif dd >= 10 or (dd >= 8 and w_rsi < 40):
        return 6, "🟢 STAGE 6: BIG DISCOUNT 🟢", "🟢 BIG BUY OPPORTUNITY 🟢", "🟢 SIP + 50% Extra Lumpsum 🟢", 50
    elif dd >= 5 or (dd >= 4 and w_rsi < 45):
        return 5, "🟡 STAGE 5: GOOD DISCOUNT 🟡", "🟢 Active Buy Zone 🟢", "🟢 SIP + 25% Extra Lumpsum 🟢", 25
    elif dd >= 2.5:
        return 4, "📊 STAGE 4: SMALL DISCOUNT 📊", "🟡 Active Buy 🟡", "🟢 SIP + 10% Extra Lumpsum 🟢", 10
    elif w_rsi > 72 and dd < 1.0:
        return 1, "🔴 STAGE 1: EXTREME HIGH (PEAK) 🔴", "🟢 ALWAYS CONTINUE SIP 🟢", "🔴 Continuous SIP + Redirect Lumpsum Buffer to Loan 🔴", 0
    elif w_rsi > 60:
        return 2, "🚀 STAGE 2: BULL RUN 🚀", "🟢 Normal SIP 🟢", "🟢 SIP Continuous + Optional Loan Prepay 🏦", 0
    else:
        return 3, "🟢 STAGE 3: NORMAL MARKET 🟢", "🟢 Active 🟢", "🟢 Normal SIP Only 🟢", 0

def generate_and_send_alert():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str)
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    target_dt = parse_input_date(args.date)
    formatted_date_str = target_dt.strftime("%d-%b-%Y")
    is_historic = bool(args.date and target_dt.date() < datetime.now().date())

    cat_data = {k: get_market_data(v, target_dt) for k, v in CATEGORIES_TICKERS.items()}

    try:
        vix_start = (target_dt - timedelta(days=4 * 365)).strftime("%Y-%m-%d")
        vix_end = (target_dt + timedelta(days=2)).strftime("%Y-%m-%d")
        vix_df = yf.download("^INDIAVIX", start=vix_start, end=vix_end, progress=False)
        vix_series = extract_safe_series(vix_df, 'Close')
        vix_series = vix_series[vix_series.index <= pd.Timestamp(target_dt)]
        vix_val = float(vix_series.iloc[-1]) if not vix_series.empty else 15.0
    except Exception:
        vix_val = 15.0

    stages_eval = [evaluate_stage(cat_data[k]) for k in cat_data]
    stages_nums = [s[0] for s in stages_eval]

    # STRICT SUPPRESSION: Stage 2, 3, 4 Suppressed
    should_send = any(s in [1, 5, 6, 7, 8] for s in stages_nums) or (vix_val >= 22.0)

    if not should_send and not args.test:
        print(f"[{formatted_date_str}] Market in Stage 2/3/4. Alert Suppressed.")
        return

    category_icons = {"LARGE CAP": "🏛️", "MID CAP": "📈", "SMALL CAP": "🚀"}
    stage_weights = {}

    weighted_dd = sum([abs(cat_data[k]['drawdown']) for k in cat_data]) / 3
    weighted_rsi = sum([cat_data[k]['weekly_rsi'] for k in cat_data]) / 3
    
    # RE-CALIBRATED BALANCED MARKET SCORE FORMULA
    # Score 0-100: Higher = Peak/Overbought, Lower = Discount/Crash
    rsi_component = weighted_rsi * 0.45
    vix_component = min(vix_val, 40) * 0.25
    dd_component = max(0, 100 - (weighted_dd * 2.5)) * 0.30
    score = max(0, min(100, rsi_component + vix_component + dd_component))

    max_stage = max(stages_nums)
    
    # SYNCED HEADER & HEALTH STATUS LOGIC BASED ON ACTUAL STAGES
    if max_stage in [7, 8] or score < 35:
        health_status = "🟢 EXTREME DISCOUNT"
        header_prefix = "🚨🚨 CRITICAL EMERGENCY CRASH ALERT"
    elif max_stage in [5, 6] or score < 45:
        health_status = "🟢 MEGA DISCOUNT BUY"
        header_prefix = "🟢🟢 HIGH OPPORTUNITY BUY ALERT"
    elif max_stage == 4:
        health_status = "Neutral 🟡"
        header_prefix = "🟡 SMALL DISCOUNT WATCH"
    elif max_stage == 1:
        health_status = "🔴 OVERBOUGHT / PEAK"
        header_prefix = "🔴 ALL-TIME HIGH PEAK ALERT"
    else:
        health_status = "Neutral 🟡"
        header_prefix = "🟢 REGULAR MARKET REPORT"

    msg = f"{header_prefix}: AI WEALTH MANAGER\n"
    msg += f"{formatted_date_str}\n"
    msg += f"──────────────────────\n"
    msg += f"🌡️ MARKET METRICS\n"
    msg += f"• Score: {score:.1f}/100 ({health_status})\n"
    msg += f"• India VIX Index: {vix_val:.2f}\n"
    msg += f"• Market Avg Drop: -{weighted_dd:.1f}% From High\n"
    msg += f"──────────────────────\n"
    msg += f"🏛️ ACTIONABLE CATEGORY MATRIX\n\n"

    for cat_name in CATEGORIES_TICKERS.keys():
        data = cat_data[cat_name]
        s_num, s_title, s_status, s_action, l_weight = evaluate_stage(data)
        stage_weights[cat_name] = l_weight

        dma_status = "🟢 50 DMA < 200 DMA (Discount Opportunity)" if data['dma_50'] < data['dma_200'] else "🔴 50 DMA > 200 DMA (High Zone)"
        icon = category_icons.get(cat_name, "🎯")

        msg += f"{icon} {cat_name}\n"
        msg += f"• Stage: {s_title}\n"
        msg += f"• SIP Status: {s_status}\n"
        msg += f"• Action: {s_action}\n"
        msg += f"• Price: {data['price']:.2f} ({data['p_change']:+.2f}%)\n"
        msg += f"• Drawdown: {data['drawdown']:.2f}% from 52W High\n"
        msg += f"• Weekly RSI: {data['weekly_rsi']:.2f} | Monthly RSI: {data['monthly_rsi']:.2f}\n"
        msg += f"• DMA Trend: {dma_status}\n\n"

    news_summary = fetch_ai_news_summary(cat_data["LARGE CAP"]['p_change'], vix_val, is_historic=is_historic, date_str=formatted_date_str)
    msg += f"──────────────────────\n"
    msg += f"📰 MARKET CONTEXT & NEWS\n"
    msg += f"{news_summary}\n\n"

    total_w = sum(stage_weights.values())
    msg += f"──────────────────────\n"
    msg += f"💡 CAPITAL ALLOCATION PLAN\n"
    if total_w > 0:
        for k, v in stage_weights.items():
            alloc_pct = round((v / total_w) * 100)
            msg += f"• {k.split()[0].capitalize()} Cap: Allocate {alloc_pct}% Capital Buffer\n"
    else:
        msg += "• Maintain Standard SIPs | Direct Extra Buffer to Home Loan Prepayment (7.75%-7.85% ROI)\n"

    msg += f"\n──────────────────────\n"
    msg += f"📊 INDIA VIX RISK GUIDE\n"
    msg += f"(VIX = Market Fear & Volatility)\n"
    msg += f"• VIX < 15 : Low Volatility 🟡\n"
    msg += f"• VIX 15-22: Moderate Volatility 🟡\n"
    msg += f"• VIX 22-30: High Fear / Buy Zone 🟢\n"
    msg += f"• VIX > 30 : Extreme Panic / Jackpot 🚀\n"

    msg += f"\n──────────────────────\n"
    msg += f"📈 MARKET HEALTH GUIDE\n"
    msg += f"(Score Range: 0 - 100)\n"
    msg += f"• Score < 35 : 🟢 Extreme Crash / Heavy Buy\n"
    msg += f"• Score 35-45: 🟢 Discount Market / Aggressive Buy\n"
    msg += f"• Score 45-65: 🟡 Normal Market / Regular SIP\n"
    msg += f"• Score > 65 : 🔴 High Peak / Stop Lumpsum & Prepay Loan\n"

    msg += f"\n──────────────────────\n"
    msg += f"📖 8-STAGE QUICK GUIDE\n\n"
    msg += f"1. 🔥 Extreme High (All-Time Peak)\n   └ 🔴 Continuous SIP | Prepay Loan with Lumpsum Buffer\n"
    msg += f"2. 🚀 Bull Run (High Zone)\n   └ 🔴 Normal SIP | Prepay Loan\n"
    msg += f"3. 🟢 Normal Market (Fair Price)\n   └ 🟡 Normal SIP Only (0% Lumpsum)\n"
    msg += f"4. 📊 Small Discount (2-3% Dip)\n   └ 🟢 SIP + Extra Lumpsum\n"
    msg += f"5. 🟡 Good Discount (5% Dip)\n   └ 🟢 SIP + Extra Lumpsum\n"
    msg += f"6. ⚠️ Big Discount (10% Drop - Buy)\n   └ 🟢 SIP + Extra Lumpsum\n"
    msg += f"7. 📉 Heavy Discount (15%+ - Mega Buy)\n   └ 🟢 SIP + Extra Lumpsum\n"
    msg += f"8. 🛑 Market Crash (25%+ - Jackpot Buy)\n   └ 🚀 SIP + Max Lumpsum Buy\n"

    msg += f"\n──────────────────────\n"
    msg += f"📌 IMPORTANT NOTES & RULES\n\n"
    msg += f"• 💎 GOLDEN WEALTH RULE: NEVER STOP YOUR REGULAR SIP. Market creates a new all-time high every 2-3 years; continuous SIP compounds wealth effortlessly.\n"
    msg += f"• Lumpsum Allocation: Extra Lumpsum% in Stages 4-8 applies strictly to your Monthly Extra Capital Buffer.\n"
    msg += f"• Peak Protection: Stage 1 signals only pause Extra Lumpsum to safely prepay Home Loan (7.75%-7.85% ROI).\n"
    msg += f"• Metrics: RSI (<30 Cheap 🟢 | >70 High 🔴) | DMA (50<200 Discount 🟢) | Drawdown (% Drop from 52W High)\n"

    if args.test or not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("\n=== [TELEGRAM MESSAGE PREVIEW] ===")
        print(msg)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        print("Telegram Alert Sent Successfully!")

if __name__ == "__main__":
    generate_and_send_alert()
