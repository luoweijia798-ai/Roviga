from __future__ import annotations

import shutil
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

try:
    import pandas as pd
except ImportError:  # Optional market-data dependency.
    pd = None  # type: ignore[assignment]

from stock_picker import (
    AkShareAdapter,
    ClassificationRecord,
    FutureDataError,
    HistoricalBar,
    PHASE4_START,
    Phase4FoundationRunner,
    Phase4SyncMonitor,
    RealMarketDataAuditor,
    SQLiteMarketCache,
    SymbolSyncStatus,
    StockInfo,
    TushareAdapter,
)
from stock_picker.real_market import _bounded_vwap


END = date(2015, 6, 4)


@contextmanager
def _test_directory():
    root = Path("data/test-runs") / uuid4().hex
    root.mkdir(parents=True)
    try:
        yield str(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


class _FakeAkShare:
    def stock_info_a_code_name(self) -> pd.DataFrame:
        return pd.DataFrame([{"code": "000001", "name": "平安银行"}])

    def stock_zh_a_hist(
        self,
        *,
        symbol: str,
        period: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> pd.DataFrame:
        offset = 1.0 if adjust == "hfq" else 0.0
        raw = [
            ("2015-06-01", 10.0, 10.1, 10.2, 9.9),
            ("2015-06-02", 10.1, 10.3, 10.4, 10.0),
            ("2015-06-03", 10.3, 10.2, 10.4, 10.1),
            ("2015-06-04", 10.2, 10.5, 10.6, 10.1),
        ]
        rows = [
            {
                "日期": trading_date,
                "股票代码": symbol,
                "开盘": open_price + offset,
                "收盘": close + offset,
                "最高": high + offset,
                "最低": low + offset,
                "成交量": 1_000,
                "成交额": 1_020_000,
            }
            for trading_date, open_price, close, high, low in raw
            if start_date <= trading_date.replace("-", "") <= end_date
        ]
        return pd.DataFrame(rows)

    def stock_zh_index_daily_em(
        self, *, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        base = 4_000 if symbol == "sh000300" else 6_000
        return pd.DataFrame(
            [
                {"date": f"2015-06-0{index}", "close": base + index}
                for index in range(1, 5)
            ]
        )

    def stock_board_industry_name_em(self) -> pd.DataFrame:
        return pd.DataFrame([{"板块名称": "银行"}])

    def stock_board_industry_cons_em(self, *, symbol: str) -> pd.DataFrame:
        return pd.DataFrame([{"代码": "000001"}])

    def stock_board_concept_name_em(self) -> pd.DataFrame:
        return pd.DataFrame([{"板块名称": "金融科技"}])

    def stock_board_concept_cons_em(self, *, symbol: str) -> pd.DataFrame:
        return pd.DataFrame([{"代码": "000001"}])


class _FakeSinaFallback(_FakeAkShare):
    def stock_zh_a_hist(self, **_: object) -> pd.DataFrame:
        raise ConnectionError("Eastmoney unavailable")

    def stock_zh_a_daily(
        self, *, symbol: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        offset = 1.0 if adjust == "hfq" else 0.0
        return pd.DataFrame(
            [
                {
                    "date": f"2015-06-0{index}",
                    "open": 10.0 + offset,
                    "high": 10.4 + offset,
                    "low": 9.9 + offset,
                    "close": 10.2 + offset,
                    "volume": 100_000,
                    "amount": 1_020_000,
                }
                for index in range(1, 5)
            ]
        )

    def stock_zh_index_daily(self, *, symbol: str) -> pd.DataFrame:
        base = 4_000 if symbol == "sh000300" else 6_000
        return pd.DataFrame(
            [
                {"date": f"2015-06-0{index}", "close": base + index}
                for index in range(1, 5)
            ]
        )


class _FlakyAkShare(_FakeAkShare):
    def __init__(self) -> None:
        self.failures_remaining = 2
        self.requested_ranges: list[tuple[str, str, str]] = []

    def stock_zh_a_hist(self, **arguments: str) -> pd.DataFrame:
        self.requested_ranges.append(
            (arguments["start_date"], arguments["end_date"], arguments["adjust"])
        )
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise ConnectionError("temporary throttle")
        return super().stock_zh_a_hist(**arguments)


class _EmptyAdjustedAkShare(_FakeAkShare):
    def stock_zh_a_hist(self, **arguments: str) -> pd.DataFrame:
        if arguments["adjust"] == "hfq":
            return pd.DataFrame()
        return super().stock_zh_a_hist(**arguments)


class _FakeTushare:
    def stock_basic(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行",
                    "industry": "银行",
                    "list_date": "19910403",
                    "delist_date": None,
                    "exchange": "SZSE",
                }
            ]
        )

    def trade_cal(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame([{"cal_date": "20150601"}])

    def daily(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "open": 11.0,
                    "high": 11.0,
                    "low": 11.0,
                    "close": 11.0,
                    "vol": 1_000,
                    "amount": 1_100,
                }
            ]
        )

    def stk_limit(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [{"ts_code": "000001.SZ", "up_limit": 11.0, "down_limit": 9.0}]
        )

    def adj_factor(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame([{"ts_code": "000001.SZ", "adj_factor": 2.0}])

    def index_daily(self, *, ts_code: str, **_: object) -> pd.DataFrame:
        close = 4_000 if ts_code == "000300.SH" else 6_000
        return pd.DataFrame([{"trade_date": "20150601", "close": close}])


class SQLiteCausalDataTests(unittest.TestCase):
    def test_vwap_clamps_sub_tick_rounding_and_rejects_material_mismatch(self) -> None:
        self.assertEqual(_bounded_vwap(12_073_481, 1_931_757, 6.25, 6.25), 6.25)
        self.assertIsNone(_bounded_vwap(100_000, 10_000, 9.0, 9.5))

    def test_round_trip_preserves_prices_limits_and_classification_time(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.upsert_bars(
                [
                    HistoricalBar(
                        PHASE4_START,
                        "AAA",
                        10,
                        11,
                        9,
                        10.5,
                        100,
                        amount=100_000,
                        up_limit=11,
                        down_limit=9,
                        signal_close=20.5,
                    )
                ]
            )
            cache.upsert_classifications(
                [
                    ClassificationRecord(
                        "AAA",
                        "industry",
                        "Test Industry",
                        PHASE4_START,
                        END,
                    )
                ]
            )
            portal = cache.as_historical_data().portal()
            portal.advance_to(PHASE4_START)

            bar = portal.bar("AAA", PHASE4_START)

            self.assertIsNotNone(bar)
            assert bar is not None
            self.assertEqual(bar.amount, 100_000)
            self.assertEqual(bar.causal_close, 20.5)
            self.assertEqual(portal.classifications_as_of("AAA", PHASE4_START), ())
            with self.assertRaises(FutureDataError):
                portal.classifications_as_of("AAA", END)

            portal.advance_to(END)
            records = portal.classifications_as_of("AAA", END)
            self.assertEqual(records[0].classification_name, "Test Industry")


@unittest.skipIf(pd is None, "pandas is installed with the market-data extra")
class AkShareAdapterTests(unittest.TestCase):
    def test_empty_adjusted_history_falls_back_to_raw_signal_prices(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            manifest = AkShareAdapter(
                ak_module=_EmptyAdjustedAkShare(),
                include_classifications=False,
                request_interval=0,
                retry_delay=0,
            ).sync(cache, PHASE4_START, END)
            portal = cache.as_historical_data().portal()
            portal.advance_to(PHASE4_START)
            bar = portal.bar("000001", PHASE4_START)

            self.assertEqual(manifest.bar_count, 4)
            self.assertIsNotNone(bar)
            assert bar is not None
            self.assertEqual(bar.signal_close, bar.close)

    def test_monitor_waits_for_all_stocks_then_writes_audit_bundle(self) -> None:
        with _test_directory() as directory:
            root = Path(directory)
            cache = SQLiteMarketCache(root / "market.sqlite")
            AkShareAdapter(
                ak_module=_FakeAkShare(), request_interval=0, retry_delay=0
            ).sync(cache, PHASE4_START, END)
            monitor = Phase4SyncMonitor(cache)

            complete, audit = monitor.refresh(
                end_date=END,
                status_output=root / "phase4_sync_status.json",
                audit_output=root / "phase4_data_audit_report",
            )

            self.assertTrue(complete["sync_complete"])
            self.assertTrue(complete["audit_triggered"])
            self.assertIsNotNone(audit)
            self.assertTrue((root / "phase4_data_audit_report/audit_report.json").exists())
            self.assertTrue((root / "phase4_data_audit_report/missing_stocks.json").exists())
            self.assertTrue((root / "phase4_data_audit_report/missing_dates.json").exists())
            self.assertTrue((root / "phase4_data_audit_report/data_anomalies.json").exists())

            cache.upsert_stocks(
                [StockInfo("000002", "Pending", "SZSE", source="test")]
            )
            incomplete, second_audit = monitor.refresh(
                end_date=END,
                status_output=root / "phase4_sync_status.json",
                audit_output=root / "not_generated",
            )
            self.assertFalse(incomplete["sync_complete"])
            self.assertFalse(incomplete["audit_triggered"])
            self.assertIsNone(second_audit)

    def test_stale_running_status_is_marked_interrupted_on_restart(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            cache.save_sync_status(
                SymbolSyncStatus(
                    "999999", "AkShare", "running", PHASE4_START, END
                )
            )

            AkShareAdapter(
                ak_module=_FakeAkShare(), request_interval=0, retry_delay=0
            ).sync(cache, PHASE4_START, END)

            statuses = {item.symbol: item for item in cache.sync_statuses()}
            self.assertEqual(statuses["999999"].status, "interrupted")
            self.assertIn("queued for resume", statuses["999999"].last_error or "")

    def test_hidden_requests_call_receives_default_timeout(self) -> None:
        import requests

        observed: dict[str, object] = {}

        def provider() -> object:
            return requests.get("https://provider.invalid/test")

        def fake_request(
            _session: object, _method: str, _url: str, **arguments: object
        ) -> object:
            observed.update(arguments)
            return object()

        adapter = AkShareAdapter(
            ak_module=_FakeAkShare(), request_interval=0, retry_delay=0
        )
        with patch("requests.sessions.Session.request", new=fake_request):
            adapter._request(provider)

        self.assertEqual(observed["timeout"], 20)

    def test_offline_client_maps_fields_and_is_incremental(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            adapter = AkShareAdapter(
                ak_module=_FakeAkShare(), request_interval=0, retry_delay=0
            )

            first = adapter.sync(cache, PHASE4_START, END)
            second = adapter.sync(cache, PHASE4_START, END)
            portal = cache.as_historical_data().portal()
            portal.advance_to(date(2015, 6, 2))
            bar = portal.bar("000001", date(2015, 6, 2))

            self.assertEqual(first.bar_count, 4)
            self.assertEqual(second.bar_count, 4)
            self.assertEqual(cache.coverage()["classification_count"], 2)
            self.assertIsNotNone(bar)
            assert bar is not None
            self.assertEqual(bar.amount, 1_020_000)
            self.assertEqual(bar.volume, 100_000)
            self.assertEqual(bar.causal_close, 11.3)
            self.assertAlmostEqual(bar.vwap or 0, 10.2)

    def test_sina_fallback_preserves_share_units_and_benchmarks(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            manifest = AkShareAdapter(
                ak_module=_FakeSinaFallback(),
                include_classifications=False,
                request_interval=0,
                retry_delay=0,
            ).sync(cache, PHASE4_START, END)
            portal = cache.as_historical_data().portal()
            portal.advance_to(PHASE4_START)
            bar = portal.bar("000001", PHASE4_START)

            self.assertEqual(manifest.bar_count, 4)
            self.assertIsNotNone(bar)
            assert bar is not None
            self.assertEqual(bar.volume, 100_000)
            self.assertAlmostEqual(bar.vwap or 0, 10.2)
            self.assertEqual(bar.causal_close, 11.2)
            self.assertEqual(
                set(cache.as_historical_data().benchmark_names),
                {"CSI300", "CSI1000"},
            )

    def test_retry_segments_status_and_completed_symbol_skip(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            client = _FlakyAkShare()
            adapter = AkShareAdapter(
                ak_module=client,
                include_classifications=False,
                request_interval=0,
                retry_delay=0,
                segment_days=2,
            )

            adapter.sync(cache, PHASE4_START, END)
            requests_after_first_sync = len(client.requested_ranges)
            adapter.sync(cache, PHASE4_START, END)
            status = cache.sync_statuses()[0]

            self.assertEqual(status.status, "complete")
            self.assertEqual(status.synced_through, END)
            self.assertEqual(status.bar_count, 4)
            self.assertGreaterEqual(status.attempts, 6)
            self.assertEqual(len(client.requested_ranges), requests_after_first_sync)
            successful_ranges = {
                (start, end) for start, end, _ in client.requested_ranges
            }
            self.assertIn(("20150601", "20150602"), successful_ranges)
            self.assertIn(("20150603", "20150604"), successful_ranges)

    def test_foundation_runner_uses_sqlite_and_writes_data_audit(self) -> None:
        with _test_directory() as directory:
            root = Path(directory)
            cache = SQLiteMarketCache(root / "market.sqlite")
            AkShareAdapter(
                ak_module=_FakeAkShare(), request_interval=0, retry_delay=0
            ).sync(
                cache, PHASE4_START, END
            )
            audit = RealMarketDataAuditor(cache).run(
                start_date=PHASE4_START, end_date=END
            )

            result = Phase4FoundationRunner(cache.path).run(
                end_date=END, report_directory=root / "report"
            )

            self.assertEqual(result.backtest.start_date, PHASE4_START)
            self.assertEqual(result.backtest.end_date, END)
            self.assertTrue(audit.passed)
            self.assertTrue((result.report_directory / "data_manifest.json").exists())
            self.assertTrue((result.report_directory / "data_coverage.json").exists())


@unittest.skipIf(pd is None, "pandas is installed with the market-data extra")
class TushareAdapterTests(unittest.TestCase):
    def test_exact_limits_adjustment_and_volume_units(self) -> None:
        with _test_directory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            TushareAdapter(pro_client=_FakeTushare()).sync(
                cache, PHASE4_START, PHASE4_START
            )
            portal = cache.as_historical_data().portal()
            portal.advance_to(PHASE4_START)
            bar = portal.bar("000001", PHASE4_START)

            self.assertIsNotNone(bar)
            assert bar is not None
            self.assertEqual(bar.volume, 100_000)
            self.assertEqual(bar.amount, 1_100_000)
            self.assertAlmostEqual(bar.vwap or 0, 11.0)
            self.assertEqual(bar.up_limit, 11.0)
            self.assertTrue(bar.limit_up_locked)
            self.assertEqual(bar.causal_close, 22.0)


if __name__ == "__main__":
    unittest.main()
