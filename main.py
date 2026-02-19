"""
JAIBird Stock Trading Platform - Main Entry Point
Coordinates all components and provides CLI interface.
"""

import gc
import os
import sys
import time
import logging
import argparse
import subprocess
import schedule
from datetime import datetime
from threading import Thread

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import get_config
from src.database.models import DatabaseManager
from src.scrapers.sens_scraper import SensScraper, run_initial_scrape, run_daily_scrape
from src.ai.pdf_parser import parse_sens_announcement
from src.notifications.telegram_bot import run_bot
from src.notifications.notifier import NotificationManager
from src.utils.dropbox_manager import DropboxManager
from src.utils.excel_manager import ExcelManager
from src.web.app import run_app
from src.company.enricher import CompanyEnricher
from src.company.company_db import CompanyDB
from src.services.price_service import PriceService


logger = logging.getLogger(__name__)


class JAIBirdScheduler:
    """Main scheduler for JAIBird operations."""

    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self):
        self.config = get_config()
        self.db_manager = DatabaseManager(self.config.database_path)
        self.notification_manager = NotificationManager(self.db_manager)
        self.dropbox_manager = DropboxManager()
        self.scraper = SensScraper(self.db_manager)
        self.price_service = PriceService(self.db_manager)
        self.enricher = CompanyEnricher(CompanyDB())
        self.running = False
        self._consecutive_scrape_failures = 0
    
    def setup_schedules(self):
        """Set up scheduled tasks."""
        schedule.every(self.config.scrape_interval_minutes).minutes.do(self.scheduled_scrape)
        schedule.every().day.at(self.config.daily_digest_time).do(self.send_daily_digest)
        schedule.every().day.at("00:00").do(self.cleanup_old_files)

        schedule.every(15).minutes.do(self.fetch_all_prices)
        schedule.every(2).minutes.do(self.fetch_hot_prices)
        schedule.every().day.at("00:30").do(self.cleanup_old_prices)
        
        logger.info(f"Scheduled SENS scraping every {self.config.scrape_interval_minutes} minutes")
        logger.info(f"Scheduled daily digest at {self.config.daily_digest_time}")
        logger.info("Scheduled daily file cleanup at midnight")
        logger.info("Scheduled stock price polling every 15 min (hot-list every 2 min)")

    # ------------------------------------------------------------------
    # Scrape lifecycle with nil-pull vs non-pull tracking
    # ------------------------------------------------------------------

    def scheduled_scrape(self):
        """Perform scheduled SENS scraping with resilience tracking."""
        scrape_ok = False
        new_count = 0
        error_msg = ""

        try:
            logger.info("Starting scheduled SENS scrape")
            announcements = self.scraper.scrape_daily_announcements()
            scrape_ok = True
            new_count = len(announcements)

            for announcement in announcements:
                try:
                    parsed_announcement = parse_sens_announcement(announcement)
                    if parsed_announcement.ai_summary:
                        self.db_manager.update_sens_parsing(parsed_announcement)
                        announcement.pdf_content = parsed_announcement.pdf_content
                        announcement.ai_summary = parsed_announcement.ai_summary
                        logger.info(f"Generated AI summary for SENS {announcement.sens_number}")
                except Exception as e:
                    logger.error(f"PDF parsing failed for SENS {announcement.sens_number}: {e}")

                if announcement.local_pdf_path:
                    dropbox_path = self.dropbox_manager.upload_pdf(
                        announcement.local_pdf_path,
                        announcement.sens_number,
                        announcement.company_name
                    )
                    if dropbox_path:
                        announcement.dropbox_pdf_path = dropbox_path

                self.notification_manager.process_new_announcement(announcement)
                self._add_to_hot_list(announcement)

                try:
                    self.enricher.enrich_from_announcement(announcement)
                except Exception as e:
                    logger.warning(f"Company enrichment failed for SENS {announcement.sens_number}: {e}")

            logger.info(f"Scheduled scrape completed: {new_count} new announcements")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Scheduled scrape failed (NON-PULL): {e}")
        finally:
            self._kill_zombie_chrome()
            self._force_gc()

        self._record_scrape_result(scrape_ok, new_count, error_msg)

    def _record_scrape_result(self, success: bool, count: int, error: str):
        """Track scrape outcome: reset or increment failure counter, alert, restart."""
        now_iso = datetime.now().isoformat()

        if success:
            self._consecutive_scrape_failures = 0
            self.db_manager.set_config_value(
                "last_scrape_status", "ok",
                f"nil-pull" if count == 0 else f"{count} new")
            self.db_manager.set_config_value("last_scrape_time", now_iso)
            self.db_manager.set_config_value("consecutive_scrape_failures", "0")
            return

        # --- NON-PULL path ---
        self._consecutive_scrape_failures += 1
        self.db_manager.set_config_value(
            "last_scrape_status", "fail", error[:200])
        self.db_manager.set_config_value("last_scrape_fail_time", now_iso)
        self.db_manager.set_config_value(
            "consecutive_scrape_failures",
            str(self._consecutive_scrape_failures))

        logger.warning(
            f"Consecutive scrape failures: {self._consecutive_scrape_failures}"
            f"/{self.MAX_CONSECUTIVE_FAILURES}")

        if self._consecutive_scrape_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._send_failure_alert(error)
            self._force_restart()

    def _add_to_hot_list(self, announcement):
        """Add a company to the price hot-list after a new SENS announcement."""
        try:
            company = self.db_manager.get_company_by_jse_code(
                announcement.company_name.split()[-1] if announcement.company_name else ""
            )
            if company and company.jse_code:
                self.db_manager.add_hot_ticker(
                    ticker=company.jse_code,
                    sens_id=announcement.id,
                    duration_minutes=60,
                )
                return

            # Fallback: check if company_name matches a watchlist company
            companies = self.db_manager.get_all_companies(active_only=True)
            for c in companies:
                if (c.name and c.name.lower() in announcement.company_name.lower()) or \
                   (c.jse_code and c.jse_code.lower() in announcement.company_name.lower()):
                    self.db_manager.add_hot_ticker(
                        ticker=c.jse_code,
                        sens_id=announcement.id,
                        duration_minutes=60,
                    )
                    return

            # Also check if the ticker appears in our tracked list
            for ticker in self.price_service.get_tickers():
                if ticker.lower() in announcement.company_name.lower():
                    self.db_manager.add_hot_ticker(
                        ticker=ticker,
                        sens_id=announcement.id,
                        duration_minutes=60,
                    )
                    return
        except Exception as e:
            logger.debug(f"Could not add hot-list entry for {announcement.company_name}: {e}")
    
    # ------------------------------------------------------------------
    # Zombie Chrome / memory cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _kill_zombie_chrome():
        """Kill any lingering chromium/chrome processes left by Selenium."""
        try:
            import platform
            if platform.system() != "Linux":
                return
            result = subprocess.run(
                ["pkill", "-9", "-f", "chromium|chrome"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("Killed lingering chromium processes")
        except Exception:
            pass

    @staticmethod
    def _force_gc():
        """Explicit garbage collection to release memory back to the OS."""
        gc.collect()

    # ------------------------------------------------------------------
    # Telegram failure alert
    # ------------------------------------------------------------------

    def _send_failure_alert(self, error: str):
        """Send a Telegram alert after repeated scrape failures."""
        try:
            import json, tempfile

            message = (
                f"🔴 *JAIBird Scrape FAILURE*\n\n"
                f"The SENS scraper has failed "
                f"{self._consecutive_scrape_failures} consecutive times.\n\n"
                f"*Last error:*\n`{error[:300]}`\n\n"
                f"The scheduler will now *restart automatically*.\n"
                f"If this keeps happening, check Docker logs on the Pi.\n\n"
                f"_JAIBird Health Monitor_"
            )

            msg_data = {"type": "system_alert", "message": message}
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(msg_data, f)
                temp_path = f.name

            script = os.path.join(
                os.path.dirname(__file__),
                "src", "notifications", "telegram_sender.py",
            )
            python_exe = sys.executable or "python"
            subprocess.run(
                [python_exe, script, temp_path],
                timeout=30, capture_output=True,
            )
            logger.info("Failure alert sent via Telegram")
        except Exception as e:
            logger.error(f"Failed to send Telegram failure alert: {e}")

    # ------------------------------------------------------------------
    # Force restart (let Docker's restart policy bring us back clean)
    # ------------------------------------------------------------------

    def _force_restart(self):
        """Exit the process so Docker restarts the container cleanly."""
        logger.critical(
            f"Forcing scheduler restart after "
            f"{self._consecutive_scrape_failures} consecutive scrape failures"
        )
        self._kill_zombie_chrome()
        os._exit(1)

    # ------------------------------------------------------------------
    # Standard scheduled tasks
    # ------------------------------------------------------------------

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

    def fetch_all_prices(self):
        """Periodic bulk fetch of stock prices for all tracked tickers."""
        try:
            count = self.price_service.fetch_all_prices()
            logger.info(f"Price fetch completed: {count} tickers updated")
        except Exception as e:
            logger.error(f"Price fetch failed: {e}")
        finally:
            self._force_gc()

    def fetch_hot_prices(self):
        """Frequent fetch of stock prices for SENS-triggered hot-list tickers."""
        try:
            self.price_service.fetch_hot_prices()
        except Exception as e:
            logger.error(f"Hot-list price fetch failed: {e}")
        finally:
            self._force_gc()

    def cleanup_old_prices(self):
        """Prune stock price history older than 90 days."""
        try:
            deleted = self.db_manager.cleanup_old_prices(days=90)
            if deleted:
                logger.info(f"Cleaned up {deleted} old price records")
        except Exception as e:
            logger.error(f"Price cleanup failed: {e}")
    
    def check_scrape_trigger(self):
        """Check for a scrape trigger file written by the web container."""
        trigger_path = os.path.join('data', 'scrape_trigger.json')
        if os.path.exists(trigger_path):
            try:
                os.remove(trigger_path)
                logger.info("Scrape trigger detected from web dashboard – running scrape now")
                self.scheduled_scrape()
            except Exception as e:
                logger.error(f"Error handling scrape trigger: {e}")

    def run_scheduler(self):
        """Run the scheduler in a loop."""
        self.running = True
        logger.info("JAIBird scheduler started")
        
        while self.running:
            schedule.run_pending()
            self.check_scrape_trigger()
            time.sleep(30)  # Check every 30 seconds (trigger file + schedule)
        
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
        'test-telegram', 'scheduler', 'setup', 'status', 'export-excel',
        'parse-pdfs', 'telegram-bot', 'backfill-companies'
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
            config = get_config()
            db_manager = DatabaseManager(config.database_path)
            notification_manager = NotificationManager(db_manager)
            dropbox_manager = DropboxManager()
            
            # Run the scrape
            announcements = run_daily_scrape()
            
            # Process notifications and PDF parsing for new announcements
            for announcement in announcements:
                try:
                    # Parse PDF and generate AI summary for ALL new announcements
                    try:
                        parsed_announcement = parse_sens_announcement(announcement)
                        if parsed_announcement.ai_summary:
                            # Update the database with parsed content
                            announcement.pdf_content = parsed_announcement.pdf_content
                            announcement.ai_summary = parsed_announcement.ai_summary
                            announcement.parse_method = parsed_announcement.parse_method
                            announcement.parse_status = parsed_announcement.parse_status
                            announcement.parsed_at = parsed_announcement.parsed_at
                            db_manager.update_sens_parsing(announcement)
                            logger.info(f"Generated AI summary for SENS {announcement.sens_number}")
                        else:
                            logger.warning(f"No AI summary generated for SENS {announcement.sens_number}")
                    except Exception as e:
                        logger.error(f"PDF parsing failed for SENS {announcement.sens_number}: {e}")
                    
                    # Upload to Dropbox
                    if announcement.local_pdf_path:
                        dropbox_path = dropbox_manager.upload_pdf(
                            announcement.local_pdf_path,
                            announcement.sens_number,
                            announcement.company_name
                        )
                        if dropbox_path:
                            # Update database with Dropbox path
                            announcement.dropbox_pdf_path = dropbox_path
                    
                    # Send notifications
                    notification_manager.process_new_announcement(announcement)
                    
                    # Enrich company intelligence DB
                    CompanyEnricher(CompanyDB()).enrich_from_announcement(announcement)

                except Exception as e:
                    logger.error(f"Failed to process announcement {announcement.sens_number}: {e}")
            
            print(f"Scrape completed: {len(announcements)} new announcements")
            
        elif args.command == 'initial-scrape':
            logger.info("Running initial 30-day SENS scrape...")
            announcements = run_initial_scrape()
            print(f"Initial scrape completed: {len(announcements)} announcements")
            
            # Parse PDFs and generate AI summaries for all new announcements
            if announcements:
                from src.ai.pdf_parser import PDFParser
                import time as _time
                
                print(f"\nParsing {len(announcements)} PDFs and generating AI summaries...")
                parser = PDFParser()  # Shared instance to track totals
                db_manager = DatabaseManager(config.database_path)
                success_count = 0
                start_time = _time.time()
                
                for i, announcement in enumerate(announcements, 1):
                    try:
                        print(f"  [{i}/{len(announcements)}] {announcement.company_name} - {announcement.title[:50]}...")
                        parsed = parser.parse_sens_pdf(announcement)
                        if parsed.ai_summary:
                            db_manager.update_sens_parsing(parsed)
                            success_count += 1
                    except Exception as e:
                        logger.error(f"PDF parsing failed for SENS {announcement.sens_number}: {e}")
                
                elapsed = _time.time() - start_time
                stats = parser.get_usage_summary()
                
                print(f"\n{'='*60}")
                print(f"INITIAL SCRAPE COMPLETE")
                print(f"{'='*60}")
                print(f"  Announcements scraped:  {len(announcements)}")
                print(f"  Successfully parsed:    {success_count}/{len(announcements)}")
                print(f"  API calls made:         {stats['api_calls']}")
                print(f"  Input tokens:           {stats['input_tokens']:,}")
                print(f"  Output tokens:          {stats['output_tokens']:,}")
                print(f"  Total tokens:           {stats['total_tokens']:,}")
                print(f"  Estimated cost:         ${stats['estimated_cost_usd']:.4f}")
                print(f"  Time elapsed:           {elapsed:.1f}s")
                print(f"  Monthly projection:     ~{len(announcements) / 30 * 22:.0f} announcements/month")
                print(f"  Projected monthly cost: ${stats['estimated_cost_usd'] / 30 * 22:.4f}")
                print(f"{'='*60}")
            
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
            
        elif args.command == 'export-excel':
            logger.info("Exporting SENS data to Excel...")
            export_to_excel()
            
        elif args.command == 'parse-pdfs':
            logger.info("Processing unparsed PDFs...")
            parse_unparsed_pdfs()
            
        elif args.command == 'telegram-bot':
            logger.info("Starting interactive Telegram bot...")
            run_telegram_bot()

        elif args.command == 'backfill-companies':
            logger.info("Backfilling company intelligence DB from existing SENS...")
            backfill_companies()

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


def export_to_excel():
    """Export all SENS announcements to Excel spreadsheet."""
    try:
        config = get_config()
        db_manager = DatabaseManager(config.database_path)
        excel_manager = ExcelManager("data/sens_announcements.xlsx")
        
        print("🔄 Exporting SENS announcements to Excel...")
        
        # Get all announcements from database
        announcements = db_manager.get_all_sens_announcements()
        
        if not announcements:
            print("📭 No SENS announcements found in database")
            print("💡 Run 'python main.py initial-scrape' first to populate the database")
            return
        
        # Create Excel export
        excel_path = excel_manager.create_or_update_spreadsheet(announcements)
        
        print(f"✅ Excel export completed!")
        print(f"📊 Exported {len(announcements)} SENS announcements")
        print(f"📁 File location: {excel_path}")
        print(f"📋 Columns: Date, SENS Number, Organization, Heading, PDF Link, PDF Summary (placeholder), Urgent, Created")
        
    except Exception as e:
        print(f"❌ Excel export failed: {e}")
        logger.error(f"Excel export failed: {e}")


def parse_unparsed_pdfs():
    """Parse unparsed PDF files and generate AI summaries."""
    try:
        config = get_config()
        db_manager = DatabaseManager(config.database_path)
        
        # Get unparsed SENS announcements
        unparsed = db_manager.get_unparsed_sens()
        
        if not unparsed:
            print("📭 No unparsed PDFs found")
            logger.info("No unparsed PDFs found")
            return
        
        print(f"🔄 Found {len(unparsed)} unparsed PDFs to process")
        logger.info(f"Found {len(unparsed)} unparsed PDFs to process")
        
        success_count = 0
        for i, announcement in enumerate(unparsed, 1):
            try:
                print(f"📄 Processing {i}/{len(unparsed)}: SENS {announcement.sens_number} - {announcement.company_name}")
                logger.info(f"Processing SENS {announcement.sens_number}: {announcement.company_name}")
                
                # Parse the PDF
                parsed_announcement = parse_sens_announcement(announcement)
                
                # Update database with results
                if db_manager.update_sens_parsing(parsed_announcement):
                    success_count += 1
                    print(f"   ✅ Success - Method: {parsed_announcement.parse_method}")
                    if parsed_announcement.ai_summary:
                        print(f"   📝 Summary: {parsed_announcement.ai_summary[:80]}...")
                    logger.info(f"Successfully processed SENS {announcement.sens_number}")
                else:
                    print(f"   ❌ Failed to save parsing results")
                    logger.error(f"Failed to save parsing results for SENS {announcement.sens_number}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                logger.error(f"Error processing SENS {announcement.sens_number}: {e}")
                continue
        
        print(f"\\n🎉 PDF parsing completed: {success_count}/{len(unparsed)} successful")
        logger.info(f"PDF parsing completed: {success_count}/{len(unparsed)} successful")
        
    except Exception as e:
        print(f"❌ PDF parsing failed: {e}")
        logger.error(f"PDF parsing failed: {e}")


def run_telegram_bot():
    """Start the interactive Telegram bot."""
    try:
        import asyncio
        asyncio.run(run_bot())
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {e}")
        raise


def backfill_companies():
    """Backfill company intelligence DB from all existing SENS with pdf_content."""
    try:
        config = get_config()
        db_manager = DatabaseManager(config.database_path)
        enricher = CompanyEnricher(CompanyDB())

        all_sens = db_manager.get_all_sens_announcements()
        with_content = [a for a in all_sens if a.pdf_content]
        total = len(with_content)

        print(f"Found {len(all_sens)} total SENS, {total} with parsed content")
        if not total:
            print("Nothing to backfill. Run 'parse-pdfs' first to extract PDF content.")
            return

        success = 0
        for i, ann in enumerate(with_content, 1):
            try:
                enricher.enrich_from_announcement(ann)
                success += 1
                if i % 25 == 0 or i == total:
                    print(f"  [{i}/{total}] processed... ({success} enriched)")
            except Exception as e:
                logger.warning(f"  [{i}/{total}] failed for {ann.sens_number}: {e}")

        count = enricher.company_db.get_company_count()
        print(f"\nBackfill complete: {success}/{total} SENS processed")
        print(f"Company intelligence DB now has {count} companies")

    except Exception as e:
        print(f"Backfill failed: {e}")
        logger.error(f"Backfill failed: {e}")


if __name__ == "__main__":
    main()
