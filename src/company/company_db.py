"""
Company Intelligence Database for JAIBird.
Stores persistent profile, leadership, sponsor history, SENS list, censures,
and time-series financial metrics for each company.
"""

import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..utils.config import get_config


@dataclass
class CompanyProfile:
    id: Optional[int]
    name: str
    jse_code: str
    website: str
    sponsor: str
    leadership_json: str  # JSON string storing leadership structure
    first_seen: Optional[datetime]
    last_updated: Optional[datetime]
    is_active: bool
    notes: str


class CompanyDB:
    """Lightweight manager for company intelligence SQLite database."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        cfg = get_config()
        # Fallback if config does not yet carry the attribute
        path = getattr(cfg, "company_database_path", None) or "data/company_intel.db"
        if db_path:
            path = db_path
        self.db_path = Path(path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            # Core company table
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    jse_code TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    sponsor TEXT DEFAULT '',
                    leadership_json TEXT DEFAULT '{}',
                    first_seen TEXT DEFAULT NULL,
                    last_updated TEXT DEFAULT NULL,
                    is_active INTEGER DEFAULT 1,
                    notes TEXT DEFAULT ''
                )
                """
            )

            # Sponsor history
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS sponsor_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    sponsor TEXT NOT NULL,
                    effective_date TEXT DEFAULT NULL,
                    source TEXT DEFAULT '',
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )

            # SENS list per company
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS company_sens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    sens_number TEXT NOT NULL,
                    date_published TEXT DEFAULT NULL,
                    title TEXT DEFAULT '',
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )

            # Censure records
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS censures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    date TEXT DEFAULT NULL,
                    summary TEXT DEFAULT '',
                    link TEXT DEFAULT '',
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )

            # Financial metrics time series (wide variety via name/value)
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    period_start TEXT DEFAULT NULL,
                    period_end TEXT DEFAULT NULL,
                    fiscal_year INTEGER DEFAULT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL,
                    unit TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )
            conn.commit()

    # ------------------------- CRUD helpers -------------------------
    def upsert_company(self, name: str, jse_code: str = "", website: str = "") -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM companies WHERE LOWER(name)=LOWER(?)", (name,))
            row = c.fetchone()
            now = datetime.now().isoformat()
            if row:
                company_id = row["id"]
                c.execute(
                    "UPDATE companies SET jse_code=COALESCE(NULLIF(?, ''), jse_code), website=COALESCE(NULLIF(?, ''), website), last_updated=? WHERE id=?",
                    (jse_code, website, now, company_id),
                )
                return company_id
            c.execute(
                "INSERT INTO companies (name, jse_code, website, first_seen, last_updated) VALUES (?,?,?,?,?)",
                (name, jse_code, website, now, now),
            )
            return c.lastrowid

    def update_leadership(self, company_id: int, leadership: Dict[str, Any]) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE companies SET leadership_json=?, last_updated=? WHERE id=?",
                (json.dumps(leadership, ensure_ascii=False), datetime.now().isoformat(), company_id),
            )

    def set_sponsor(self, company_id: int, sponsor: str, source: str = "") -> None:
        sponsor = sponsor.strip()
        if not sponsor:
            return
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("UPDATE companies SET sponsor=?, last_updated=? WHERE id=?", (sponsor, datetime.now().isoformat(), company_id))
            c.execute(
                "INSERT INTO sponsor_history (company_id, sponsor, effective_date, source) VALUES (?,?,?,?)",
                (company_id, sponsor, datetime.now().isoformat(), source),
            )

    def add_company_sens(self, company_id: int, sens_number: str, date_published: Optional[str], title: str) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO company_sens (company_id, sens_number, date_published, title) VALUES (?,?,?,?)",
                (company_id, sens_number, date_published, title),
            )

    def add_censure(self, company_id: int, date: Optional[str], summary: str, link: str = "") -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO censures (company_id, date, summary, link) VALUES (?,?,?,?)",
                (company_id, date, summary, link),
            )

    def add_metric(
        self,
        company_id: int,
        metric_name: str,
        metric_value: Optional[float],
        unit: str = "",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        source: str = "",
    ) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO financial_metrics (company_id, period_start, period_end, fiscal_year, metric_name, metric_value, unit, source)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (company_id, period_start, period_end, fiscal_year, metric_name, metric_value, unit, source),
            )


