from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Protocol

from .models import DailyBar


class MarketDataSource(Protocol):
    """Boundary implemented by any database, API, CSV, or test data source."""

    def daily_snapshot(self, trading_date: date) -> Sequence[DailyBar]:
        """Return all known symbols for one date."""


class InMemoryMarketData:
    """Small data adapter used by examples and unit tests."""

    def __init__(self, bars: Iterable[DailyBar]) -> None:
        grouped: dict[date, list[DailyBar]] = {}
        for bar in bars:
            grouped.setdefault(bar.trading_date, []).append(bar)
        self._bars = {key: tuple(value) for key, value in grouped.items()}

    def daily_snapshot(self, trading_date: date) -> Sequence[DailyBar]:
        return self._bars.get(trading_date, ())

