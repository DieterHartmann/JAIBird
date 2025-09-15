"""
Simple test script to verify the configuration loads properly.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.utils.config import get_config
    
    print("🧪 Testing JAIBird Configuration...")
    
    config = get_config()
    print("✅ Configuration loaded successfully!")
    
    print(f"📊 Environment: {config.environment}")
    print(f"⏱️  Scrape Interval: {config.scrape_interval_minutes} minutes")
    print(f"📧 Email enabled: {config.email_notifications_enabled}")
    print(f"💬 Telegram enabled: {config.telegram_notifications_enabled}")
    print(f"🧪 Test mode: {config.test_mode}")
    
    print("\n🎉 Configuration test passed! JAIBird is ready to run.")
    
except Exception as e:
    print(f"❌ Configuration test failed: {e}")
    print("\nPlease check your .env file configuration.")
    sys.exit(1)
