"""
Notification system for JAIBird Stock Trading Platform.
Handles Telegram and email notifications for SENS announcements.
"""

import smtplib
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import requests
from telegram import Bot
from telegram.error import TelegramError

from ..database.models import DatabaseManager, SensAnnouncement, Notification
from ..utils.config import get_config


logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Custom exception for notification errors."""
    pass


class TelegramNotifier:
    """Handles Telegram notifications."""
    
    def __init__(self):
        self.config = get_config()
        self.bot = None
        self._initialize_bot()
    
    def _initialize_bot(self):
        """Initialize Telegram bot."""
        try:
            if not self.config.telegram_notifications_enabled:
                logger.info("Telegram notifications are disabled")
                return
            
            self.bot = Bot(token=self.config.telegram_bot_token)
            # Test the bot
            bot_info = self.bot.get_me()
            logger.info(f"Telegram bot initialized: @{bot_info.username}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            if not self.config.test_mode:
                raise NotificationError(f"Telegram initialization failed: {e}")
    
    def send_urgent_notification(self, announcement: SensAnnouncement) -> bool:
        """Send urgent SENS notification via Telegram."""
        if not self.config.telegram_notifications_enabled or not self.bot:
            logger.warning("Telegram notifications disabled or bot not initialized")
            return False
        
        if self.config.test_mode:
            logger.info(f"TEST MODE: Would send Telegram notification for SENS {announcement.sens_number}")
            return True
        
        try:
            # Format the message
            message = self._format_urgent_message(announcement)
            
            # Send the message
            self.bot.send_message(
                chat_id=self.config.telegram_chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            logger.info(f"Sent urgent Telegram notification for SENS {announcement.sens_number}")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram error sending notification for SENS {announcement.sens_number}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification: {e}")
            return False
    
    def _format_urgent_message(self, announcement: SensAnnouncement) -> str:
        """Format urgent announcement message for Telegram."""
        urgency_emoji = "🚨" if announcement.is_urgent else "📢"
        
        message = f"{urgency_emoji} *URGENT SENS ANNOUNCEMENT*\n\n"
        message += f"*Company:* {announcement.company_name}\n"
        message += f"*SENS Number:* {announcement.sens_number}\n"
        message += f"*Title:* {announcement.title}\n\n"
        
        if announcement.urgent_reason:
            message += f"*Urgent Reason:* {announcement.urgent_reason}\n\n"
        
        message += f"*Published:* {announcement.date_published.strftime('%Y-%m-%d %H:%M') if announcement.date_published else 'Unknown'}\n"
        
        if announcement.pdf_url:
            message += f"*PDF Link:* {announcement.pdf_url}\n"
        
        message += f"\n_JAIBird Alert System_"
        
        return message
    
    def send_test_message(self) -> bool:
        """Send a test message to verify Telegram setup."""
        if not self.bot:
            return False
        
        try:
            test_message = "🤖 JAIBird Test Message\n\nTelegram notifications are working correctly!"
            self.bot.send_message(
                chat_id=self.config.telegram_chat_id,
                text=test_message
            )
            logger.info("Test Telegram message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send test Telegram message: {e}")
            return False


class EmailNotifier:
    """Handles email notifications."""
    
    def __init__(self):
        self.config = get_config()
    
    def send_daily_digest(self, announcements: List[SensAnnouncement]) -> bool:
        """Send daily digest email with all SENS announcements."""
        if not self.config.email_notifications_enabled:
            logger.warning("Email notifications are disabled")
            return False
        
        if self.config.test_mode:
            logger.info(f"TEST MODE: Would send daily digest email with {len(announcements)} announcements")
            return True
        
        try:
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"JAIBird Daily SENS Digest - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = self.config.email_username
            msg['To'] = self.config.notification_email
            
            # Create HTML content
            html_content = self._create_daily_digest_html(announcements)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            logger.info(f"Sent daily digest email with {len(announcements)} announcements")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily digest email: {e}")
            return False
    
    def send_watchlist_alert(self, announcement: SensAnnouncement) -> bool:
        """Send email alert for watchlist company announcement."""
        if not self.config.email_notifications_enabled:
            logger.warning("Email notifications are disabled")
            return False
        
        if self.config.test_mode:
            logger.info(f"TEST MODE: Would send watchlist email alert for SENS {announcement.sens_number}")
            return True
        
        try:
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"JAIBird Alert: {announcement.company_name} - SENS {announcement.sens_number}"
            msg['From'] = self.config.email_username
            msg['To'] = self.config.notification_email
            
            # Create HTML content
            html_content = self._create_watchlist_alert_html(announcement)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            logger.info(f"Sent watchlist email alert for SENS {announcement.sens_number}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send watchlist email alert: {e}")
            return False
    
    def _create_daily_digest_html(self, announcements: List[SensAnnouncement]) -> str:
        """Create HTML content for daily digest email."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #1e3a8a; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .announcement {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }}
                .urgent {{ border-left: 5px solid #dc2626; background-color: #fef2f2; }}
                .watchlist {{ border-left: 5px solid #059669; background-color: #f0fdf4; }}
                .company {{ font-weight: bold; color: #1e3a8a; }}
                .sens-number {{ color: #6b7280; font-size: 0.9em; }}
                .title {{ margin: 10px 0; }}
                .date {{ color: #6b7280; font-size: 0.9em; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #6b7280; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 JAIBird Daily SENS Digest</h1>
                <p>{datetime.now().strftime('%A, %B %d, %Y')}</p>
            </div>
            
            <div class="content">
                <h2>Summary</h2>
                <p>Total announcements: <strong>{len(announcements)}</strong></p>
                <p>Urgent announcements: <strong>{len([a for a in announcements if a.is_urgent])}</strong></p>
                <p>Watchlist companies: <strong>{len([a for a in announcements if self._is_watchlist_company(a.company_name)])}</strong></p>
        """
        
        if not announcements:
            html += "<p>No SENS announcements today.</p>"
        else:
            html += "<h2>Announcements</h2>"
            
            for announcement in sorted(announcements, key=lambda x: (not x.is_urgent, x.date_published or datetime.min)):
                css_class = "announcement"
                if announcement.is_urgent:
                    css_class += " urgent"
                elif self._is_watchlist_company(announcement.company_name):
                    css_class += " watchlist"
                
                html += f"""
                <div class="{css_class}">
                    <div class="company">{announcement.company_name}</div>
                    <div class="sens-number">SENS {announcement.sens_number}</div>
                    <div class="title">{announcement.title}</div>
                    <div class="date">{announcement.date_published.strftime('%H:%M') if announcement.date_published else 'Unknown time'}</div>
                    {f'<div style="color: #dc2626; font-weight: bold;">⚠️ {announcement.urgent_reason}</div>' if announcement.urgent_reason else ''}
                    {f'<div><a href="{announcement.pdf_url}">View PDF</a></div>' if announcement.pdf_url else ''}
                </div>
                """
        
        html += """
                <div class="footer">
                    <p>This digest was generated by JAIBird Stock Trading Platform.</p>
                    <p>🟢 Green border: Watchlist company | 🔴 Red border: Urgent announcement</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _create_watchlist_alert_html(self, announcement: SensAnnouncement) -> str:
        """Create HTML content for watchlist alert email."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #059669; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .alert-box {{ border: 2px solid #059669; padding: 20px; border-radius: 10px; background-color: #f0fdf4; }}
                .company {{ font-size: 1.5em; font-weight: bold; color: #059669; }}
                .sens-number {{ color: #6b7280; font-size: 1.1em; margin: 10px 0; }}
                .title {{ font-size: 1.2em; margin: 15px 0; }}
                .details {{ margin: 20px 0; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #6b7280; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎯 JAIBird Watchlist Alert</h1>
            </div>
            
            <div class="content">
                <div class="alert-box">
                    <div class="company">{announcement.company_name}</div>
                    <div class="sens-number">SENS Number: {announcement.sens_number}</div>
                    <div class="title">{announcement.title}</div>
                    
                    <div class="details">
                        <p><strong>Published:</strong> {announcement.date_published.strftime('%Y-%m-%d %H:%M') if announcement.date_published else 'Unknown'}</p>
                        {f'<p><strong>⚠️ Urgent:</strong> {announcement.urgent_reason}</p>' if announcement.urgent_reason else ''}
                        {f'<p><strong>PDF:</strong> <a href="{announcement.pdf_url}">Download PDF</a></p>' if announcement.pdf_url else ''}
                    </div>
                </div>
                
                <div class="footer">
                    <p>This alert was generated because {announcement.company_name} is on your watchlist.</p>
                    <p>JAIBird Stock Trading Platform</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _is_watchlist_company(self, company_name: str) -> bool:
        """Check if company is on watchlist (simplified for email formatting)."""
        # This would normally check against the database
        # For now, return False to avoid circular imports
        return False
    
    def send_test_email(self) -> bool:
        """Send a test email to verify email setup."""
        if not self.config.email_notifications_enabled:
            return False
        
        try:
            msg = MIMEText("JAIBird Test Email\n\nEmail notifications are working correctly!")
            msg['Subject'] = "JAIBird Test Email"
            msg['From'] = self.config.email_username
            msg['To'] = self.config.notification_email
            
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            logger.info("Test email sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False


class NotificationManager:
    """Main notification manager that coordinates all notification types."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.config = get_config()
        self.db_manager = db_manager
        self.telegram = TelegramNotifier()
        self.email = EmailNotifier()
    
    def process_new_announcement(self, announcement: SensAnnouncement) -> bool:
        """Process a new announcement and send appropriate notifications."""
        success = True
        
        try:
            # Check if company is on watchlist
            is_watchlist_company = self.db_manager.is_company_on_watchlist(announcement.company_name)
            
            # Send urgent Telegram notification if needed
            if announcement.is_urgent or is_watchlist_company:
                telegram_success = self.telegram.send_urgent_notification(announcement)
                
                # Log notification attempt
                notification = Notification(
                    sens_id=announcement.id,
                    notification_type='telegram',
                    status='sent' if telegram_success else 'failed',
                    error_message='' if telegram_success else 'Failed to send Telegram notification'
                )
                self.db_manager.log_notification(notification)
                
                if not telegram_success:
                    success = False
            
            # Send email alert for watchlist companies
            if is_watchlist_company:
                email_success = self.email.send_watchlist_alert(announcement)
                
                # Log notification attempt
                notification = Notification(
                    sens_id=announcement.id,
                    notification_type='email',
                    status='sent' if email_success else 'failed',
                    error_message='' if email_success else 'Failed to send email alert'
                )
                self.db_manager.log_notification(notification)
                
                if not email_success:
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing notification for SENS {announcement.sens_number}: {e}")
            return False
    
    def send_daily_digest(self) -> bool:
        """Send daily digest email with recent announcements."""
        try:
            # Get announcements from the last day
            recent_announcements = self.db_manager.get_recent_sens(days=1)
            
            if not recent_announcements and not self.config.test_mode:
                logger.info("No announcements for daily digest")
                return True
            
            # Send digest email
            email_success = self.email.send_daily_digest(recent_announcements)
            
            # Log digest attempt
            if recent_announcements:
                for announcement in recent_announcements:
                    notification = Notification(
                        sens_id=announcement.id,
                        notification_type='email_digest',
                        status='sent' if email_success else 'failed',
                        error_message='' if email_success else 'Failed to send daily digest'
                    )
                    self.db_manager.log_notification(notification)
            
            return email_success
            
        except Exception as e:
            logger.error(f"Error sending daily digest: {e}")
            return False
    
    def test_notifications(self) -> dict:
        """Test all notification systems."""
        results = {}
        
        # Test Telegram
        if self.config.telegram_notifications_enabled:
            results['telegram'] = self.telegram.send_test_message()
        else:
            results['telegram'] = 'disabled'
        
        # Test Email
        if self.config.email_notifications_enabled:
            results['email'] = self.email.send_test_email()
        else:
            results['email'] = 'disabled'
        
        return results
