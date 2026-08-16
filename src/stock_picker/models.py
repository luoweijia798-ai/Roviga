from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DailyBar:
    """The minimum daily data needed by the phase-one strategy."""

    trading_date: date
    symbol: str
    close: float
    previous_close: float
    volume: int
    tradable: bool = True

    @property
    def momentum(self) -> float:
        return self.close / self.previous_close - 1.0


@dataclass(frozen=True, slots=True)
class Selection:
    trading_date: date
    symbol: str
    score: float
    momentum: float
    volume_rank: float

