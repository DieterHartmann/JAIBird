"""
SENS Announcement Scraper for JAIBird Stock Trading Platform.
Scrapes SENS announcements from the JSE website and downloads PDFs.
"""

import os
import re
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

from ..database.models import DatabaseManager, SensAnnouncement
from ..utils.config import get_config


logger = logging.getLogger(__name__)


class SensScraperError(Exception):
    """Custom exception for SENS scraper errors."""
    pass


class SensScraper:
    """Scrapes SENS announcements from the JSE website."""
    
    JSE_SENS_URL = "https://clientportal.jse.co.za/communication/sens-announcements"
    
    # XPath selectors as provided in requirements
    XPATH_LAST_30_DAYS = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[1]/div[2]/div[3]/input"
    XPATH_TODAY_ANNOUNCEMENTS = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[1]/div[2]/div[1]/input"
    XPATH_PDF_LINK = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/a"
    XPATH_COMPANY_NAME = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/ul/li/a"
    XPATH_SENS_NUMBER = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/div"
    
    def __init__(self, db_manager: DatabaseManager):
        self.config = get_config()
        self.db_manager = db_manager
        self.driver = None
        self.download_path = Path(self.config.webdriver_download_path)
        self.download_path.mkdir(parents=True, exist_ok=True)
    
    def _setup_driver(self):
        """Set up Chrome WebDriver with appropriate options."""
        chrome_options = Options()
        
        if self.config.webdriver_headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # Set download preferences
        prefs = {
            "download.default_directory": str(self.download_path.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            # Use webdriver-manager to automatically handle ChromeDriver
            service = webdriver.chrome.service.Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(self.config.webdriver_timeout)
            logger.info("Chrome WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            raise SensScraperError(f"WebDriver initialization failed: {e}")
    
    def _wait_for_element(self, xpath: str, timeout: int = None) -> Optional[object]:
        """Wait for an element to be present and return it."""
        if timeout is None:
            timeout = self.config.webdriver_timeout
        
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element
        except TimeoutException:
            logger.warning(f"Element not found within {timeout} seconds: {xpath}")
            return None
    
    def _click_element_safely(self, xpath: str, description: str = "") -> bool:
        """Safely click an element with error handling."""
        try:
            element = self._wait_for_element(xpath, 10)
            if element:
                element.click()
                logger.debug(f"Clicked element: {description}")
                time.sleep(2)  # Allow page to load
                return True
            else:
                logger.warning(f"Could not find element to click: {description}")
                return False
        except Exception as e:
            logger.error(f"Error clicking element {description}: {e}")
            return False
    
    def _extract_sens_number(self, sens_text: str) -> str:
        """Extract SENS number from text."""
        # Look for patterns like "SENS 123456" or just numbers
        match = re.search(r'(?:SENS\s*)?(\d+)', sens_text.strip())
        if match:
            return match.group(1)
        return sens_text.strip()
    
    def _is_urgent_announcement(self, title: str, company_name: str) -> Tuple[bool, str]:
        """Determine if an announcement is urgent based on keywords."""
        urgent_keywords = self.config.get_urgent_keywords_list()
        title_lower = title.lower()
        company_lower = company_name.lower()
        
        for keyword in urgent_keywords:
            if keyword in title_lower or keyword in company_lower:
                return True, f"Contains urgent keyword: {keyword}"
        
        return False, ""
    
    def _download_pdf(self, pdf_url: str, sens_number: str, company_name: str) -> Optional[str]:
        """Download PDF file and return local path."""
        try:
            # Clean filename
            safe_company = re.sub(r'[^\w\s-]', '', company_name).strip()
            safe_company = re.sub(r'[-\s]+', '-', safe_company)
            
            filename = f"SENS_{sens_number}_{safe_company}.pdf"
            local_path = self.download_path / filename
            
            # Check if file already exists
            if local_path.exists():
                logger.info(f"PDF already exists locally: {filename}")
                return str(local_path)
            
            # Download the file
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Save the file
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded PDF: {filename} ({len(response.content)} bytes)")
            return str(local_path)
            
        except Exception as e:
            logger.error(f"Failed to download PDF {pdf_url}: {e}")
            return None
    
    def _scrape_announcements_from_page(self) -> List[SensAnnouncement]:
        """Scrape SENS announcements from the current page."""
        announcements = []
        
        try:
            # Find all announcement list items
            announcement_items = self.driver.find_elements(
                By.XPATH, 
                "//div[contains(@class, 'announcement')]//ul/li[position()=1]"
            )
            
            # If the specific xpath doesn't work, try a more general approach
            if not announcement_items:
                announcement_items = self.driver.find_elements(
                    By.XPATH,
                    "//ul/li[a[contains(@href, '.pdf')]]"
                )
            
            logger.info(f"Found {len(announcement_items)} potential announcements on page")
            
            for i, item in enumerate(announcement_items, 1):
                try:
                    # Extract PDF link and title
                    pdf_link_element = item.find_element(By.XPATH, ".//a[contains(@href, '.pdf')]")
                    pdf_url = pdf_link_element.get_attribute('href')
                    title = pdf_link_element.text.strip()
                    
                    # Extract company name (usually in a nested ul/li)
                    company_element = None
                    try:
                        company_element = item.find_element(By.XPATH, ".//ul/li/a")
                        company_name = company_element.text.strip()
                    except NoSuchElementException:
                        # Try alternative xpath
                        try:
                            company_element = item.find_element(By.XPATH, ".//li[2]//a")
                            company_name = company_element.text.strip()
                        except NoSuchElementException:
                            logger.warning(f"Could not find company name for announcement {i}")
                            continue
                    
                    # Extract SENS number
                    sens_number_element = None
                    sens_number = ""
                    try:
                        sens_number_element = item.find_element(By.XPATH, ".//div[contains(text(), 'SENS') or contains(text(), 'SEN')]")
                        sens_number = self._extract_sens_number(sens_number_element.text)
                    except NoSuchElementException:
                        # Try to extract from title or URL
                        sens_match = re.search(r'(?:SENS|SEN)\s*(\d+)', title, re.IGNORECASE)
                        if sens_match:
                            sens_number = sens_match.group(1)
                        else:
                            # Use timestamp as fallback
                            sens_number = f"TEMP_{int(datetime.now().timestamp())}"
                    
                    # Skip if we already have this SENS
                    if self.db_manager.sens_exists(sens_number):
                        logger.debug(f"SENS {sens_number} already exists, skipping")
                        continue
                    
                    # Check if urgent
                    is_urgent, urgent_reason = self._is_urgent_announcement(title, company_name)
                    
                    # Download PDF
                    local_pdf_path = self._download_pdf(pdf_url, sens_number, company_name)
                    
                    # Create announcement object
                    announcement = SensAnnouncement(
                        sens_number=sens_number,
                        company_name=company_name,
                        title=title,
                        pdf_url=pdf_url,
                        local_pdf_path=local_pdf_path or "",
                        date_published=datetime.now(),  # We'll improve this later
                        is_urgent=is_urgent,
                        urgent_reason=urgent_reason
                    )
                    
                    announcements.append(announcement)
                    logger.info(f"Scraped SENS {sens_number}: {company_name} - {title[:50]}...")
                    
                except Exception as e:
                    logger.error(f"Error processing announcement {i}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error scraping announcements from page: {e}")
        
        return announcements
    
    def scrape_initial_30_days(self) -> List[SensAnnouncement]:
        """Perform initial scrape of last 30 days of SENS announcements."""
        logger.info("Starting initial 30-day SENS scrape")
        
        try:
            self._setup_driver()
            self.driver.get(self.JSE_SENS_URL)
            
            # Wait for page to load
            time.sleep(5)
            
            # Click "Last 30 days" button
            if self._click_element_safely(self.XPATH_LAST_30_DAYS, "Last 30 days button"):
                time.sleep(5)  # Wait for results to load
            else:
                logger.warning("Could not click 'Last 30 days' button, proceeding with default view")
            
            # Scrape announcements
            announcements = self._scrape_announcements_from_page()
            
            # Save to database
            saved_count = 0
            for announcement in announcements:
                try:
                    self.db_manager.add_sens_announcement(announcement)
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Failed to save announcement {announcement.sens_number}: {e}")
            
            logger.info(f"Initial scrape completed: {saved_count} new announcements saved")
            return announcements
            
        except Exception as e:
            logger.error(f"Error during initial 30-day scrape: {e}")
            raise SensScraperError(f"Initial scrape failed: {e}")
        finally:
            if self.driver:
                self.driver.quit()
    
    def scrape_daily_announcements(self) -> List[SensAnnouncement]:
        """Scrape today's SENS announcements."""
        logger.info("Starting daily SENS scrape")
        
        try:
            self._setup_driver()
            self.driver.get(self.JSE_SENS_URL)
            
            # Wait for page to load
            time.sleep(5)
            
            # Click "Today's announcements" button to ensure we're looking at today
            if self._click_element_safely(self.XPATH_TODAY_ANNOUNCEMENTS, "Today's announcements button"):
                time.sleep(5)  # Wait for results to load
            
            # Scrape announcements
            announcements = self._scrape_announcements_from_page()
            
            # Save new announcements to database
            saved_count = 0
            for announcement in announcements:
                try:
                    if not self.db_manager.sens_exists(announcement.sens_number):
                        self.db_manager.add_sens_announcement(announcement)
                        saved_count += 1
                    else:
                        logger.debug(f"SENS {announcement.sens_number} already exists")
                except Exception as e:
                    logger.error(f"Failed to save announcement {announcement.sens_number}: {e}")
            
            logger.info(f"Daily scrape completed: {saved_count} new announcements found")
            return [ann for ann in announcements if not self.db_manager.sens_exists(ann.sens_number)]
            
        except Exception as e:
            logger.error(f"Error during daily scrape: {e}")
            raise SensScraperError(f"Daily scrape failed: {e}")
        finally:
            if self.driver:
                self.driver.quit()
    
    def cleanup_old_files(self):
        """Clean up old PDF files based on retention policy."""
        try:
            retention_days = self.config.local_cache_retention_days
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            deleted_count = 0
            for pdf_file in self.download_path.glob("*.pdf"):
                if pdf_file.stat().st_mtime < cutoff_date.timestamp():
                    try:
                        pdf_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old PDF: {pdf_file.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete {pdf_file}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old PDF files")
                
        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")


def run_initial_scrape():
    """Run initial 30-day scrape. Use this for first-time setup."""
    config = get_config()
    db_manager = DatabaseManager(config.database_path)
    scraper = SensScraper(db_manager)
    
    try:
        announcements = scraper.scrape_initial_30_days()
        print(f"Initial scrape completed successfully: {len(announcements)} announcements")
        return announcements
    except Exception as e:
        print(f"Initial scrape failed: {e}")
        raise


def run_daily_scrape():
    """Run daily scrape for new announcements."""
    config = get_config()
    db_manager = DatabaseManager(config.database_path)
    scraper = SensScraper(db_manager)
    
    try:
        announcements = scraper.scrape_daily_announcements()
        scraper.cleanup_old_files()
        print(f"Daily scrape completed successfully: {len(announcements)} new announcements")
        return announcements
    except Exception as e:
        print(f"Daily scrape failed: {e}")
        raise


if __name__ == "__main__":
    # For testing purposes
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "initial":
        run_initial_scrape()
    else:
        run_daily_scrape()
