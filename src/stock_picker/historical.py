from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from .models import DailyBar


class FutureDataError(RuntimeError):
    """Raised whenever code asks for data beyond the simulated clock."""


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    trading_date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    tradable: bool = True
    limit_up_locked: bool = False
    limit_down_locked: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be blank")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if not self.low <= min(self.open, self.close) <= max(
            self.open, self.close
        ) <= self.high:
            raise ValueError("prices must satisfy low <= open/close <= high")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.vwap is not None and not self.low <= self.vwap <= self.high:
            raise ValueError("VWAP must be inside the daily range")
        if self.limit_up_locked and self.limit_down_locked:
            raise ValueError("a bar cannot be locked at both limits")


@dataclass(frozen=True, slots=True)
class BenchmarkPoint:
    trading_date: date
    name: str
    close: float

    def __post_init__(self) -> None:
        if not self.name.strip() or self.close <= 0:
            raise ValueError("benchmark name and close must be valid")


class InMemoryHistoricalData:
    """Immutable historical store; each backtest receives a fresh guarded portal."""

    def __init__(
        self,
        bars: Iterable[HistoricalBar],
        benchmarks: Iterable[BenchmarkPoint] = (),
    ) -> None:
        bar_map: dict[tuple[date, str], HistoricalBar] = {}
        by_date: dict[date, list[HistoricalBar]] = {}
        by_symbol: dict[str, list[HistoricalBar]] = {}
        for bar in bars:
            key = (bar.trading_date, bar.symbol)
            if key in bar_map:
                raise ValueError(f"duplicate historical bar: {key}")
            bar_map[key] = bar
            by_date.setdefault(bar.trading_date, []).append(bar)
            by_symbol.setdefault(bar.symbol, []).append(bar)
        benchmark_map: dict[tuple[str, date], BenchmarkPoint] = {}
        for point in benchmarks:
            key = (point.name, point.trading_date)
            if key in benchmark_map:
                raise ValueError(f"duplicate benchmark point: {key}")
            benchmark_map[key] = point
        self._bars = bar_map
        self._by_date = {
            key: tuple(sorted(value, key=lambda item: item.symbol))
            for key, value in by_date.items()
        }
        self._by_symbol = {
            key: tuple(sorted(value, key=lambda item: item.trading_date))
            for key, value in by_symbol.items()
        }
        self._benchmarks = benchmark_map
        self._dates = tuple(sorted(by_date))

    @property
    def trading_dates(self) -> tuple[date, ...]:
        return self._dates

    @property
    def benchmark_names(self) -> tuple[str, ...]:
        return tuple(sorted({name for name, _ in self._benchmarks}))

    def portal(self) -> HistoricalDataPortal:
        return HistoricalDataPortal(self)


class HistoricalDataPortal:
    """Read-only data view whose clock can only move forward."""

    def __init__(self, store: InMemoryHistoricalData) -> None:
        self._store = store
        self._clock: date | None = None

    @property
    def clock(self) -> date | None:
        return self._clock

    def advance_to(self, trading_date: date) -> None:
        if self._clock is not None and trading_date < self._clock:
            raise FutureDataError("historical clock cannot move backwards")
        self._clock = trading_date

    def bar(self, symbol: str, trading_date: date) -> HistoricalBar | None:
        self._guard(trading_date)
        return self._store._bars.get((trading_date, symbol))

    def bars_on(self, trading_date: date) -> tuple[HistoricalBar, ...]:
        self._guard(trading_date)
        return self._store._by_date.get(trading_date, ())

    def daily_snapshot(self, trading_date: date) -> Sequence[DailyBar]:
        """Adapt known-at-close bars to the unchanged phase-one selector API."""

        self._guard(trading_date)
        snapshot: list[DailyBar] = []
        for bar in self._store._by_date.get(trading_date, ()):
            previous = self.previous_bar(bar.symbol, trading_date)
            if previous is None:
                continue
            snapshot.append(
                DailyBar(
                    trading_date=trading_date,
                    symbol=bar.symbol,
                    close=bar.close,
                    previous_close=previous.close,
                    volume=bar.volume,
                    tradable=bar.tradable,
                )
            )
        return tuple(snapshot)

    def previous_bar(
        self, symbol: str, before_date: date
    ) -> HistoricalBar | None:
        self._guard(before_date)
        prior = [
            bar
            for bar in self._store._by_symbol.get(symbol, ())
            if bar.trading_date < before_date
        ]
        return prior[-1] if prior else None

    def benchmark_close(self, name: str, trading_date: date) -> float | None:
        self._guard(trading_date)
        point = self._store._benchmarks.get((name, trading_date))
        return point.close if point else None

    def benchmark_history(
        self, name: str, through_date: date, lookback: int
    ) -> tuple[float, ...]:
        self._guard(through_date)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        values = [
            point.close
            for (point_name, point_date), point in sorted(
                self._store._benchmarks.items(), key=lambda item: item[0][1]
            )
            if point_name == name and point_date <= through_date
        ]
        return tuple(values[-lookback:])

    def _guard(self, requested_date: date) -> None:
        if self._clock is None:
            raise FutureDataError("historical clock has not started")
        if requested_date > self._clock:
            raise FutureDataError(
                f"requested {requested_date.isoformat()} beyond simulated "
                f"clock {self._clock.isoformat()}"
            )
