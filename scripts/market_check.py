import os
import requests
import yfinance as yf

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def get_index_data(symbol):
    data = yf.Ticker(symbol).history(
        period="1y",
        auto_adjust=False
    )

    if data.empty or len(data) < 200:
        raise Exception(f"Not enough data for {symbol}")

    close = float(data["Close"].iloc[-1])
    previous_close = float(data["Close"].iloc[-2])

    daily_change = ((close - previous_close) / previous_close) * 100

    # ==========================================
    # MOVING AVERAGES
    # ==========================================

    dma20 = data["Close"].rolling(20).mean().iloc[-1]
    dma50 = data["Close"].rolling(50).mean().iloc[-1]
    dma200 = data["Close"].rolling(200).mean().iloc[-1]

    # ==========================================
    # RSI 14
    # ==========================================

    delta = data["Close"].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    rsi_value = float(rsi.iloc[-1])

    # ==========================================
    # PRICE VS MOVING AVERAGES
    # ==========================================

    vs50 = ((close - dma50) / dma50) * 100
    vs200 = ((close - dma200) / dma200) * 100

    # ==========================================
    # TREND
    # ==========================================

    if close > dma20 and dma20 > dma50 and dma50 > dma200:
        trend = "STRONG UPTREND 🟢"

    elif close > dma50 and dma50 > dma200:
        trend = "UPTREND 🟢"

    elif close < dma50 and dma50 < dma200:
        trend = "DOWNTREND 🔴"

    else:
        trend = "NEUTRAL 🟡"

    # ==========================================
    # RSI STATUS
    # ==========================================

    if rsi_value >= 70:
        rsi_status = "OVERBOUGHT 🔴"

    elif rsi_value >= 60:
        rsi_status = "STRONG 🟢"

    elif rsi_value >= 50:
        rsi_status = "POSITIVE 🟢"

    elif rsi_value >= 40:
        rsi_status = "WEAK 🟡"

    elif rsi_value >= 30:
        rsi_status = "VERY WEAK 🔴"

    else:
        rsi_status = "OVERSOLD 🟢"

    return {
        "close": round(close, 2),
        "change": round(daily_change, 2),
        "dma20": round(float(dma20), 2),
        "dma50": round(float(dma50), 2),
        "dma200": round(float(dma200), 2),
        "vs50": round(float(vs50), 2),
        "vs200": round(float(vs200), 2),
        "rsi": round(rsi_value, 2),
        "rsi_status": rsi_status,
        "trend": trend
    }


try:

    # ==========================================
    # NIFTY 50
    # ==========================================

    nifty50 = get_index_data("^NSEI")

    # ==========================================
    # LARGE CAP - NIFTY 100
    # ==========================================

    nifty100 = get_index_data("^CNX100")

    # ==========================================
    # MID CAP - NIFTY MIDCAP 150
    # ==========================================

    midcap150 = get_index_data(
        "NIFTYMIDCAP150.NS"
    )

    # ==========================================
    # SMALL CAP - NIFTY SMALLCAP 250
    # ==========================================

    smallcap250 = get_index_data(
        "NIFTYSMLCAP250.NS"
    )

    # ==========================================
    # OVERALL MARKET - NIFTY 500
    # ==========================================

    nifty500 = get_index_data("^CRSLDX")

    # ==========================================
    # SENSEX
    # ==========================================

    sensex = get_index_data("^BSESN")


    # ==========================================
    # TELEGRAM MESSAGE
    # ==========================================

    message = f"""
📊 AI MARKET ANALYSIS REPORT
━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price: {nifty50['close']}
Daily Change: {nifty50['change']}%

20 DMA: {nifty50['dma20']}
50 DMA: {nifty50['dma50']}
200 DMA: {nifty50['dma200']}

Price vs 50 DMA: {nifty50['vs50']}%
Price vs 200 DMA: {nifty50['vs200']}%

RSI 14: {nifty50['rsi']}
RSI Status: {nifty50['rsi_status']}
Trend: {nifty50['trend']}


🟢 LARGE CAP
NIFTY 100

Price: {nifty100['close']}
Daily Change: {nifty100['change']}%

20 DMA: {nifty100['dma20']}
50 DMA: {nifty100['dma50']}
200 DMA: {nifty100['dma200']}

Price vs 50 DMA: {nifty100['vs50']}%
Price vs 200 DMA: {nifty100['vs200']}%

RSI 14: {nifty100['rsi']}
RSI Status: {nifty100['rsi_status']}
Trend: {nifty100['trend']}


🟡 MID CAP
NIFTY MIDCAP 150

Price: {midcap150['close']}
Daily Change: {midcap150['change']}%

20 DMA: {midcap150['dma20']}
50 DMA: {midcap150['dma50']}
200 DMA: {midcap150['dma200']}

Price vs 50 DMA: {midcap150['vs50']}%
Price vs 200 DMA: {midcap150['vs200']}%

RSI 14: {midcap150['rsi']}
RSI Status: {midcap150['rsi_status']}
Trend: {midcap150['trend']}


🔴 SMALL CAP
NIFTY SMALLCAP 250

Price: {smallcap250['close']}
Daily Change: {smallcap250['change']}%

20 DMA: {smallcap250['dma20']}
50 DMA: {smallcap250['dma50']}
200 DMA: {smallcap250['dma200']}

Price vs 50 DMA: {smallcap250['vs50']}%
Price vs 200 DMA: {smallcap250['vs200']}%

RSI 14: {smallcap250['rsi']}
RSI Status: {smallcap250['rsi_status']}
Trend: {smallcap250['trend']}


🌐 OVERALL MARKET
NIFTY 500

Price: {nifty500['close']}
Daily Change: {nifty500['change']}%

20 DMA: {nifty500['dma20']}
50 DMA: {nifty500['dma50']}
200 DMA: {nifty500['dma200']}

Price vs 50 DMA: {nifty500['vs50']}%
Price vs 200 DMA: {nifty500['vs200']}%

RSI 14: {nifty500['rsi']}
RSI Status: {nifty500['rsi_status']}
Trend: {nifty500['trend']}


🇮🇳 SENSEX

Price: {sensex['close']}
Daily Change: {sensex['change']}%

RSI 14: {sensex['rsi']}
RSI Status: {sensex['rsi_status']}
Trend: {sensex['trend']}


━━━━━━━━━━━━━━━━━━━━
🤖 AI WEALTH MANAGER
━━━━━━━━━━━━━━━━━━━━
"""


except Exception as e:

    message = f"""
❌ MARKET ANALYSIS ERROR

{str(e)}
"""


# ==========================================
# SEND MESSAGE TO TELEGRAM
# ==========================================

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

response = requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": message
    }
)

print("Status Code:", response.status_code)
print("Response:", response.text)
