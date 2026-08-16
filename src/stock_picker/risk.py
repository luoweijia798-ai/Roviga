from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from math import floor


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """All percentages are expressed as fractions of account equity."""

    risk_per_trade: float = 0.01
    max_single_position: float = 0.20
    max_total_exposure: float = 0.80
    loss_streak_reduce_after: int = 3
    loss_streak_pause_after: int = 5
    reduced_risk_multiplier: float = 0.50
    daily_loss_limit: float = 0.03
    weekly_loss_limit: float = 0.06
    max_drawdown_limit: float = 0.15

    def __post_init__(self) -> None:
        fractions = (
            self.risk_per_trade,
            self.max_single_position,
            self.max_total_exposure,
            self.reduced_risk_multiplier,
            self.daily_loss_limit,
            self.weekly_loss_limit,
            self.max_drawdown_limit,
        )
        if any(value <= 0 or value > 1 for value in fractions):
            raise ValueError("risk percentages must be in the interval (0, 1]")
        if self.max_single_position > self.max_total_exposure:
            raise ValueError("single-position limit cannot exceed total exposure limit")
        if self.loss_streak_reduce_after < 1:
            raise ValueError("loss streak reduction threshold must be positive")
        if self.loss_streak_pause_after <= self.loss_streak_reduce_after:
            raise ValueError("pause threshold must exceed reduction threshold")


@dataclass(frozen=True, slots=True)
class RiskStatus:
    as_of: date
    trading_allowed: bool
    reasons: tuple[str, ...]
    consecutive_losses: int
    risk_multiplier: float
    effective_risk_per_trade: float
    daily_drawdown: float
    weekly_drawdown: float
    total_drawdown: float
    current_exposure_ratio: float

    def as_dict(self) -> dict[str, object]:
        """Serializable snapshot suitable for a CLI, API, or live dashboard."""

        result = asdict(self)
        result["as_of"] = self.as_of.isoformat()
        return result

    def display(self) -> str:
        state = "ACTIVE" if self.trading_allowed else "PAUSED"
        reason = ", ".join(self.reasons) if self.reasons else "none"
        return (
            f"risk={state} losses={self.consecutive_losses} "
            f"risk/trade={self.effective_risk_per_trade:.2%} "
            f"day_dd={self.daily_drawdown:.2%} "
            f"week_dd={self.weekly_drawdown:.2%} "
            f"max_dd={self.total_drawdown:.2%} "
            f"exposure={self.current_exposure_ratio:.2%} reasons={reason}"
        )


@dataclass(frozen=True, slots=True)
class PositionSizing:
    quantity: int
    entry_price: float
    stop_price: float
    risk_per_share: float
    risk_budget: float
    position_value: float
    limited_by: tuple[str, ...]


class RiskManager:
    """Stateful risk monitor and position-sizing service."""

    def __init__(
        self,
        initial_equity: float,
        as_of: date,
        config: RiskConfig | None = None,
    ) -> None:
        if initial_equity <= 0:
            raise ValueError("initial equity must be positive")
        self.config = config or RiskConfig()
        self._as_of = as_of
        self._day_key = as_of
        self._week_key = as_of.isocalendar()[:2]
        self._day_start_equity = initial_equity
        self._week_start_equity = initial_equity
        self._peak_equity = initial_equity
        self._consecutive_losses = 0

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    def start_day(self, trading_date: date, opening_equity: float) -> None:
        """Roll the daily/weekly baselines before processing that day's trades."""

        if opening_equity <= 0:
            raise ValueError("opening equity must be positive")
        if trading_date < self._as_of:
            raise ValueError("risk state cannot move backwards in time")
        if trading_date != self._day_key:
            self._day_key = trading_date
            self._day_start_equity = opening_equity
        week_key = trading_date.isocalendar()[:2]
        if week_key != self._week_key:
            self._week_key = week_key
            self._week_start_equity = opening_equity
        self._as_of = trading_date
        self._peak_equity = max(self._peak_equity, opening_equity)

    def record_trade_result(self, net_profit: float) -> None:
        if net_profit < 0:
            self._consecutive_losses += 1
        elif net_profit > 0:
            self._consecutive_losses = 0

    def status(
        self,
        trading_date: date,
        equity: float,
        current_exposure: float,
    ) -> RiskStatus:
        if trading_date != self._as_of:
            self.start_day(trading_date, equity)
        if equity <= 0:
            raise ValueError("equity must be positive")
        if current_exposure < 0:
            raise ValueError("exposure cannot be negative")

        self._peak_equity = max(self._peak_equity, equity)
        daily = self._drawdown(self._day_start_equity, equity)
        weekly = self._drawdown(self._week_start_equity, equity)
        total = self._drawdown(self._peak_equity, equity)
        reasons: list[str] = []
        if self._consecutive_losses >= self.config.loss_streak_pause_after:
            reasons.append("consecutive_loss_pause")
        if daily >= self.config.daily_loss_limit:
            reasons.append("daily_loss_limit")
        if weekly >= self.config.weekly_loss_limit:
            reasons.append("weekly_loss_limit")
        if total >= self.config.max_drawdown_limit:
            reasons.append("max_drawdown_limit")
        if current_exposure / equity >= self.config.max_total_exposure:
            reasons.append("total_exposure_limit")

        multiplier = (
            self.config.reduced_risk_multiplier
            if self._consecutive_losses >= self.config.loss_streak_reduce_after
            else 1.0
        )
        return RiskStatus(
            as_of=trading_date,
            trading_allowed=not reasons,
            reasons=tuple(reasons),
            consecutive_losses=self._consecutive_losses,
            risk_multiplier=multiplier,
            effective_risk_per_trade=self.config.risk_per_trade * multiplier,
            daily_drawdown=daily,
            weekly_drawdown=weekly,
            total_drawdown=total,
            current_exposure_ratio=current_exposure / equity,
        )

    def calculate_position(
        self,
        *,
        trading_date: date,
        equity: float,
        cash: float,
        current_exposure: float,
        current_symbol_exposure: float,
        entry_price: float,
        stop_price: float,
    ) -> PositionSizing:
        if entry_price <= 0 or stop_price <= 0:
            raise ValueError("entry and stop prices must be positive")
        if stop_price >= entry_price:
            raise ValueError("long-position stop price must be below entry price")
        if cash < 0 or current_symbol_exposure < 0:
            raise ValueError("cash and symbol exposure cannot be negative")

        status = self.status(trading_date, equity, current_exposure)
        risk_per_share = entry_price - stop_price
        risk_budget = equity * status.effective_risk_per_trade
        if not status.trading_allowed:
            return PositionSizing(
                quantity=0,
                entry_price=entry_price,
                stop_price=stop_price,
                risk_per_share=risk_per_share,
                risk_budget=risk_budget,
                position_value=0.0,
                limited_by=status.reasons,
            )

        by_risk = floor(risk_budget / risk_per_share)
        single_room = max(
            0.0, equity * self.config.max_single_position - current_symbol_exposure
        )
        total_room = max(
            0.0, equity * self.config.max_total_exposure - current_exposure
        )
        limits = {
            "risk_budget": by_risk,
            "single_position_limit": floor(single_room / entry_price),
            "total_exposure_limit": floor(total_room / entry_price),
            "cash_limit": floor(cash / entry_price),
        }
        quantity = max(0, min(limits.values()))
        binding = tuple(name for name, value in limits.items() if value == quantity)
        return PositionSizing(
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            risk_per_share=risk_per_share,
            risk_budget=risk_budget,
            position_value=quantity * entry_price,
            limited_by=binding,
        )

    @staticmethod
    def _drawdown(reference: float, equity: float) -> float:
        return max(0.0, (reference - equity) / reference)
