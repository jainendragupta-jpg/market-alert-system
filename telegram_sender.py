import re
import requests
import logging
from typing import Dict, Any

class TelegramReporter:
    """Formats market data and pushes formatted notifications to Telegram API."""

    def __init__(self, bot_token: str, chat_id: str):
        # Strip accidental Markdown link wrappers, URLs, and quotes from secrets
        raw_token = re.sub(r'\[.*?\]\(.*?\)', '', str(bot_token))
        raw_token = re.sub(r'https?://\S+', '', raw_token)
        self.bot_token = raw_token.strip(" '\"<>[]")
        
        self.chat_id = str(chat_id).strip(" '\"")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def format_message(self, data: Dict[str, Any]) -> str:
        news_items = data.get("high_impact_news", [])
        outlook = data.get("market_outlook")

        if not news_items:
            return ""

        msg = "🚨 <b>GLOBAL & INDIAN MARKET ALERT</b> 🚨\n"
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
            msg += "🇮🇳 <b>INDIAN & GLOBAL MARKET OUTLOOK</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🗓 <b>Nifty 1-Month:</b> {outlook.get('nifty_outlook_1m', 'N/A')}\n"
            msg += f"🗓 <b>Nifty 3-Month:</b> {outlook.get('nifty_outlook_3m', 'N/A')}\n"
            msg += f"🗓 <b>Nifty 6-Month:</b> {outlook.get('nifty_outlook_6m', 'N/A')}\n"
            msg += f"🇺🇸 <b>US S&P500 3-Month:</b> {outlook.get('us_market_outlook_3m', 'N/A')}\n\n"

            msg += "⚠️ <b>Key India Risks:</b>\n"
            for r in outlook.get("key_risks_india", []):
                msg += f" • {r}\n"

            msg += "\n💡 <b>Key India Opportunities:</b>\n"
            for o in outlook.get("key_opportunities_india", []):
                msg += f" • {o}\n"

            action = outlook.get("investor_action_summary", {})
            if action:
                msg += "\n🎯 <b>INDIAN INVESTOR ACTION SUMMARY</b>\n"
                msg += f"👀 <b>What to Watch:</b> {action.get('what_to_watch', 'N/A')}\n"
                msg += f"🟢 <b>Gaining Indian Sectors:</b> {action.get('indian_sectors_benefiting', 'N/A')}\n"
                msg += f"🔴 <b>Pressured Indian Sectors:</b> {action.get('indian_sectors_pressured', 'N/A')}\n"
                msg += f"📊 <b>Nifty & Large Caps:</b> {action.get('nifty_sensex_impact', 'N/A')}\n"
                msg += f"🚀 <b>MidCap & SmallCap:</b> {action.get('indian_mid_smallcap_impact', 'N/A')}\n"
                msg += f"💰 <b>Mutual Funds & SIPs:</b> {action.get('indian_mutual_funds_impact', 'N/A')}\n"
                msg += f"🇺🇸 <b>US Equities:</b> {action.get('us_markets_impact', 'N/A')}\n"
                msg += f"🥇 <b>Gold & Silver (MCX):</b> {action.get('gold_silver_impact', 'N/A')}\n"
                msg += f"🛢 <b>Crude Oil & USD/INR:</b> {action.get('crude_oil_inr_impact', 'N/A')}\n"

                # Impact Score Reference Chart
                msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
                msg += "📊 <b>IMPACT SCORE REFERENCE CHART</b>\n"
                msg += "━━━━━━━━━━━━━━━━━━━━\n"
                msg += "🔴 <b>80 - 100:</b> High Volatility / Major Market Shift\n"
                msg += "🟠 <b>60 - 79:</b> Moderate Impact / Sector Specific Movement\n"
                msg += "🟡 <b>40 - 59:</b> Mild Impact / Watchlist Alert\n"
                msg += "⚪ <b>0 - 39:</b> Low Impact / Market Noise\n"

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
