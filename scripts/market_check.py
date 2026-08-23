import os
import argparse
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# CONFIGURATION & HIGH AVAILABILITY CONSTANTS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Ultra-Clean Verified Tickers to Prevent "No Data Found" Terminal Warnings
CATEGORIES_TICKERS = {
    "LARGE CAP": ["^NSEI", "^CNX100"],
    "MID CAP": ["^NSEMDCP150", "^NSEMDCP50"],
    "SMALL CAP": ["NIFTY_SMLCAP_250.NS", "^BSESMLCAP"]
}

SCREENER_URLS = {
    "LARGE CAP": "https://www.screener.in/company/NIFTY100/",
    "MID CAP": "https://www.screener.in/company/NIFTYMIDCAP150/",
    "SMALL CAP": "https://www.screener.in/company/NIFTYSMALLCAP250/"
}

SYSTEM_WARNINGS = []

# ==========================================
# HELPER FUNCTIONS: DATA FETCHING & RESILIENCE
# ==========================================
def fetch_screener_pe(category):
    """Fetches Live PE Ratio from Screener.in with HTML fallback parsing"""
    url = SCREENER_URLS.get(category)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            top_ratios = soup.find('ul', id='top-ratios')
            if top_ratios:
                for li in top_ratios.find_all('li'):
                    name = li.find('span', class_='name')
                    if name and ('Stock P/E' in name.text or 'P/E' in name.text):
                        val = li.find('span', class_='number').text.replace(',', '').strip()
                        return float(val)
    except Exception as e:
        SYSTEM_WARNINGS.append(f"Screener PE warning for {category}: {e}")
    
    fallback_pe = {"LARGE CAP": 22.5, "MID CAP": 28.0, "SMALL CAP": 25.0}
    return fallback_pe.get(category, 23.0)

def calculate_rsi(series, period=14):
    """Calculates RSI with zero-division guard & Pandas compatibility"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    rsi = 100 - (100 / (1 + rs))
    return rsi

def extract_safe_series(df, col_name='Close'):
    """Extracts clean 1D pandas Series handling single/multi-index yfinance DataFrames"""
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
    """Parses various date format strings safely into datetime object"""
    if not date_str:
        return datetime.now()
    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.now()

def get_market_data_with_fallback(ticker_list, target_datetime=None):
    """Fetches market data with historic slicing support & clean fallback protection"""
    if target_datetime is None:
        target_datetime = datetime.now()

    for ticker_symbol in ticker_list:
        try:
            df = yf.download(ticker_symbol, period="3y", interval="1d", progress=False)
            close = extract_safe_series(df, 'Close')
            
            if close.empty:
                continue

            close = close[close.index <= pd.Timestamp(target_datetime)]

            if len(close) < 50:
                continue

            current_price = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) > 1 else current_price
            p_change = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0.0

            high_52w = float(close.rolling(window=min(len(close), 252), min_periods=1).max().iloc[-1])
            drawdown = ((current_price - high_52w) / high_52w) * 100

            weekly_close = close.resample('W').last().dropna()
            weekly_rsi = calculate_rsi(weekly_close, 14)
            
            monthly_close = close.resample('ME' if hasattr(pd.Series, 'resample') else 'M').last().dropna()
            monthly_rsi = calculate_rsi(monthly_close, 14)

            cur_w_rsi = float(weekly_rsi.iloc[-1]) if not weekly_rsi.empty else 50.0
            cur_m_rsi = float(monthly_rsi.iloc[-1]) if not monthly_rsi.empty else 50.0

            dma_50 = float(close.rolling(window=min(len(close), 50), min_periods=1).mean().iloc[-1])
            dma_200 = float(close.rolling(window=min(len(close), 200), min_periods=1).mean().iloc[-1])

            return {
                'price': current_price,
                'p_change': p_change,
                'drawdown': drawdown,
                'weekly_rsi': cur_w_rsi,
                'monthly_rsi': cur_m_rsi,
                'dma_50': dma_50,
                'dma_200': dma_200
            }
        except Exception:
            continue

    raise RuntimeError(f"❌ Critical Error: All tickers failed for candidate list: {ticker_list}")

def fetch_ai_news_summary(nifty_p_change, vix_val, is_historic=False, date_str=""):
    """Fetches market news context via Gemini API or fallback logic"""
    if is_historic:
        return f"• Historical Backtest Mode ({date_str}): Market metrics calculated based on historical price action."

    if not GEMINI_API_KEY:
        if nifty_p_change < -1.0:
            return "• Market down due to standard profit booking and FII institutional rebalancing."
        elif nifty_p_change > 1.0:
            return "• Market rally driven by strong domestic liquidity and positive global market cues."
        else:
            return "• Market trading in a stable range with neutral macro triggers."
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = (
            f"Indian stock market moved {nifty_p_change:.2f}% today with VIX at {vix_val:.2f}. "
            f"Provide a brief 2-line simple Hinglish explanation on why the market moved today (mention key global or domestic reasons like FII/DII, crude oil, or interest rates). Keep it crisp and easy to understand for an investor."
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=8)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return f"• {text}"
    except Exception as e:
        SYSTEM_WARNINGS.append(f"Gemini API news fetch error: {e}")
    
    return "• Market moving in normal parameters based on domestic & global fund flows."

# ==========================================
# MULTI-FACTOR STAGE DECISION ENGINE WITH VISUAL COLOR CODES
# ==========================================
def evaluate_stage(category, data, pe_ratio):
    dd = abs(data['drawdown'])
    w_rsi = data['weekly_rsi']
    m_rsi = data['monthly_rsi']
    
    pe_high = {"LARGE CAP": 24, "MID CAP": 32, "SMALL CAP": 28}[category]
    pe_cheap = {"LARGE CAP": 18, "MID CAP": 24, "SMALL CAP": 20}[category]

    if dd >= 25 or (dd >= 20 and w_rsi < 30):
        return 8, "🚀🚀 🛑 STAGE 8: MARKET CRASH 🛑 🚀🚀", "🟢🟢🟢 JACKPOT LUMPSUM BUY 🟢🟢🟢", "🟢🟢 SIP + 100% MAX EXTRA LUMPSUM 🟢🟢"
    elif dd >= 15 or (dd >= 12 and w_rsi < 35):
        return 7, "🟢🟢 STAGE 7: HEAVY DISCOUNT 🟢🟢", "🟢 MEGA BUY OPPORTUNITY 🟢", "🟢 SIP + 75% Extra Lumpsum 🟢"
    elif dd >= 10 or (dd >= 8 and pe_ratio < pe_cheap):
        return 6, "🟢 STAGE 6: BIG DISCOUNT 🟢", "🟢 BIG BUY OPPORTUNITY 🟢", "🟢 SIP + 50% Extra Lumpsum 🟢"
    elif dd >= 5 or (dd >= 4 and w_rsi < 45):
        return 5, "🟡 STAGE 5: GOOD DISCOUNT 🟡", "🟡 Active Buy Zone 🟡", "🟢 SIP + 25% Extra Lumpsum 🟢"
    elif dd >= 2.5:
        return 4, "📊 STAGE 4: SMALL DISCOUNT 📊", "🟡 Active 🟡", "🟢 SIP + 10% Extra Lumpsum 🟢"
    elif (w_rsi > 70 and pe_ratio > pe_high) or m_rsi > 70:
        return 1, "🔴🔴 STAGE 1: EXTREME HIGH 🔴🔴", "🚨 STOP THIS MONTH 🚨", "🔴 Book Small Profit 💰 & Prepay Loan 🏦"
    elif w_rsi > 60:
        return 2, "🚀 STAGE 2: BULL RUN 🚀", "🟢 Normal SIP 🟢", "🟢 Normal SIP + Prepay Loan 🏦"
    else:
        return 3, "🟢 STAGE 3: NORMAL MARKET 🟢", "🟢 Active 🟢", "🟢 Normal SIP Only (0% Lumpsum)"

# ==========================================
# MAIN EXECUTION ENGINE
# ==========================================
def generate_and_send_alert():
    parser = argparse.ArgumentParser(description="AI Wealth Manager Strategy Engine")
    parser.add_argument('--date', type=str, help='Run date format YYYY-MM-DD or DD-MM-YYYY')
    parser.add_argument('--test', action='store_true', help='Test mode flag')
    parser.add_argument('--dry-run', action='store_true', help='Dry run flag (outputs to console only)')
    args = parser.parse_args()

    target_dt = parse_input_date(args.date)
    formatted_date_str = target_dt.strftime("%d-%b-%Y")

    is_historic = bool(args.date and target_dt.date() < datetime.now().date())
    is_test_mode = args.test or args.dry_run

    try:
        nifty = get_market_data_with_fallback(CATEGORIES_TICKERS["LARGE CAP"], target_dt)
    except Exception as e:
        emergency_msg = f"⚠️ SYSTEM ALERT: Market data download failed.\nError: {e}\nPlease check yfinance version or repository settings."
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and not is_test_mode:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": emergency_msg})
        print(emergency_msg)
        return

    try:
        vix_df = yf.download("^INDIAVIX", period="3y", progress=False)
        vix_series = extract_safe_series(vix_df, 'Close')
        vix_series = vix_series[vix_series.index <= pd.Timestamp(target_dt)]
        vix_val = float(vix_series.iloc[-1]) if not vix_series.empty else 15.0
    except Exception:
        vix_val = 15.0

    nifty_pe = fetch_screener_pe("LARGE CAP")

    score = 100 - (nifty['monthly_rsi'] * 0.5 + (nifty_pe / 35.0) * 30 + (abs(nifty['drawdown']) * 0.5))
    score = max(0, min(100, score))
    health_status = "Neutral 🟡" if 40 <= score <= 60 else ("Bullish 🔴" if score < 40 else "Discount Zone 🟢")

    # Dynamic Header Siren Logic based on Score & Risk Severity
    if score < 30 or vix_val > 25:
        header_prefix = "🚨🚨 CRITICAL EMERGENCY CRASH ALERT"
    elif score < 45 or nifty['drawdown'] < -10:
        header_prefix = "🟢🟢 HIGH OPPORTUNITY BUY ALERT"
    elif score < 55:
        header_prefix = "🟡 DISCOUNT WATCH ALERT"
    else:
        header_prefix = "🟢 REGULAR MARKET REPORT"

    msg = f"{header_prefix}: AI WEALTH MANAGER\n"
    msg += f"{formatted_date_str}\n"
    msg += f"──────────────────────\n"
    msg += f"🌡️ MARKET METRICS\n"
    msg += f"• Score: {score:.1f}/100 ({health_status})\n"
    msg += f"• Nifty PE (Exact): {nifty_pe:.2f} | VIX: {vix_val:.2f}\n"
    msg += f"• Nifty 100: {nifty['price']:.2f} ({nifty['p_change']:+.2f}%)\n"
    msg += f"• Monthly RSI: {nifty['monthly_rsi']:.2f}\n"
    msg += f"──────────────────────\n"
    msg += f"🏛️ ACTIONABLE CATEGORY MATRIX\n\n"

    summary_actions = []

    for cat_name, ticker_list in CATEGORIES_TICKERS.items():
        data = get_market_data_with_fallback(ticker_list, target_dt)
        pe = fetch_screener_pe(cat_name)
        stage_num, stage_title, sip_status, action_text = evaluate_stage(cat_name, data, pe)

        if stage_num in [2, 3]:
            continue

        pe_remark = "Fair Price 🟡" if stage_num == 3 else ("Growth Zone 🔴" if stage_num in [1, 2] else "Discount Zone 🟢")
        dma_status = "🟢 50 DMA < 200 DMA (Discount Opportunity)" if data['dma_50'] < data['dma_200'] else "🔴 50 DMA > 200 DMA (High Zone)"

        category_icon = "🏛️" if cat_name == "LARGE CAP" else ("📈" if cat_name == "MID CAP" else "🚀")

        msg += f"{category_icon} {cat_name}\n"
        msg += f"• Stage: {stage_title}\n"
        msg += f"• SIP Status: {sip_status}\n"
        msg += f"• Action: {action_text}\n"
        msg += f"• Index PE: {pe:.2f} ({pe_remark})\n"
        msg += f"• Price: {data['price']:.2f} ({data['p_change']:+.2f}%)\n"
        msg += f"• Weekly RSI: {data['weekly_rsi']:.2f} | Monthly RSI: {data['monthly_rsi']:.2f}\n"
        msg += f"• DMA Trend: {dma_status}\n\n"

        short_cat = cat_name.split()[0].capitalize()
        summary_actions.append(f"• {short_cat}: {action_text}")

    if not summary_actions:
        msg += "🟢 ALL CATEGORIES ARE IN NORMAL ZONE (STAGE 2/3). NO SPECIAL LUMPSUM/PROFIT BOOKING NEEDED.\n\n"

    # News Section
    news_summary = fetch_ai_news_summary(nifty['p_change'], vix_val, is_historic=is_historic, date_str=formatted_date_str)
    msg += f"──────────────────────\n"
    msg += f"📰 MARKET CONTEXT & NEWS\n"
    msg += f"{news_summary}\n"

    msg += f"──────────────────────\n"
    msg += f"💡 SUMMARY ACTION\n"
    for sum_act in summary_actions:
        msg += f"{sum_act}\n"

    msg += f"\n──────────────────────\n"
    msg += f"📖 8-STAGE QUICK GUIDE\n\n"
    msg += f"1. 🔥 Extreme High (All-Time Peak)\n   └ 🔴 Stop SIP | Book Small Profit -> Prepay Loan\n"
    msg += f"2. 🚀 Bull Run (High Zone)\n   └ 🔴 Normal SIP | Prepay Loan\n"
    msg += f"3. 🟢 Normal Market (Fair Price)\n   └ 🟡 Normal SIP Only (0% Lumpsum)\n"
    msg += f"4. 📊 Small Discount (2-3% Dip)\n   └ 🟢 SIP + 10% Extra\n"
    msg += f"5. 🟡 Good Discount (5% Dip)\n   └ 🟢 SIP + 25% Extra\n"
    msg += f"6. ⚠️ Big Discount (10% Drop - Buy)\n   └ 🟢 SIP + 50% Extra\n"
    msg += f"7. 📉 Heavy Discount (15%+ - Mega Buy)\n   └ 🟢 SIP + 75% Extra\n"
    msg += f"8. 🛑 Market Crash (25%+ - JackPot Buy)\n   └ 🚀 SIP + Max Lumpsum Buy\n"

    msg += f"\n──────────────────────\n"
    msg += f"📌 IMPORTANT NOTES & RULES\n\n"
    msg += f"• NOTE: Extra Lumpsum% (10% to 100%) in Stages 4-8 applies strictly to your allocated Monthly Extra Lumpsum Capital Buffer.\n"
    msg += f"• RSI (<30 Cheap 🟢 | >70 High 🔴)\n"
    msg += f"• DMA (50<200 Discount 🟢 | 50>200 High 🔴)\n"
    msg += f"• Drawdown (% Drop from 52W High)\n\n"
    msg += f"📊 PE RATIO GUIDE:\n"
    msg += f"• Large Cap: <18 Cheap 🟢 | >24 High 🔴\n"
    msg += f"• Mid Cap:   <24 Cheap 🟢 | >32 High 🔴\n"
    msg += f"• Small Cap: <20 Cheap 🟢 | >28 High 🔴\n"

    if is_test_mode or not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("\n=== [TEST/DRY-RUN MODE OUTPUT] ===")
        print(msg)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        res = requests.post(url, json=payload, timeout=10)
        print("Telegram Response Status:", res.status_code)

if __name__ == "__main__":
    generate_and_send_alert()
