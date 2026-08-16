from __future__ import annotations

import unittest
from datetime import date

from stock_picker import (
    DailyBar,
    InMemoryMarketData,
    NoEligibleStockError,
    SelectionConfig,
    StockSelector,
)


DAY = date(2026, 8, 14)


class StockSelectorTests(unittest.TestCase):
    def test_selects_exactly_one_highest_scoring_stock(self) -> None:
        source = InMemoryMarketData(
            [
                DailyBar(DAY, "AAA", 10.5, 10.0, 100),
                DailyBar(DAY, "BBB", 11.0, 10.0, 200),
                DailyBar(DAY, "CCC", 12.0, 10.0, 1_000, tradable=False),
            ]
        )

        result = StockSelector(source).select_one(DAY)

        self.assertEqual(result.symbol, "BBB")

    def test_tie_break_is_deterministic_and_independent_of_input_order(self) -> None:
        bars = [
            DailyBar(DAY, "ZZZ", 11.0, 10.0, 100),
            DailyBar(DAY, "AAA", 11.0, 10.0, 100),
        ]

        first = StockSelector(InMemoryMarketData(bars)).select_one(DAY)
        second = StockSelector(InMemoryMarketData(reversed(bars))).select_one(DAY)

        self.assertEqual(first.symbol, "AAA")
        self.assertEqual(second.symbol, "AAA")

    def test_filters_rows_below_minimum_volume(self) -> None:
        source = InMemoryMarketData(
            [
                DailyBar(DAY, "LOW", 20.0, 10.0, 9),
                DailyBar(DAY, "OK", 10.1, 10.0, 10),
            ]
        )

        result = StockSelector(
            source, SelectionConfig(min_volume=10)
        ).select_one(DAY)

        self.assertEqual(result.symbol, "OK")

    def test_raises_when_no_stock_is_eligible(self) -> None:
        source = InMemoryMarketData(
            [DailyBar(DAY, "HALTED", 10.0, 10.0, 100, tradable=False)]
        )

        with self.assertRaises(NoEligibleStockError):
            StockSelector(source).select_one(DAY)


if __name__ == "__main__":
    unittest.main()

