"""Synthetic retry checkpoints; no live data or market requests."""

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stock_picker import sync_retry
from stock_picker.real_market import SQLiteMarketCache, StockInfo, SymbolSyncStatus


class RetryExtensionTests(unittest.TestCase):
    def test_persistent_review_survives_end_extension_but_new_evidence_reopens(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "synthetic.sqlite")
            stock = StockInfo("TEST", "synthetic", "SZSE", date(2010, 1, 1),
                              source="provider-a")
            start, old_end = date(2015, 6, 1), date(2026, 10, 16)
            new_end = date(2026, 10, 30)
            now = datetime(2026, 11, 2, tzinfo=timezone.utc)
            error = ValueError("raw VWAP outside daily range: synthetic")
            sync_retry.failed(cache, stock, start, old_end, error, now)
            cache.save_sync_status(SymbolSyncStatus(
                stock.symbol, "AkShare", "failed", start, old_end,
                date(2026, 10, 12), last_error=f"ValueError: {error}"))

            self.assertFalse(sync_retry.eligible(cache, stock, start, new_end, now))
            self.assertTrue(sync_retry.eligible(
                cache, StockInfo(stock.symbol, stock.name, stock.exchange,
                                 stock.list_date, source="verified-provider-b"),
                start, new_end, now))

            cache.save_sync_status(SymbolSyncStatus(
                stock.symbol, "AkShare", "failed", start, old_end,
                date(2026, 10, 12), last_error="ValueError: independently resolved"))
            self.assertTrue(sync_retry.eligible(cache, stock, start, new_end, now))
            sync_retry.clear(cache, stock.symbol)
            self.assertTrue(sync_retry.eligible(cache, stock, start, new_end, now))

    def test_bse_review_stays_deferred_but_temporary_cooldown_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "synthetic.sqlite")
            stock = StockInfo("920000", "synthetic", "BSE", source="provider-a")
            start, old_end = date(2015, 6, 1), date(2026, 10, 16)
            new_end = old_end + timedelta(days=14)
            now = datetime(2026, 11, 2, tzinfo=timezone.utc)
            error = RuntimeError("source-switch HFQ conflict: synthetic")
            sync_retry.failed(cache, stock, start, old_end, error, now)
            cache.save_sync_status(SymbolSyncStatus(
                stock.symbol, "AkShare", "failed", start, old_end,
                date(2026, 10, 12), last_error=f"RuntimeError: {error}"))
            self.assertTrue(sync_retry.eligible(cache, stock, start, new_end, now))

            sync_retry.failed(cache, stock, start, old_end, error, now)
            sync_retry.failed(cache, stock, start, old_end, error, now)
            self.assertFalse(sync_retry.eligible(cache, stock, start, new_end, now))


if __name__ == "__main__":
    unittest.main()
