from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .models import Selection
from .trading import Side, Trade


class TrackingState(str, Enum):
    WAITING_FILL = "WAITING_FILL"
    ACTIVE = "ACTIVE"
    STOPPED_OUT = "STOPPED_OUT"
    TOOK_PROFIT = "TOOK_PROFIT"


@dataclass(frozen=True, slots=True)
class PriceObservation:
    trading_date: date
    close: float
    high: float
    low: float


@dataclass(slots=True)
class CandidateTrack:
    signal: Selection
    planned_entry_price: float
    stop_price: float
    take_profit_price: float
    fill: Trade | None = None
    observations: list[PriceObservation] = field(default_factory=list)
    performance: dict[int, float] = field(default_factory=dict)
    maximum_gain: float = 0.0
    maximum_loss: float = 0.0
    state: TrackingState = TrackingState.WAITING_FILL

    @property
    def reference_price(self) -> float:
        return self.fill.execution_price if self.fill else self.planned_entry_price


class DailyTracker:
    """Tracks one and only one candidate for each signal date."""

    HORIZONS = (1, 3, 5)

    def __init__(self) -> None:
        self._tracks: dict[date, CandidateTrack] = {}

    def record_signal(
        self,
        selection: Selection,
        *,
        planned_entry_price: float,
        stop_price: float,
        take_profit_price: float,
    ) -> CandidateTrack:
        if selection.trading_date in self._tracks:
            raise ValueError("a candidate is already recorded for this trading day")
        if not 0 < stop_price < planned_entry_price < take_profit_price:
            raise ValueError("prices must satisfy stop < entry < take profit")
        track = CandidateTrack(
            signal=selection,
            planned_entry_price=planned_entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        self._tracks[selection.trading_date] = track
        return track

    def record_fill(self, signal_date: date, trade: Trade) -> CandidateTrack:
        track = self.get(signal_date)
        if trade.side is not Side.BUY:
            raise ValueError("candidate fill must be a buy trade")
        if trade.symbol != track.signal.symbol:
            raise ValueError("fill symbol does not match the selected candidate")
        if track.fill is not None:
            raise ValueError("candidate fill has already been recorded")
        track.fill = trade
        track.state = TrackingState.ACTIVE
        self._recalculate(track)
        return track

    def update_market(
        self,
        signal_date: date,
        *,
        trading_date: date,
        close: float,
        high: float | None = None,
        low: float | None = None,
    ) -> CandidateTrack:
        track = self.get(signal_date)
        if trading_date <= signal_date:
            raise ValueError("performance observations must be after the signal date")
        if close <= 0:
            raise ValueError("close must be positive")
        high = close if high is None else high
        low = close if low is None else low
        if low <= 0 or high < close or low > close:
            raise ValueError("prices must satisfy 0 < low <= close <= high")
        if any(item.trading_date == trading_date for item in track.observations):
            raise ValueError("market date has already been recorded")

        observation = PriceObservation(trading_date, close, high, low)
        track.observations.append(observation)
        track.observations.sort(key=lambda item: item.trading_date)
        self._recalculate(track)
        return track

    def get(self, signal_date: date) -> CandidateTrack:
        try:
            return self._tracks[signal_date]
        except KeyError as error:
            raise KeyError(f"no candidate recorded for {signal_date.isoformat()}") from error

    def all(self) -> tuple[CandidateTrack, ...]:
        return tuple(self._tracks[key] for key in sorted(self._tracks))

    def _recalculate(self, track: CandidateTrack) -> None:
        reference = track.reference_price
        track.performance.clear()
        for horizon in self.HORIZONS:
            if len(track.observations) >= horizon:
                close = track.observations[horizon - 1].close
                track.performance[horizon] = close / reference - 1.0

        gains = [item.high / reference - 1.0 for item in track.observations]
        losses = [item.low / reference - 1.0 for item in track.observations]
        track.maximum_gain = max([0.0, *gains])
        track.maximum_loss = min([0.0, *losses])
        if any(item.low <= track.stop_price for item in track.observations):
            track.state = TrackingState.STOPPED_OUT
        elif any(
            item.high >= track.take_profit_price for item in track.observations
        ):
            track.state = TrackingState.TOOK_PROFIT
        elif track.fill is not None:
            track.state = TrackingState.ACTIVE
