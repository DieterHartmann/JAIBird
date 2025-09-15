#!/usr/bin/env python3
"""
Standalone Telegram sender process for JAIBird.
Handles async Telegram operations in isolation to avoid event loop conflicts.
"""

import sys
import json
import asyncio
import logging
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram import Bot
from telegram.error import TelegramError
from src.utils.config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def send_telegram_message(message_data: dict, config) -> bool:
    """Send Telegram message asynchronously."""
    try:
        bot = Bot(token=config.telegram_bot_token)
        
        if message_data['type'] == 'test':
            # Send test message
            await bot.send_message(
                chat_id=config.telegram_chat_id,
                text=message_data['message']
            )
            logger.info("Test Telegram message sent successfully")
            
        elif message_data['type'] == 'urgent':
            # Format urgent message
            message = format_urgent_message(message_data)
            
            # Send urgent message
            await bot.send_message(
                chat_id=config.telegram_chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            logger.info(f"Urgent Telegram notification sent for SENS {message_data['sens_number']}")
        
        return True
        
    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}")
        return False


def format_urgent_message(data: dict) -> str:
    """Format urgent announcement message for Telegram."""
    urgency_emoji = "🚨" if data.get('urgent_reason') else "📢"
    
    message = f"{urgency_emoji} *URGENT SENS ANNOUNCEMENT*\n\n"
    message += f"*Company:* {data['company_name']}\n"
    message += f"*SENS Number:* {data['sens_number']}\n"
    message += f"*Title:* {data['title']}\n\n"
    
    if data.get('urgent_reason'):
        message += f"*Urgent Reason:* {data['urgent_reason']}\n\n"
    
    if data.get('date_published'):
        from datetime import datetime
        try:
            date_obj = datetime.fromisoformat(data['date_published'])
            message += f"*Published:* {date_obj.strftime('%Y-%m-%d %H:%M')}\n"
        except:
            message += f"*Published:* {data['date_published']}\n"
    
    if data.get('pdf_url'):
        message += f"*PDF Link:* {data['pdf_url']}\n"
    
    message += f"\n_JAIBird Alert System_"
    
    return message


async def test_telegram_connection(config) -> bool:
    """Test Telegram bot connection."""
    try:
        bot = Bot(token=config.telegram_bot_token)
        bot_info = await bot.get_me()
        logger.info(f"Telegram bot connected: @{bot_info.username}")
        return True
    except Exception as e:
        logger.error(f"Telegram connection test failed: {e}")
        return False


def main():
    """Main function for standalone Telegram sender."""
    if len(sys.argv) < 2:
        print("Usage: python telegram_sender.py <message_file.json> [test]")
        sys.exit(1)
    
    try:
        # Load configuration
        config = get_config()
        
        if not config.telegram_notifications_enabled:
            logger.error("Telegram notifications are disabled")
            sys.exit(1)
        
        # Check if this is a connection test
        if len(sys.argv) > 2 and sys.argv[2] == 'test':
            success = asyncio.run(test_telegram_connection(config))
            sys.exit(0 if success else 1)
        
        # Load message data
        message_file = sys.argv[1]
        with open(message_file, 'r') as f:
            message_data = json.load(f)
        
        # Send message
        success = asyncio.run(send_telegram_message(message_data, config))
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Telegram sender failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
