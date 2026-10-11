from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_real_market import END, _FakeAkShare, _FakeSinaFallback, _test_directory, pd
from stock_picker.real_market import AkShareAdapter, PHASE4_START, SQLiteMarketCache, StockInfo, SymbolSyncStatus
from stock_picker.sina_archive import archive_frames
from stock_picker.data_audit import RealMarketDataAuditor


@unittest.skipIf(pd is None, "optional pandas market dependency")
class RetiredRecoveryTests(unittest.TestCase):
    def adapter(self, client):
        return AkShareAdapter(ak_module=client, include_classifications=False,
                              request_interval=0, retry_delay=0, max_attempts=1, segment_days=2)

    def archive(self):
        raw = _FakeSinaFallback().stock_zh_a_daily(symbol="sz000001", start_date="20150601", end_date="20150604", adjust="")
        raw["date"] = raw["date"].map(date.fromisoformat)
        adjusted = raw.copy()
        for field in ("open", "high", "low", "close"):
            adjusted[field] *= 2
        return raw, adjusted, 1

    def test_raw_archive_preserves_sessions_and_uses_only_past_factors(self):
        rows = [{"date": "2015-06-01T00:00:00.000Z", "open": 10, "high": 11, "low": 9,
                 "close": 10, "volume": 1000, "amount": 10000},
                {"date": "2015-06-03T00:00:00.000Z", "open": 11, "high": 12, "low": 10,
                 "close": 11, "volume": 2000, "amount": 22000}]
        factors = [{"d": "2015-06-03", "f": "3"}, {"d": "2010-01-01", "f": "2"}]
        raw, adjusted, multiplier = archive_frames(rows, factors, PHASE4_START, END)
        self.assertEqual(list(raw.date), [PHASE4_START, date(2015, 6, 3)])
        self.assertEqual(list(adjusted.close), [20, 33])
        self.assertEqual(list(raw.volume), [1000, 2000])
        self.assertEqual(list(raw.amount), [10000, 22000])
        self.assertEqual(multiplier, 1)
        with self.assertRaisesRegex(ValueError, "no causal HFQ"):
            archive_frames(rows, [{"d": "2015-06-03", "f": "3"}], PHASE4_START, END)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            archive_frames(rows + [rows[0]], factors, PHASE4_START, END)

    def test_retired_archive_recovers_all_history_not_just_stale_checkpoint(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000001", "Retired", "SZSE", delist_date=END)])
            cache.save_sync_status(SymbolSyncStatus("000001", "AkShare", "failed", PHASE4_START, END, END, 0, 15))
            with patch("stock_picker.real_market.fetch_sina_archive", return_value=self.archive()) as loader:
                self.adapter(_FakeSinaFallback()).sync(cache, PHASE4_START, END)
            self.assertEqual(cache.symbol_bar_count("000001"), 4)
            self.assertEqual(loader.call_count, 1)
            status = cache.sync_statuses()[0]
            self.assertEqual(status.status, "complete")
            self.assertEqual(status.source, "AkShare.SinaArchive.KLC+HFQ")
            self.assertGreater(status.attempts, 15)

    def test_download_is_bounded_by_documented_delisting(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000001", "Retired", "SZSE", delist_date=date(2015, 6, 3))])
            raw, adjusted, units = self.archive()
            raw, adjusted = raw.iloc[:3].copy(), adjusted.iloc[:3].copy()
            with patch("stock_picker.real_market.fetch_sina_archive", return_value=(raw, adjusted, units)):
                self.adapter(_FakeSinaFallback()).sync(cache, PHASE4_START, END)
            self.assertEqual(cache.latest_bar_date("000001"), date(2015, 6, 3))
            self.assertEqual(cache.sync_statuses()[0].synced_through, END)

    def test_pre_range_retirement_is_explicit_and_not_a_missing_required_stock(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000002", "Outside", "SZSE", delist_date=date(2010, 1, 1))])
            cache.save_sync_status(SymbolSyncStatus("000002", "AkShare", "failed", PHASE4_START, END))
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            statuses = {item.symbol: item for item in cache.sync_statuses()}
            self.assertEqual(statuses["000002"].bar_count, 0)
            self.assertIn("outside_requested_range", statuses["000002"].source)
            audit = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertTrue(audit.passed)
            self.assertEqual(audit.payload["stock_coverage"]["outside_requested_range_count"], 1)
            self.assertEqual(audit.payload["stock_coverage"]["required_delisted_count"], 0)

    def test_empty_or_conflicting_archive_remains_failed(self):
        for kind in ("empty", "after_delisting"):
            with self.subTest(kind=kind), _test_directory() as directory:
                cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
                cache.upsert_stocks([StockInfo("000001", "Retired", "SZSE", delist_date=date(2015, 6, 3))])
                frames = self.archive()
                if kind == "empty":
                    frames = (frames[0].iloc[:0], frames[1].iloc[:0], 1)
                with patch("stock_picker.real_market.fetch_sina_archive", return_value=frames):
                    self.adapter(_FakeSinaFallback()).sync(cache, PHASE4_START, END)
                self.assertEqual(cache.sync_statuses()[0].status, "failed")

    def test_transport_circuit_is_temporary_not_permanent_fallback(self):
        import requests
        class Client(_FakeSinaFallback):
            calls = 0
            def stock_zh_a_hist(self, **args):
                self.calls += 1
                raise requests.ConnectionError("endpoint unavailable")
        client = Client()
        adapter = self.adapter(client)
        for symbol in ("000001", "000002"):
            adapter._fetch_symbol_bars(client, StockInfo(symbol, "listed", "SZSE"), PHASE4_START, END)
        self.assertEqual(client.calls, 1)
        adapter._eastmoney_retry_at = 0
        adapter._fetch_symbol_bars(client, StockInfo("000003", "listed", "SZSE"), PHASE4_START, END)
        self.assertEqual(client.calls, 2)

    def test_system_proxy_failure_tries_direct_once_and_restores_session(self):
        import requests
        observed = []
        original = requests.sessions.Session.request
        def fake(session, method, url, **args):
            observed.append((session.trust_env, args["timeout"], args.get("verify")))
            if session.trust_env:
                raise requests.exceptions.ProxyError("dead system proxy")
            return object()
        def provider(timeout=20):
            return requests.get("https://provider.invalid/test", timeout=timeout)
        with patch("requests.sessions.Session.request", new=fake):
            self.adapter(_FakeAkShare())._request(provider)
        self.assertEqual(observed, [(True, 20, None), (False, 20, None)])
        self.assertIs(requests.sessions.Session.request, original)

    def test_explicit_proxy_is_not_overridden(self):
        import requests
        observed = []
        def fake(session, method, url, **args):
            observed.append(session.trust_env)
            raise requests.exceptions.ProxyError("explicit proxy unavailable")
        def provider(timeout=20):
            return requests.get("https://provider.invalid/test", timeout=timeout,
                                proxies={"https": "https://configured.invalid"})
        with patch("requests.sessions.Session.request", new=fake):
            with self.assertRaises(requests.exceptions.ProxyError):
                self.adapter(_FakeAkShare())._request(provider)
        self.assertEqual(observed, [True])

    def test_reusing_adapter_refetches_archive_for_extended_range(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_stocks([StockInfo("000001", "Retired", "SZSE", delist_date=END)])
            adapter = self.adapter(_FakeSinaFallback())
            def loader(**kwargs):
                raw, adjusted, units = self.archive()
                finish = date.fromisoformat(kwargs["end_date"])
                return raw[raw.date <= finish], adjusted[adjusted.date <= finish], units
            with patch("stock_picker.real_market.fetch_sina_archive", side_effect=loader) as fetch:
                adapter.sync(cache, PHASE4_START, date(2015, 6, 2))
                adapter.sync(cache, PHASE4_START, END)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(cache.symbol_bar_count("000001"), 4)

    def test_audit_rejects_bars_conflicting_with_delisting_metadata(self):
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            self.adapter(_FakeAkShare()).sync(cache, PHASE4_START, END)
            cache.upsert_stocks([StockInfo("000001", "Conflict", "SZSE", delist_date=PHASE4_START)])
            audit = RealMarketDataAuditor(cache).run(end_date=END)
            self.assertFalse(audit.passed)
            self.assertIn("known_listing_dates_consistent_with_bars", audit.payload["failed_items"])
            self.assertEqual(audit.payload["stock_date_conflicts"][0]["symbol"], "000001")
