"""
JAIBird Stock Trading Platform - Main Entry Point
Coordinates all components and provides CLI interface.
"""

import os
import sys
import time
import logging
import argparse
import schedule
from datetime import datetime
from threading import Thread

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import get_config
from src.database.models import DatabaseManager
from src.scrapers.sens_scraper import SensScraper, run_initial_scrape, run_daily_scrape
from src.notifications.notifier import NotificationManager
from src.utils.dropbox_manager import DropboxManager
from src.web.app import run_app


logger = logging.getLogger(__name__)


class JAIBirdScheduler:
    """Main scheduler for JAIBird operations."""
    
    def __init__(self):
        self.config = get_config()
        self.db_manager = DatabaseManager(self.config.database_path)
        self.notification_manager = NotificationManager(self.db_manager)
        self.dropbox_manager = DropboxManager()
        self.scraper = SensScraper(self.db_manager)
        self.running = False
    
    def setup_schedules(self):
        """Set up scheduled tasks."""
        # Schedule SENS scraping every N minutes
        schedule.every(self.config.scrape_interval_minutes).minutes.do(self.scheduled_scrape)
        
        # Schedule daily digest at specified time
        schedule.every().day.at(self.config.daily_digest_time).do(self.send_daily_digest)
        
        # Schedule file cleanup daily at midnight
        schedule.every().day.at("00:00").do(self.cleanup_old_files)
        
        logger.info(f"Scheduled SENS scraping every {self.config.scrape_interval_minutes} minutes")
        logger.info(f"Scheduled daily digest at {self.config.daily_digest_time}")
        logger.info("Scheduled daily file cleanup at midnight")
    
    def scheduled_scrape(self):
        """Perform scheduled SENS scraping."""
        try:
            logger.info("Starting scheduled SENS scrape")
            announcements = self.scraper.scrape_daily_announcements()
            
            # Process notifications for new announcements
            for announcement in announcements:
                # Upload to Dropbox
                if announcement.local_pdf_path:
                    dropbox_path = self.dropbox_manager.upload_pdf(
                        announcement.local_pdf_path,
                        announcement.sens_number,
                        announcement.company_name
                    )
                    if dropbox_path:
                        # Update database with Dropbox path
                        announcement.dropbox_pdf_path = dropbox_path
                
                # Send notifications
                self.notification_manager.process_new_announcement(announcement)
            
            logger.info(f"Scheduled scrape completed: {len(announcements)} new announcements")
            
        except Exception as e:
            logger.error(f"Scheduled scrape failed: {e}")
    
    def send_daily_digest(self):
        """Send daily digest email."""
        try:
            logger.info("Sending daily digest")
            success = self.notification_manager.send_daily_digest()
            if success:
                logger.info("Daily digest sent successfully")
            else:
                logger.error("Failed to send daily digest")
        except Exception as e:
            logger.error(f"Daily digest failed: {e}")
    
    def cleanup_old_files(self):
        """Clean up old PDF files."""
        try:
            logger.info("Starting file cleanup")
            self.scraper.cleanup_old_files()
            logger.info("File cleanup completed")
        except Exception as e:
            logger.error(f"File cleanup failed: {e}")
    
    def run_scheduler(self):
        """Run the scheduler in a loop."""
        self.running = True
        logger.info("JAIBird scheduler started")
        
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        
        logger.info("JAIBird scheduler stopped")
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False


def run_web_interface():
    """Run the Flask web interface."""
    try:
        run_app()
    except Exception as e:
        logger.error(f"Web interface failed: {e}")


def main():
    """Main function with CLI interface."""
    parser = argparse.ArgumentParser(description="JAIBird Stock Trading Platform")
    parser.add_argument('command', choices=[
        'web', 'scrape', 'initial-scrape', 'digest', 'test-notifications',
        'test-telegram', 'scheduler', 'setup', 'status'
    ], help='Command to execute')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        config = get_config()
        logger.info(f"JAIBird starting in {config.environment} mode")
        
        if args.command == 'web':
            logger.info("Starting web interface...")
            run_web_interface()
            
        elif args.command == 'scrape':
            logger.info("Running daily SENS scrape...")
            announcements = run_daily_scrape()
            print(f"Scrape completed: {len(announcements)} new announcements")
            
        elif args.command == 'initial-scrape':
            logger.info("Running initial 30-day SENS scrape...")
            announcements = run_initial_scrape()
            print(f"Initial scrape completed: {len(announcements)} announcements")
            
        elif args.command == 'digest':
            logger.info("Sending daily digest...")
            db_manager = DatabaseManager(config.database_path)
            notification_manager = NotificationManager(db_manager)
            success = notification_manager.send_daily_digest()
            print(f"Daily digest: {'sent successfully' if success else 'failed'}")
            
        elif args.command == 'test-notifications':
            logger.info("Testing notification systems...")
            db_manager = DatabaseManager(config.database_path)
            notification_manager = NotificationManager(db_manager)
            results = notification_manager.test_notifications()
            
            print("Notification Test Results:")
            for system, status in results.items():
                status_text = "✅ Working" if status is True else \
                             "⚠️ Disabled" if status == 'disabled' else \
                             "❌ Failed"
                print(f"  {system.capitalize()}: {status_text}")
        
        elif args.command == 'test-telegram':
            logger.info("Testing Telegram connection separately...")
            import subprocess
            import os
            
            script_path = os.path.join('src', 'notifications', 'telegram_sender.py')
            result = subprocess.run([
                'python', script_path, 'dummy', 'test'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Telegram connection test passed!")
            else:
                print(f"❌ Telegram connection test failed: {result.stderr}")
                sys.exit(1)
            
        elif args.command == 'scheduler':
            logger.info("Starting JAIBird scheduler...")
            scheduler = JAIBirdScheduler()
            scheduler.setup_schedules()
            
            try:
                scheduler.run_scheduler()
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping scheduler...")
                scheduler.stop()
            
        elif args.command == 'setup':
            logger.info("Setting up JAIBird...")
            setup_jaibird()
            
        elif args.command == 'status':
            logger.info("Checking JAIBird status...")
            show_status()
            
    except Exception as e:
        logger.error(f"JAIBird failed: {e}")
        sys.exit(1)


def setup_jaibird():
    """Set up JAIBird for first use."""
    print("🚀 JAIBird Setup")
    print("=" * 50)
    
    try:
        config = get_config()
        
        # Check database
        print("📊 Initializing database...")
        db_manager = DatabaseManager(config.database_path)
        stats = db_manager.get_database_stats()
        print(f"   Database ready: {stats}")
        
        # Test Dropbox
        print("☁️  Testing Dropbox connection...")
        dropbox_manager = DropboxManager()
        storage_info = dropbox_manager.get_storage_usage()
        if 'error' in storage_info:
            print(f"   ❌ Dropbox connection failed: {storage_info['error']}")
        else:
            print(f"   ✅ Dropbox connected: {storage_info['used_gb']:.1f}GB used")
        
        # Test notifications
        print("📧 Testing notifications...")
        notification_manager = NotificationManager(db_manager)
        results = notification_manager.test_notifications()
        
        for system, status in results.items():
            status_icon = "✅" if status is True else "⚠️" if status == 'disabled' else "❌"
            print(f"   {status_icon} {system.capitalize()}: {status}")
        
        print("\n🎉 JAIBird setup completed!")
        print("\nNext steps:")
        print("1. Run 'python main.py initial-scrape' to populate with SENS data")
        print("2. Run 'python main.py web' to start the web interface")
        print("3. Run 'python main.py scheduler' to start automated monitoring")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")


def show_status():
    """Show JAIBird system status."""
    try:
        config = get_config()
        
        print("📊 JAIBird System Status")
        print("=" * 50)
        
        # Database stats
        db_manager = DatabaseManager(config.database_path)
        stats = db_manager.get_database_stats()
        
        print(f"📁 Database:")
        print(f"   Total SENS: {stats.get('sens_announcements', {}).get('total', 0)}")
        print(f"   Urgent SENS: {stats.get('sens_announcements', {}).get('urgent', 0)}")
        print(f"   Watchlist Companies: {stats.get('companies', {}).get('active', 0)}")
        print(f"   Notifications Sent: {stats.get('notifications', {}).get('sent', 0)}")
        
        # Configuration
        print(f"\n⚙️  Configuration:")
        print(f"   Environment: {config.environment}")
        print(f"   Scrape Interval: {config.scrape_interval_minutes} minutes")
        print(f"   Daily Digest Time: {config.daily_digest_time}")
        print(f"   Test Mode: {config.test_mode}")
        
        # Storage
        try:
            dropbox_manager = DropboxManager()
            storage_info = dropbox_manager.get_storage_usage()
            if 'error' not in storage_info:
                print(f"\n☁️  Dropbox Storage:")
                print(f"   Used: {storage_info.get('used_gb', 0):.1f}GB")
                print(f"   Total: {storage_info.get('allocated_gb', 0):.1f}GB")
        except:
            print(f"\n☁️  Dropbox: Connection failed")
        
        print(f"\n✅ JAIBird is operational")
        
    except Exception as e:
        print(f"❌ Status check failed: {e}")


def run_combined():
    """Run both scheduler and web interface in separate threads."""
    config = get_config()
    
    # Start scheduler in background thread
    scheduler = JAIBirdScheduler()
    scheduler.setup_schedules()
    scheduler_thread = Thread(target=scheduler.run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Run web interface in main thread
    logger.info("Starting combined mode: scheduler + web interface")
    run_web_interface()


if __name__ == "__main__":
    main()
