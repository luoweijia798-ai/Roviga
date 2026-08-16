from __future__ import annotations

import unittest
from datetime import date

from stock_picker import RiskConfig, RiskManager


DAY = date(2026, 8, 17)


class RiskCalculationTests(unittest.TestCase):
    def test_default_risk_budget_and_stop_distance_size_position(self) -> None:
        manager = RiskManager(100_000, DAY)

        sizing = manager.calculate_position(
            trading_date=DAY,
            equity=100_000,
            cash=100_000,
            current_exposure=0,
            current_symbol_exposure=0,
            entry_price=100,
            stop_price=95,
        )

        self.assertEqual(sizing.risk_budget, 1_000)
        self.assertEqual(sizing.quantity, 200)
        self.assertEqual(sizing.position_value, 20_000)

    def test_single_and_total_position_caps_are_applied(self) -> None:
        manager = RiskManager(
            100_000,
            DAY,
            RiskConfig(
                risk_per_trade=0.05,
                max_single_position=0.20,
                max_total_exposure=0.50,
            ),
        )

        sizing = manager.calculate_position(
            trading_date=DAY,
            equity=100_000,
            cash=50_000,
            current_exposure=45_000,
            current_symbol_exposure=10_000,
            entry_price=100,
            stop_price=90,
        )

        self.assertEqual(sizing.quantity, 50)
        self.assertIn("total_exposure_limit", sizing.limited_by)

    def test_three_losses_halves_risk_and_five_losses_pause_trading(self) -> None:
        manager = RiskManager(100_000, DAY)
        for _ in range(3):
            manager.record_trade_result(-100)

        reduced = manager.status(DAY, 100_000, 0)
        self.assertTrue(reduced.trading_allowed)
        self.assertEqual(reduced.effective_risk_per_trade, 0.005)

        manager.record_trade_result(-100)
        manager.record_trade_result(-100)
        paused = manager.status(DAY, 100_000, 0)
        self.assertFalse(paused.trading_allowed)
        self.assertIn("consecutive_loss_pause", paused.reasons)


class DrawdownControlTests(unittest.TestCase):
    def test_daily_weekly_and_max_drawdown_circuit_breakers(self) -> None:
        manager = RiskManager(
            100_000,
            DAY,
            RiskConfig(
                daily_loss_limit=0.02,
                weekly_loss_limit=0.03,
                max_drawdown_limit=0.04,
            ),
        )

        status = manager.status(DAY, 95_000, 0)

        self.assertFalse(status.trading_allowed)
        self.assertEqual(
            set(status.reasons),
            {"daily_loss_limit", "weekly_loss_limit", "max_drawdown_limit"},
        )
        self.assertIn("risk=PAUSED", status.display())
        self.assertEqual(status.as_dict()["daily_drawdown"], 0.05)
        self.assertEqual(status.as_dict()["as_of"], "2026-08-17")

    def test_new_day_resets_daily_but_not_same_week_drawdown(self) -> None:
        manager = RiskManager(100_000, DAY, RiskConfig(weekly_loss_limit=0.03))
        next_day = date(2026, 8, 18)

        manager.start_day(next_day, 96_000)
        status = manager.status(next_day, 96_000, 0)

        self.assertEqual(status.daily_drawdown, 0)
        self.assertAlmostEqual(status.weekly_drawdown, 0.04)
        self.assertIn("weekly_loss_limit", status.reasons)


if __name__ == "__main__":
    unittest.main()
