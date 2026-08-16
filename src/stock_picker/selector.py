from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .data import MarketDataSource
from .models import DailyBar, Selection


class NoEligibleStockError(LookupError):
    """Raised when the requested day has no row that passes the filters."""


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    min_volume: int = 1
    momentum_weight: float = 1.0
    liquidity_weight: float = 0.01

    def __post_init__(self) -> None:
        if self.min_volume < 0:
            raise ValueError("min_volume must be non-negative")
        if self.momentum_weight < 0 or self.liquidity_weight < 0:
            raise ValueError("weights must be non-negative")
        if self.momentum_weight == 0 and self.liquidity_weight == 0:
            raise ValueError("at least one weight must be positive")


class StockSelector:
    def __init__(
        self,
        data_source: MarketDataSource,
        config: SelectionConfig | None = None,
    ) -> None:
        self._data_source = data_source
        self._config = config or SelectionConfig()

    def select_one(self, trading_date: date) -> Selection:
        """Return one winner; equal scores are resolved by symbol ascending."""

        eligible = [
            bar
            for bar in self._data_source.daily_snapshot(trading_date)
            if self._is_eligible(bar, trading_date)
        ]
        if not eligible:
            raise NoEligibleStockError(
                f"no eligible stock for {trading_date.isoformat()}"
            )

        volume_ranks = self._volume_percentile_ranks(eligible)
        scored = [
            Selection(
                trading_date=trading_date,
                symbol=bar.symbol,
                score=(
                    self._config.momentum_weight * bar.momentum
                    + self._config.liquidity_weight * volume_ranks[bar.symbol]
                ),
                momentum=bar.momentum,
                volume_rank=volume_ranks[bar.symbol],
            )
            for bar in eligible
        ]
        return min(scored, key=lambda item: (-item.score, item.symbol))

    def _is_eligible(self, bar: DailyBar, requested_date: date) -> bool:
        return (
            bar.trading_date == requested_date
            and bool(bar.symbol.strip())
            and bar.tradable
            and bar.close > 0
            and bar.previous_close > 0
            and bar.volume >= self._config.min_volume
        )

    @staticmethod
    def _volume_percentile_ranks(bars: list[DailyBar]) -> dict[str, float]:
        """Map volume to [0, 1]; equal volumes receive equal ranks."""

        unique_volumes = sorted({bar.volume for bar in bars})
        if len(unique_volumes) == 1:
            return {bar.symbol: 1.0 for bar in bars}
        denominator = len(unique_volumes) - 1
        rank_by_volume = {
            volume: index / denominator
            for index, volume in enumerate(unique_volumes)
        }
        return {bar.symbol: rank_by_volume[bar.volume] for bar in bars}

