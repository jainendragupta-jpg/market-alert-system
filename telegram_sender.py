import requests
import logging
from typing import Dict, Any

class TelegramReporter:
    """Formats market data and pushes formatted notifications to Telegram API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){self.bot_token}/sendMessage"

    def format_message(self, data: Dict[str, Any]) -> str:
        news_items = data.get("high_impact_news", [])
        outlook = data.get("market_outlook")

        if not news_items:
            return ""

        msg = "🚨 <b>GLOBAL MARKET IMPACT ALERT</b> 🚨\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

        for idx, item in enumerate(news_items[:8], 1):
            msg += f"<b>{idx}️⃣ {item['headline']}</b>\n"
            msg += f"🔥 <b>Impact Score:</b> {item.get('impact_score', 'N/A')}/100\n"
            msg += f"📝 <b>Summary:</b> {item['summary']}\n"
            
            msg += "📊 <b>Impact:</b>\n"
            for imp in item.get('impact_details', []):
                direction_emoji = "📈" if "bullish" in imp['direction'].lower() else "📉" if "bearish" in imp['direction'].lower() else "➖"
                msg += f"  • {imp['asset']}: {direction_emoji} {imp['direction']}\n"
            
            msg += f"🔗 <a href='{item['link']}'>Read Full Source</a>\n\n"

        if outlook:
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += "📈 <b>GLOBAL MARKET OUTLOOK</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🗓 <b>1 Month:</b> {outlook.get('outlook_1m', 'N/A')}\n"
            msg += f"🗓 <b>3 Months:</b> {outlook.get('outlook_3m', 'N/A')}\n"
            msg += f"🗓 <b>6 Months:</b> {outlook.get('outlook_6m', 'N/A')}\n\n"

            msg += "⚠️ <b>Key Risks:</b>\n"
            for r in outlook.get("key_risks", []):
                msg += f" • {r}\n"

            msg += "\n💡 <b>Key Opportunities:</b>\n"
            for o in outlook.get("key_opportunities", []):
                msg += f" • {o}\n"

            action = outlook.get("investor_action_summary", {})
            if action:
                msg += "\n🎯 <b>INVESTOR ACTION SUMMARY</b>\n"
                msg += f"👀 <b>Watch:</b> {action.get('what_to_watch', 'N/A')}\n"
                msg += f"🟢 <b>Gaining Sectors:</b> {action.get('benefiting_sectors', 'N/A')}\n"
                msg += f"🔴 <b>Pressured Sectors:</b> {action.get('pressured_sectors', 'N/A')}\n"
                msg += f"💼 <b>Equities & MFs:</b> {action.get('equities_impact', 'N/A')}\n"
                msg += f"🥇 <b>Gold:</b> {action.get('gold_impact', 'N/A')}\n"
                msg += f"🛢 <b>Crude Oil:</b> {action.get('crude_oil_impact', 'N/A')}\n"

        return msg

    def send_notification(self, message: str) -> bool:
        if not message:
            logging.info("No message content generated. Skipping Telegram dispatch.")
            return True

        # Telegram limits messages to 4096 characters. Split if exceeded.
        chunks = [message[i:i + 4000] for i in range(0, len(message), 4000)]
        
        for chunk in chunks:
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            try:
                response = requests.post(self.api_url, json=payload, timeout=15)
                res_data = response.json()
                if not res_data.get("ok"):
                    logging.error(f"Telegram API Error: {res_data}")
                    return False
            except Exception as e:
                logging.error(f"Failed to post alert to Telegram: {e}")
                return False

        logging.info("Telegram notification sent successfully!")
        return True
