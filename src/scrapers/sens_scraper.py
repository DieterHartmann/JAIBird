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
from ..utils.excel_manager import ExcelManager


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
        
        # Initialize Excel manager
        self.excel_manager = ExcelManager("data/sens_announcements.xlsx")
        
        # Define ignore list for announcements to skip
        self.ignore_patterns = [
            "JSE Contact List",
            "JSE%20Contact%20List", 
            "JSE Contact List 2024",
            "JSE%20Contact%20List%202024",
            "Contact List",
            "contact list"  # case insensitive match will catch variations
        ]
    
    def _should_ignore_announcement(self, heading: str, company_name: str = "") -> bool:
        """
        Check if an announcement should be ignored based on heading or company name.
        
        Args:
            heading: The announcement heading/title
            company_name: The company name (optional)
            
        Returns:
            True if the announcement should be ignored, False otherwise
        """
        # Combine heading and company name for checking
        text_to_check = f"{heading} {company_name}".lower()
        
        # Check against ignore patterns
        for pattern in self.ignore_patterns:
            if pattern.lower() in text_to_check:
                logger.info(f"IGNORE - Skipping announcement matching pattern '{pattern}': {heading}")
                return True
                
        return False
    
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
            # Bypass WebDriverManager and download ChromeDriver manually for 64-bit
            import os
            import requests
            import zipfile
            import tempfile
            from pathlib import Path
            
            # First try to find Chrome manually
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            
            chrome_path = None
            for path in chrome_paths:
                if os.path.exists(path):
                    chrome_path = path
                    break
            
            if chrome_path:
                chrome_options.binary_location = chrome_path
                logger.info(f"Using Chrome from: {chrome_path}")
            
            # Manual ChromeDriver download for 64-bit Windows
            driver_dir = Path.home() / ".jaibird_drivers"
            driver_dir.mkdir(exist_ok=True)
            driver_path = driver_dir / "chromedriver.exe"
            
            # Download if not exists or force refresh
            if not driver_path.exists():
                logger.info("Downloading 64-bit ChromeDriver manually...")
                chrome_version = "140.0.7339.82"  # Match your Chrome version
                download_url = f"https://storage.googleapis.com/chrome-for-testing-public/{chrome_version}/win64/chromedriver-win64.zip"
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = Path(temp_dir) / "chromedriver.zip"
                    
                    # Download the zip file
                    response = requests.get(download_url)
                    response.raise_for_status()
                    
                    with open(zip_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Extract the exe
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    
                    # Find and copy chromedriver.exe
                    extracted_driver = Path(temp_dir) / "chromedriver-win64" / "chromedriver.exe"
                    if extracted_driver.exists():
                        import shutil
                        shutil.copy2(extracted_driver, driver_path)
                        logger.info(f"ChromeDriver downloaded to: {driver_path}")
                    else:
                        raise Exception("Failed to extract chromedriver.exe")
            
            # Use the manually downloaded driver
            service = webdriver.chrome.service.Service(str(driver_path))
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
            element = self._wait_for_element(xpath, 15)  # Longer timeout for JSE
            if element:
                # Scroll element into view first
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)
                element.click()
                logger.info(f"Successfully clicked: {description}")
                return True
            else:
                logger.warning(f"Could not find element to click: {description}")
                return False
        except Exception as e:
            logger.error(f"Error clicking element {description}: {e}")
            return False
    
    def _extract_sens_number(self, sens_text: str) -> str:
        """Extract SENS number from text like 'S510561 | 2025/09/15 16:45'."""
        # Look for patterns like "S510561" (S followed by digits)
        match = re.search(r'(S\d{6})', sens_text.strip())
        if match:
            return match.group(1)
        
        # Fallback: look for old patterns like "SENS 123456" or just numbers
        match = re.search(r'(?:SENS\s*)?(\d+)', sens_text.strip())
        if match:
            return match.group(1)
            
        return sens_text.strip()
    
    def _extract_sens_info(self, sens_text: str) -> Tuple[str, Optional[datetime]]:
        """Extract SENS number and publication date from text like 'S510561 | 2025/09/17 09:30'."""
        sens_number = ""
        pub_date = None
        
        try:
            # Look for the full pattern: S510561 | 2025/09/17 09:30
            match = re.search(r'(S\d{6})\s*\|\s*(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2})', sens_text.strip())
            if match:
                sens_number = match.group(1)
                date_str = match.group(2)
                time_str = match.group(3)
                
                # Parse the date and time
                datetime_str = f"{date_str} {time_str}"
                pub_date = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
                
                logger.info(f"SUCCESS: Extracted SENS info - Number: {sens_number}, Date: {pub_date}")
                return sens_number, pub_date
            
            # Fallback to just extract SENS number
            sens_number = self._extract_sens_number(sens_text)
            logger.warning(f"WARN: Could not extract publication date from '{sens_text}', got SENS: {sens_number}")
            
        except Exception as e:
            logger.error(f"ERROR: Failed to parse SENS info from '{sens_text}': {e}")
            sens_number = self._extract_sens_number(sens_text)
        
        return sens_number, pub_date
    
    def _is_urgent_announcement(self, title: str, company_name: str) -> Tuple[bool, str]:
        """Determine if an announcement is urgent based on keywords or watchlist telegram flag."""
        # First check if company is flagged for Telegram notifications
        if self.db_manager.should_send_telegram_for_company(company_name):
            return True, f"Company '{company_name}' is flagged for Telegram notifications"
        
        # Fallback to keyword-based urgency detection
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
            # Debug: Save page source for inspection
            if logger.isEnabledFor(logging.DEBUG):
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.debug("Saved page source to debug_page.html")
            
            # Try multiple strategies to find announcements
            announcement_items = []
            
            # Strategy 1: Original specific xpath
            try:
                announcement_items = self.driver.find_elements(
                    By.XPATH, 
                    "//div[contains(@class, 'announcement')]//ul/li[position()=1]"
                )
                if announcement_items:
                    logger.info(f"Strategy 1 found {len(announcement_items)} items")
            except Exception as e:
                logger.debug(f"Strategy 1 failed: {e}")
            
            # Strategy 2: Look for PDF links in list items
            if not announcement_items:
                try:
                    announcement_items = self.driver.find_elements(
                        By.XPATH,
                        "//ul/li[a[contains(@href, '.pdf')]]"
                    )
                    if announcement_items:
                        logger.info(f"Strategy 2 found {len(announcement_items)} items")
                except Exception as e:
                    logger.debug(f"Strategy 2 failed: {e}")
            
            # Strategy 3: Any link with PDF
            if not announcement_items:
                try:
                    pdf_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf')]")
                    # Convert to parent li elements
                    announcement_items = []
                    for link in pdf_links:
                        try:
                            li_parent = link.find_element(By.XPATH, "./ancestor::li[1]")
                            if li_parent not in announcement_items:
                                announcement_items.append(li_parent)
                        except:
                            # If no li parent, create a wrapper
                            announcement_items.append(link)
                    if announcement_items:
                        logger.info(f"Strategy 3 found {len(announcement_items)} items")
                except Exception as e:
                    logger.debug(f"Strategy 3 failed: {e}")
            
            # Strategy 4: Look for any structure with SENS
            if not announcement_items:
                try:
                    sens_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'SENS')]")
                    for sens_elem in sens_elements:
                        try:
                            li_parent = sens_elem.find_element(By.XPATH, "./ancestor::li[1]")
                            if li_parent not in announcement_items:
                                announcement_items.append(li_parent)
                        except:
                            pass
                    if announcement_items:
                        logger.info(f"Strategy 4 found {len(announcement_items)} items")
                except Exception as e:
                    logger.debug(f"Strategy 4 failed: {e}")
            
            logger.info(f"Found {len(announcement_items)} potential announcements on page")
            
            for i, item in enumerate(announcement_items, 1):
                try:
                    # Extract PDF link and title
                    pdf_link_element = item.find_element(By.XPATH, ".//a[contains(@href, '.pdf')]")
                    pdf_url = pdf_link_element.get_attribute('href')
                    title = pdf_link_element.text.strip()
                    
                    # Extract company name with multiple strategies
                    company_name = ""
                    
                    # Strategy 1: Original nested ul/li approach
                    try:
                        company_element = item.find_element(By.XPATH, ".//ul/li/a")
                        company_name = company_element.text.strip()
                        logger.debug(f"Company name strategy 1 worked: {company_name}")
                    except NoSuchElementException:
                        pass
                    
                    # Strategy 2: Alternative xpath
                    if not company_name:
                        try:
                            company_element = item.find_element(By.XPATH, ".//li[2]//a")
                            company_name = company_element.text.strip()
                            logger.debug(f"Company name strategy 2 worked: {company_name}")
                        except NoSuchElementException:
                            pass
                    
                    # Strategy 3: Look for any text that looks like a company name
                    if not company_name:
                        try:
                            # Get all text in the item and look for company patterns
                            item_text = item.text
                            lines = [line.strip() for line in item_text.split('\n') if line.strip()]
                            
                            for line in lines:
                                # Skip the PDF title line and SENS number
                                if 'SENS' in line.upper() or line == title:
                                    continue
                                # Look for lines that could be company names (not too short, not too long)
                                if 3 <= len(line) <= 50 and not line.isdigit():
                                    company_name = line
                                    logger.debug(f"Company name strategy 3 worked: {company_name}")
                                    break
                        except Exception as e:
                            logger.debug(f"Company name strategy 3 failed: {e}")
                    
                    # Strategy 4: Extract from PDF filename or URL
                    if not company_name:
                        try:
                            # Sometimes company name is in the PDF URL or filename
                            url_parts = pdf_url.split('/')
                            filename = url_parts[-1] if url_parts else ""
                            if filename and len(filename) > 10:
                                # Remove .pdf and try to extract meaningful name
                                base_name = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
                                if len(base_name) > 3:
                                    company_name = base_name
                                    logger.debug(f"Company name strategy 4 worked: {company_name}")
                        except Exception as e:
                            logger.debug(f"Company name strategy 4 failed: {e}")
                    
                    if not company_name:
                        logger.warning(f"Could not find company name for announcement {i}, using 'Unknown Company'")
                        company_name = "Unknown Company"
                        # Don't skip - still process the announcement
                    
                    # Check if this announcement should be ignored
                    if self._should_ignore_announcement(title, company_name):
                        continue
                    
                    # Extract SENS number and publication date (format: S510561 | 2025/09/17 09:30)
                    sens_number_element = None
                    sens_number = ""
                    pub_date = None
                    
                    try:
                        # Look for div containing S followed by digits and date/time
                        sens_number_element = item.find_element(By.XPATH, ".//div[contains(text(), 'S5') and contains(text(), '|')]")
                        sens_number, pub_date = self._extract_sens_info(sens_number_element.text)
                        logger.info(f"SUCCESS: Found SENS element with text: '{sens_number_element.text}' -> Number: {sens_number}, Date: {pub_date}")
                    except NoSuchElementException as e:
                        logger.warning(f"WARN: Primary XPath failed for item {i}: No SENS div found")
                        # Try alternative XPath - look for any div with S followed by 6 digits
                        try:
                            sens_number_element = item.find_element(By.XPATH, ".//div[contains(text(), 'S51')]")
                            sens_number, pub_date = self._extract_sens_info(sens_number_element.text)
                            logger.info(f"SUCCESS: Found SENS (alternative) with text: '{sens_number_element.text}' -> Number: {sens_number}, Date: {pub_date}")
                        except NoSuchElementException as e2:
                            logger.warning(f"WARN: Alternative XPath also failed for item {i}: No SENS div found")
                            # Log the item text for debugging
                            try:
                                item_text = item.text
                                logger.warning(f"DEBUG: Item {i} full text: '{item_text}'")
                                
                                # Try to extract from title or item text
                                sens_match = re.search(r'(S\d{6})', item_text, re.IGNORECASE)
                                if sens_match:
                                    sens_number = sens_match.group(1)
                                    logger.info(f"SUCCESS: Extracted SENS from item text: '{sens_number}'")
                                else:
                                    # Try from title
                                    sens_match = re.search(r'(S\d{6})', title, re.IGNORECASE)
                                    if sens_match:
                                        sens_number = sens_match.group(1)
                                        logger.info(f"SUCCESS: Extracted SENS from title: '{sens_number}'")
                                    else:
                                        # Use timestamp as fallback
                                        sens_number = f"TEMP_{int(datetime.now().timestamp())}"
                                        logger.warning(f"WARN: Could not extract SENS number from anywhere, using fallback: {sens_number}")
                            except Exception as e3:
                                sens_number = f"TEMP_{int(datetime.now().timestamp())}"
                                logger.error(f"ERROR: Error getting item text for item {i}: {e3}, using fallback: {sens_number}")
                    
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
                        date_published=pub_date or datetime.now(),  # Use extracted publication date or fallback to now
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
            
            # Wait for page to load completely
            logger.info("Waiting for JSE page to load completely...")
            time.sleep(10)
            
            # Click "Last 30 days" button
            if self._click_element_safely(self.XPATH_LAST_30_DAYS, "Last 30 days button"):
                logger.info("Waiting for SENS announcements to load (30 seconds - JSE is very slow)...")
                time.sleep(30)  # Wait for results to load - JSE is VERY slow!
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
            
            # Create/update Excel spreadsheet with all announcements
            if announcements:
                try:
                    excel_path = self.excel_manager.create_or_update_spreadsheet(announcements)
                    logger.info(f"Excel spreadsheet created/updated: {excel_path}")
                except Exception as e:
                    logger.error(f"Failed to create Excel spreadsheet: {e}")
            
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
            
            # Wait for page to load completely
            logger.info("Waiting for JSE page to load completely...")
            time.sleep(10)
            
            # Click "Today's announcements" button to ensure we're looking at today
            if self._click_element_safely(self.XPATH_TODAY_ANNOUNCEMENTS, "Today's announcements button"):
                logger.info("Waiting for SENS announcements to load (15 seconds)...")
                time.sleep(15)  # Wait for results to load - JSE is slow!
            
            # Scrape announcements
            announcements = self._scrape_announcements_from_page()
            
            # Save new announcements to database
            saved_count = 0
            new_announcements: List[SensAnnouncement] = []
            for announcement in announcements:
                try:
                    if not self.db_manager.sens_exists(announcement.sens_number):
                        self.db_manager.add_sens_announcement(announcement)
                        saved_count += 1
                        new_announcements.append(announcement)
                    else:
                        logger.debug(f"SENS {announcement.sens_number} already exists")
                except Exception as e:
                    logger.error(f"Failed to save announcement {announcement.sens_number}: {e}")
            
            logger.info(f"Daily scrape completed: {saved_count} new announcements found")
            
            # Update Excel spreadsheet if we have new announcements
            if saved_count > 0:
                try:
                    if new_announcements:
                        excel_path = self.excel_manager.create_or_update_spreadsheet(new_announcements)
                        logger.info(f"Excel spreadsheet updated: {excel_path}")
                except Exception as e:
                    logger.error(f"Failed to update Excel spreadsheet: {e}")
            
            # Return only the newly saved announcements so downstream processing can act on them
            return new_announcements
            
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
