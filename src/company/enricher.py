"""
Company Enricher - updates CompanyDB when a new SENS arrives.
Uses AI structured extraction to pull directors, sponsors, descriptions,
JSE codes, and sector information from parsed PDF content.
Falls back to regex when AI is unavailable.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..database.models import SensAnnouncement
from ..utils.config import get_config
from .company_db import CompanyDB

logger = logging.getLogger(__name__)

_TICKER_FILE = Path("data/jse_tickers.txt")

_AI_EXTRACTION_PROMPT = """You are a structured data extractor for JSE (Johannesburg Stock Exchange) SENS announcements.

Given the SENS announcement below, extract the following fields as a JSON object. If a field cannot be determined, use null or an empty list. Only include information explicitly stated in the text.

Required JSON structure:
{{
  "jse_code": "3-4 letter JSE ticker code, e.g. SOL, NPN, ABG",
  "company_name": "Full registered company name",
  "sponsor": "JSE sponsor / designated adviser name, e.g. Java Capital, Nedbank CIB",
  "company_description": "What the company does (1-2 sentences), only if described in the announcement",
  "sector": "Industry sector, e.g. Mining, Financial Services, Retail, Technology",
  "directors_appointed": [
    {{"name": "Full Name", "role": "e.g. Independent Non-Executive Director, CEO, CFO"}}
  ],
  "directors_resigned": [
    {{"name": "Full Name", "role": "role if mentioned"}}
  ]
}}

SENS Title: {title}
Company: {company_name}
SENS Number: {sens_number}

Text (first 6000 chars):
{content}

Return ONLY the JSON object, no explanation or markdown fences."""


class CompanyEnricher:
    def __init__(self, db: Optional[CompanyDB] = None) -> None:
        self.company_db = db or CompanyDB()
        self.config = get_config()
        self._ai_client = None
        self._init_ai_client()

    def _init_ai_client(self) -> None:
        """Set up the AI client using the same summary provider config."""
        try:
            if self.config.summary_provider == "openai":
                key = self.config.get_summary_openai_key()
                if key:
                    from openai import OpenAI
                    self._ai_client = ("openai", OpenAI(api_key=key))
            elif self.config.summary_provider == "anthropic":
                key = self.config.get_summary_anthropic_key()
                if key:
                    import anthropic
                    self._ai_client = ("anthropic", anthropic.Anthropic(api_key=key))
        except Exception as e:
            logger.warning(f"Could not initialise AI client for enricher: {e}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def enrich_from_announcement(self, ann: SensAnnouncement) -> None:
        """Update company intelligence tables from a SENS announcement."""
        jse_code = self._extract_jse_code_from_name(ann.company_name)
        company_id = self.company_db.upsert_company(
            ann.company_name, jse_code=jse_code
        )

        pub = ann.date_published.isoformat() if ann.date_published else None
        self.company_db.add_company_sens(company_id, ann.sens_number, pub, ann.title)

        # Regex-based sponsor extraction (fast, always runs)
        sponsor = self._extract_sponsor(ann)
        if sponsor:
            self.company_db.set_sponsor(
                company_id, sponsor, source=f"SENS:{ann.sens_number}"
            )

        website = self._extract_website(ann)
        if website:
            self.company_db.upsert_company(ann.company_name, website=website)

        # AI structured extraction (if content available)
        if ann.pdf_content and self._ai_client:
            try:
                self._ai_enrich(company_id, ann)
            except Exception as e:
                logger.warning(f"AI enrichment failed for {ann.sens_number}: {e}")

        # Auto-discover: add new JSE codes to the ticker file
        final_code = jse_code
        if not final_code:
            co = self.company_db.get_company_by_jse_code("")
            if co:
                final_code = co.get("jse_code", "")
        if final_code:
            self._auto_add_ticker(final_code)

    # ------------------------------------------------------------------
    # AI structured extraction
    # ------------------------------------------------------------------

    def _ai_enrich(self, company_id: int, ann: SensAnnouncement) -> None:
        """Call AI to extract structured company intelligence from SENS content."""
        content = (ann.pdf_content or "")[:6000]
        if len(content) < 50:
            return

        prompt = _AI_EXTRACTION_PROMPT.format(
            title=ann.title,
            company_name=ann.company_name,
            sens_number=ann.sens_number,
            content=content,
        )

        raw = self._call_ai(prompt)
        if not raw:
            return

        data = self._parse_json_response(raw)
        if not data:
            return

        # Update JSE code if found
        jse_code = (data.get("jse_code") or "").strip().upper()
        if jse_code and len(jse_code) <= 5:
            self.company_db.upsert_company(
                ann.company_name, jse_code=jse_code
            )
            self._auto_add_ticker(jse_code)

        # Sponsor (AI may find it even when regex misses)
        ai_sponsor = (data.get("sponsor") or "").strip()
        if ai_sponsor:
            self.company_db.set_sponsor(
                company_id, ai_sponsor, source=f"SENS:{ann.sens_number}"
            )

        # Company description -- synthesise if different
        desc = (data.get("company_description") or "").strip()
        if desc:
            existing = self.company_db.get_description(company_id)
            if not existing:
                self.company_db.update_description(company_id, desc)
            elif existing.lower() != desc.lower():
                merged = self._synthesise_description(existing, desc)
                self.company_db.update_description(company_id, merged)

        # Sector
        sector = (data.get("sector") or "").strip()
        if sector:
            self.company_db.update_sector(company_id, sector)

        # Directors appointed
        for d in data.get("directors_appointed") or []:
            name = (d.get("name") or "").strip()
            if name:
                self.company_db.add_director(
                    company_id,
                    name=name,
                    role=(d.get("role") or "").strip(),
                    appointed_date=ann.date_published.isoformat()
                    if ann.date_published
                    else None,
                    source_sens=ann.sens_number,
                )

        # Directors resigned
        for d in data.get("directors_resigned") or []:
            name = (d.get("name") or "").strip()
            if name:
                self.company_db.resign_director(
                    company_id,
                    name=name,
                    resigned_date=ann.date_published.isoformat()
                    if ann.date_published
                    else None,
                    source_sens=ann.sens_number,
                )

    def _call_ai(self, prompt: str) -> str:
        """Call the configured AI provider and return raw response text."""
        if not self._ai_client:
            return ""
        provider, client = self._ai_client
        try:
            if provider == "openai":
                resp = client.chat.completions.create(
                    model=self.config.summary_openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You extract structured data from JSE SENS announcements. Always respond with valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=800,
                    temperature=0.0,
                )
                return resp.choices[0].message.content.strip()
            elif provider == "anthropic":
                resp = client.messages.create(
                    model=self.config.summary_anthropic_model,
                    max_tokens=800,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text.strip()
        except Exception as e:
            logger.error(f"AI extraction call failed: {e}")
        return ""

    def _synthesise_description(self, existing: str, new: str) -> str:
        """Merge two descriptions using AI when they differ."""
        if not self._ai_client:
            return new

        prompt = (
            f"A company had this description:\n\"{existing}\"\n\n"
            f"A newer SENS now says:\n\"{new}\"\n\n"
            f"Write a single concise description (1-3 sentences) that synthesises both, "
            f"keeping the most current information. Return only the description, no explanation."
        )
        result = self._call_ai(prompt)
        return result.strip('"').strip() if result else new

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from AI response, tolerating markdown fences."""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Could not parse AI extraction JSON: {text[:200]}")
            return None

    # ------------------------------------------------------------------
    # Regex-based extractors (fallback / always-on)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_sponsor(ann: SensAnnouncement) -> str:
        text = ann.pdf_content or ""
        patterns = [
            r"(?i)(?:jse\s+sponsor|designated\s+adviser|sponsor)\s*[:\-]\s*([\w\-&'()/,\.\s]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                val = re.split(r"\n|\.{2,}", val)[0].strip()
                if 3 < len(val) < 80:
                    return val
        return ""

    @staticmethod
    def _extract_website(ann: SensAnnouncement) -> str:
        text = ann.pdf_content or ""
        m = re.search(r"https?://[\w\.-/]+", text)
        return m.group(0) if m else ""

    @staticmethod
    def _extract_jse_code_from_name(company_name: str) -> str:
        """Try to extract a JSE code from the SENS company_name field.
        SENS often formats as 'COMPANY NAME LTD (ABC)' or 'ABC - Company Name'."""
        if not company_name:
            return ""
        m = re.search(r"\(([A-Z]{2,5})\)", company_name)
        if m:
            return m.group(1)
        parts = company_name.split()
        if parts and re.match(r"^[A-Z]{2,5}$", parts[-1]):
            return parts[-1]
        return ""

    # ------------------------------------------------------------------
    # Auto-discovery: append new tickers to jse_tickers.txt
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_add_ticker(jse_code: str) -> None:
        """Append a new JSE code to jse_tickers.txt if not already present."""
        if not jse_code or len(jse_code) > 5:
            return
        jse_code = jse_code.upper()
        try:
            existing: set[str] = set()
            if _TICKER_FILE.exists():
                for line in _TICKER_FILE.read_text().splitlines():
                    stripped = line.split("#")[0].strip()
                    if stripped:
                        existing.add(stripped.upper())

            if jse_code not in existing:
                from datetime import datetime as _dt
                with open(_TICKER_FILE, "a") as f:
                    f.write(f"\n{jse_code}  # auto-discovered {_dt.now().strftime('%Y-%m-%d')}\n")
                logger.info(f"Auto-added ticker {jse_code} to {_TICKER_FILE}")
        except Exception as e:
            logger.debug(f"Could not auto-add ticker {jse_code}: {e}")
