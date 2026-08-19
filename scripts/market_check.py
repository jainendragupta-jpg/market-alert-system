import os
import requests
import yfinance as yf

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def get_index_data(symbol):
    data = yf.Ticker(symbol).history(period="2d")

    close = round(data["Close"].iloc[-1], 2)
    previous_close = round(data["Close"].iloc[-2], 2)

    change = round(
        ((close - previous_close) / previous_close) * 100,
        2
    )

    return close, change


try:
    # Nifty 50
    nifty50_close, nifty50_change = get_index_data("^NSEI")

    # Nifty 100 - Large Cap
    nifty100_close, nifty100_change = get_index_data("^CNX100")

    # Nifty Midcap 150 - Mid Cap
    midcap150_close, midcap150_change = get_index_data("^NSEMDCP150")

    # Nifty Smallcap 250 - Small Cap
    smallcap250_close, smallcap250_change = get_index_data("^NIFTYSMLCAP250")

    # Nifty 500 - Overall Market
    nifty500_close, nifty500_change = get_index_data("^CRSLDX")

    # Sensex
    sensex_close, sensex_change = get_index_data("^BSESN")


    message = f"""
📊 DAILY MARKET REPORT

🇮🇳 NIFTY 50
Price: {nifty50_close}
Change: {nifty50_change}%

🟢 LARGE CAP - NIFTY 100
Price: {nifty100_close}
Change: {nifty100_change}%

🟡 MID CAP - NIFTY MIDCAP 150
Price: {midcap150_close}
Change: {midcap150_change}%

🔴 SMALL CAP - NIFTY SMALLCAP 250
Price: {smallcap250_close}
Change: {smallcap250_change}%

🌐 OVERALL MARKET - NIFTY 500
Price: {nifty500_close}
Change: {nifty500_change}%

🇮🇳 SENSEX
Price: {sensex_close}

✅ GitHub Actions Active
🤖 Telegram Bot Active
"""

except Exception as e:
    message = f"❌ Error fetching market data:\n{str(e)}"


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
