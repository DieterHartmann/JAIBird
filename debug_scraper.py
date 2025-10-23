#!/usr/bin/env python3
"""
Debug script for SENS scraper - helps identify JSE website structure.
"""

import sys
import os
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def debug_jse_page():
    """Debug the JSE SENS page structure."""
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    print("🔍 JAIBird SENS Scraper Debug")
    print("=" * 50)
    
    # Set up Chrome driver
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    try:
        service = webdriver.chrome.service.Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        print("✅ Chrome WebDriver initialized")
        
        # Navigate to JSE SENS page
        jse_url = "https://clientportal.jse.co.za/communication/sens-announcements"
        print(f"🌐 Navigating to: {jse_url}")
        driver.get(jse_url)
        
        # Wait for page to load completely (JSE is slow)
        import time
        print("⏳ Waiting for page to load completely (10 seconds)...")
        time.sleep(10)
        
        print(f"📄 Page title: {driver.title}")
        print(f"🔗 Current URL: {driver.current_url}")
        
        # Try to click "Last 30 days" button
        try:
            last_30_days_xpath = "/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[1]/div[2]/div[3]/input"
            button = driver.find_element(By.XPATH, last_30_days_xpath)
            # Scroll into view first
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(1)
            button.click()
            print("✅ Clicked 'Last 30 days' button")
            print("⏳ Waiting for announcements to load (30 seconds - JSE is VERY slow)...")
            time.sleep(30)  # JSE is VERY slow!
        except Exception as e:
            print(f"⚠️ Could not click 'Last 30 days' button: {e}")
            print("Proceeding with current page content...")
        
        # Look for PDF links
        pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf')]")
        print(f"📄 Found {len(pdf_links)} PDF links")
        
        if pdf_links:
            print("\n🔍 PDF Links Analysis:")
            for i, link in enumerate(pdf_links[:5], 1):  # Show first 5
                try:
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    parent_text = link.find_element(By.XPATH, "./..").text.strip()
                    
                    print(f"\n  📄 PDF {i}:")
                    print(f"     URL: {href}")
                    print(f"     Link Text: {text}")
                    print(f"     Parent Text: {parent_text[:100]}...")
                    
                except Exception as e:
                    print(f"     Error analyzing PDF {i}: {e}")
        
        # Look for SENS text
        sens_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'SENS')]")
        print(f"\n🏷️  Found {len(sens_elements)} elements containing 'SENS'")
        
        if sens_elements:
            print("\n🔍 SENS Elements Analysis:")
            for i, elem in enumerate(sens_elements[:5], 1):  # Show first 5
                try:
                    text = elem.text.strip()
                    tag = elem.tag_name
                    print(f"  🏷️  SENS {i}: <{tag}> {text}")
                except Exception as e:
                    print(f"     Error analyzing SENS {i}: {e}")
        
        # Save page source for manual inspection
        try:
            with open("debug_jse_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"\n💾 Saved page source to: debug_jse_page.html")
        except Exception as e:
            print(f"⚠️ Could not save page source: {e}")
        
        # Look for list structures
        ul_elements = driver.find_elements(By.TAG_NAME, "ul")
        print(f"\n📋 Found {len(ul_elements)} <ul> elements")
        
        li_elements = driver.find_elements(By.TAG_NAME, "li")
        print(f"📋 Found {len(li_elements)} <li> elements")
        
        # Try to find announcement containers
        announcement_containers = driver.find_elements(By.XPATH, "//div[contains(@class, 'announcement')]")
        print(f"📦 Found {len(announcement_containers)} announcement containers")
        
        if not announcement_containers:
            # Look for any div that might contain announcements
            all_divs = driver.find_elements(By.TAG_NAME, "div")
            print(f"📦 Total <div> elements: {len(all_divs)}")
            
            # Look for divs with IDs or classes that might be relevant
            relevant_divs = []
            for div in all_divs:
                div_class = div.get_attribute('class') or ''
                div_id = div.get_attribute('id') or ''
                if any(keyword in (div_class + div_id).lower() for keyword in ['sens', 'announcement', 'news', 'content', 'list']):
                    relevant_divs.append((div, div_class, div_id))
            
            print(f"📦 Found {len(relevant_divs)} potentially relevant divs:")
            for div, div_class, div_id in relevant_divs[:10]:  # Show first 10
                print(f"     Class: '{div_class}', ID: '{div_id}'")
        
        print(f"\n🎉 Debug completed! Check debug_jse_page.html for full page source.")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            driver.quit()
    
    return True

if __name__ == "__main__":
    debug_jse_page()
