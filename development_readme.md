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
- **Architecture**: Multi-process design to avoid async/sync conflicts

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

## Multi-Process Architecture

### The Async/Sync Conflict Problem
**Problem**: Mixing async (Telegram Bot API) and sync (Flask, email, scraping) operations in the same Python process causes event loop conflicts, leading to errors like:
- `'coroutine' object has no attribute 'username'`
- `RuntimeError: This event loop is already running`
- `RuntimeWarning: coroutine was never awaited`

### Solution: Process Separation
JAIBird uses a **multi-process architecture** to completely isolate async and sync operations:

#### 1. Main Processes:
- **Scheduler Process**: Handles scraping, database operations, email notifications
- **Web Interface Process**: Flask app for management interface
- **Telegram Sender Process**: Isolated async Telegram operations

#### 2. Implementation Details:

**Telegram Isolation**:
```python
# Instead of direct async calls in main process:
bot = Bot(token)
await bot.send_message()  # ❌ Causes conflicts

# Use subprocess isolation:
subprocess.run(['python', 'telegram_sender.py', message_file])  # ✅ Clean separation
```

**Process Communication**:
- JSON files for message passing between processes
- Temporary files for data exchange
- Exit codes for success/failure communication

#### 3. Deployment Strategies:

**Windows (Development/Production)**:
```batch
start_jaibird.bat  # Launches all processes
stop_jaibird.bat   # Stops all processes
```

**Linux/Raspberry Pi (Production)**:
```bash
# Systemd services for each process
sudo systemctl start jaibird-scheduler
sudo systemctl start jaibird-web
```

#### 4. Benefits:
- ✅ **No async conflicts**: Each process has its own event loop
- ✅ **Fault isolation**: One process crash doesn't affect others
- ✅ **Scalability**: Easy to distribute across multiple machines
- ✅ **Maintainability**: Clear separation of concerns
- ✅ **Debugging**: Isolated logs per process

#### 5. File Structure:
```
src/notifications/
├── notifier.py           # Main notification coordinator
├── telegram_sender.py    # Isolated async Telegram process
└── email_sender.py       # Sync email operations
```

### Best Practices for Future Development:

1. **Keep Async Isolated**: Any new async operations (Discord, Slack, etc.) should use subprocess pattern
2. **Process Communication**: Use JSON files or queues for inter-process communication
3. **Error Handling**: Each process should handle its own errors and report via exit codes
4. **Logging**: Separate log files per process for debugging
5. **Testing**: Test each process independently

### Common Patterns to Avoid:
```python
# ❌ DON'T: Mix async and sync in same process
class BadNotifier:
    def __init__(self):
        self.bot = Bot(token)  # Async
        self.email = SMTPClient()  # Sync
    
    def send_all(self):
        asyncio.run(self.bot.send())  # ❌ Event loop conflicts
        self.email.send()

# ✅ DO: Separate processes
class GoodNotifier:
    def send_telegram(self, data):
        subprocess.run(['python', 'telegram_sender.py', data])
    
    def send_email(self, data):
        self.email.send(data)  # Pure sync
```

This architecture pattern should be used for **any future project** that needs to mix async and sync operations.

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

## Dropbox OAuth 2.0 Setup (Critical Reference)

### Getting Refresh Tokens (Required - Long-lived tokens are deprecated)

**Problem**: Dropbox deprecated long-lived access tokens in 2021. You MUST use short-lived tokens + refresh tokens.

**Solution Process**:

1. **Authorization URL** (CRITICAL: Must include `token_access_type=offline`):
   ```
   https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&response_type=code&token_access_type=offline
   ```

2. **Authorize and get code** from redirect URL (expires in ~10 minutes - work quickly!)

3. **PowerShell command** (paste as one line):
   ```powershell
   $body = "code=YOUR_CODE&grant_type=authorization_code&client_id=YOUR_APP_KEY&client_secret=YOUR_APP_SECRET"; $response = Invoke-WebRequest -Uri "https://api.dropbox.com/oauth2/token" -Method POST -ContentType "application/x-www-form-urlencoded" -Body $body; $response.Content | Out-File -FilePath "dropbox_tokens.txt"; Get-Content "dropbox_tokens.txt"
   ```

4. **Add to .env file**:
   ```
   DROPBOX_ACCESS_TOKEN=sl.u.ABC123...
   DROPBOX_REFRESH_TOKEN=DEF456...
   DROPBOX_APP_KEY=your_app_key
   DROPBOX_APP_SECRET=your_app_secret
   ```

**Key Points**:
- Authorization codes expire quickly (~10 minutes)
- MUST include `token_access_type=offline` or no refresh token
- PowerShell truncates output with `...` - save to file to see full response
- Access tokens expire every ~4 hours but refresh automatically with this setup

## Excel Export System

### Overview
JAIBird automatically creates and maintains an Excel spreadsheet with all SENS announcements for easy analysis and reporting.

### Features
- **Automatic Export**: Excel file is updated automatically after each scrape
- **Newest First**: New SENS announcements are added at the top, pushing older ones down
- **Comprehensive Data**: Includes date, SENS number, organization, heading, PDF link, and urgency status
- **Local PDF Links**: Prioritizes local PDF file paths over online URLs for better reliability
- **Manual Export**: Command-line tool to export all existing data

### File Structure
**Location**: `data/sens_announcements.xlsx`

**Columns**:
1. **Date** - Publication date and time of SENS announcement
2. **SENS Number** - Unique JSE SENS identifier (e.g., S510561)
3. **Organization** - Company or entity that published the SENS
4. **Heading** - Title/subject of the SENS announcement
5. **PDF Link** - Path to PDF file (local preferred, online fallback)
6. **PDF Summary** - AI-generated summary (placeholder for future feature)
7. **Urgent** - Whether announcement was flagged as urgent (YES/NO)
8. **Created** - When record was added to JAIBird database

### Usage
```bash
# Automatic export (happens during scraping)
python main.py initial-scrape  # Creates/updates Excel file
python main.py scrape          # Updates Excel file with new SENS

# Manual export of all data
python main.py export-excel
```

### Excel File Features
- **Formatted Headers**: Professional styling with blue headers
- **Auto-sized Columns**: Optimized widths for readability
- **Frozen Header**: Header row stays visible when scrolling
- **Metadata Sheet**: Export information and column descriptions
- **Duplicate Prevention**: SENS numbers are unique across exports

### Future Enhancement: AI PDF Summaries

**Planned Feature**: Automatic AI-generated summaries of SENS PDF content.

**Implementation Plan**:
1. **PDF Text Extraction**: Extract text content from downloaded PDFs
2. **AI Summarization**: Use Anthropic Claude or OpenAI GPT to generate concise summaries
3. **Summary Storage**: Store summaries in database and update Excel automatically
4. **Key Information Extraction**: Extract key financial figures, dates, and business impacts
5. **Urgency Classification**: Enhance urgent detection based on PDF content analysis

**Target Columns for AI Enhancement**:
- `PDF Summary`: Concise 2-3 sentence summary of the announcement
- `Key Figures`: Extracted financial numbers, percentages, dates
- `Business Impact`: Classification of impact type (financial, operational, regulatory)
- `Sentiment`: Positive/Negative/Neutral classification

**Configuration Options** (future):
```env
# AI Summary Settings
ENABLE_PDF_SUMMARIES=true
AI_PROVIDER=anthropic  # anthropic or openai
MAX_SUMMARY_LENGTH=200
SUMMARY_LANGUAGE=english
EXTRACT_KEY_FIGURES=true
```

**Benefits**:
- Rapid understanding of SENS content without reading full PDFs
- Better filtering and prioritization of announcements
- Enhanced watchlist alerts with context
- Improved investment decision making through quick content analysis

---

## Session Progress: September 17, 2025

### Major Accomplishments

**AI-Powered PDF Processing System Implementation**
- Successfully integrated OpenAI and Anthropic APIs for PDF content analysis and summarization
- Implemented multi-stage PDF parsing with OCR-first approach and AI fallback for cost optimization
- Created `src/ai/pdf_parser.py` with comprehensive PDF text extraction and AI summarization
- Added configurable AI provider selection (OpenAI/Anthropic) with separate keys for parsing vs. summarization
- Implemented SPODE (Simple, Practical, One Definition Everywhere) pattern for API key fallbacks
- Fixed critical Tesseract OCR path issues by setting `TESSDATA_PREFIX` environment variable correctly
- Added AI summary storage in database with parsing status tracking and method logging

**Database Schema Evolution for AI Integration**
- Extended `sens_announcements` table with AI-related columns: `pdf_content`, `ai_summary`, `parse_method`, `parse_status`, `parsed_at`
- Added `send_telegram` boolean field to `companies` table for granular Telegram notification control
- Implemented automatic database migration system to handle schema updates gracefully
- Enhanced fuzzy matching for company watchlist detection with bidirectional LIKE queries
- Fixed `sqlite3.Row` object access issues by replacing `.get()` with proper key checking

**Notification System Refinement**
- Implemented configurable Telegram notifications per company with `send_telegram` flag
- Enhanced urgency detection to prioritize watchlist company flags over keyword-based detection
- Added AI summaries to Telegram notifications with interactive PDF request buttons
- Created interactive Telegram bot (`src/notifications/telegram_bot.py`) for PDF document delivery
- Fixed notification workflow to ensure all new SENS trigger appropriate processing

**Web Interface AI Integration**
- Added AI summary tooltips to web interface with Bootstrap integration
- Displayed robot icons for SENS with AI summaries for quick visual identification
- Created Telegram notification toggle switches in watchlist management
- Added real-time API endpoint for updating company Telegram preferences
- Enhanced UI with visual indicators for AI-processed content

**SENS Scraping Intelligence Improvements**
- Enhanced SENS number and publication date extraction from format `S510630 | 2025/09/17 09:30`
- Added intelligent announcement filtering to skip irrelevant content (e.g., "JSE Contact List")
- Improved company name extraction with multiple fallback strategies
- Updated urgent keywords list with financial reporting terms like "Late Submission of Condensed Financial Statements"
- Corrected SENS ordering logic to prioritize publication date over SENS number for chronological accuracy

**Automated PDF Processing Workflow**
- Integrated PDF parsing directly into scraping workflow for immediate AI summary generation
- Ensured all new SENS announcements automatically receive AI processing regardless of urgency
- Fixed CLI scrape command to include full notification and PDF processing pipeline
- Synchronized scheduled scraper and CLI scraper to have identical processing capabilities
- Added comprehensive error handling and logging for PDF processing failures

### Critical Technical Fixes Resolved

1. **OCR Path Configuration**: Fixed Tesseract `TESSDATA_PREFIX` environment variable to enable cost-effective OCR processing
2. **Database Migration**: Implemented automatic schema updates to handle new AI-related columns
3. **Row Object Access**: Fixed `sqlite3.Row` object attribute access throughout database operations
4. **Notification Workflow**: Resolved inconsistent notification triggers by integrating processing into all scrape operations
5. **AI API Configuration**: Implemented flexible API key management with fallback patterns for different AI operations
6. **Fuzzy Matching Logic**: Enhanced company name matching for watchlist detection with bidirectional queries
7. **SENS Date Extraction**: Improved publication date parsing from JSE's combined SENS number and timestamp format

### Architecture Patterns Established

**SPODE Configuration Pattern**
- Single Definition: Main API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)
- Specialized Fallbacks: Specific operation keys (`PDF_PARSE_OPENAI_KEY`, `SUMMARY_OPENAI_KEY`) 
- Everywhere Access: Helper methods provide appropriate keys with automatic fallback logic
- Practical Implementation: Reduces configuration complexity while maintaining flexibility

**Multi-Stage PDF Processing**
- Stage 1: OCR extraction with quality assessment (cost-effective)
- Stage 2: AI-powered text cleaning and structuring (fallback)
- Stage 3: AI summarization with configurable word limits
- Comprehensive logging of methods used and success rates for optimization

**Integrated Scraping Workflow**
- Scrape → Parse PDFs → Generate Summaries → Upload to Dropbox → Send Notifications
- Consistent processing between CLI commands and scheduled operations
- Error isolation to prevent single failures from stopping entire workflow

### Current System Capabilities

- ✅ **Intelligent PDF Processing**: OCR-first with AI fallback for cost optimization
- ✅ **AI-Powered Summaries**: Automatic generation for all new SENS announcements  
- ✅ **Granular Notifications**: Per-company Telegram notification control
- ✅ **Interactive Telegram Bot**: PDF document delivery on demand
- ✅ **Enhanced Web Interface**: AI summary tooltips and visual indicators
- ✅ **Robust Database Schema**: Automatic migrations and comprehensive data storage
- ✅ **Integrated Workflows**: Seamless processing from scraping to notification
- ✅ **Flexible AI Configuration**: Multi-provider support with intelligent fallbacks

### Known Issues and Troubleshooting Focus

**Inconsistent Performance Areas Identified**
- PDF processing success rates vary between SENS announcements
- Telegram notification delivery inconsistencies reported
- AI summary generation not 100% reliable across all document types
- Database update timing may affect real-time web interface display

**Debugging Priorities**
1. Investigate PDF processing failure patterns and error handling
2. Verify Telegram notification subprocess execution and error reporting
3. Analyze AI API response patterns for summary generation failures
4. Review database transaction timing for web interface consistency

---

## Session Progress: September 15-16, 2025

### Major Accomplishments

**Excel Export System Implementation**
- Successfully implemented comprehensive Excel export functionality for SENS announcements
- Created `src/utils/excel_manager.py` with full-featured spreadsheet management
- Added automatic Excel updates during scraping operations
- Implemented newest-first sorting with duplicate prevention
- Added professional formatting with frozen headers, auto-sized columns, and table styling
- Created metadata sheet with export information and column descriptions
- Added placeholder "PDF Summary" column for future AI integration

**Database Schema Alignment**
- Resolved critical field name mismatches between `SensAnnouncement` dataclass and database operations
- Fixed `published_date`/`date_published` and `created_at`/`date_scraped` inconsistencies
- Improved error handling in database query methods with robust row conversion
- Enhanced `get_all_sens_announcements` method for Excel export compatibility

**SENS Scraper Robustness Improvements**
- Fixed SENS number extraction to properly handle format `S######` (e.g., S510561)
- Resolved Unicode encoding issues in Windows Command Prompt logging
- Improved XPath selectors and fallback strategies for announcement parsing
- Enhanced debug logging and error handling throughout scraping pipeline

**Multi-Process Architecture Refinement**
- Confirmed Telegram notification isolation via subprocess works correctly
- Validated async/sync conflict resolution through process separation
- Documented deployment strategies for Windows batch files and Linux systemd services

**Dropbox OAuth 2.0 Integration**
- Successfully implemented persistent authentication with refresh tokens
- Resolved app permission issues (files.content.write, files.metadata.read/write)
- Created helper script `get_dropbox_refresh_token.py` for token acquisition
- Updated configuration to support `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`

**Configuration and Environment Management**
- Enhanced email configuration with flexible SMTP/SSL/TLS settings
- Improved Pydantic v2 compatibility with proper field validation
- Added comprehensive error handling for missing or invalid configuration

### Technical Fixes Resolved

1. **Excel Export Errors**: Fixed `'SensAnnouncement' object has no attribute 'published_date'` and similar field name mismatches
2. **Database Query Errors**: Resolved `'sqlite3.Row' object has no attribute 'get'` and column name inconsistencies  
3. **Unicode Encoding**: Fixed `'charmap' codec can't encode character '\u2705'` in Windows logging
4. **SENS Number Extraction**: Corrected regex pattern and XPath selectors for proper JSE SENS format
5. **Dropbox Authentication**: Resolved token expiration and refresh token implementation
6. **Pydantic Configuration**: Fixed validation errors and import issues with Pydantic v2

### Files Modified This Session

- `src/database/models.py` - Enhanced query methods and field alignment
- `src/utils/excel_manager.py` - Complete implementation with formatting and metadata
- `src/scrapers/sens_scraper.py` - SENS number extraction and Excel integration
- `requirements.txt` - Added openpyxl dependency for Excel functionality
- `main.py` - Added export-excel command and integration
- Various configuration and template files

### Current System Status

- ✅ SENS scraping with proper number extraction
- ✅ Dropbox integration with persistent authentication  
- ✅ Excel export with professional formatting
- ✅ Multi-process notification architecture
- ✅ Database operations with robust error handling
- ✅ Web interface ready for testing
- 🔄 Ready for fresh 30-day initialization scrape
- 🔄 Notification system testing pending
- 🔄 Watchlist management testing pending

### Next Steps

1. Clean existing database entries
2. Perform comprehensive 30-day initialization scrape
3. Test web interface functionality
4. Add companies to watchlist and test notifications
5. Validate daily scraping and Excel updates
6. Test email digest and Telegram alert systems

## Future Development Requirements

### Phase 2: Advanced Company Intelligence

**Company Profile Management**
- Build comprehensive profiles for all JSE-listed companies
- Include: company name, website, directors, business description, subsidiaries
- Implement weekly website scraping to keep director information current
- Extract and store sponsor/advisor information per company record
- Track company performance metrics and financial health indicators

**SENS Classification System**
- Develop ML-based classification for all SENS announcement types:
  - Trading statements
  - Cautionary announcements  
  - Directors' dealings (buy/sell transactions with amounts)
  - Results releases (interim, annual)
  - Corporate actions
  - Regulatory filings
- Integrate classification results into web interface views
- Store classification metadata in database for historical analysis

**Director Transaction Intelligence**
- Parse directors' dealings announcements for transaction details
- Extract: transaction type (buy/sell), share quantities, transaction values
- Maintain historical database of all director transactions
- Flag unusual patterns or significant transactions
- Cross-reference with company performance timing

**AI-Powered Content Analysis**
- Generate concise LLM summaries of PDF announcements for quick reference
- Implement sentiment analysis for longer documents
- Extract key financial metrics and forward-looking statements
- Identify material information and potential market-moving content

**Multi-Source Information Gathering**
- Scan press releases, financial news, and social media for company mentions
- Track director social media activity and posting patterns
- Analyze sentiment and frequency of posts to identify behavioral patterns
- Correlate social media activity with market performance
- Monitor for potential insider information or market manipulation signals

**Advanced Analytics Dashboard**
- Pattern recognition across director transactions and market movements
- Sentiment trending for companies and sectors
- Early warning system for potential corporate actions
- Predictive modeling for announcement impact on share prices

### Technical Architecture Extensions

**Database Schema Enhancements**
- Company profiles table with full metadata
- Director information with historical tracking
- SENS classification taxonomy
- Transaction history with detailed breakdowns
- Social media sentiment tracking tables

**AI/ML Integration**
- Document classification models
- Sentiment analysis pipelines
- Pattern recognition algorithms
- Natural language processing for PDF content extraction

**External Data Integration**
- Financial news APIs
- Social media monitoring tools
- Company website scraping infrastructure
- Market data feeds for correlation analysis

---

*This document is a living specification that evolves with the project. All architectural decisions and future enhancements should be documented here.*
