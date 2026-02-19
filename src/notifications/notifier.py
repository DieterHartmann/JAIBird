"""
Notification system for JAIBird Stock Trading Platform.
Handles Telegram and email notifications for SENS announcements.
"""

import smtplib
import logging
import subprocess
import sys
import json
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import requests

from ..database.models import DatabaseManager, SensAnnouncement, Notification
from ..utils.config import get_config
from ..utils.dropbox_manager import DropboxManager


logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Custom exception for notification errors."""
    pass


class TelegramNotifier:
    """Handles Telegram notifications via subprocess to avoid async conflicts."""
    
    def __init__(self):
        self.config = get_config()
    
    def send_urgent_notification(self, announcement: SensAnnouncement) -> bool:
        """Send urgent SENS notification via Telegram using subprocess."""
        if not self.config.telegram_notifications_enabled:
            logger.warning("Telegram notifications are disabled")
            return False
        
        if self.config.test_mode:
            logger.info(f"TEST MODE: Would send Telegram notification for SENS {announcement.sens_number}")
            return True
        
        try:
            # Prefer a Dropbox shared link if available
            pdf_link = None
            try:
                if getattr(announcement, 'dropbox_pdf_path', ''):
                    dbx = DropboxManager()
                    pdf_link = dbx.create_shared_link(announcement.dropbox_pdf_path)
            except Exception as _e:
                logger.debug(f"Could not create Dropbox shared link: {_e}")

            # Create message data
            message_data = {
                'type': 'urgent',
                'sens_number': announcement.sens_number,
                'company_name': announcement.company_name,
                'title': announcement.title,
                'urgent_reason': announcement.urgent_reason,
                'date_published': announcement.date_published.isoformat() if announcement.date_published else None,
                # Prefer Dropbox shared link; fallback to original JSE URL
                'pdf_link': pdf_link or announcement.pdf_url,
                'ai_summary': getattr(announcement, 'ai_summary', ''),
                'local_pdf_path': getattr(announcement, 'local_pdf_path', '')
            }
            
            return self._send_telegram_message(message_data)
            
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """Send a test message to verify Telegram setup."""
        if not self.config.telegram_notifications_enabled:
            return False
        
        try:
            message_data = {
                'type': 'test',
                'message': '🤖 JAIBird Test Message\n\nTelegram notifications are working correctly!'
            }
            
            return self._send_telegram_message(message_data)
            
        except Exception as e:
            logger.error(f"Failed to send test Telegram message: {e}")
            return False
    
    def send_pdf_file(self, sens_number: str, pdf_path: str, company_name: str = "") -> bool:
        """Send PDF file via Telegram."""
        if not self.config.telegram_notifications_enabled:
            logger.warning("Telegram notifications are disabled")
            return False
        
        if not Path(pdf_path).exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return False
        
        try:
            message_data = {
                'type': 'pdf',
                'sens_number': sens_number,
                'pdf_path': pdf_path,
                'company_name': company_name
            }
            
            return self._send_telegram_message(message_data)
            
        except Exception as e:
            logger.error(f"Failed to send PDF via Telegram: {e}")
            return False
    
    def _send_telegram_message(self, message_data: dict) -> bool:
        """Send message via subprocess to avoid async conflicts."""
        try:
            # Create temporary file with message data
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(message_data, f)
                temp_file = f.name
            
            # Call the telegram sender subprocess
            script_path = os.path.join(os.path.dirname(__file__), 'telegram_sender.py')
            # Use the same interpreter to avoid PATH issues
            python_exe = sys.executable or 'python'
            result = subprocess.run([
                python_exe, script_path, temp_file
            ], capture_output=True, text=True, timeout=30)
            
            # Clean up temp file
            os.unlink(temp_file)
            
            if result.returncode == 0:
                logger.info("Telegram message sent successfully via subprocess")
                return True
            else:
                logger.error(f"Telegram subprocess failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Telegram subprocess timed out")
            return False
        except Exception as e:
            logger.error(f"Error in telegram subprocess: {e}")
            return False


class EmailNotifier:
    """Handles email notifications."""
    
    def __init__(self):
        self.config = get_config()
        self._dbx = None
    
    def _resolve_pdf_link(self, announcement: SensAnnouncement) -> str:
        """Prefer a Dropbox shared link; fallback to original URL or empty string."""
        try:
            dropbox_path = getattr(announcement, 'dropbox_pdf_path', '')
            if dropbox_path:
                if self._dbx is None:
                    self._dbx = DropboxManager()
                link = self._dbx.create_shared_link(dropbox_path)
                if link:
                    return link
        except Exception as e:
            logger.debug(f"Could not create Dropbox shared link for email: {e}")
        return getattr(announcement, 'pdf_url', '') or ''
    
    def _send_email(self, msg):
        """Helper method to send email with proper SSL/TLS handling."""
        smtp_server, smtp_port = self.config.get_smtp_settings()
        
        if self.config.email_use_ssl:
            # Use SSL connection (typically port 465)
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
        else:
            # Use regular SMTP with optional STARTTLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                if self.config.email_use_tls:
                    server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
    
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
            
            # Send email using helper method
            self._send_email(msg)
            
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
            
            # Send email using helper method
            self._send_email(msg)
            
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
                pdf_link = self._resolve_pdf_link(announcement)
                
                html += f"""
                <div class="{css_class}">
                    <div class="company">{announcement.company_name}</div>
                    <div class="sens-number">SENS {announcement.sens_number}</div>
                    <div class="title">{announcement.title}</div>
                    <div class="date">{announcement.date_published.strftime('%H:%M') if announcement.date_published else 'Unknown time'}</div>
                    {f'<div style="color: #dc2626; font-weight: bold;">⚠️ {announcement.urgent_reason}</div>' if announcement.urgent_reason else ''}
                    {f'<div><a href="{pdf_link}">View PDF</a></div>' if pdf_link else ''}
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
        pdf_link = self._resolve_pdf_link(announcement)
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
                        {f'<p><strong>PDF:</strong> <a href="{pdf_link}">Download PDF</a></p>' if pdf_link else ''}
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
            
            # Send email using helper method
            self._send_email(msg)
            
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
