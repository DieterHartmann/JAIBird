#!/usr/bin/env python3
"""
Helper script to get your Telegram chat ID for JAIBird setup.
"""

import sys
import os
import requests

# Add src to path for config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.utils.config import get_config
    
    config = get_config()
    
    if not config.telegram_bot_token:
        print("❌ No Telegram bot token found in .env file")
        print("Please add your TELEGRAM_BOT_TOKEN to the .env file first")
        sys.exit(1)
    
    print("🤖 Getting Telegram Chat ID...")
    print("=" * 50)
    
    # Get updates from Telegram
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/getUpdates"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        if data['result']:
            print("✅ Found messages! Here are your chat IDs:")
            print()
            
            seen_chats = set()
            for message in data['result']:
                if 'message' in message:
                    chat = message['message']['chat']
                    chat_id = chat['id']
                    chat_type = chat['type']
                    
                    if chat_id not in seen_chats:
                        seen_chats.add(chat_id)
                        
                        if chat_type == 'private':
                            first_name = chat.get('first_name', 'Unknown')
                            last_name = chat.get('last_name', '')
                            username = chat.get('username', '')
                            
                            print(f"👤 Private Chat:")
                            print(f"   Chat ID: {chat_id}")
                            print(f"   Name: {first_name} {last_name}".strip())
                            if username:
                                print(f"   Username: @{username}")
                            print()
                        else:
                            title = chat.get('title', 'Unknown Group')
                            print(f"👥 Group Chat:")
                            print(f"   Chat ID: {chat_id}")
                            print(f"   Title: {title}")
                            print()
            
            print("📝 To use JAIBird:")
            print("1. Copy the Chat ID you want to use")
            print("2. Add it to your .env file as: TELEGRAM_CHAT_ID=your_chat_id_here")
            print("3. Run: python main.py test-telegram")
            
        else:
            print("❌ No messages found!")
            print()
            print("To get your chat ID:")
            print("1. Send a message to your bot on Telegram")
            print("2. Run this script again")
            
    else:
        print(f"❌ Error getting updates: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    print()
    print("Make sure:")
    print("1. Your .env file exists and has TELEGRAM_BOT_TOKEN set")
    print("2. Your bot token is valid")
    print("3. You have internet connection")
