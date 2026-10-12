"""Isolated audit/source fixtures only; no strategy execution or live DB writes."""
from __future__ import annotations

import hashlib
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from test_real_market import END, _FakeAkShare, _test_directory, pd
from stock_picker.data_audit import RealMarketDataAuditor, stock_active_interval
from stock_picker.phase4_acceptance import SnapshotCache, admission_report, freeze_database, write_admission
from stock_picker.real_market import AkShareAdapter, PHASE4_START, SQLiteMarketCache, StockInfo, SymbolSyncStatus
from stock_picker.sina_archive import isolate_retired_terminal_duplicate
from stock_picker.tencent_bse import frame_from_payload, fetch_tencent_bse, verify_overlap
from stock_picker import sync_retry
from stock_picker.phase4_foundation import Phase4FoundationRunner, DataCoverageError


@unittest.skipIf(pd is None, "optional pandas dependency")
class AcceptanceTests(unittest.TestCase):
    def build(self, path):
        cache = SQLiteMarketCache(path)
        AkShareAdapter(ak_module=_FakeAkShare(), include_classifications=False,
                       max_attempts=1, request_interval=0, retry_delay=0).sync(cache, PHASE4_START, END)
        return cache

    def test_snapshot_is_read_only_and_audit_never_opens_production_gate(self):
        with _test_directory() as tmp:
            root = Path(tmp)
            live = self.build(root / "live.sqlite")
            revision = live.data_revision
            identity = freeze_database(live.path, root / "snapshot.sqlite")
            frozen = SnapshotCache(root / "snapshot.sqlite")
            # A later production mutation cannot appear in the frozen audit.
            live.upsert_stocks([StockInfo("000002", "new", "SZSE")])
            result = RealMarketDataAuditor(frozen).run(end_date=END, output=root / "preaudit")
            self.assertEqual(result.payload["stock_inventory_count"], 1)
            self.assertFalse(result.payload["formal_gate_eligible"])
            self.assertIsNone(live.load_audit())
            self.assertEqual(identity["data_revision"], revision)
            self.assertEqual(identity["id"], "sha256:" + hashlib.sha256(frozen.path.read_bytes()).hexdigest())
            with frozen.connect() as c:
                with self.assertRaises(Exception):
                    c.execute("DELETE FROM bars")
            with self.assertRaises(ValueError):
                freeze_database(live.path, frozen.path)

    def test_failed_sync_still_emits_admission_and_full_blocker_bundle(self):
        with _test_directory() as tmp:
            root = Path(tmp)
            cache = self.build(root / "market.sqlite")
            cache.save_sync_status(SymbolSyncStatus("000001", "AkShare", "failed", PHASE4_START, END,
                                                    last_error="real source not available"))
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=END).payload
            report = admission_report(SnapshotCache(cache.path), audit, {"id": "test-only"})
            write_admission(root, report)
            self.assertFalse(report["formal_backtest_ready"])
            self.assertFalse(report["gate_released"])
            self.assertTrue((root / "blockers.json").exists())
            self.assertIn("sync_incomplete", report["blocker_summary"])

    def test_wal_snapshot_stays_consistent_when_writer_commits_during_backup(self):
        with _test_directory() as tmp:
            root = Path(tmp)
            live = self.build(root / "live.sqlite")
            called = []
            def concurrent_write(status, remaining, total):
                if not called:
                    called.append(True)
                    live.upsert_stocks([StockInfo("000002", "later real-writer fixture", "SZSE")])
            identity = freeze_database(live.path, root / "snapshot.sqlite", progress=concurrent_write)
            frozen = SnapshotCache(root / "snapshot.sqlite")
            self.assertEqual(len(frozen.stock_inventory()), 1)
            self.assertEqual(len(live.stock_inventory()), 2)
            self.assertLess(identity["data_revision"], live.data_revision)

    def test_benchmark_hole_is_not_hidden_by_matching_maximum_date(self):
        with _test_directory() as tmp:
            cache = self.build(Path(tmp) / "market.sqlite")
            with cache.connect() as c:
                c.execute("DELETE FROM benchmarks WHERE name='CSI1000' AND trading_date='2015-06-02'")
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=END).payload
            evidence = {"calendar": {"verified_through": str(END), "dates":
                                      ["2015-06-01", "2015-06-02", "2015-06-03", "2015-06-04"]}}
            report = admission_report(SnapshotCache(cache.path), audit, {}, evidence)
            self.assertFalse(report["benchmark_coverage"]["CSI1000"]["session_check_passed"])
            self.assertEqual(report["benchmark_coverage"]["CSI1000"]["missing_ranges"][0]["start"], "2015-06-02")

    def test_outside_range_proof_is_distinct_from_complete_market_history(self):
        with _test_directory() as tmp:
            cache = self.build(Path(tmp) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000002", "retired", "SZSE", delist_date=date(2010, 1, 1),
                                          source="AkShare.stock_info_sz_delist")])
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=END).payload
            missing = admission_report(SnapshotCache(cache.path), audit, {})
            self.assertEqual(missing["outside_interval_review"][0]["category"], "missing_or_conflicting")
            evidence = {"retired_metadata": {"rows": {"000002": {"delist_date": "2010-01-01"}}}}
            report = admission_report(SnapshotCache(cache.path), audit, {}, evidence)
            row = report["outside_interval_review"][0]
            self.assertEqual(row["category"], "whole_interval_exempt")
            self.assertFalse(row["counted_as_complete_market_history"])
            self.assertEqual(report["market_history_categories"]["segment_exempt"], 0)

    def test_later_incremental_anomaly_does_not_shift_historical_acceptance(self):
        with _test_directory() as tmp:
            cache = self.build(Path(tmp) / "market.sqlite")
            with cache.connect() as c:
                c.execute("UPDATE bars SET close=100000 WHERE trading_date='2015-06-04'")
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=date(2015, 6, 3)).payload
            self.assertEqual(audit["anomalies"]["count"], 0)
            self.assertEqual(audit["date_coverage"]["end_date"], "2015-06-03")
            self.assertEqual(audit["global_date_coverage"]["end_date"], str(END))

    def test_future_bse_listing_is_range_exemption_not_missing_history(self):
        with _test_directory() as tmp:
            cache = self.build(Path(tmp) / "market.sqlite")
            cache.upsert_stocks([StockInfo("920006", "later", "BSE", list_date=date(2015, 6, 10))])
            cache.save_sync_status(SymbolSyncStatus("920006", "AkShare", "complete", PHASE4_START,
                END, END, source="exchange:outside_requested_range"))
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=END).payload
            self.assertTrue(audit["audit_checks"]["bse_stocks_have_data"])
            self.assertEqual(audit["stock_coverage"]["required_bse_count"], 0)
            self.assertEqual(audit["stock_coverage"]["outside_requested_range_count"], 1)

    def test_exchange_removal_date_is_not_expected_trading_session(self):
        row = {"list_date": "2009-10-30", "delist_date": "2020-08-03",
               "source": "AkShare.stock_info_sz_delist"}
        first, last = stock_active_interval(row, PHASE4_START, date(2026, 9, 30))
        self.assertEqual(first, PHASE4_START)
        self.assertEqual(last, date(2020, 8, 2))

    def test_preaudit_can_never_authorize_strategy_execution(self):
        with _test_directory() as tmp:
            path = Path(tmp) / "market.sqlite"
            cache = self.build(path)
            result = RealMarketDataAuditor(SnapshotCache(path)).run(end_date=END)
            # Even an incorrectly copied preaudit payload must be rejected.
            cache.save_audit(result.payload)
            with patch("stock_picker.phase4_foundation.EventDrivenBacktester.run") as engine:
                with self.assertRaises(DataCoverageError):
                    Phase4FoundationRunner(path).run(end_date=END, report_directory=Path(tmp) / "must-not-exist")
                engine.assert_not_called()


@unittest.skipIf(pd is None, "optional pandas dependency")
class SourceRepairTests(unittest.TestCase):
    def frames(self, echo_date=date(2021, 6, 27)):
        return pd.DataFrame([dict(date=date(2020, 7, 31), open=.3, high=.31, low=.29,
            close=.3, volume=10000, amount=3000), dict(date=echo_date, open=.3, high=.31,
            low=.29, close=.3, volume=10000, amount=3000)])

    def test_terminal_echo_is_quarantined_not_deleted_or_formally_approved(self):
        with _test_directory() as tmp:
            cache = SQLiteMarketCache(Path(tmp) / "isolated.sqlite")
            stock = StockInfo("300028", "retired", "SZSE", delist_date=date(2020, 8, 3),
                              source="AkShare.stock_info_sz_delist")
            raw = self.frames()
            repaired, _ = isolate_retired_terminal_duplicate(raw, raw.copy(), stock, cache)
            self.assertEqual(len(raw), 2)
            self.assertEqual(len(repaired), 1)
            with cache.connect() as c:
                row = c.execute("SELECT * FROM provider_quarantine").fetchone()
            self.assertEqual(json.loads(row["evidence"])["original"]["date"], "2021-06-27")
            audit = RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=END)
            self.assertFalse(audit.payload["audit_checks"]["provider_quarantines_formally_reviewed"])

    def test_non_echo_or_weekday_or_multiple_later_rows_are_not_suppressed(self):
        with _test_directory() as tmp:
            cache = SQLiteMarketCache(Path(tmp) / "isolated.sqlite")
            stock = StockInfo("300028", "retired", "SZSE", delist_date=date(2020, 8, 3),
                              source="AkShare.stock_info_sz_delist")
            for kind in ("weekday", "different_amount", "multiple"):
                raw = self.frames(date(2021, 6, 28) if kind == "weekday" else date(2021, 6, 27))
                if kind == "different_amount": raw.loc[1, "amount"] = 4000
                if kind == "multiple": raw = pd.concat([raw, raw.tail(1)])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    isolate_retired_terminal_duplicate(raw, raw.copy(), stock, cache)

    def payload(self, row=None, key="day"):
        return {"code": 0, "data": {"bj920006": {key: [row or
            ["2015-06-01", "10", "10", "11", "9", "100", {}, "1", "10"]]}}}

    def test_tencent_bse_uses_lots_yuan_and_clips_unrequested_dates(self):
        frame = frame_from_payload(self.payload(), "920006", PHASE4_START, END)
        self.assertEqual(frame.iloc[0].amount, 100000)
        self.assertEqual(frame.iloc[0].volume, 100)
        self.assertEqual(frame.iloc[0].amount / (frame.iloc[0].volume * 100), 10)
        clipped = frame_from_payload(self.payload(), "920006", date(2015, 6, 2), END)
        self.assertTrue(clipped.empty)

    def test_tencent_unit_mismatch_missing_turnover_and_duplicate_fail(self):
        cases = [self.payload(["2015-06-01", "10", "10", "11", "9", "10000", {}, "1", "10"]),
                 self.payload(["2015-06-01", "10", "10", "11", "9", "100"])]
        duplicate = self.payload()
        duplicate["data"]["bj920006"]["day"] *= 2
        cases.append(duplicate)
        for payload in cases:
            with self.assertRaises(ValueError):
                frame_from_payload(payload, "920006", PHASE4_START, END)

    def test_tencent_empty_response_cannot_be_marked_no_data(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"code": 0, "data": {"bj920006": {"day": []}}}
        with patch("requests.get", return_value=Response()):
            with self.assertRaises(RuntimeError):
                fetch_tencent_bse(symbol="920006", start_date="2015-06-01", end_date="2015-06-04")

    def test_source_switch_cannot_splice_conflicting_hfq_series(self):
        raw = frame_from_payload(self.payload(), "920006", PHASE4_START, END)
        old = dict(trading_date="2015-06-01", open=10, high=11, low=9, close=10,
                   volume=10000, amount=100000, signal_open=10, signal_high=11,
                   signal_low=9, signal_close=10)
        verify_overlap(raw, raw, [old], "920006")
        old["signal_close"] = 20
        with self.assertRaisesRegex(ValueError, "HFQ convention"):
            verify_overlap(raw, raw, [old], "920006")

    def test_persistent_bse_error_cools_down_then_requires_source_review(self):
        with _test_directory() as tmp:
            cache = SQLiteMarketCache(Path(tmp) / "isolated.sqlite")
            stock = StockInfo("920006", "BSE", "BSE")
            now = datetime(2026, 10, 12, tzinfo=timezone.utc)
            error = RuntimeError("source unavailable")
            sync_retry.failed(cache, stock, PHASE4_START, END, error, now)
            self.assertFalse(sync_retry.eligible(cache, stock, PHASE4_START, END, now + timedelta(minutes=15)))
            self.assertTrue(sync_retry.eligible(cache, stock, PHASE4_START, END, now + timedelta(hours=1)))
            for _ in range(2): sync_retry.failed(cache, stock, PHASE4_START, END, error, now)
            self.assertFalse(sync_retry.eligible(cache, stock, PHASE4_START, END, now + timedelta(days=30)))
            corrected = StockInfo("920006", "BSE", "BSE", list_date=PHASE4_START)
            self.assertTrue(sync_retry.eligible(cache, corrected, PHASE4_START, END, now))
            sync_retry.clear(cache, stock.symbol)
            self.assertTrue(sync_retry.eligible(cache, stock, PHASE4_START, END, now))


if __name__ == "__main__":
    unittest.main()
