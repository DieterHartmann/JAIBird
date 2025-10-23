#!/usr/bin/env python3
"""
Helper script to get Dropbox refresh token for JAIBird.
This handles the OAuth flow to get a permanent refresh token.
"""

import requests
import base64
import webbrowser
import urllib.parse
from typing import Dict, Any

def get_dropbox_refresh_token():
    """Interactive script to get Dropbox refresh token."""
    
    print("🔄 JAIBird Dropbox Refresh Token Generator")
    print("=" * 50)
    
    # Get app credentials
    app_key = input("Enter your Dropbox App Key: ").strip()
    app_secret = input("Enter your Dropbox App Secret: ").strip()
    
    if not app_key or not app_secret:
        print("❌ App Key and Secret are required!")
        return
    
    # Step 1: Generate authorization URL
    redirect_uri = "http://localhost:8080"  # You can use any URI you control
    auth_url = (
        f"https://www.dropbox.com/oauth2/authorize?"
        f"client_id={app_key}&"
        f"response_type=code&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"token_access_type=offline"  # This requests a refresh token
    )
    
    print(f"\n🌐 Opening authorization URL in your browser...")
    print(f"URL: {auth_url}")
    
    try:
        webbrowser.open(auth_url)
    except:
        print("⚠️ Could not open browser automatically.")
        print("Please copy and paste the URL above into your browser.")
    
    print("\n📋 After authorizing:")
    print("1. You'll be redirected to a URL that starts with your redirect URI")
    print("2. Copy the 'code' parameter from that URL")
    print("3. Example: http://localhost:8080?code=ABC123&state=...")
    print("4. Copy just the 'ABC123' part")
    
    auth_code = input("\nEnter the authorization code: ").strip()
    
    if not auth_code:
        print("❌ Authorization code is required!")
        return
    
    # Step 2: Exchange code for tokens
    print("\n🔄 Exchanging code for tokens...")
    
    # Prepare authentication header
    credentials = f"{app_key}:{app_secret}"
    auth_header = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }
    
    try:
        response = requests.post(
            "https://api.dropboxapi.com/oauth2/token",
            headers=headers,
            data=data
        )
        
        if response.status_code == 200:
            token_data = response.json()
            
            print("\n✅ Success! Here are your tokens:")
            print("=" * 50)
            print(f"Access Token: {token_data.get('access_token', 'Not found')}")
            print(f"Refresh Token: {token_data.get('refresh_token', 'Not found')}")
            print(f"Token Type: {token_data.get('token_type', 'Not found')}")
            print(f"Expires In: {token_data.get('expires_in', 'Not found')} seconds")
            
            print("\n📝 Add these to your .env file:")
            print("=" * 50)
            print(f"DROPBOX_ACCESS_TOKEN={token_data.get('access_token', '')}")
            print(f"DROPBOX_REFRESH_TOKEN={token_data.get('refresh_token', '')}")
            print(f"DROPBOX_APP_KEY={app_key}")
            
            print("\n🎉 Your tokens are now set up for automatic refresh!")
            
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error making request: {e}")

if __name__ == "__main__":
    get_dropbox_refresh_token()
