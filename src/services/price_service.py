"""
Stock price service for JAIBird.
Fetches JSE stock prices via Yahoo Finance (yfinance) and stores them in SQLite.
Supports bulk periodic polling and SENS-triggered hot-list tracking.
"""

import gc
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Batch size for yfinance downloads to limit peak memory usage
_BATCH_SIZE = 40


class PriceService:
    """Fetches and stores JSE stock prices via Yahoo Finance."""

    def __init__(self, db_manager, ticker_file: str = "data/jse_tickers.txt"):
        self.db = db_manager
        self.ticker_file = Path(ticker_file)
        self._tickers: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Ticker management
    # ------------------------------------------------------------------

    def load_tickers(self) -> List[str]:
        """Load tickers from file + DB watchlist, deduplicated."""
        tickers: set = set()

        if self.ticker_file.exists():
            for line in self.ticker_file.read_text().splitlines():
                code = line.strip().upper()
                if code and not code.startswith("#"):
                    tickers.add(code)

        try:
            companies = self.db.get_all_companies(active_only=True)
            for c in companies:
                if c.jse_code:
                    tickers.add(c.jse_code.upper())
        except Exception as e:
            logger.warning(f"Could not load watchlist tickers: {e}")

        self._tickers = sorted(tickers)
        logger.info(f"Loaded {len(self._tickers)} unique tickers")
        return self._tickers

    def get_tickers(self) -> List[str]:
        if self._tickers is None:
            self.load_tickers()
        return self._tickers

    @staticmethod
    def _to_yahoo(jse_code: str) -> str:
        return f"{jse_code}.JO"

    @staticmethod
    def _from_yahoo(yahoo_symbol: str) -> str:
        return yahoo_symbol.replace(".JO", "")

    @staticmethod
    def _zac_to_zar(cents_value: float) -> float:
        """Convert Yahoo Finance ZAc (cents) to ZAR (rands).

        Yahoo reports JSE prices in South African cents. We truncate to
        whole cents (JSE never prices in fractions of a cent) and then
        convert to rands for display.
        """
        return int(cents_value) / 100

    # ------------------------------------------------------------------
    # Bulk fetch (every 15 min)
    # ------------------------------------------------------------------

    def fetch_all_prices(self) -> int:
        """Batch-fetch latest prices for all tickers in small batches to cap memory."""
        tickers = self.get_tickers()
        if not tickers:
            logger.warning("No tickers configured – nothing to fetch")
            return 0

        yahoo_syms = [self._to_yahoo(t) for t in tickers]
        total_count = 0

        for batch_start in range(0, len(yahoo_syms), _BATCH_SIZE):
            batch = yahoo_syms[batch_start : batch_start + _BATCH_SIZE]
            total_count += self._fetch_batch(batch)

        logger.info(f"Bulk fetch: stored prices for {total_count}/{len(tickers)} tickers")
        return total_count

    def _fetch_batch(self, yahoo_syms: List[str]) -> int:
        """Download and store prices for a single batch, then release memory."""
        data = None
        try:
            data = yf.download(
                yahoo_syms,
                period="5d",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
            )

            if data is None or data.empty:
                return 0

            count = 0
            single = len(yahoo_syms) == 1

            for sym in yahoo_syms:
                try:
                    jse_code = self._from_yahoo(sym)

                    if single:
                        ticker_df = data
                    else:
                        if sym not in data.columns.get_level_values(0):
                            continue
                        ticker_df = data[sym]

                    ticker_df = ticker_df.dropna(subset=["Close"])
                    if ticker_df.empty:
                        continue

                    latest = ticker_df.iloc[-1]
                    raw_close = float(latest["Close"])

                    prev_close = (
                        float(ticker_df["Close"].iloc[-2])
                        if len(ticker_df) >= 2
                        else None
                    )
                    change_pct = (
                        round((raw_close - prev_close) / prev_close * 100, 2)
                        if prev_close
                        else None
                    )

                    price = self._zac_to_zar(raw_close)
                    vol = (
                        int(latest["Volume"])
                        if not pd.isna(latest["Volume"])
                        else None
                    )
                    high = (
                        self._zac_to_zar(float(latest["High"]))
                        if not pd.isna(latest["High"])
                        else None
                    )
                    low = (
                        self._zac_to_zar(float(latest["Low"]))
                        if not pd.isna(latest["Low"])
                        else None
                    )

                    self.db.add_stock_price(
                        ticker=jse_code,
                        price=price,
                        change_pct=change_pct,
                        volume=vol,
                        day_high=high,
                        day_low=low,
                    )
                    count += 1

                except Exception as e:
                    logger.debug(f"Skipped {sym}: {e}")

            return count

        except Exception as e:
            logger.error(f"Batch price fetch failed: {e}")
            return 0
        finally:
            del data
            gc.collect()

    # ------------------------------------------------------------------
    # Hot-list fetch (every 2 min, only SENS-triggered tickers)
    # ------------------------------------------------------------------

    def fetch_hot_prices(self) -> int:
        """Fetch prices for tickers on the hot list. Returns count stored."""
        hot_tickers = self.db.get_active_hot_tickers()
        if not hot_tickers:
            return 0

        count = 0
        yahoo_syms = [self._to_yahoo(t) for t in hot_tickers]
        data = None

        try:
            data = yf.download(
                yahoo_syms,
                period="1d",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
            )

            if data is None or data.empty:
                return 0

            single = len(yahoo_syms) == 1

            for sym in yahoo_syms:
                try:
                    jse_code = self._from_yahoo(sym)

                    if single:
                        ticker_df = data
                    else:
                        if sym not in data.columns.get_level_values(0):
                            continue
                        ticker_df = data[sym]

                    ticker_df = ticker_df.dropna(subset=["Close"])
                    if ticker_df.empty:
                        continue

                    latest = ticker_df.iloc[-1]
                    price = self._zac_to_zar(float(latest["Close"]))
                    vol = (
                        int(latest["Volume"])
                        if not pd.isna(latest["Volume"])
                        else None
                    )
                    high = (
                        self._zac_to_zar(float(latest["High"]))
                        if not pd.isna(latest["High"])
                        else None
                    )
                    low = (
                        self._zac_to_zar(float(latest["Low"]))
                        if not pd.isna(latest["Low"])
                        else None
                    )

                    self.db.add_stock_price(
                        ticker=jse_code,
                        price=price,
                        volume=vol,
                        day_high=high,
                        day_low=low,
                    )
                    count += 1

                except Exception as e:
                    logger.debug(f"Hot fetch skipped {sym}: {e}")

        except Exception as e:
            logger.error(f"Hot-list price fetch failed: {e}")
        finally:
            del data
            gc.collect()

        if count:
            logger.info(f"Hot-list: stored prices for {count}/{len(hot_tickers)} tickers")
        return count

    # ------------------------------------------------------------------
    # Snapshot / movers / momentum queries
    # ------------------------------------------------------------------

    def get_snapshot(self) -> List[Dict[str, Any]]:
        """Return the latest price for every tracked ticker."""
        return self.db.get_latest_prices()

    def get_movers(self, n: int = 5) -> Dict[str, List[Dict]]:
        """Top N gainers and losers by daily change %, enriched with company name + recent SENS."""
        snapshot = self.get_snapshot()
        with_change = [s for s in snapshot if s.get("change_pct") is not None]
        by_change = sorted(with_change, key=lambda x: x["change_pct"], reverse=True)
        movers = {
            "gainers": by_change[:n],
            "losers": by_change[-n:][::-1] if len(by_change) >= n else [],
        }
        self._enrich_movers(movers["gainers"] + movers["losers"])
        return movers

    def _enrich_movers(self, items: List[Dict]):
        """Add company_name and recent_sens to each mover item."""
        company_cache: Dict[str, str] = {}
        for item in items:
            ticker = item.get("ticker", "")
            if ticker not in company_cache:
                co = self.db.get_company_by_jse_code(ticker)
                company_cache[ticker] = co.name if co else ""
            item["company_name"] = company_cache[ticker]

            try:
                item["recent_sens"] = self.db.get_recent_sens_for_code(ticker, hours=36)
            except Exception:
                item["recent_sens"] = []

    def get_momentum_report(self) -> List[Dict[str, Any]]:
        """For every hot-list ticker, compute price change since SENS trigger."""
        hot_entries = self.db.get_active_hot_entries()
        results = []
        for entry in hot_entries:
            ticker = entry["ticker"]
            triggered_at = entry["triggered_at"]

            history = self.db.get_price_history(ticker, hours=6)
            if not history:
                continue

            latest_price = history[0]["price"]

            base_price = None
            for rec in reversed(history):
                if rec["timestamp"] <= triggered_at:
                    base_price = rec["price"]
                    break
            if base_price is None:
                base_price = history[-1]["price"]

            change = latest_price - base_price
            change_pct = round(change / base_price * 100, 2) if base_price else 0

            results.append({
                "ticker": ticker,
                "sens_triggered_at": triggered_at,
                "base_price": round(base_price, 2),
                "current_price": round(latest_price, 2),
                "change": round(change, 2),
                "change_pct": change_pct,
            })

        return results
