"""Isolated recovery tests. Fixtures never enter the production market cache."""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_real_market import END, _FakeAkShare, _FakeSinaFallback, _test_directory, pd
from stock_picker.real_market import AkShareAdapter, PHASE4_START, SQLiteMarketCache, StockInfo, SymbolSyncStatus
from stock_picker.sync_monitor import Phase4SyncMonitor
from stock_picker.data_audit import RealMarketDataAuditor
from stock_picker.sync_guardian import acquire_lock, batch_end, worker_command


@unittest.skipIf(pd is None, "requires optional pandas market dependency")
class Phase4RecoveryTests(unittest.TestCase):
    def adapter(self, client):
        return AkShareAdapter(ak_module=client, include_classifications=False,
                              request_interval=0, retry_delay=0, max_attempts=1, segment_days=2)

    def test_resume_skips_successful_empty_segment(self):
        class Client(_FakeAkShare):
            broken = True
            requests = []
            def stock_zh_a_hist(self, **args):
                self.requests.append(args["start_date"])
                if args["start_date"] == "20150601":
                    return pd.DataFrame()
                if self.broken:
                    raise ConnectionError("interrupted provider")
                return super().stock_zh_a_hist(**args)
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            client = Client()
            self.adapter(client).sync(cache, PHASE4_START, END)
            failed = cache.sync_statuses()[0]
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.synced_through, date(2015, 6, 2))
            self.assertEqual(failed.bar_count, 0)
            before = failed.attempts
            client.broken = False
            client.requests = []
            self.adapter(client).sync(cache, PHASE4_START, END)
            self.assertEqual(client.requests[0], "20150603")
            self.assertNotIn("20150601", client.requests)
            self.assertGreater(cache.sync_statuses()[0].attempts, before)

    def test_failed_symbols_precede_completed_date_updates(self):
        class Client(_FakeAkShare):
            requested = []
            def stock_info_a_code_name(self):
                return pd.DataFrame([{"code": "000001", "name": "A"}, {"code": "000002", "name": "B"}])
            def stock_zh_a_hist(self, **args):
                self.requested.append(args["symbol"])
                return super().stock_zh_a_hist(**args)
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            client = Client()
            self.adapter(client).sync(cache, PHASE4_START, date(2015, 6, 2))
            cache.save_sync_status(SymbolSyncStatus("000002", "AkShare", "failed",
                                                   PHASE4_START, END, date(2015, 6, 2), 2))
            client.requested = []
            self.adapter(client).sync(cache, PHASE4_START, END)
            self.assertEqual(client.requested[0], "000002")

    def test_inventory_omissions_and_listing_metadata_are_preserved(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000002", "retained", "SZSE", list_date=PHASE4_START),
                                 StockInfo("000001", "old", "SZSE", list_date=PHASE4_START)])
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            self.assertEqual({s.symbol for s in cache.sync_statuses()}, {"000001", "000002"})
            self.assertEqual(cache.stock_inventory()[0].list_date, PHASE4_START)

    def test_bse_failure_never_calls_unsupported_sina(self):
        class Client(_FakeSinaFallback):
            sina_called = False
            def stock_info_a_code_name(self):
                return pd.DataFrame([{"code": "920001", "name": "BSE"}])
            def stock_zh_a_daily(self, **args):
                self.sina_called = True
                raise AssertionError("unsupported source must not be called")
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            client = Client()
            self.adapter(client).sync(cache, PHASE4_START, END)
            status = cache.sync_statuses()[0]
            self.assertFalse(client.sina_called)
            self.assertEqual(status.status, "failed")
            self.assertIn("does not support this exchange", status.last_error)

    def test_settled_failures_are_not_sync_complete(self):
        with _test_directory() as directory:
            root = Path(directory)
            cache = SQLiteMarketCache(root / "market.sqlite")
            cache.upsert_stocks([StockInfo("000001", "failed", "SZSE")])
            cache.save_sync_status(SymbolSyncStatus("000001", "AkShare", "failed", PHASE4_START, END))
            payload, audit = Phase4SyncMonitor(cache).refresh(end_date=END,
                status_output=root / "status.json", audit_output=root / "audit", audit_when_settled=False)
            self.assertTrue(payload["scan_complete"])
            self.assertFalse(payload["sync_complete"])
            self.assertIsNone(audit)
            self.assertEqual(json.loads((root / "status.json").read_text())["failed_count"], 1)

    def test_old_completed_range_is_pending_for_new_end(self):
        with _test_directory() as directory:
            root = Path(directory)
            cache = SQLiteMarketCache(root / "market.sqlite")
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            payload, _ = Phase4SyncMonitor(cache).refresh(end_date=date(2015, 6, 5),
                status_output=root / "status.json", audit_output=root / "audit")
            self.assertFalse(payload["scan_complete"])
            self.assertEqual(payload["target_pending_count"], 1)

    def test_market_writes_invalidate_audit(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            result = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertTrue(result.passed)
            revision = cache.data_revision
            cache.upsert_stocks([StockInfo("000002", "missing", "SZSE")])
            self.assertIsNone(cache.load_audit())
            self.assertGreater(cache.data_revision, revision)
            result = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertFalse(result.passed)
            self.assertIn("all_inventory_symbols_have_bars", result.payload["failed_items"])

    def test_mutation_during_audit_closes_gate(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            original = cache.save_audit
            def mutate_then_save(payload):
                cache.upsert_stocks([StockInfo("000002", "new", "SZSE")])
                original(payload)
            with patch.object(cache, "save_audit", side_effect=mutate_then_save):
                result = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertFalse(result.passed)
            self.assertIn("data changed during audit", " ".join(result.payload["blockers"]))

    def test_missing_sessions_and_inconsistent_vwap_close_gate(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            with cache.connect() as connection:
                connection.execute("DELETE FROM bars WHERE trading_date='2015-06-02'")
                connection.execute("UPDATE bars SET vwap=1 WHERE trading_date='2015-06-01'")
            result = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertFalse(result.passed)
            self.assertIn("trading_sessions_complete_or_explained", result.payload["failed_items"])
            self.assertIn("inconsistent_vwap", {r["reason"] for r in result.payload["anomalies"]["rows"]})


class GuardianTests(unittest.TestCase):
    def test_batch_end_is_fixed_until_audit_completes(self):
        self.assertEqual(batch_end({"end": "2026-09-30", "phase": "retry_wait"}, date(2026, 10, 2)), date(2026, 9, 30))

    def test_guardian_cannot_start_backtest(self):
        command = worker_command(Path("local.sqlite"), END)
        self.assertIn("sync", command)
        self.assertNotIn("backtest", command)
        self.assertIn(END.isoformat(), command)

    def test_lock_prevents_duplicate_supervisors(self):
        with _test_directory() as directory:
            path = Path(directory) / "guard.lock"
            first = acquire_lock(path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(acquire_lock(path))
            finally:
                first.close()
            second = acquire_lock(path)
            self.assertIsNotNone(second)
            second.close()
