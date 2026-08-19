import os
import requests
import yfinance as yf

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def get_index_data(symbol):
    data = yf.Ticker(symbol).history(
        period="5d",
        auto_adjust=False
    )

    if data.empty or len(data) < 2:
        raise Exception(f"No sufficient data available for {symbol}")

    close = float(data["Close"].iloc[-1])
    previous_close = float(data["Close"].iloc[-2])

    change = ((close - previous_close) / previous_close) * 100

    return round(close, 2), round(change, 2)


try:

    # ==========================================
    # NIFTY 50
    # ==========================================
    nifty50_close, nifty50_change = get_index_data("^NSEI")


    # ==========================================
    # LARGE CAP - NIFTY 100
    # ==========================================
    nifty100_close, nifty100_change = get_index_data("^CNX100")


    # ==========================================
    # MID CAP - NIFTY MIDCAP 150
    # ==========================================
    midcap150_close, midcap150_change = get_index_data(
        "NIFTYMIDCAP150.NS"
    )


    # ==========================================
    # SMALL CAP - NIFTY SMALLCAP 250
    # ==========================================
    smallcap250_close, smallcap250_change = get_index_data(
        "NIFTYSMLCAP250.NS"
    )


    # ==========================================
    # OVERALL MARKET - NIFTY 500
    # ==========================================
    nifty500_close, nifty500_change = get_index_data("^CRSLDX")


    # ==========================================
    # SENSEX
    # ==========================================
    sensex_close, sensex_change = get_index_data("^BSESN")


    # ==========================================
    # TELEGRAM MESSAGE
    # ==========================================

    message = f"""
📊 DAILY MARKET REPORT
━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50
Price: {nifty50_close}
Change: {nifty50_change}%

🟢 LARGE CAP
NIFTY 100
Price: {nifty100_close}
Change: {nifty100_change}%

🟡 MID CAP
NIFTY MIDCAP 150
Price: {midcap150_close}
Change: {midcap150_change}%

🔴 SMALL CAP
NIFTY SMALLCAP 250
Price: {smallcap250_close}
Change: {smallcap250_change}%

🌐 OVERALL MARKET
NIFTY 500
Price: {nifty500_close}
Change: {nifty500_change}%

🇮🇳 SENSEX
Price: {sensex_close}
Change: {sensex_change}%

━━━━━━━━━━━━━━━━━━━━
✅ GitHub Actions Active
🤖 Telegram Bot Active
"""


except Exception as e:

    message = f"""
❌ MARKET DATA ERROR

{str(e)}

Please check Yahoo Finance ticker/data availability.
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
