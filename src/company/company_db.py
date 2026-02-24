"""
Company Intelligence Database for JAIBird.
Stores persistent profile, leadership, sponsor history, SENS list, censures,
and time-series financial metrics for each company.
"""

import logging
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..utils.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class CompanyProfile:
    id: Optional[int]
    name: str
    jse_code: str
    website: str
    sponsor: str
    description: str
    sector: str
    leadership_json: str
    first_seen: Optional[datetime]
    last_updated: Optional[datetime]
    is_active: bool
    notes: str


class CompanyDB:
    """Lightweight manager for company intelligence SQLite database.

    Uses a single persistent connection (WAL mode supports concurrent readers)
    to avoid the overhead of opening/closing connections on every operation.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        cfg = get_config()
        path = getattr(cfg, "company_database_path", None) or "data/company_intel.db"
        if db_path:
            path = db_path
        self.db_path = Path(path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Return the persistent connection, creating it if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=30)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self) -> None:
        """Explicitly close the persistent connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    jse_code TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    sponsor TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    sector TEXT DEFAULT '',
                    leadership_json TEXT DEFAULT '{}',
                    first_seen TEXT DEFAULT NULL,
                    last_updated TEXT DEFAULT NULL,
                    is_active INTEGER DEFAULT 1,
                    notes TEXT DEFAULT ''
                )
                """
            )

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS directors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT DEFAULT '',
                    appointed_date TEXT DEFAULT NULL,
                    resigned_date TEXT DEFAULT NULL,
                    source_sens TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )

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

            # Migrations for existing DBs
            self._migrate(c)
            conn.commit()

    def _migrate(self, cursor: sqlite3.Cursor) -> None:
        """Add columns/tables that may not exist in older versions of the DB."""
        cols = {
            row[1]
            for row in cursor.execute("PRAGMA table_info(companies)").fetchall()
        }
        for col, default in [("description", "''"), ("sector", "''")]:
            if col not in cols:
                cursor.execute(
                    f"ALTER TABLE companies ADD COLUMN {col} TEXT DEFAULT {default}"
                )

        existing_tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "directors" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE directors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT DEFAULT '',
                    appointed_date TEXT DEFAULT NULL,
                    resigned_date TEXT DEFAULT NULL,
                    source_sens TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
                """
            )

    # ------------------------------------------------------------------
    # Company CRUD
    # ------------------------------------------------------------------

    def upsert_company(
        self,
        name: str,
        jse_code: str = "",
        website: str = "",
    ) -> int:
        """Insert or update a company, returning its id."""
        with self._connect() as conn:
            c = conn.cursor()
            # Match on jse_code first (more reliable), then name
            row = None
            if jse_code:
                c.execute(
                    "SELECT id FROM companies WHERE LOWER(jse_code)=LOWER(?) AND jse_code != ''",
                    (jse_code,),
                )
                row = c.fetchone()
            if not row:
                c.execute(
                    "SELECT id FROM companies WHERE LOWER(name)=LOWER(?)", (name,)
                )
                row = c.fetchone()

            now = datetime.now().isoformat()
            if row:
                company_id = row["id"]
                c.execute(
                    """UPDATE companies
                       SET jse_code=COALESCE(NULLIF(?, ''), jse_code),
                           website=COALESCE(NULLIF(?, ''), website),
                           last_updated=?
                       WHERE id=?""",
                    (jse_code, website, now, company_id),
                )
                return company_id
            c.execute(
                "INSERT INTO companies (name, jse_code, website, first_seen, last_updated) VALUES (?,?,?,?,?)",
                (name, jse_code, website, now, now),
            )
            return c.lastrowid

    def update_description(self, company_id: int, description: str) -> None:
        if not description:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE companies SET description=?, last_updated=? WHERE id=?",
                (description, datetime.now().isoformat(), company_id),
            )

    def update_sector(self, company_id: int, sector: str) -> None:
        if not sector:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE companies SET sector=COALESCE(NULLIF(?, ''), sector), last_updated=? WHERE id=?",
                (sector, datetime.now().isoformat(), company_id),
            )

    def get_description(self, company_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT description FROM companies WHERE id=?", (company_id,)
            ).fetchone()
            return row["description"] if row else ""

    # ------------------------------------------------------------------
    # Director tracking
    # ------------------------------------------------------------------

    def add_director(
        self,
        company_id: int,
        name: str,
        role: str = "",
        appointed_date: Optional[str] = None,
        source_sens: str = "",
    ) -> int:
        """Add a director if not already present (fuzzy name match)."""
        with self._connect() as conn:
            c = conn.cursor()
            existing = c.execute(
                """SELECT id FROM directors
                   WHERE company_id=? AND LOWER(name)=LOWER(?) AND is_active=1""",
                (company_id, name),
            ).fetchone()
            if existing:
                if role:
                    c.execute(
                        "UPDATE directors SET role=?, source_sens=? WHERE id=?",
                        (role, source_sens, existing["id"]),
                    )
                return existing["id"]

            c.execute(
                """INSERT INTO directors
                   (company_id, name, role, appointed_date, source_sens, is_active)
                   VALUES (?,?,?,?,?,1)""",
                (company_id, name, role, appointed_date, source_sens),
            )
            conn.execute(
                "UPDATE companies SET last_updated=? WHERE id=?",
                (datetime.now().isoformat(), company_id),
            )
            return c.lastrowid

    def resign_director(
        self,
        company_id: int,
        name: str,
        resigned_date: Optional[str] = None,
        source_sens: str = "",
    ) -> bool:
        """Mark a director as resigned (fuzzy name match)."""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """UPDATE directors
                   SET is_active=0, resigned_date=?, source_sens=?
                   WHERE company_id=? AND LOWER(name)=LOWER(?) AND is_active=1""",
                (resigned_date, source_sens, company_id, name),
            )
            if c.rowcount:
                conn.execute(
                    "UPDATE companies SET last_updated=? WHERE id=?",
                    (datetime.now().isoformat(), company_id),
                )
                return True
            return False

    def get_directors(
        self, company_id: int, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            sql = "SELECT * FROM directors WHERE company_id=?"
            if active_only:
                sql += " AND is_active=1"
            sql += " ORDER BY name"
            rows = conn.execute(sql, (company_id,)).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Sponsor
    # ------------------------------------------------------------------

    def set_sponsor(self, company_id: int, sponsor: str, source: str = "") -> None:
        sponsor = sponsor.strip()
        if not sponsor:
            return
        with self._connect() as conn:
            c = conn.cursor()
            current = c.execute(
                "SELECT sponsor FROM companies WHERE id=?", (company_id,)
            ).fetchone()
            if current and current["sponsor"] == sponsor:
                return
            c.execute(
                "UPDATE companies SET sponsor=?, last_updated=? WHERE id=?",
                (sponsor, datetime.now().isoformat(), company_id),
            )
            c.execute(
                "INSERT INTO sponsor_history (company_id, sponsor, effective_date, source) VALUES (?,?,?,?)",
                (company_id, sponsor, datetime.now().isoformat(), source),
            )

    def get_sponsor_history(self, company_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sponsor_history WHERE company_id=? ORDER BY effective_date DESC",
                (company_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # SENS linkage
    # ------------------------------------------------------------------

    def add_company_sens(
        self,
        company_id: int,
        sens_number: str,
        date_published: Optional[str],
        title: str,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM company_sens WHERE company_id=? AND sens_number=?",
                (company_id, sens_number),
            ).fetchone()
            if existing:
                return
            conn.execute(
                "INSERT INTO company_sens (company_id, sens_number, date_published, title) VALUES (?,?,?,?)",
                (company_id, sens_number, date_published, title),
            )

    def get_company_sens(
        self, company_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM company_sens WHERE company_id=? ORDER BY date_published DESC LIMIT ?",
                (company_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Censure / metrics (kept from original)
    # ------------------------------------------------------------------

    def add_censure(
        self, company_id: int, date: Optional[str], summary: str, link: str = ""
    ) -> None:
        with self._connect() as conn:
            conn.execute(
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
            conn.execute(
                """INSERT INTO financial_metrics
                   (company_id, period_start, period_end, fiscal_year, metric_name, metric_value, unit, source)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    company_id,
                    period_start,
                    period_end,
                    fiscal_year,
                    metric_name,
                    metric_value,
                    unit,
                    source,
                ),
            )

    # Keep legacy method
    def update_leadership(self, company_id: int, leadership: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE companies SET leadership_json=?, last_updated=? WHERE id=?",
                (
                    json.dumps(leadership, ensure_ascii=False),
                    datetime.now().isoformat(),
                    company_id,
                ),
            )

    # ------------------------------------------------------------------
    # Query helpers for UI
    # ------------------------------------------------------------------

    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Lightweight list of all companies for the table page."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.name, c.jse_code, c.sector, c.sponsor,
                       c.description, c.website, c.is_active, c.last_updated,
                       (SELECT COUNT(*) FROM directors d WHERE d.company_id=c.id AND d.is_active=1) AS director_count,
                       (SELECT COUNT(*) FROM company_sens s WHERE s.company_id=c.id) AS sens_count
                FROM companies c
                ORDER BY c.name
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get_company_detail(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Full profile with directors, sponsor history, SENS history."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE id=?", (company_id,)
            ).fetchone()
            if not row:
                return None
            detail = dict(row)
            detail["directors"] = self.get_directors(company_id, active_only=False)
            detail["sponsor_history"] = self.get_sponsor_history(company_id)
            detail["recent_sens"] = self.get_company_sens(company_id, limit=30)
            return detail

    def search_companies(self, query: str) -> List[Dict[str, Any]]:
        """Text search across name, jse_code, description, sector."""
        with self._connect() as conn:
            q = f"%{query}%"
            rows = conn.execute(
                """
                SELECT c.id, c.name, c.jse_code, c.sector, c.sponsor,
                       c.description, c.website, c.is_active, c.last_updated,
                       (SELECT COUNT(*) FROM directors d WHERE d.company_id=c.id AND d.is_active=1) AS director_count,
                       (SELECT COUNT(*) FROM company_sens s WHERE s.company_id=c.id) AS sens_count
                FROM companies c
                WHERE c.name LIKE ? OR c.jse_code LIKE ?
                      OR c.description LIKE ? OR c.sector LIKE ?
                ORDER BY c.name
                """,
                (q, q, q, q),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_company_by_jse_code(self, jse_code: str) -> Optional[Dict[str, Any]]:
        """Look up a company by JSE code."""
        if not jse_code:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE LOWER(jse_code)=LOWER(?)", (jse_code,)
            ).fetchone()
            return dict(row) if row else None

    def get_company_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM companies").fetchone()
            return row["cnt"] if row else 0
