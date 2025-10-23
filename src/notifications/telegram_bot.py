#!/usr/bin/env python3
"""
Telegram Bot Handler for JAIBird Interactive Features.
Handles callback queries for PDF requests and other interactive features.
"""

import sys
import json
import asyncio
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram import Update, Bot
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from src.utils.config import get_config
from src.database.models import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JAIBirdTelegramBot:
    """Interactive Telegram bot for JAIBird."""
    
    def __init__(self, config):
        self.config = config
        self.db_manager = DatabaseManager(config.database_path)
        self.application = None
        
    async def start_bot(self):
        """Start the Telegram bot with handlers."""
        try:
            # Create application
            self.application = Application.builder().token(self.config.telegram_bot_token).build()
            
            # Add handlers
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            # Start the bot
            logger.info("Starting JAIBird Telegram bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("JAIBird Telegram bot is running...")
            
            # Keep the bot running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error starting Telegram bot: {e}")
            raise
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons."""
        query = update.callback_query
        await query.answer()  # Acknowledge the callback
        
        try:
            callback_data = query.data
            logger.info(f"Received callback: {callback_data}")
            
            if callback_data.startswith("pdf:"):
                # Extract SENS number
                sens_number = callback_data.split(":", 1)[1]
                await self.send_pdf_for_sens(query, sens_number)
            else:
                await query.edit_message_text("❌ Unknown command")
                
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await query.edit_message_text("❌ Error processing request")
    
    async def send_pdf_for_sens(self, query, sens_number: str):
        """Send PDF file for the requested SENS number."""
        try:
            # Get SENS announcement from database
            announcement = self.db_manager.get_sens_by_number(sens_number)
            
            if not announcement:
                await query.edit_message_text(f"❌ SENS {sens_number} not found in database")
                return
            
            # Check if PDF file exists
            if not announcement.local_pdf_path or not Path(announcement.local_pdf_path).exists():
                await query.edit_message_text(f"❌ PDF file not found for SENS {sens_number}")
                return
            
            # Send PDF file using the application's bot
            bot = self.application.bot
            
            with open(announcement.local_pdf_path, 'rb') as pdf_file:
                await bot.send_document(
                    chat_id=query.message.chat_id,
                    document=pdf_file,
                    filename=f"SENS_{sens_number}.pdf",
                    caption=f"📄 SENS {sens_number} - {announcement.company_name}\n\n_{announcement.title}_"
                )
            
            # Update the original message to show PDF was sent
            await query.edit_message_text(
                query.message.text + f"\n\n✅ _PDF sent successfully!_",
                parse_mode='Markdown'
            )
            
            logger.info(f"PDF sent for SENS {sens_number}")
            
        except Exception as e:
            logger.error(f"Error sending PDF for SENS {sens_number}: {e}")
            await query.edit_message_text(f"❌ Error sending PDF: {str(e)}")


async def run_bot():
    """Run the Telegram bot."""
    try:
        config = get_config()
        
        if not config.telegram_notifications_enabled:
            logger.error("Telegram notifications are disabled")
            return
        
        bot = JAIBirdTelegramBot(config)
        await bot.start_bot()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


def main():
    """Main function for standalone bot runner."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
