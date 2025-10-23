"""
Configuration management for JAIBird Stock Trading Platform.
Handles loading and validation of environment variables and settings.
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


class JAIBirdConfig(BaseSettings):
    """Main configuration class for JAIBird application."""
    
    # ============================================================================
    # API KEYS
    # ============================================================================
    dropbox_access_token: str = Field(..., env="DROPBOX_ACCESS_TOKEN")
    dropbox_refresh_token: Optional[str] = Field(None, env="DROPBOX_REFRESH_TOKEN")
    dropbox_app_key: Optional[str] = Field(None, env="DROPBOX_APP_KEY")
    dropbox_app_secret: Optional[str] = Field(None, env="DROPBOX_APP_SECRET")
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(..., env="TELEGRAM_CHAT_ID")
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    
    # ============================================================================
    # EMAIL CONFIGURATION
    # ============================================================================
    smtp_server: str = Field("smtp.gmail.com", env="SMTP_SERVER")
    smtp_port: int = Field(587, env="SMTP_PORT")
    email_username: str = Field(..., env="EMAIL_USERNAME")
    email_password: str = Field(..., env="EMAIL_PASSWORD")
    notification_email: str = Field(..., env="NOTIFICATION_EMAIL")
    
    # Additional email server settings
    email_smtp_server: Optional[str] = Field(None, env="EMAIL_SMTP_SERVER")
    email_smtp_port: Optional[int] = Field(None, env="EMAIL_SMTP_PORT")
    email_imap_server: Optional[str] = Field(None, env="EMAIL_IMAP_SERVER")
    email_imap_port: Optional[int] = Field(None, env="EMAIL_IMAP_PORT")
    email_pop3_server: Optional[str] = Field(None, env="EMAIL_POP3_SERVER")
    email_pop3_port: Optional[int] = Field(None, env="EMAIL_POP3_PORT")
    email_use_ssl: bool = Field(False, env="EMAIL_USE_SSL")
    email_use_tls: bool = Field(True, env="EMAIL_USE_TLS")
    
    # ============================================================================
    # SCRAPING CONFIGURATION
    # ============================================================================
    scrape_interval_minutes: int = Field(5, env="SCRAPE_INTERVAL_MINUTES")
    local_cache_retention_days: int = Field(30, env="LOCAL_CACHE_RETENTION_DAYS")
    daily_digest_time: str = Field("08:30", env="DAILY_DIGEST_TIME")
    
    # ============================================================================
    # STORAGE CONFIGURATION
    # ============================================================================
    local_storage_path: str = Field("./data/sens_pdfs/", env="LOCAL_STORAGE_PATH")
    dropbox_folder: str = Field("/JAIBird/SENS/", env="DROPBOX_FOLDER")
    
    # ============================================================================
    # DATABASE CONFIGURATION
    # ============================================================================
    database_path: str = Field("./data/jaibird.db", env="DATABASE_PATH")
    
    # ============================================================================
    # WEB INTERFACE CONFIGURATION
    # ============================================================================
    flask_host: str = Field("127.0.0.1", env="FLASK_HOST")
    flask_port: int = Field(5000, env="FLASK_PORT")
    flask_debug: bool = Field(True, env="FLASK_DEBUG")
    flask_secret_key: str = Field(..., env="FLASK_SECRET_KEY")
    
    # ============================================================================
    # LOGGING CONFIGURATION
    # ============================================================================
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file_path: str = Field("./logs/jaibird.log", env="LOG_FILE_PATH")
    
    # ============================================================================
    # SELENIUM CONFIGURATION
    # ============================================================================
    webdriver_headless: bool = Field(True, env="WEBDRIVER_HEADLESS")
    webdriver_timeout: int = Field(30, env="WEBDRIVER_TIMEOUT")
    webdriver_download_path: str = Field("./data/sens_pdfs/temp/", env="WEBDRIVER_DOWNLOAD_PATH")
    
    # ============================================================================
    # AI CONFIGURATION - PDF PARSING & SUMMARIZATION
    # ============================================================================
    
    # Main AI API Keys (shared across functions)
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", env="ANTHROPIC_API_KEY")
    
    # PDF Parsing (OCR cleanup, document structure extraction)
    pdf_parse_provider: str = Field("openai", env="PDF_PARSE_PROVIDER")  # openai or anthropic
    pdf_parse_openai_key: str = Field("", env="PDF_PARSE_OPENAI_KEY")
    pdf_parse_openai_model: str = Field("gpt-4", env="PDF_PARSE_OPENAI_MODEL")
    pdf_parse_anthropic_key: str = Field("", env="PDF_PARSE_ANTHROPIC_KEY")
    pdf_parse_anthropic_model: str = Field("claude-3-sonnet-20240229", env="PDF_PARSE_ANTHROPIC_MODEL")
    
    # Summary Generation (financial analysis, concise summaries)
    summary_provider: str = Field("openai", env="SUMMARY_PROVIDER")  # openai or anthropic
    summary_openai_key: str = Field("", env="SUMMARY_OPENAI_KEY")
    summary_openai_model: str = Field("gpt-4", env="SUMMARY_OPENAI_MODEL")
    summary_anthropic_key: str = Field("", env="SUMMARY_ANTHROPIC_KEY")
    summary_anthropic_model: str = Field("claude-3-sonnet-20240229", env="SUMMARY_ANTHROPIC_MODEL")
    summary_max_words: int = Field(50, env="SUMMARY_MAX_WORDS")
    
    def get_pdf_parse_openai_key(self) -> str:
        """Get OpenAI key for PDF parsing with fallback to main key."""
        return self.pdf_parse_openai_key or self.openai_api_key
    
    def get_pdf_parse_anthropic_key(self) -> str:
        """Get Anthropic key for PDF parsing with fallback to main key."""
        return self.pdf_parse_anthropic_key or self.anthropic_api_key
    
    def get_summary_openai_key(self) -> str:
        """Get OpenAI key for summaries with fallback to main key."""
        return self.summary_openai_key or self.openai_api_key
    
    def get_summary_anthropic_key(self) -> str:
        """Get Anthropic key for summaries with fallback to main key."""
        return self.summary_anthropic_key or self.anthropic_api_key
    
    # ============================================================================
    # NOTIFICATION PREFERENCES
    # ============================================================================
    urgent_keywords: str = Field(
        "profit warning,delisting,suspension,trading halt,cautionary,acquisition,merger,rights issue,late submission of condensed financial statements,late submission",
        env="URGENT_KEYWORDS"
    )
    telegram_notifications_enabled: bool = Field(True, env="TELEGRAM_NOTIFICATIONS_ENABLED")
    email_notifications_enabled: bool = Field(True, env="EMAIL_NOTIFICATIONS_ENABLED")
    
    # ============================================================================
    # DEVELOPMENT SETTINGS
    # ============================================================================
    environment: str = Field("development", env="ENVIRONMENT")
    test_mode: bool = Field(False, env="TEST_MODE")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"  # Allow extra fields in .env file
    }
    
    @field_validator("daily_digest_time")
    @classmethod
    def validate_time_format(cls, v):
        """Validate that daily_digest_time is in HH:MM format."""
        import re
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
            raise ValueError("daily_digest_time must be in HH:MM format (24-hour)")
        return v
    
    @field_validator("dropbox_folder")
    @classmethod
    def validate_dropbox_folder(cls, v):
        """Ensure dropbox folder starts with /."""
        if not v.startswith("/"):
            v = "/" + v
        if not v.endswith("/"):
            v = v + "/"
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
    
    def get_urgent_keywords_list(self) -> List[str]:
        """Return urgent keywords as a list."""
        return [keyword.strip().lower() for keyword in self.urgent_keywords.split(",")]
    
    def get_smtp_settings(self) -> tuple:
        """Return SMTP settings, preferring EMAIL_SMTP_* over SMTP_* if available."""
        # Use EMAIL_SMTP_* settings if available, otherwise fall back to SMTP_*
        server = self.email_smtp_server or self.smtp_server
        port = self.email_smtp_port or self.smtp_port
        return server, port
    
    def ensure_directories_exist(self):
        """Create necessary directories if they don't exist."""
        directories = [
            self.local_storage_path,
            self.webdriver_download_path,
            Path(self.database_path).parent,
            Path(self.log_file_path).parent,
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def setup_logging(self):
        """Configure logging based on settings."""
        # Ensure log directory exists
        Path(self.log_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file_path),
                logging.StreamHandler()
            ]
        )
        
        # Set specific logger levels
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


def load_config() -> JAIBirdConfig:
    """Load and return configuration, creating directories as needed."""
    # Load environment variables from .env file
    load_dotenv()
    
    try:
        config = JAIBirdConfig()
        config.ensure_directories_exist()
        config.setup_logging()
        
        logger = logging.getLogger(__name__)
        logger.info(f"Configuration loaded successfully for environment: {config.environment}")
        
        if config.test_mode:
            logger.warning("Running in TEST MODE - notifications will not be sent!")
        
        return config
        
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Please check your .env file and ensure all required variables are set.")
        print("Use env_template.txt as a reference.")
        raise


# Global configuration instance
config = None

def get_config() -> JAIBirdConfig:
    """Get the global configuration instance."""
    global config
    if config is None:
        config = load_config()
    return config


def reload_config() -> JAIBirdConfig:
    """Reload configuration from environment."""
    global config
    config = None
    return get_config()
