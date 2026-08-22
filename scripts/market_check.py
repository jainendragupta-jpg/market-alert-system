import os
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CATEGORIES = {
    "LARGE CAP": "^NSEI",          # Nifty 50
    "MID CAP": "^NSEMDCP50",       # Nifty Midcap 50
    "SMALL CAP": "^CNXSMALL30"     # Nifty Smallcap 50
}

SCREENER_URLS = {
    "LARGE CAP": "https://www.screener.in/company/NIFTY/",
    "MID CAP": "https://www.screener.in/company/NIFTYMIDCAP50/",
    "SMALL CAP": "https://www.screener.in/company/NIFTYSMALLCAP50/"
}

# ==========================================
# HELPER FUNCTIONS: DATA FETCHING
# ==========================================
def fetch_screener_pe(category):
    """Fetches Live PE Ratio from Screener.in with fallback handling"""
    url = SCREENER_URLS.get(category)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            top_ratios = soup.find('ul', id='top-ratios')
            if top_ratios:
                for li in top_ratios.find_all('li'):
                    name = li.find('span', class_='name')
                    if name and 'Stock P/E' in name.text:
                        val = li.find('span', class_='number').text.replace(',', '').strip()
                        return float(val)
    except Exception as e:
        print(f"Screener PE fetch failed for {category}: {e}")
    
    # Fallback default values
    fallback_pe = {"LARGE CAP": 21.5, "MID CAP": 28.0, "SMALL CAP": 25.0}
    return fallback_pe.get(category, 22.0)

def calculate_rsi(series, period=14):
    """Calculates Relative Strength Index (RSI)"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_data(ticker_symbol):
    """Fetches stock data and calculates RSI, DMAs, and Drawdown"""
    df = yf.download(ticker_symbol, period="2y", interval="1d", progress=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker {ticker_symbol}")
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df['Close']
    current_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    p_change = ((current_price - prev_close) / prev_close) * 100

    high_52w = float(close.rolling(window=252, min_periods=1).max().iloc[-1])
    drawdown = ((current_price - high_52w) / high_52w) * 100

    # Indicators
    daily_rsi = calculate_rsi(close, 14)
    weekly_close = close.resample('W').last()
    weekly_rsi = calculate_rsi(weekly_close, 14)
    monthly_close = close.resample('ME').last()
    monthly_rsi = calculate_rsi(monthly_close, 14)

    cur_w_rsi = float(weekly_rsi.iloc[-1]) if not weekly_rsi.empty else 50.0
    cur_m_rsi = float(monthly_rsi.iloc[-1]) if not monthly_rsi.empty else 50.0

    dma_50 = float(close.rolling(window=50).mean().iloc[-1])
    dma_200 = float(close.rolling(window=200).mean().iloc[-1])

    return {
        'price': current_price,
        'p_change': p_change,
        'drawdown': drawdown,
        'weekly_rsi': cur_w_rsi,
        'monthly_rsi': cur_m_rsi,
        'dma_50': dma_50,
        'dma_200': dma_200
    }

# ==========================================
# MULTI-FACTOR STAGE DECISION ENGINE
# ==========================================
def evaluate_stage(category, data, pe_ratio):
    dd = abs(data['drawdown'])
    w_rsi = data['weekly_rsi']
    m_rsi = data['monthly_rsi']
    
    # PE Thresholds
    pe_high = {"LARGE CAP": 24, "MID CAP": 32, "SMALL CAP": 28}[category]
    pe_cheap = {"LARGE CAP": 18, "MID CAP": 24, "SMALL CAP": 20}[category]

    # STAGE EVALUATION (Drawdown as Primary Anchor)
    if dd >= 25 or (dd >= 20 and w_rsi < 30):
        return 8, "🛑 Market Crash (Stg 8)", "Jackpot Lumpsum Buy 🚀", "SIP + 100% Max Lumpsum"
    elif dd >= 15 or (dd >= 12 and w_rsi < 35):
        return 7, "📉 Heavy Discount (Stg 7)", "Mega Buy Opportunity 🟢", "SIP + 75% Extra Lumpsum 🟢"
    elif dd >= 10 or (dd >= 8 and pe_ratio < pe_cheap):
        return 6, "⚠️ Big Discount (Stg 6)", "Big Buy Opportunity 🟢", "SIP + 50% Extra Lumpsum 🟢"
    elif dd >= 5 or (dd >= 4 and w_rsi < 45):
        return 5, "🟡 Good Discount (Stg 5)", "Active 🟢", "SIP + 25% Extra Lumpsum 🟢"
    elif dd >= 2.5:
        return 4, "📊 Small Discount (Stg 4)", "Active 🟢", "SIP + 10% Extra Lumpsum 🟢"
    elif (w_rsi > 70 and pe_ratio > pe_high) or m_rsi > 70:
        return 1, "🔥 Extreme High (Stg 1)", "Stop This Month 🔴", "Book Small Profit 💰 & Prepay Loan 🏦"
    elif w_rsi > 60:
        return 2, "🚀 Bull Run (Stg 2)", "Normal SIP 🟢", "Normal SIP + Prepay Loan 🏦"
    else:
        return 3, "🟢 Normal Market (Stg 3)", "Active 🟢", "Normal SIP Only (0% Lumpsum)"

# ==========================================
# MAIN EXECUTION & MESSAGE FORMATTER
# ==========================================
def generate_and_send_alert():
    # 1. Market Overview Data
    nifty = get_market_data("^NSEI")
    vix = yf.download("^INDIAVIX", period="5d", progress=False)['Close'].iloc[-1]
    vix_val = float(vix.iloc[-1]) if isinstance(vix, pd.Series) else float(vix)
    nifty_pe = fetch_screener_pe("LARGE CAP")

    # Overall Market Health Score Calculation
    score = 100 - (nifty['monthly_rsi'] * 0.5 + (nifty_pe / 35.0) * 30 + (abs(nifty['drawdown']) * 0.5))
    score = max(0, min(100, score))
    health_status = "Neutral 🟡" if 40 <= score <= 60 else ("Bullish 🔴" if score < 40 else "Discount Zone 🟢")

    date_str = datetime.now().strftime("%d-%b-%Y")

    # Header
    msg = f"🚨 ACTION ALERT: AI WEALTH MANAGER\n"
    msg += f"{date_str}\n"
    msg += f"──────────────────────\n"
    msg += f"🌡️ MARKET METRICS\n"
    msg += f"• Score: {score:.1f}/100 ({health_status})\n"
    msg += f"• Nifty PE (Exact): {nifty_pe:.2f} | VIX: {vix_val:.2f}\n"
    msg += f"• Nifty 50: {nifty['price']:.2f} ({nifty['p_change']:+.2f}%)\n"
    msg += f"• Monthly RSI: {nifty['monthly_rsi']:.2f}\n"
    msg += f"──────────────────────\n"
    msg += f"🏛️ ACTIONABLE CATEGORY MATRIX\n\n"

    summary_actions = []

    for cat_name, ticker in CATEGORIES.items():
        data = get_market_data(ticker)
        pe = fetch_screener_pe(cat_name)
        stage_num, stage_title, sip_status, action_text = evaluate_stage(cat_name, data, pe)

        # Skip Stage 2 and 3 to avoid spamming
        if stage_num in [2, 3]:
            continue

        pe_remark = "Fair Price" if stage_num == 3 else ("Growth Zone" if stage_num in [1, 2] else "Discount Zone")
        dma_status = "🟢 50 DMA < 200 DMA (Discount Opportunity)" if data['dma_50'] < data['dma_200'] else "🔴 50 DMA > 200 DMA"

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
    msg += f"• RSI (<30 Cheap | >70 High)\n"
    msg += f"• DMA (50<200 Discount 🟢 | 50>200 High 🔴)\n"
    msg += f"• Drawdown (% Drop from 52W High)\n\n"
    msg += f"📊 PE RATIO GUIDE:\n"
    msg += f"• Large Cap: <18 Cheap | >24 High\n"
    msg += f"• Mid Cap:   <24 Cheap | >32 High\n"
    msg += f"• Small Cap: <20 Cheap | >28 High\n"

    # Send to Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        res = requests.post(url, json=payload)
        print("Telegram Response Status:", res.status_code)
    else:
        print("Telegram Credentials not set. Outputting message to console:\n")
        print(msg)

if __name__ == "__main__":
    generate_and_send_alert()
