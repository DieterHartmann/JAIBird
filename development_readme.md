# JAIBird - Stock Trading Platform Development Documentation

## Project Vision
JAIBird is a comprehensive stock trading platform designed as an information aggregator and movement detection tool. The platform merges qualitative and quantitative assessments using publicly available sources including the JSE website, South African press, and company websites.

## Core Architecture

### Phase 1: SENS Announcement Scraping & Notification System
The foundation of the platform focuses on automated SENS (Stock Exchange News Service) announcement monitoring and intelligent notification delivery.

#### Key Components:
1. **SENS Scraper**: Selenium-based web scraper for JSE SENS announcements
2. **Storage System**: Dual storage (Dropbox + local cache) for performance optimization
3. **Notification Engine**: Telegram (urgent) + Email (daily digest) notifications
4. **Watchlist Database**: SQLite database for company tracking
5. **Flask Web Interface**: Management interface for watchlist and configuration
6. **Configuration System**: Flexible config for timing, storage, and preferences

## Technical Stack
- **Backend**: Python 3.x
- **Web Scraping**: Selenium WebDriver
- **Database**: SQLite (initial), PostgreSQL (future scaling)
- **Web Framework**: Flask
- **Cloud Storage**: Dropbox API
- **Notifications**: Telegram Bot API, SMTP Email
- **AI Integration**: Anthropic Claude, OpenAI APIs
- **Deployment**: Raspberry Pi (production)

## SENS Scraping Specifications

### Target URL
`https://clientportal.jse.co.za/communication/sens-announcements`

### Key XPath Selectors:
- **PDF Link**: `/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/a`
- **Company Name**: `/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/ul/li/a`
- **SENS Number**: `/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/ul/li[1]/div`
- **Last 30 Days Button**: `/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[1]/div[2]/div[3]/input`
- **Today's Announcements**: `/html/body/form/div[4]/div[1]/div[4]/div[1]/div/div/div/div/div/div[1]/div/div[1]/div[2]/div[1]/input`

### Scraping Logic:
1. **Initial Setup**: Click "Last 30 days" for first-time initialization
2. **Regular Operation**: Default to "Today's announcements" (force click for reliability)
3. **Deduplication**: Use SENS sequential numbers to avoid re-downloading
4. **Storage**: Download PDFs to Dropbox, maintain local cache
5. **Frequency**: Every 5 minutes (configurable)

## Notification Strategy

### Immediate Notifications (Telegram):
- Companies on watchlist
- Critical announcements (profit warnings, delistings, major news)
- Time-sensitive market movements

### Daily Digest (Email):
- All other SENS announcements
- Configurable delivery time (default: 08:30, alternative: 13:00)
- Summary format with links to full documents

## Database Schema

### Tables:
1. **companies**: Watchlist management
   - id, name, jse_code, added_date, active_status
2. **sens_announcements**: SENS tracking
   - id, sens_number, company_name, title, pdf_url, date_published, processed_date
3. **notifications**: Notification log
   - id, sens_id, notification_type, sent_date, status
4. **config**: System configuration
   - key, value, description, last_updated

## Configuration Management

### Environment Variables (.env):
```
# API Keys
DROPBOX_ACCESS_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Email Configuration
SMTP_SERVER=
SMTP_PORT=
EMAIL_USERNAME=
EMAIL_PASSWORD=
NOTIFICATION_EMAIL=

# Scraping Configuration
SCRAPE_INTERVAL_MINUTES=5
LOCAL_CACHE_RETENTION_DAYS=30
DAILY_DIGEST_TIME=08:30

# Storage Paths
LOCAL_STORAGE_PATH=./data/sens_pdfs/
DROPBOX_FOLDER=/JAIBird/SENS/
```

## Future Development Roadmap

### Phase 2: Media & Sentiment Analysis
- Longitudinal media scraping from SA financial press
- Sentiment analysis on company coverage
- Key personnel press coverage monitoring
- Social media sentiment tracking (where possible)

### Phase 3: Advanced Analytics
- Technical analysis integration
- Quantitative scoring models
- Predictive analytics for market movements
- Portfolio management tools

### Phase 4: Trading Integration
- Broker API integration
- Automated trading strategies
- Risk management systems
- Performance tracking and reporting

## Development Guidelines

### Code Organization:
```
JAIBird/
├── src/
│   ├── scrapers/
│   ├── notifications/
│   ├── database/
│   ├── web/
│   └── utils/
├── data/
├── config/
├── tests/
└── docs/
```

### Git Workflow:
- Regular commits with descriptive messages
- Feature branches for major developments
- Automated testing before merges
- Production deployment tags

### Performance Considerations:
- Local caching for frequently accessed data
- Efficient deduplication algorithms
- Asynchronous processing for notifications
- Resource-conscious scraping intervals

## Security & Privacy
- API keys in environment variables only
- Secure storage of user data
- Rate limiting for external API calls
- Regular security updates for dependencies

## Testing Strategy
- Unit tests for core functions
- Integration tests for external APIs
- End-to-end tests for scraping workflows
- Performance testing for production deployment

---

*This document is a living specification that evolves with the project. All architectural decisions and future enhancements should be documented here.*
