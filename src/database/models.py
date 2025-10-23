"""
Database models for JAIBird Stock Trading Platform.
Defines the schema for companies, SENS announcements, notifications, and configuration.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager


logger = logging.getLogger(__name__)


@dataclass
class Company:
    """Model for watchlist companies."""
    id: Optional[int] = None
    name: str = ""
    jse_code: str = ""
    added_date: Optional[datetime] = None
    active_status: bool = True
    send_telegram: bool = False
    notes: str = ""


@dataclass
class SensAnnouncement:
    """Model for SENS announcements."""
    id: Optional[int] = None
    sens_number: str = ""
    company_name: str = ""
    title: str = ""
    pdf_url: str = ""
    local_pdf_path: str = ""
    dropbox_pdf_path: str = ""
    date_published: Optional[datetime] = None
    date_scraped: Optional[datetime] = None
    processed: bool = False
    is_urgent: bool = False
    urgent_reason: str = ""
    pdf_content: str = ""
    ai_summary: str = ""
    parse_method: str = ""  # 'ocr', 'ai', 'failed'
    parse_status: str = "pending"  # 'pending', 'processing', 'completed', 'failed'
    parsed_at: Optional[datetime] = None


@dataclass
class Notification:
    """Model for notification log."""
    id: Optional[int] = None
    sens_id: int = 0
    notification_type: str = ""  # 'telegram' or 'email'
    sent_date: Optional[datetime] = None
    status: str = ""  # 'sent', 'failed', 'pending'
    error_message: str = ""


@dataclass
class ConfigSetting:
    """Model for configuration settings."""
    key: str = ""
    value: str = ""
    description: str = ""
    last_updated: Optional[datetime] = None


class DatabaseManager:
    """Manages database operations for JAIBird."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create companies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    jse_code TEXT UNIQUE NOT NULL,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active_status BOOLEAN DEFAULT TRUE,
                    notes TEXT DEFAULT ''
                )
            """)
            
            # Create sens_announcements table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sens_announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sens_number TEXT UNIQUE NOT NULL,
                    company_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    pdf_url TEXT NOT NULL,
                    local_pdf_path TEXT DEFAULT '',
                    dropbox_pdf_path TEXT DEFAULT '',
                    date_published TIMESTAMP,
                    date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE,
                    is_urgent BOOLEAN DEFAULT FALSE,
                    urgent_reason TEXT DEFAULT '',
                    pdf_content TEXT DEFAULT '',
                    ai_summary TEXT DEFAULT '',
                    parse_method TEXT DEFAULT '',
                    parse_status TEXT DEFAULT 'pending',
                    parsed_at TIMESTAMP
                )
            """)
            
            # Create notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sens_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT DEFAULT '',
                    FOREIGN KEY (sens_id) REFERENCES sens_announcements (id)
                )
            """)
            
            # Run database migrations
            self._run_migrations(cursor)
            
            # Create config_settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sens_number ON sens_announcements(sens_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_name ON sens_announcements(company_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_date_published ON sens_announcements(date_published)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed ON sens_announcements(processed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_urgent ON sens_announcements(is_urgent)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jse_code ON companies(jse_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_status ON companies(active_status)")
            
            logger.info("Database initialized successfully")
    
    def _run_migrations(self, cursor):
        """Run database migrations to add new columns."""
        try:
            # Check if new columns exist in sens_announcements table
            cursor.execute("PRAGMA table_info(sens_announcements)")
            sens_columns = [row[1] for row in cursor.fetchall()]
            
            sens_migrations = [
                ("pdf_content", "ALTER TABLE sens_announcements ADD COLUMN pdf_content TEXT DEFAULT ''"),
                ("ai_summary", "ALTER TABLE sens_announcements ADD COLUMN ai_summary TEXT DEFAULT ''"),
                ("parse_method", "ALTER TABLE sens_announcements ADD COLUMN parse_method TEXT DEFAULT ''"),
                ("parse_status", "ALTER TABLE sens_announcements ADD COLUMN parse_status TEXT DEFAULT 'pending'"),
                ("parsed_at", "ALTER TABLE sens_announcements ADD COLUMN parsed_at TIMESTAMP"),
            ]
            
            for column_name, migration_sql in sens_migrations:
                if column_name not in sens_columns:
                    logger.info(f"Running migration: Adding column {column_name} to sens_announcements")
                    cursor.execute(migration_sql)
            
            # Check if new columns exist in companies table
            cursor.execute("PRAGMA table_info(companies)")
            company_columns = [row[1] for row in cursor.fetchall()]
            
            company_migrations = [
                ("send_telegram", "ALTER TABLE companies ADD COLUMN send_telegram BOOLEAN DEFAULT 0"),
            ]
            
            for column_name, migration_sql in company_migrations:
                if column_name not in company_columns:
                    logger.info(f"Running migration: Adding column {column_name} to companies")
                    cursor.execute(migration_sql)
                    
        except Exception as e:
            logger.error(f"Migration error: {e}")
    
    # ============================================================================
    # COMPANY OPERATIONS
    # ============================================================================
    
    def add_company(self, company: Company) -> int:
        """Add a company to the watchlist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO companies (name, jse_code, send_telegram, notes)
                VALUES (?, ?, ?, ?)
            """, (company.name, company.jse_code, company.send_telegram, company.notes))
            company_id = cursor.lastrowid
            logger.info(f"Added company {company.name} ({company.jse_code}) to watchlist")
            return company_id
    
    def get_all_companies(self, active_only: bool = True) -> List[Company]:
        """Get all companies from the watchlist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM companies"
            if active_only:
                query += " WHERE active_status = TRUE"
            query += " ORDER BY name"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            return [Company(
                id=row['id'],
                name=row['name'],
                jse_code=row['jse_code'],
                added_date=datetime.fromisoformat(row['added_date']) if row['added_date'] else None,
                active_status=bool(row['active_status']),
                send_telegram=bool(row['send_telegram']) if 'send_telegram' in row.keys() else False,
                notes=row['notes']
            ) for row in rows]
    
    def get_company_by_jse_code(self, jse_code: str) -> Optional[Company]:
        """Get a company by its JSE code."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companies WHERE jse_code = ?", (jse_code,))
            row = cursor.fetchone()
            
            if row:
                return Company(
                    id=row['id'],
                    name=row['name'],
                    jse_code=row['jse_code'],
                    added_date=datetime.fromisoformat(row['added_date']) if row['added_date'] else None,
                    active_status=bool(row['active_status']),
                    send_telegram=bool(row['send_telegram']) if 'send_telegram' in row.keys() else False,
                    notes=row['notes']
                )
            return None
    
    def is_company_on_watchlist(self, company_name: str) -> bool:
        """Check if a company is on the watchlist (fuzzy bidirectional match on name)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM companies 
                WHERE active_status = TRUE AND (
                    LOWER(name) LIKE LOWER(?) OR 
                    LOWER(jse_code) LIKE LOWER(?) OR
                    LOWER(?) LIKE LOWER('%' || name || '%') OR
                    LOWER(?) LIKE LOWER('%' || jse_code || '%')
                )
            """, (f"%{company_name}%", f"%{company_name}%", company_name, company_name))
            result = cursor.fetchone()
            return result['count'] > 0
    
    def should_send_telegram_for_company(self, company_name: str) -> bool:
        """Check if a company is flagged for Telegram notifications."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM companies 
                WHERE active_status = TRUE AND send_telegram = TRUE AND (
                    LOWER(name) LIKE LOWER(?) OR 
                    LOWER(jse_code) LIKE LOWER(?) OR
                    LOWER(?) LIKE LOWER('%' || name || '%') OR
                    LOWER(?) LIKE LOWER('%' || jse_code || '%')
                )
            """, (f"%{company_name}%", f"%{company_name}%", company_name, company_name))
            result = cursor.fetchone()
            return result['count'] > 0
    
    def update_company_telegram_flag(self, jse_code: str, send_telegram: bool) -> bool:
        """Update the Telegram notification flag for a company."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE companies 
                SET send_telegram = ? 
                WHERE jse_code = ?
            """, (send_telegram, jse_code))
            
            if cursor.rowcount > 0:
                logger.info(f"Updated Telegram flag for {jse_code}: {send_telegram}")
                return True
            else:
                logger.warning(f"No company found with JSE code: {jse_code}")
                return False
    
    def update_sens_parsing(self, announcement: SensAnnouncement) -> bool:
        """Update SENS announcement with parsed content and summary."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sens_announcements 
                SET pdf_content = ?, ai_summary = ?, parse_method = ?, 
                    parse_status = ?, parsed_at = ?
                WHERE sens_number = ?
            """, (
                announcement.pdf_content,
                announcement.ai_summary,
                announcement.parse_method,
                announcement.parse_status,
                announcement.parsed_at.isoformat() if announcement.parsed_at else None,
                announcement.sens_number
            ))
            return cursor.rowcount > 0
    
    def get_unparsed_sens(self) -> List[SensAnnouncement]:
        """Get SENS announcements that haven't been parsed yet."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sens_announcements 
                WHERE parse_status = 'pending' AND local_pdf_path != ''
                ORDER BY date_published DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            return [self._row_to_sens_announcement(row) for row in rows]
    
    def deactivate_company(self, jse_code: str) -> bool:
        """Deactivate a company from the watchlist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE companies SET active_status = FALSE 
                WHERE jse_code = ?
            """, (jse_code,))
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Deactivated company with JSE code: {jse_code}")
            return success
    
    # ============================================================================
    # SENS ANNOUNCEMENT OPERATIONS
    # ============================================================================
    
    def add_sens_announcement(self, announcement: SensAnnouncement) -> int:
        """Add a SENS announcement to the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sens_announcements (
                    sens_number, company_name, title, pdf_url, local_pdf_path,
                    dropbox_pdf_path, date_published, is_urgent, urgent_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                announcement.sens_number,
                announcement.company_name,
                announcement.title,
                announcement.pdf_url,
                announcement.local_pdf_path,
                announcement.dropbox_pdf_path,
                announcement.date_published,
                announcement.is_urgent,
                announcement.urgent_reason
            ))
            announcement_id = cursor.lastrowid
            # Propagate generated id back to the in-memory object for downstream logging/notifications
            announcement.id = announcement_id
            logger.info(f"Added SENS announcement {announcement.sens_number} for {announcement.company_name}")
            return announcement_id
    
    def sens_exists(self, sens_number: str) -> bool:
        """Check if a SENS announcement already exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM sens_announcements WHERE sens_number = ?", (sens_number,))
            result = cursor.fetchone()
            return result['count'] > 0
    
    def get_unprocessed_sens(self) -> List[SensAnnouncement]:
        """Get all unprocessed SENS announcements."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sens_announcements 
                WHERE processed = FALSE 
                ORDER BY date_published DESC, date_scraped DESC
            """)
            rows = cursor.fetchall()
            
            return [self._row_to_sens_announcement(row) for row in rows]
    
    def get_recent_sens(self, days: int = 1) -> List[SensAnnouncement]:
        """Get SENS announcements from the last N days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sens_announcements 
                WHERE date_published >= datetime('now', '-{} days')
                ORDER BY date_published DESC
            """.format(days))
            rows = cursor.fetchall()
            
            return [self._row_to_sens_announcement(row) for row in rows]
    
    def mark_sens_processed(self, sens_id: int) -> bool:
        """Mark a SENS announcement as processed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sens_announcements SET processed = TRUE 
                WHERE id = ?
            """, (sens_id,))
            return cursor.rowcount > 0
    
    def _row_to_sens_announcement(self, row) -> SensAnnouncement:
        """Convert database row to SensAnnouncement object."""
        return SensAnnouncement(
            id=row['id'],
            sens_number=row['sens_number'],
            company_name=row['company_name'],
            title=row['title'],
            pdf_url=row['pdf_url'],
            local_pdf_path=row['local_pdf_path'],
            dropbox_pdf_path=row['dropbox_pdf_path'],
            date_published=datetime.fromisoformat(row['date_published']) if row['date_published'] else None,
            date_scraped=datetime.fromisoformat(row['date_scraped']) if row['date_scraped'] else None,
            processed=bool(row['processed']),
            is_urgent=bool(row['is_urgent']),
            urgent_reason=row['urgent_reason'],
            pdf_content=row['pdf_content'] if 'pdf_content' in row.keys() else '',
            ai_summary=row['ai_summary'] if 'ai_summary' in row.keys() else '',
            parse_method=row['parse_method'] if 'parse_method' in row.keys() else '',
            parse_status=row['parse_status'] if 'parse_status' in row.keys() else 'pending',
            parsed_at=datetime.fromisoformat(row['parsed_at']) if ('parsed_at' in row.keys() and row['parsed_at']) else None
        )
    
    # ============================================================================
    # NOTIFICATION OPERATIONS
    # ============================================================================
    
    def log_notification(self, notification: Notification) -> int:
        """Log a notification attempt."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notifications (sens_id, notification_type, status, error_message)
                VALUES (?, ?, ?, ?)
            """, (notification.sens_id, notification.notification_type, notification.status, notification.error_message))
            return cursor.lastrowid
    
    def update_notification_status(self, notification_id: int, status: str, error_message: str = "") -> bool:
        """Update notification status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE notifications 
                SET status = ?, error_message = ?, sent_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, error_message, notification_id))
            return cursor.rowcount > 0
    
    # ============================================================================
    # CONFIGURATION OPERATIONS
    # ============================================================================
    
    def get_config_value(self, key: str, default: str = "") -> str:
        """Get a configuration value."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM config_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    def set_config_value(self, key: str, value: str, description: str = "") -> None:
        """Set a configuration value."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_settings (key, value, description, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, value, description))
    
    # ============================================================================
    # UTILITY OPERATIONS
    # ============================================================================
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Company stats
            cursor.execute("SELECT COUNT(*) as total, COUNT(CASE WHEN active_status = 1 THEN 1 END) as active FROM companies")
            row = cursor.fetchone()
            stats['companies'] = {'total': row['total'], 'active': row['active']}
            
            # SENS stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN processed = 1 THEN 1 END) as processed,
                    COUNT(CASE WHEN is_urgent = 1 THEN 1 END) as urgent
                FROM sens_announcements
            """)
            row = cursor.fetchone()
            stats['sens_announcements'] = {
                'total': row['total'], 
                'processed': row['processed'], 
                'urgent': row['urgent']
            }
            
            # Notification stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                FROM notifications
            """)
            row = cursor.fetchone()
            stats['notifications'] = {
                'total': row['total'], 
                'sent': row['sent'], 
                'failed': row['failed']
            }
            
            return stats
    
    def get_all_sens_announcements(self) -> List[SensAnnouncement]:
        """Get all SENS announcements from database, ordered by publication date (newest first)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, sens_number, company_name, title, pdf_url, 
                    local_pdf_path, dropbox_pdf_path, date_published, 
                    date_scraped, processed, is_urgent, urgent_reason,
                    pdf_content, ai_summary, parse_method, parse_status, parsed_at
                FROM sens_announcements 
                ORDER BY 
                    CASE WHEN date_published IS NOT NULL THEN date_published ELSE date_scraped END DESC
            """)
            rows = cursor.fetchall()
            
            announcements = []
            for row in rows:
                try:
                    announcement = SensAnnouncement(
                        id=row['id'],
                        sens_number=row['sens_number'],
                        company_name=row['company_name'],
                        title=row['title'],
                        date_published=datetime.fromisoformat(row['date_published']) if row['date_published'] else None,
                        pdf_url=row['pdf_url'],
                        local_pdf_path=row['local_pdf_path'] or '',
                        dropbox_pdf_path=row['dropbox_pdf_path'] or '',
                        date_scraped=datetime.fromisoformat(row['date_scraped']) if row['date_scraped'] else None,
                        processed=bool(row['processed']),
                        is_urgent=bool(row['is_urgent']),
                        urgent_reason=row['urgent_reason'] or '',
                        pdf_content=row['pdf_content'] or '',
                        ai_summary=row['ai_summary'] or '',
                        parse_method=row['parse_method'] or '',
                        parse_status=row['parse_status'] or 'pending',
                        parsed_at=datetime.fromisoformat(row['parsed_at']) if row['parsed_at'] else None
                    )
                    announcements.append(announcement)
                except Exception as e:
                    logger.error(f"Error converting row to SensAnnouncement: {e}")
                    continue
            
            return announcements
    
    def get_sens_by_number(self, sens_number: str) -> Optional[SensAnnouncement]:
        """Get a SENS announcement by its number."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sens_announcements 
                WHERE sens_number = ?
            """, (sens_number,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_sens_announcement(row)
            return None
