from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

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
    SQLiteMarketCache,
    TushareAdapter,
)


END = date(2015, 6, 4)


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
    def test_round_trip_preserves_prices_limits_and_classification_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
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
    def test_offline_client_maps_fields_and_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = SQLiteMarketCache(Path(directory) / "market.sqlite")
            adapter = AkShareAdapter(ak_module=_FakeAkShare())

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
            self.assertEqual(bar.causal_close, 11.3)
            self.assertAlmostEqual(bar.vwap or 0, 10.2)

    def test_foundation_runner_uses_sqlite_and_writes_data_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = SQLiteMarketCache(root / "market.sqlite")
            AkShareAdapter(ak_module=_FakeAkShare()).sync(
                cache, PHASE4_START, END
            )

            result = Phase4FoundationRunner(cache.path).run(
                end_date=END, report_directory=root / "report"
            )

            self.assertEqual(result.backtest.start_date, PHASE4_START)
            self.assertEqual(result.backtest.end_date, END)
            self.assertTrue((result.report_directory / "data_manifest.json").exists())
            self.assertTrue((result.report_directory / "data_coverage.json").exists())


@unittest.skipIf(pd is None, "pandas is installed with the market-data extra")
class TushareAdapterTests(unittest.TestCase):
    def test_exact_limits_adjustment_and_volume_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
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
