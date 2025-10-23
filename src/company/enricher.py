"""
Company Enricher - updates CompanyDB when a new SENS arrives.
Extracts sponsor, website, leadership hints from parsed PDF content and
optionally performs light web lookups (placeholder hooks).
"""

import re
from typing import Dict, Any, Optional

from ..database.models import SensAnnouncement
from .company_db import CompanyDB


class CompanyEnricher:
    def __init__(self, db: Optional[CompanyDB] = None) -> None:
        self.company_db = db or CompanyDB()

    def enrich_from_announcement(self, ann: SensAnnouncement) -> None:
        """Update company intelligence tables from a SENS announcement."""
        company_id = self.company_db.upsert_company(ann.company_name)

        # Persist SENS reference
        pub = ann.date_published.isoformat() if ann.date_published else None
        self.company_db.add_company_sens(company_id, ann.sens_number, pub, ann.title)

        # Extract sponsor from parsed content or title
        sponsor = self._extract_sponsor(ann)
        if sponsor:
            self.company_db.set_sponsor(company_id, sponsor, source=f"SENS:{ann.sens_number}")

        # Extract website if present in text
        website = self._extract_website(ann)
        if website:
            self.company_db.upsert_company(ann.company_name, website=website)

        # Leadership changes from title/content (simple pattern-based starter)
        leadership_update = self._extract_leadership_change(ann)
        if leadership_update:
            self.company_db.update_leadership(company_id, leadership_update)

    # ---------------- simple extractors (can be improved later) ----------------
    @staticmethod
    def _extract_sponsor(ann: SensAnnouncement) -> str:
        text = (ann.pdf_content or "")
        # Often last page footer lines include "Sponsor: <name>" or "JSE Sponsor"
        patterns = [
            r"(?i)(?:jse\s+sponsor|sponsor)\s*[:\-]\s*([\w\-&'()/,\.\s]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_website(ann: SensAnnouncement) -> str:
        text = (ann.pdf_content or "")
        # Look for http(s) links in the text
        m = re.search(r"https?://[\w\.-/]+", text)
        return m.group(0) if m else ""

    @staticmethod
    def _extract_leadership_change(ann: SensAnnouncement) -> Optional[Dict[str, Any]]:
        # Simple detection from title; expand as needed
        title = ann.title.lower()
        data: Dict[str, Any] = {}
        if "resignation" in title or "appointment" in title or "board" in title:
            data["last_event"] = ann.title
            data["last_event_sens"] = ann.sens_number
            # More detailed parsing can be added later
            return data
        return None


