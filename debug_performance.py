#!/usr/bin/env python3

from src.database.models import DatabaseManager
from src.utils.config import get_config
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

def analyze_recent_sens():
    """Analyze recent SENS for inconsistent AI processing."""
    config = get_config()
    db = DatabaseManager(config.database_path)
    
    print("=== RECENT SENS ANALYSIS ===")
    recent = db.get_recent_sens(15)
    
    for i, sens in enumerate(recent, 1):
        has_summary = 'YES' if sens.ai_summary else 'NO'
        parse_status = sens.parse_status or 'None'
        is_urgent = 'YES' if sens.is_urgent else 'NO'
        print(f"{i:2d}. {sens.sens_number} - {sens.company_name[:25]:25s} | AI: {has_summary:3s} | Parse: {parse_status:9s} | Urgent: {is_urgent:3s}")
    
    print("\n=== FIRSTRAND AND PRESCIENT DETAILED CHECK ===")
    problem_companies = ['firstrand', 'prescient']
    
    for sens in recent:
        company_lower = sens.company_name.lower()
        if any(company in company_lower for company in problem_companies):
            print(f"SENS {sens.sens_number}: {sens.company_name}")
            print(f"  Parse Status: {sens.parse_status}")
            print(f"  Parse Method: {sens.parse_method}")
            print(f"  AI Summary Length: {len(sens.ai_summary) if sens.ai_summary else 0} chars")
            print(f"  PDF Content Length: {len(sens.pdf_content) if sens.pdf_content else 0} chars")
            print(f"  Is Urgent: {sens.is_urgent}")
            print(f"  Date Scraped: {sens.date_scraped}")
            print(f"  Local PDF Path: {sens.local_pdf_path}")
            print()

def check_telegram_config():
    """Check Telegram notification configuration."""
    print("=== TELEGRAM CONFIGURATION CHECK ===")
    config = get_config()
    
    print(f"Telegram Notifications Enabled: {config.telegram_notifications_enabled}")
    print(f"Telegram Bot Token Set: {'YES' if config.telegram_bot_token else 'NO'}")
    print(f"Telegram Chat ID Set: {'YES' if config.telegram_chat_id else 'NO'}")
    print(f"Test Mode: {config.test_mode}")
    
    # Check watchlist companies with Telegram flags
    db = DatabaseManager(config.database_path)
    companies = db.get_all_companies()
    telegram_enabled = [c for c in companies if c.active_status and c.send_telegram]
    
    print(f"\nWatchlist Companies with Telegram Enabled:")
    for company in telegram_enabled:
        print(f"  - {company.name} ({company.jse_code})")

if __name__ == "__main__":
    analyze_recent_sens()
    print()
    check_telegram_config()
