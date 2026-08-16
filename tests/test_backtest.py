from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_picker import (
    BacktestConfig,
    BenchmarkPoint,
    EventDrivenBacktester,
    ExecutionMode,
    FutureDataError,
    HistoricalBar,
    InMemoryHistoricalData,
)
from stock_picker.backtest_demo import build_demo_data


def _dates(count: int) -> list[date]:
    start = date(2025, 1, 2)
    return [start + timedelta(days=index) for index in range(count)]


def _single_symbol_data(
    *, limit_up_on_entry: bool = False, future_close: float = 100.0
) -> InMemoryHistoricalData:
    dates = _dates(4)
    closes = [100.0, 102.0, 101.0, future_close]
    lows = [98.0, 100.0, 90.0, 90.0]
    bars = []
    benchmarks = []
    for index, trading_date in enumerate(dates):
        open_price = closes[index - 1] if index else 99.0
        close = closes[index]
        bars.append(
            HistoricalBar(
                trading_date=trading_date,
                symbol="AAA",
                open=open_price,
                high=max(open_price, close) + 3,
                low=min(lows[index], open_price, close),
                close=close,
                volume=1_000_000,
                vwap=(open_price + close) / 2,
                limit_up_locked=limit_up_on_entry and index == 2,
            )
        )
        benchmarks.extend(
            [
                BenchmarkPoint(trading_date, "CSI300", 4_000 + index),
                BenchmarkPoint(trading_date, "CSI1000", 6_000 + index),
            ]
        )
    return InMemoryHistoricalData(bars, benchmarks)


class NoFutureDataTests(unittest.TestCase):
    def test_portal_rejects_future_date_access(self) -> None:
        data = _single_symbol_data()
        portal = data.portal()
        first, second = data.trading_dates[:2]
        portal.advance_to(first)

        with self.assertRaises(FutureDataError):
            portal.bars_on(second)
        with self.assertRaises(FutureDataError):
            portal.benchmark_close("CSI300", second)

    def test_signal_is_created_at_close_and_filled_next_session(self) -> None:
        data = _single_symbol_data()
        result = EventDrivenBacktester(data).run()
        signal_date = data.trading_dates[1]
        entry_date = data.trading_dates[2]

        fill = result.tracker.get(signal_date).fill

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill.trading_date, entry_date)
        self.assertAlmostEqual(fill.market_price, 102.0)
        self.assertAlmostEqual(fill.execution_price, 102.0 * 1.0005)

    def test_changing_unseen_future_bar_does_not_change_prior_result(self) -> None:
        normal = _single_symbol_data(future_close=100.0)
        shocked = _single_symbol_data(future_close=200.0)
        cutoff = normal.trading_dates[2]

        first = EventDrivenBacktester(normal).run(end_date=cutoff)
        second = EventDrivenBacktester(shocked).run(end_date=cutoff)

        self.assertEqual(first.equity_curve, second.equity_curve)
        self.assertEqual(first.events, second.events)


class BacktestConsistencyTests(unittest.TestCase):
    def test_same_inputs_produce_identical_results(self) -> None:
        engine = EventDrivenBacktester(
            build_demo_data(),
            BacktestConfig(regime_lookback=5),
        )

        first = engine.run()
        second = engine.run()

        self.assertEqual(first.equity_curve, second.equity_curve)
        self.assertEqual(first.trades, second.trades)
        self.assertEqual(first.events, second.events)


class BacktestExecutionRuleTests(unittest.TestCase):
    def test_entry_day_stop_touch_cannot_sell_until_following_session(self) -> None:
        data = _single_symbol_data()
        result = EventDrivenBacktester(data).run()

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.entry_date, data.trading_dates[2])
        self.assertEqual(trade.exit_date, data.trading_dates[3])
        self.assertEqual(trade.exit_reason, "stop_loss")

    def test_upper_limit_lock_rejects_scheduled_buy(self) -> None:
        data = _single_symbol_data(limit_up_on_entry=True)
        result = EventDrivenBacktester(data).run()

        rejection_reasons = [
            event.reason
            for event in result.events
            if event.event_type == "ENTRY_REJECTED"
        ]
        self.assertTrue(any("upper limit" in reason for reason in rejection_reasons))

    def test_vwap_fill_uses_next_session_vwap_not_signal_close(self) -> None:
        data = _single_symbol_data()
        result = EventDrivenBacktester(
            data,
            BacktestConfig(execution_mode=ExecutionMode.VWAP),
        ).run()
        fill = result.tracker.get(data.trading_dates[1]).fill

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertAlmostEqual(fill.market_price, 101.5)


if __name__ == "__main__":
    unittest.main()
