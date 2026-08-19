import os
import requests
import yfinance as yf

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

try:
    # Nifty 50
    nifty = yf.Ticker("^NSEI")
    nifty_data = nifty.history(period="2d")

    nifty_close = round(nifty_data["Close"].iloc[-1], 2)
    nifty_prev = round(nifty_data["Close"].iloc[-2], 2)

    nifty_change = round(
        ((nifty_close - nifty_prev) / nifty_prev) * 100,
        2
    )

    # Sensex
    sensex = yf.Ticker("^BSESN")
    sensex_data = sensex.history(period="2d")

    sensex_close = round(sensex_data["Close"].iloc[-1], 2)

    message = f"""
📊 Daily Market Report

🇮🇳 NIFTY 50: {nifty_close}
📈 Change: {nifty_change}%

🇮🇳 SENSEX: {sensex_close}

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
