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
        raise Exception(
            f"Not enough historical data available for {symbol}"
        )

    close = float(data["Close"].iloc[-1])

    previous_close = float(data["Close"].iloc[-2])

    daily_change = (
        (close - previous_close) / previous_close
    ) * 100

    dma20 = data["Close"].rolling(20).mean().iloc[-1]
    dma50 = data["Close"].rolling(50).mean().iloc[-1]
    dma200 = data["Close"].rolling(200).mean().iloc[-1]

    price_vs_50 = (
        (close - dma50) / dma50
    ) * 100

    price_vs_200 = (
        (close - dma200) / dma200
    ) * 100

    return {
        "close": round(close, 2),
        "change": round(daily_change, 2),
        "dma20": round(float(dma20), 2),
        "dma50": round(float(dma50), 2),
        "dma200": round(float(dma200), 2),
        "vs50": round(float(price_vs_50), 2),
        "vs200": round(float(price_vs_200), 2)
    }


try:

    # ==========================================
    # MARKET INDICES
    # ==========================================

    nifty50 = get_index_data("^NSEI")

    nifty100 = get_index_data("^CNX100")

    midcap150 = get_index_data(
        "NIFTYMIDCAP150.NS"
    )

    smallcap250 = get_index_data(
        "NIFTYSMLCAP250.NS"
    )

    nifty500 = get_index_data("^CRSLDX")

    sensex = get_index_data("^BSESN")


    # ==========================================
    # TELEGRAM MESSAGE
    # ==========================================

    message = f"""
📊 MARKET ANALYSIS REPORT
━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price: {nifty50['close']}
Daily: {nifty50['change']}%

20 DMA: {nifty50['dma20']}
50 DMA: {nifty50['dma50']}
200 DMA: {nifty50['dma200']}

Price vs 50 DMA: {nifty50['vs50']}%
Price vs 200 DMA: {nifty50['vs200']}%


🟢 LARGE CAP
NIFTY 100

Price: {nifty100['close']}
Daily: {nifty100['change']}%

20 DMA: {nifty100['dma20']}
50 DMA: {nifty100['dma50']}
200 DMA: {nifty100['dma200']}

Price vs 50 DMA: {nifty100['vs50']}%
Price vs 200 DMA: {nifty100['vs200']}%


🟡 MID CAP
NIFTY MIDCAP 150

Price: {midcap150['close']}
Daily: {midcap150['change']}%

20 DMA: {midcap150['dma20']}
50 DMA: {midcap150['dma50']}
200 DMA: {midcap150['dma200']}

Price vs 50 DMA: {midcap150['vs50']}%
Price vs 200 DMA: {midcap150['vs200']}%


🔴 SMALL CAP
NIFTY SMALLCAP 250

Price: {smallcap250['close']}
Daily: {smallcap250['change']}%

20 DMA: {smallcap250['dma20']}
50 DMA: {smallcap250['dma50']}
200 DMA: {smallcap250['dma200']}

Price vs 50 DMA: {smallcap250['vs50']}%
Price vs 200 DMA: {smallcap250['vs200']}%


🌐 OVERALL MARKET
NIFTY 500

Price: {nifty500['close']}
Daily: {nifty500['change']}%

20 DMA: {nifty500['dma20']}
50 DMA: {nifty500['dma50']}
200 DMA: {nifty500['dma200']}

Price vs 50 DMA: {nifty500['vs50']}%
Price vs 200 DMA: {nifty500['vs200']}%


🇮🇳 SENSEX

Price: {sensex['close']}
Daily: {sensex['change']}%

━━━━━━━━━━━━━━━━━━━━
🤖 AI WEALTH MANAGER
Data Analysis Phase
━━━━━━━━━━━━━━━━━━━━
"""


except Exception as e:

    message = f"""
❌ MARKET ANALYSIS ERROR

{str(e)}
"""


# ==========================================
# SEND TO TELEGRAM
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
