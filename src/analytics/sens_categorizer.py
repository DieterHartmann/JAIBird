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
            "ai_summary": getattr(ann, "ai_summary", None) or "",
            "pdf_url": getattr(ann, "pdf_url", None) or "",
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


# ---------------------------------------------------------------------------
# Phase 2: Advanced dashboard analytics
# ---------------------------------------------------------------------------

def get_today_strategic(categorised: List[Dict]) -> List[Dict[str, Any]]:
    """
    Today's strategic (non-noise) announcements for the ticker banner.
    """
    today = datetime.now().date()
    results = []
    for item in categorised:
        dt = item.get("date_published")
        if dt and dt.date() == today and not item["is_noise"]:
            results.append(item)
    # Most recent first
    results.sort(key=lambda x: x["date_published"] or datetime.min, reverse=True)
    return results


def get_director_dealing_signal(categorised: List[Dict]) -> Dict[str, Any]:
    """
    Analyse director dealings to determine net buy/sell signal.

    Sub-classifies "Dealings by Directors" into buys vs sells based on
    title keyword heuristics.
    """
    buy_pattern = re.compile(
        r"purchase|acquisition|bought|buy|acquire|exercise\s+of\s+options|"
        r"settlement\s+of\s+shares|share\s+incentive|employee\s+share\s+plan",
        re.IGNORECASE
    )
    sell_pattern = re.compile(
        r"(?<!ac)(?<!dis)sale|sold|dispos(?:al|ed)|selling",
        re.IGNORECASE
    )

    buys = []
    sells = []
    neutral = []

    for item in categorised:
        if item["category"] != "Dealings by Directors":
            continue

        title = item["title"]
        is_buy = bool(buy_pattern.search(title))
        is_sell = bool(sell_pattern.search(title))

        record = {
            "company_name": item["company_name"],
            "title": item["title"],
            "date_published": item["date_published"],
        }

        if is_buy and not is_sell:
            buys.append(record)
        elif is_sell and not is_buy:
            sells.append(record)
        else:
            neutral.append(record)

    # Net signal
    net = len(buys) - len(sells)
    if net > 0:
        signal = "Net Buying"
    elif net < 0:
        signal = "Net Selling"
    else:
        signal = "Neutral"

    return {
        "signal": signal,
        "net": net,
        "total_dealings": len(buys) + len(sells) + len(neutral),
        "buys": len(buys),
        "sells": len(sells),
        "neutral": len(neutral),
        "recent_buys": sorted(buys, key=lambda x: x["date_published"] or datetime.min, reverse=True)[:5],
        "recent_sells": sorted(sells, key=lambda x: x["date_published"] or datetime.min, reverse=True)[:5],
    }


def get_unusual_activity_alerts(categorised: List[Dict],
                                 lookback_days: int = 30,
                                 threshold_factor: float = 2.0) -> List[Dict[str, Any]]:
    """
    Flag companies whose recent SENS frequency is unusually high.

    Compares each company's last-7-day count against their average
    weekly rate over the lookback period.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=lookback_days)
    recent_cutoff = now - timedelta(days=7)

    # Build per-company time data
    company_all: Dict[str, int] = Counter()
    company_recent: Dict[str, int] = Counter()

    for item in categorised:
        dt = item.get("date_published")
        if not dt or dt < cutoff:
            continue
        name = item["company_name"]
        company_all[name] += 1
        if dt >= recent_cutoff:
            company_recent[name] += 1

    weeks = max(lookback_days / 7, 1)
    alerts = []
    for company, recent_count in company_recent.items():
        total = company_all.get(company, 0)
        avg_weekly = total / weeks
        if avg_weekly > 0 and recent_count > avg_weekly * threshold_factor and recent_count >= 3:
            alerts.append({
                "company": company,
                "recent_7d": recent_count,
                "avg_weekly": round(avg_weekly, 1),
                "ratio": round(recent_count / avg_weekly, 1) if avg_weekly else 0,
            })

    # Sort by ratio descending
    alerts.sort(key=lambda x: x["ratio"], reverse=True)
    return alerts[:10]


def get_watchlist_pulse(categorised: List[Dict],
                        watchlist_names: List[str]) -> Dict[str, Any]:
    """
    Compare watchlist company SENS activity vs the overall market.

    Args:
        categorised: All categorised announcements
        watchlist_names: List of watchlist company names
    """
    if not watchlist_names or not categorised:
        return {
            "watchlist_count": 0,
            "market_count": 0,
            "watchlist_strategic": 0,
            "market_strategic": 0,
            "watchlist_companies": [],
        }

    wl_lower = [n.lower() for n in watchlist_names]

    def is_watchlist(name: str) -> bool:
        name_l = name.lower()
        for wl in wl_lower:
            if wl in name_l or name_l in wl:
                return True
        return False

    wl_count = 0
    wl_strategic = 0
    market_count = len(categorised)
    market_strategic = 0
    per_company: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "strategic": 0})

    for item in categorised:
        if not item["is_noise"]:
            market_strategic += 1
        if is_watchlist(item["company_name"]):
            wl_count += 1
            co = item["company_name"]
            per_company[co]["total"] += 1
            if not item["is_noise"]:
                wl_strategic += 1
                per_company[co]["strategic"] += 1

    company_list = sorted(
        [{"company": k, **v} for k, v in per_company.items()],
        key=lambda x: x["total"], reverse=True
    )

    return {
        "watchlist_count": wl_count,
        "market_count": market_count,
        "watchlist_strategic": wl_strategic,
        "market_strategic": market_strategic,
        "watchlist_pct": round(wl_count / market_count * 100, 1) if market_count else 0,
        "watchlist_companies": company_list,
    }


def get_sentiment_summary(announcements_with_summaries: List[Dict]) -> Dict[str, Any]:
    """
    Simple keyword-based sentiment analysis of AI summaries.

    Scores each summary as positive / negative / neutral based on
    keyword frequency. Returns aggregate stats and per-company scores.
    """
    positive_words = re.compile(
        r"\b(?:growth|increase|profit|gain|strong|positive|improvement|"
        r"exceed|outperform|upgrade|beat|record|successful|dividend|"
        r"expansion|milestone|optimistic|recovery|robust|surplus|"
        r"confident|opportunity|upside)\b",
        re.IGNORECASE
    )
    negative_words = re.compile(
        r"\b(?:loss|decline|decrease|negative|warning|risk|concern|"
        r"impairment|writedown|write-down|downgrade|underperform|"
        r"deteriorat|weak|challenge|uncertainty|cautionary|default|"
        r"restructur|retrench|suspend|liquidat|fraud|irregular)\b",
        re.IGNORECASE
    )

    scores = []
    company_sentiment: Dict[str, List[float]] = defaultdict(list)

    for item in announcements_with_summaries:
        summary = item.get("ai_summary", "")
        if not summary:
            continue

        pos = len(positive_words.findall(summary))
        neg = len(negative_words.findall(summary))
        total = pos + neg
        if total == 0:
            score = 0.0
        else:
            score = (pos - neg) / total  # Range: -1 to +1

        scores.append(score)
        company_sentiment[item["company_name"]].append(score)

    # Aggregate
    if scores:
        avg_score = sum(scores) / len(scores)
    else:
        avg_score = 0.0

    positive_count = sum(1 for s in scores if s > 0.2)
    negative_count = sum(1 for s in scores if s < -0.2)
    neutral_count = len(scores) - positive_count - negative_count

    # Per-company average
    company_scores = []
    for name, s_list in company_sentiment.items():
        avg = sum(s_list) / len(s_list) if s_list else 0
        company_scores.append({
            "company": name,
            "avg_sentiment": round(avg, 2),
            "count": len(s_list),
            "label": "Positive" if avg > 0.2 else ("Negative" if avg < -0.2 else "Neutral"),
        })
    company_scores.sort(key=lambda x: x["avg_sentiment"], reverse=True)

    return {
        "overall_score": round(avg_score, 2),
        "overall_label": "Positive" if avg_score > 0.2 else ("Negative" if avg_score < -0.2 else "Neutral"),
        "positive": positive_count,
        "negative": negative_count,
        "neutral": neutral_count,
        "total_analysed": len(scores),
        "company_scores": company_scores[:15],
    }


def get_upcoming_events(categorised: List[Dict]) -> List[Dict[str, Any]]:
    """
    Extract upcoming corporate events from SENS titles.

    Looks for patterns indicating AGMs, results releases, meetings etc.
    that mention future dates or are forward-looking.
    """
    event_patterns = [
        (re.compile(r"(?:notice\s+of|upcoming)\s+.*general\s+meeting", re.I), "AGM / General Meeting"),
        (re.compile(r"(?:notice|release)\s+(?:of|regarding).*(?:financial\s+results|results\s+presentation)", re.I), "Results Announcement"),
        (re.compile(r"distribution\s+(?:of\s+)?circular", re.I), "Circular Distribution"),
        (re.compile(r"cautionary\s+announcement", re.I), "Cautionary Period"),
        (re.compile(r"firm\s+intention|general\s+offer", re.I), "M&A Event"),
        (re.compile(r"trading\s+statement", re.I), "Trading Statement"),
    ]

    events = []
    seen = set()
    for item in categorised:
        for pattern, event_type in event_patterns:
            if pattern.search(item["title"]):
                key = (item["company_name"], event_type)
                if key not in seen:
                    seen.add(key)
                    events.append({
                        "company": item["company_name"],
                        "event_type": event_type,
                        "title": item["title"],
                        "date": item["date_published"],
                        "sens_number": item.get("sens_number", ""),
                        "pdf_url": item.get("pdf_url", ""),
                        "ai_summary": item.get("ai_summary", ""),
                    })
                break

    # Sort by date, most recent first
    events.sort(key=lambda x: x["date"] or datetime.min, reverse=True)
    return events[:20]


# ---------------------------------------------------------------------------
# JSE Sector classification (static lookup for known companies)
# ---------------------------------------------------------------------------

_JSE_SECTOR_MAP = {
    # Banking & Financial Services
    "standard bank": "Banking",
    "absa": "Banking",
    "firstrand": "Banking",
    "nedbank": "Banking",
    "investec": "Financial Services",
    "capitec": "Banking",
    "discovery": "Financial Services",
    "sanlam": "Financial Services",
    "old mutual": "Financial Services",
    "momentum": "Financial Services",
    "african bank": "Banking",

    # Mining & Resources
    "anglo american": "Mining",
    "bhp": "Mining",
    "glencore": "Mining",
    "south32": "Mining",
    "kumba": "Mining",
    "exxaro": "Mining",
    "gold fields": "Mining",
    "harmony": "Mining",
    "impala platinum": "Mining",
    "sibanye": "Mining",
    "northam": "Mining",
    "anglo platinum": "Mining",
    "eastern platinum": "Mining",
    "orion mineral": "Mining",
    "southern palladium": "Mining",

    # Retail & Consumer
    "shoprite": "Retail",
    "pick n pay": "Retail",
    "clicks": "Retail",
    "woolworths": "Retail",
    "mr price": "Retail",
    "truworths": "Retail",
    "spar": "Retail",
    "pepkor": "Retail",
    "dis-chem": "Retail",

    # Telecoms & Technology
    "mtn": "Telecoms",
    "vodacom": "Telecoms",
    "telkom": "Telecoms",
    "bytes technology": "Technology",
    "datatec": "Technology",
    "naspers": "Technology",
    "prosus": "Technology",

    # Property
    "redefine": "Property",
    "growthpoint": "Property",
    "emira": "Property",
    "accelerate": "Property",
    "attacq": "Property",
    "vukile": "Property",
    "resilient": "Property",

    # Industrial
    "barloworld": "Industrial",
    "bidvest": "Industrial",
    "imperial": "Industrial",
    "mondi": "Industrial",
    "sappi": "Industrial",
    "sasol": "Energy",
    "british american tobacco": "Consumer Goods",
    "quilter": "Financial Services",
    "life healthcare": "Healthcare",
    "mediclinic": "Healthcare",
    "netcare": "Healthcare",

    # ETFs & Fund Managers
    "satrix": "ETF / Fund",
    "sygnia": "ETF / Fund",
    "prescient": "ETF / Fund",
    "allan gray": "ETF / Fund",
    "1nvest": "ETF / Fund",
    "easyetf": "ETF / Fund",
    "10x fund": "ETF / Fund",
    "fnb cis": "ETF / Fund",
    "newgold": "ETF / Fund",
    "newwave": "ETF / Fund",
    "goldman sachs": "Investment Bank",
    "ubs": "Investment Bank",
    "bnp paribas": "Investment Bank",
}


def classify_sector(company_name: str) -> str:
    """Classify a company into a JSE sector based on name matching."""
    name_lower = company_name.lower()
    for key, sector in _JSE_SECTOR_MAP.items():
        if key in name_lower:
            return sector
    return "Other"


def get_sector_breakdown(categorised: List[Dict],
                          exclude_noise: bool = True) -> List[Dict[str, Any]]:
    """SENS announcements grouped by JSE sector."""
    counter: Counter = Counter()
    for item in categorised:
        if exclude_noise and item["is_noise"]:
            continue
        sector = classify_sector(item["company_name"])
        counter[sector] += 1
    return [{"sector": s, "count": c} for s, c in counter.most_common()]
