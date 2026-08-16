from __future__ import annotations

from datetime import date

from .data import InMemoryMarketData
from .models import DailyBar
from .selector import StockSelector


def build_example_selector() -> StockSelector:
    trading_day = date(2026, 8, 14)
    source = InMemoryMarketData(
        [
            DailyBar(trading_day, "AAA", close=10.40, previous_close=10.00, volume=800_000),
            DailyBar(trading_day, "BBB", close=21.20, previous_close=20.00, volume=500_000),
            DailyBar(trading_day, "CCC", close=8.80, previous_close=8.00, volume=1_200_000),
            DailyBar(
                trading_day,
                "SUSPENDED",
                close=15.00,
                previous_close=10.00,
                volume=2_000_000,
                tradable=False,
            ),
        ]
    )
    return StockSelector(source)


def main() -> None:
    trading_day = date(2026, 8, 14)
    winner = build_example_selector().select_one(trading_day)
    print(
        f"{winner.trading_date.isoformat()} selected {winner.symbol} "
        f"score={winner.score:.4f} momentum={winner.momentum:.2%}"
    )


if __name__ == "__main__":
    main()

