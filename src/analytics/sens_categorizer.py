"""
SENS Announcement Categorizer for JAIBird Executive Dashboard.

Classifies SENS announcements into thematic categories based on title pattern
matching.  Categories are split into two tiers:

  * **Strategic** – announcements with material business significance
  * **Noise**     – routine regulatory/administrative filings that clutter
                    executive-level views

The module exposes helper functions that operate on lists of
SensAnnouncement dataclass instances (from src.database.models).
"""

import re
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------
# Each entry: (category_name, compiled_regex, is_noise)
# Order matters – first match wins.

_CATEGORY_RULES: List[Tuple[str, re.Pattern, bool]] = []


def _r(category: str, pattern: str, *, noise: bool = False):
    """Helper to register a category rule."""
    _CATEGORY_RULES.append((category, re.compile(pattern, re.IGNORECASE), noise))


# ---- Strategic categories (shown prominently) ----

_r("Trading Statements & Updates",
   r"trading\s+(?:statement|update)|operational\s+(?:update|performance)|festive\s+season\s+trading")

_r("Financial Results",
   r"(?:financial|interim|annual)\s+results|condensed\s+(?:consolidated\s+)?financial|"
   r"earnings\s+release|quarterly\s+(?:investor\s+)?report|investor\s+report|"
   r"results\s+for\s+the\s+(?:first|second|third|fourth)\s+quarter|"
   r"results\s+presentation|short-form\s+announcement.*results|"
   r"q[1-4]\s+fy\d{4}\s+results|production\s+report|"
   r"business\s+update\s+for\s+the|publication\s+of\s+.*(?:results|financial\s+statements)|"
   r"monthly\s+fact\s*sheet|notice\s+of\s+availability.*factsheet")

_r("Acquisitions & Disposals",
   r"acquisition\s+of\s+(?:the\s+)?(?!beneficial|securities|shares)|"
   r"proposed\s+acquisition|"
   r"disposal\s+of|disposal\s+by|divestment|general\s+offer\s+to\s+acquire|"
   r"purchase\s+of\s+(?!investec|.*shares)|"
   r"voluntary\s+announcement.*(?:disposal|acquisition|purchase)|"
   r"(?:earn[\s-]*in\s+agreement|prepayment\s+facility)|"
   r"firm\s+intention.*(?:offer|acquire|disposal)|"
   r"offer\s+for\s+.*(?:by|from)\s+")

# Share Buybacks MUST come before Dealings by Directors since
# "Transaction in own shares" would otherwise match the more general
# dealings pattern.
_r("Share Buybacks & Treasury",
   r"transaction\s+in\s+own\s+shares|repurchase\s+of|share\s+buyback|"
   r"treasury\s+shares|confirmation\s+of\s+treasury|"
   r"buy-?back\s+(?:notification|programme|program)|repurchase\s+programme")

_r("Dealings by Directors",
   r"dealings?\s+in\s+securities\s+by|dealings?\s+in\s+securities$|"
   r"transactions?\s+(?:in\s+.*shares|by\s+persons?\s+discharging\s+managerial)|"
   r"dealing\s+in\s+(?:securities|shares)\s+by|dealing\s+in\s+securities$|dealing\s+in\s+shares$|"
   r"dealing\s+by\s+(?:subsidiary|director)|"
   r"share\s+(?:incentive|option).*(?:exercise|settlement|transaction)|"
   r"employee\s+share\s+plan|exercise\s+of\s+options|"
   r"settlement\s+of\s+shares\s+in\s+terms|share\s+(?:plan|scheme)\s+transaction|"
   r"disclosure\s+of\s+management\s+transaction|"
   r"share\s+subdivision|notification\s+of\s+securities")

_r("Board & Management Changes",
   r"change(?:s)?\s+to\s+the\s+board|directorate\s+change|"
   r"appointment\s+of\s+(?:independent\s+)?(?:non-executive\s+)?director|"
   r"retirement\s+of\s+(?:senior\s+executive|.*director)|"
   r"executive\s+responsibilities|management\s+arrangements|"
   r"board\s+committees|change\s+to\s+the\s+board|"
   r"termination\s+of\s+board\s+member")

_r("Cautionary Announcements",
   r"cautionary\s+announcement|cautionary$")

_r("Dividends & Distributions",
   r"(?:declaration\s+of\s+)?dividend|distribution\s+finalisation|"
   r"preference\s+share\s+dividend|rectification.*dividend")

_r("Capital Raises & Placements",
   r"private\s+placement|rights\s+issue|capital\s+raise|share\s+placement|"
   r"tap\s+issuance")

_r("Funding & Debt",
   r"credit\s+facilit|refinancing|(?:medium\s+term\s+note|note)\s+programme|"
   r"corporate\s+facilities|pricing\s+supplement")

_r("Major Holdings Disclosure",
   r"major\s+holdings?|beneficial\s+interest|change\s+in\s+beneficial|"
   r"disclosure\s+of\s+(?:acquisition|increase|significant\s+holding|beneficial)|"
   r"notification\s+of\s+(?:major|change\s+in\s+(?:a\s+)?major)|"
   r"total\s+voting\s+rights|voting\s+rights\s+and\s+capital|"
   r"schedule\s+13[gd]|acquisition\s+of\s+securities\s+by\s+clients")

_r("AGM & Shareholder Meetings",
   r"general\s+meeting|circular.*shareholders|notice\s+of\s+general\s+meeting|"
   r"results\s+of\s+(?:the\s+)?(?:annual|extraordinary)\s+general\s+meeting|"
   r"withdrawal\s+of\s+resolutions|voluntary\s+business\s+update\s+at\s+agm")

_r("Corporate Actions",
   r"suspension\s+from\s+quotation|reinstatement\s+to\s+quotation|"
   r"auditor\s+(?:appointment|change)|bbbee\s+compliance|"
   r"ceo\s+letter|response\s+to\s+rule|"
   r"notice\s+to\s+affected\s+persons|name\s+change|"
   r"annual\s+financial\s+statements|availability\s+of\s+.*annual")

# ---- Noise categories (de-emphasised / filtered from default views) ----

_r("Interest Payments", noise=True,
   pattern=r"interest\s+(?:payment|amount)|notification\s+of\s+interest|"
           r"interest\s+rate\s+reset|fixed\s+interim\s+payment|"
           r"interest\s+and\s+capital\s+payment")

_r("Listing / Delisting of Securities", noise=True,
   pattern=r"listing\s+of\s+additional|additional\s+listing|partial\s+(?:de-?listing|delisting)|"
           r"new\s+(?:financial\s+instrument\s+)?listing|listing\s+of\s+\d|"
           r"listing\s+of\s+satrix|new\s+listing\s+announcement|"
           r"partial\s+capital\s+redemption|"
           r"(?:de-?listing|delisting)\s+of\s+(?:financial\s+)?instrument|"
           r"notice\s+of\s+(?:expiry|partial\s+redemption)|"
           r"notification\s+of\s+(?:a\s+)?partial\s+capital\s+reduction")

_r("ETF / Fund Administration", noise=True,
   pattern=r"redemption\s+of\s+(?:1nvest|newgold|etf)|partial\s+redemption\s+of\s+securities|"
           r"etf\s+securities|results\s+of\s+the\s+initial\s+offer|"
           r"cdi\s+monthly\s+movement|actively\s+managed\s+certificate|"
           r"early\s+(?:termination|redemption)")

_r("Regulatory Forms & Filings", noise=True,
   pattern=r"form\s+8[\.\-]?[3k]|tr-?1:|trp121|"
           r"section\s+(?:122|45)|notice\s+in\s+terms\s+of\s+section|"
           r"notification\s+in\s+terms\s+of\s+section|"
           r"form\s+8[\.\-]?\s*(?:announcement|dealing\s+disclosure|opd)|"
           r"public\s+opening\s+position|"
           r"jse\s+contact\s+list|"
           r"notice\s+of\s+availability.*(?:quarterly|portfolio\s+composition)|"
           r"publication\s+of\s+information\s+by\s+means\s+of\s+supplement")

_r("Amendments & Corrections", noise=True,
   pattern=r"amendment|correction|cancellation\s+of\s+s\d|"
           r"late\s+(?:correction|announcement)")

_r("Debt Programme Admin", noise=True,
   pattern=r"amendments?\s+to\s+.*(?:note|bond)\s+programme|"
           r"amended\s+and\s+restated.*pricing|"
           r"notice\s+requesting\s+written\s+consent.*holders|"
           r"final\s+redemption\s+announcement|"
           r"financial\s+instrument\s+(?:partial\s+de-?listing|final\s+redemption)|"
           r"notice\s+of\s+partial\s+redemption|"
           r"issue\s+of\s+zar.*(?:securities|notes)\s+due")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize_title(title: str) -> Tuple[str, bool]:
    """
    Classify a single SENS title.

    Returns:
        (category_name, is_noise)  – e.g. ("Trading Statements & Updates", False)
        Falls back to ("Other / Uncategorised", False) if no rule matches.
    """
    if not title:
        return ("Other / Uncategorised", False)

    for category, pattern, is_noise in _CATEGORY_RULES:
        if pattern.search(title):
            return (category, is_noise)

    return ("Other / Uncategorised", False)


def categorize_announcements(announcements) -> List[Dict[str, Any]]:
    """
    Categorise a list of SensAnnouncement objects.

    Returns a list of dicts with keys:
        sens_number, company_name, title, date_published, category, is_noise
    """
    results = []
    for ann in announcements:
        cat, noise = categorize_title(ann.title)
        results.append({
            "sens_number": ann.sens_number,
            "company_name": ann.company_name,
            "title": ann.title,
            "date_published": ann.date_published,
            "is_urgent": getattr(ann, "is_urgent", False),
            "category": cat,
            "is_noise": noise,
        })
    return results


# ---------------------------------------------------------------------------
# Dashboard aggregation helpers
# ---------------------------------------------------------------------------

def get_top_companies(categorised: List[Dict], n: int = 10,
                      exclude_noise: bool = False) -> List[Dict[str, Any]]:
    """Top N companies by SENS announcement count."""
    counter: Counter = Counter()
    for item in categorised:
        if exclude_noise and item["is_noise"]:
            continue
        counter[item["company_name"]] += 1
    return [{"company": name, "count": count}
            for name, count in counter.most_common(n)]


def get_category_breakdown(categorised: List[Dict],
                           exclude_noise: bool = True) -> List[Dict[str, Any]]:
    """
    Announcement counts by category.
    By default, noise categories are excluded.
    """
    counter: Counter = Counter()
    for item in categorised:
        if exclude_noise and item["is_noise"]:
            continue
        counter[item["category"]] += 1
    return [{"category": cat, "count": count}
            for cat, count in counter.most_common()]


def get_noise_summary(categorised: List[Dict]) -> Dict[str, Any]:
    """Summary of noise vs strategic announcements."""
    noise_count = sum(1 for item in categorised if item["is_noise"])
    total = len(categorised)
    return {
        "total": total,
        "strategic": total - noise_count,
        "noise": noise_count,
        "noise_pct": round(noise_count / total * 100, 1) if total else 0,
    }


def get_volume_over_time(categorised: List[Dict],
                         bucket: str = "day",
                         exclude_noise: bool = False) -> List[Dict[str, Any]]:
    """
    SENS volume bucketed by time period.

    Args:
        bucket: 'day', 'week', or 'month'
    """
    buckets: Dict[str, int] = defaultdict(int)

    for item in categorised:
        if exclude_noise and item["is_noise"]:
            continue
        dt = item["date_published"]
        if not dt:
            continue

        if bucket == "day":
            key = dt.strftime("%Y-%m-%d")
        elif bucket == "week":
            # ISO week start (Monday)
            start = dt - timedelta(days=dt.weekday())
            key = start.strftime("%Y-%m-%d")
        else:  # month
            key = dt.strftime("%Y-%m")

        buckets[key] += 1

    sorted_items = sorted(buckets.items())
    return [{"date": k, "count": v} for k, v in sorted_items]


def get_urgency_breakdown(categorised: List[Dict]) -> Dict[str, int]:
    """Urgent vs normal announcement counts."""
    urgent = sum(1 for item in categorised if item.get("is_urgent"))
    return {
        "urgent": urgent,
        "normal": len(categorised) - urgent,
    }


def get_recent_strategic_highlights(categorised: List[Dict],
                                     n: int = 5) -> List[Dict[str, Any]]:
    """
    Most recent *strategic* (non-noise) announcements for the highlights feed.
    """
    strategic = [item for item in categorised if not item["is_noise"]]
    # Sort by date descending
    strategic.sort(key=lambda x: x["date_published"] or datetime.min, reverse=True)
    return strategic[:n]


def get_company_activity_heatmap(categorised: List[Dict],
                                  top_n: int = 10) -> Dict[str, Any]:
    """
    For the top N companies, build a category-by-company matrix.
    Returns {companies: [...], categories: [...], matrix: [[...]]}
    """
    # Find top companies
    company_counts = Counter(item["company_name"] for item in categorised)
    top_companies = [name for name, _ in company_counts.most_common(top_n)]

    # Find strategic categories used by those companies
    cat_counter: Counter = Counter()
    company_cat: Dict[str, Counter] = defaultdict(Counter)
    for item in categorised:
        if item["company_name"] in top_companies and not item["is_noise"]:
            cat_counter[item["category"]] += 1
            company_cat[item["company_name"]][item["category"]] += 1

    categories = [c for c, _ in cat_counter.most_common()]

    matrix = []
    for company in top_companies:
        row = [company_cat[company].get(cat, 0) for cat in categories]
        matrix.append(row)

    return {
        "companies": top_companies,
        "categories": categories,
        "matrix": matrix,
    }


def get_all_categories() -> List[Dict[str, Any]]:
    """Return the full category taxonomy with noise flags."""
    return [{"name": cat, "is_noise": noise}
            for cat, _, noise in _CATEGORY_RULES] + [
                {"name": "Other / Uncategorised", "is_noise": False}
            ]
