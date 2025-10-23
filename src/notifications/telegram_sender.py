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

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
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
            
            # Create interactive keyboard if PDF is available
            reply_markup = None
            if message_data.get('local_pdf_path') and Path(message_data['local_pdf_path']).exists():
                keyboard = [[
                    InlineKeyboardButton("📄 Send PDF", callback_data=f"pdf:{message_data['sens_number']}")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send urgent message
            await bot.send_message(
                chat_id=config.telegram_chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False,
                reply_markup=reply_markup
            )
            logger.info(f"Urgent Telegram notification sent for SENS {message_data['sens_number']}")
        
        elif message_data['type'] == 'pdf':
            # Send PDF file
            pdf_path = message_data.get('pdf_path')
            if pdf_path and Path(pdf_path).exists():
                with open(pdf_path, 'rb') as pdf_file:
                    await bot.send_document(
                        chat_id=config.telegram_chat_id,
                        document=pdf_file,
                        filename=f"SENS_{message_data['sens_number']}.pdf",
                        caption=f"📄 SENS {message_data['sens_number']} - {message_data.get('company_name', 'Unknown Company')}"
                    )
                logger.info(f"PDF sent for SENS {message_data['sens_number']}")
            else:
                await bot.send_message(
                    chat_id=config.telegram_chat_id,
                    text=f"❌ Sorry, PDF not found for SENS {message_data['sens_number']}"
                )
                logger.warning(f"PDF not found: {pdf_path}")
        
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
    
    message = f"{urgency_emoji} *WATCHLIST ALERT*\n\n"
    message += f"*Company:* {data['company_name']}\n"
    message += f"*SENS Number:* {data['sens_number']}\n"
    message += f"*Title:* {data['title']}\n\n"
    
    # Add AI Summary if available
    if data.get('ai_summary'):
        message += f"🤖 *AI Summary:*\n_{data['ai_summary']}_\n\n"
    
    if data.get('urgent_reason'):
        message += f"*Urgent Reason:* {data['urgent_reason']}\n\n"
    
    if data.get('date_published'):
        from datetime import datetime
        try:
            date_obj = datetime.fromisoformat(data['date_published'])
            message += f"*Published:* {date_obj.strftime('%Y-%m-%d %H:%M')}\n"
        except:
            message += f"*Published:* {data['date_published']}\n"
    
    # Prefer provided pdf_link (e.g., Dropbox shared link)
    if data.get('pdf_link'):
        message += f"*PDF Link:* {data['pdf_link']}\n"
    
    # Add instruction for PDF if available
    if data.get('local_pdf_path'):
        message += f"\n📄 _Click the button below to receive the full PDF document_"
    
    message += f"\n\n_JAIBird Alert System_"
    
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
