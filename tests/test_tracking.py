from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_picker import (
    DailyTracker,
    PaperAccount,
    PaperBroker,
    Selection,
    TrackingState,
)


DAY = date(2026, 8, 17)


class DailyTrackingTests(unittest.TestCase):
    def test_tracks_fill_one_three_five_day_returns_and_extremes(self) -> None:
        tracker = DailyTracker()
        signal = Selection(DAY, "AAA", 0.2, 0.1, 1.0)
        tracker.record_signal(
            signal,
            planned_entry_price=10,
            stop_price=9,
            take_profit_price=12,
        )
        trade = PaperBroker(PaperAccount(10_000)).buy(
            trading_date=DAY,
            symbol="AAA",
            quantity=10,
            market_price=10,
        )
        tracker.record_fill(DAY, trade)

        closes = [10.5, 10.4, 11.0, 10.8, 11.5]
        for offset, close in enumerate(closes, start=1):
            tracker.update_market(
                DAY,
                trading_date=DAY + timedelta(days=offset),
                close=close,
                high=close + 0.2,
                low=close - 0.3,
            )

        result = tracker.get(DAY)
        self.assertEqual(set(result.performance), {1, 3, 5})
        self.assertGreater(result.performance[5], result.performance[1])
        self.assertGreater(result.maximum_gain, 0)
        self.assertLess(result.maximum_loss, result.maximum_gain)
        self.assertEqual(result.state, TrackingState.ACTIVE)

    def test_stop_loss_has_conservative_priority_over_take_profit(self) -> None:
        tracker = DailyTracker()
        signal = Selection(DAY, "AAA", 0.2, 0.1, 1.0)
        tracker.record_signal(
            signal,
            planned_entry_price=10,
            stop_price=9,
            take_profit_price=11,
        )

        result = tracker.update_market(
            DAY,
            trading_date=DAY + timedelta(days=1),
            close=10,
            high=11.5,
            low=8.5,
        )

        self.assertEqual(result.state, TrackingState.STOPPED_OUT)

    def test_rejects_a_second_candidate_on_the_same_day(self) -> None:
        tracker = DailyTracker()
        signal = Selection(DAY, "AAA", 0.2, 0.1, 1.0)
        tracker.record_signal(
            signal,
            planned_entry_price=10,
            stop_price=9,
            take_profit_price=12,
        )

        with self.assertRaisesRegex(ValueError, "already recorded"):
            tracker.record_signal(
                Selection(DAY, "BBB", 0.3, 0.2, 1.0),
                planned_entry_price=20,
                stop_price=18,
                take_profit_price=24,
            )


if __name__ == "__main__":
    unittest.main()
