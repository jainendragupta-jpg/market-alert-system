import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

message = """
✅ Market Alert System Started

Repository Connected Successfully
GitHub Actions Working
Telegram Working
"""

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

if response.status_code == 200:
    print("Message Sent Successfully")
else:
    print("Telegram Error")
