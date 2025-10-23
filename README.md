# JAIBird Stock Trading Platform

🚀 **JAIBird** is an intelligent stock market monitoring platform focused on automated SENS (Stock Exchange News Service) announcement tracking and notification delivery for the Johannesburg Stock Exchange (JSE).

## 🐍 **Environment Setup**

**IMPORTANT**: JAIBird requires a dedicated Python environment to avoid package conflicts. Use the clean requirements file for setup:

```bash
# Create dedicated environment
conda create -n jaibird python=3.11
conda activate jaibird

# Install from clean requirements (avoids pandas/numpy conflicts)
pip install -r requirements_clean.txt
```

This prevents binary compatibility issues with pandas/numpy that can occur in shared environments.

## Features

- **Automated SENS Scraping**: Continuously monitors JSE SENS announcements
- **Intelligent Notifications**: Telegram alerts for urgent announcements, email digests for daily summaries
- **Watchlist Management**: Track specific companies with immediate notifications
- **PDF Storage**: Automatic download and cloud storage via Dropbox
- **Web Interface**: Modern Flask-based dashboard for management
- **Smart Detection**: Automatically identifies urgent announcements (profit warnings, delistings, etc.)

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd JAIBird

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy the environment template
copy env_template.txt .env

# Edit .env with your API keys and preferences
# - Dropbox access token
# - Telegram bot token and chat ID
# - Email SMTP settings
# - AI API keys (optional)
```

### 3. Setup

```bash
# Initialize the system
python main.py setup

# Perform initial SENS scrape (last 30 days)
python main.py initial-scrape
```

### 4. Run

```bash
# Start web interface
python main.py web

# OR start automated scheduler
python main.py scheduler

# OR run specific commands
python main.py scrape          # Manual scrape
python main.py digest          # Send daily digest
python main.py test-notifications  # Test notifications
```

## Architecture

### Core Components

- **SENS Scraper**: Selenium-based web scraper for JSE announcements
- **Database**: SQLite database for companies, announcements, and notifications
- **Notification System**: Telegram + Email notifications with smart routing
- **Dropbox Integration**: Cloud storage for PDF announcements
- **Web Interface**: Flask dashboard for management and monitoring

### Directory Structure

```
JAIBird/
├── src/
│   ├── scrapers/       # Web scraping components
│   ├── database/       # Database models and operations
│   ├── notifications/  # Telegram and email notifications
│   ├── utils/          # Configuration and utilities
│   └── web/           # Flask web interface
├── data/              # Local storage and database
├── logs/              # Application logs
└── main.py           # Main entry point
```

## Usage

### Web Interface

Access the web interface at `http://localhost:5000` to:

- View recent SENS announcements
- Manage your company watchlist
- Monitor system statistics
- Test notifications
- Trigger manual scrapes

### Command Line

```bash
# Available commands
python main.py web                 # Start web interface
python main.py scheduler           # Start automated monitoring
python main.py scrape             # Manual SENS scrape
python main.py initial-scrape     # Initial 30-day scrape
python main.py digest             # Send daily digest
python main.py test-notifications # Test notification systems
python main.py setup              # System setup and verification
python main.py status             # System status check
```

### Notifications

**Telegram (Immediate)**:
- Companies on your watchlist
- Urgent announcements (profit warnings, delistings, etc.)

**Email (Daily Digest)**:
- All SENS announcements from the previous day
- Configurable delivery time (default: 08:30)

## Configuration

Key configuration options in `.env`:

```env
# Scraping
SCRAPE_INTERVAL_MINUTES=5
DAILY_DIGEST_TIME=08:30

# Storage
LOCAL_CACHE_RETENTION_DAYS=30
DROPBOX_FOLDER=/JAIBird/SENS/

# Notifications
URGENT_KEYWORDS=profit warning,delisting,suspension,trading halt
TELEGRAM_NOTIFICATIONS_ENABLED=true
EMAIL_NOTIFICATIONS_ENABLED=true

# Development
ENVIRONMENT=development
TEST_MODE=false
```

## API Integration

JAIBird requires several API integrations:

1. **Dropbox**: For PDF storage
2. **Telegram Bot**: For instant notifications
3. **Email SMTP**: For daily digests
4. **Anthropic/OpenAI**: For future AI features

## Deployment

### Raspberry Pi (Recommended)

```bash
# Install Python dependencies
sudo apt update && sudo apt install python3-pip chromium-browser

# Install ChromeDriver
sudo apt install chromium-chromedriver

# Clone and setup JAIBird
git clone <repo-url> && cd JAIBird
pip3 install -r requirements.txt

# Create systemd service for auto-start
sudo cp scripts/jaibird.service /etc/systemd/system/
sudo systemctl enable jaibird
sudo systemctl start jaibird
```

### Production Considerations

- Use `WEBDRIVER_HEADLESS=true` for server deployment
- Set `ENVIRONMENT=production` in .env
- Configure proper logging with log rotation
- Set up monitoring for the scheduler process
- Use a reverse proxy (nginx) for the web interface

## Development

### Adding New Features

1. Update `development_readme.md` with design decisions
2. Follow the existing code structure
3. Add appropriate logging
4. Update configuration as needed
5. Test with `TEST_MODE=true`

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Troubleshooting

### Common Issues

**Selenium WebDriver Issues**:
```bash
# Install/update ChromeDriver
pip install --upgrade webdriver-manager
```

**Dropbox Connection Failed**:
- Verify your access token in .env
- Check Dropbox app permissions

**No SENS Found**:
- Check JSE website structure hasn't changed
- Verify XPath selectors in sens_scraper.py

**Notifications Not Working**:
```bash
# Test notification systems
python main.py test-notifications
```

### Logs

Check application logs for detailed error information:
- Location: `./logs/jaibird.log`
- Level: Configurable via `LOG_LEVEL` in .env

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please:
1. Check the troubleshooting section
2. Review the logs for error details
3. Open an issue on GitHub with detailed information

---

**JAIBird** - Intelligent Stock Market Monitoring 📊🤖
