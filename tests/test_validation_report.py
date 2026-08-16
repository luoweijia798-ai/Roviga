from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_picker import (
    BacktestConfig,
    BacktestReportWriter,
    EventDrivenBacktester,
    MarketRegime,
    TestPeriod,
    WalkForwardSplit,
    WalkForwardValidator,
    analyze_backtest,
)
from stock_picker.backtest_demo import build_demo_data


class ValidationAndReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = build_demo_data()
        self.config = BacktestConfig(
            regime_lookback=5,
            bull_threshold=0.015,
            bear_threshold=-0.015,
        )

    def test_walk_forward_periods_are_independent_and_ordered(self) -> None:
        dates = self.data.trading_dates
        split = WalkForwardSplit(
            TestPeriod("training", dates[0], dates[24]),
            TestPeriod("validation", dates[25], dates[49]),
            TestPeriod("out_of_sample", dates[50], dates[74]),
        )

        result = WalkForwardValidator(self.data, self.config).run(split)

        self.assertEqual(result.training.result.start_date, dates[0])
        self.assertEqual(result.validation.result.start_date, dates[25])
        self.assertEqual(result.out_of_sample.result.start_date, dates[50])
        self.assertEqual(result.out_of_sample.result.end_date, dates[74])

    def test_analysis_includes_benchmarks_regimes_and_required_metrics(self) -> None:
        result = EventDrivenBacktester(self.data, self.config).run()

        analysis = analyze_backtest(result)

        self.assertGreater(analysis.summary.total_trades, 0)
        self.assertGreaterEqual(analysis.summary.maximum_drawdown, 0)
        self.assertEqual(set(analysis.benchmarks), {"CSI300", "CSI1000"})
        self.assertEqual(set(analysis.regimes), set(MarketRegime))
        self.assertTrue(analysis.monthly_returns)
        self.assertIsNotNone(analysis.maximum_profit_trade)
        self.assertIsNotNone(analysis.maximum_loss_trade)

    def test_report_contains_curve_trades_reasons_and_extreme_trades(self) -> None:
        result = EventDrivenBacktester(self.data, self.config).run()
        expected_files = {
            "summary.json",
            "equity_curve.csv",
            "equity_curve.svg",
            "trades.csv",
            "events.csv",
            "monthly_returns.csv",
        }

        with tempfile.TemporaryDirectory() as directory:
            output = BacktestReportWriter().write(result, directory)
            payload = json.loads((output / "summary.json").read_text("utf-8"))

            self.assertEqual(
                {path.name for path in Path(output).iterdir()}, expected_files
            )
            self.assertIn("maximum_profit_trade", payload)
            self.assertIn("maximum_loss_trade", payload)
            self.assertIn("exit_reason", (output / "trades.csv").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
