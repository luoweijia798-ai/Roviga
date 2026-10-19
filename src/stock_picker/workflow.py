from __future__ import annotations

from dataclasses import dataclass

from .models import Selection
from .risk import PositionSizing, RiskManager, RiskStatus
from .tracking import CandidateTrack, DailyTracker
from .trading import PaperAccount, PaperBroker, Trade


@dataclass(frozen=True, slots=True)
class CandidateExecution:
    track: CandidateTrack
    sizing: PositionSizing
    risk_status: RiskStatus
    trade: Trade | None


class PaperTradingWorkflow:
    """Connects a phase-one Selection to risk sizing and a paper fill."""

    def __init__(
        self,
        account: PaperAccount,
        broker: PaperBroker,
        risk_manager: RiskManager,
        tracker: DailyTracker,
    ) -> None:
        if broker.account is not account:
            raise ValueError("broker and workflow must use the same account")
        self.account = account
        self.broker = broker
        self.risk_manager = risk_manager
        self.tracker = tracker

    def submit_candidate(
        self,
        selection: Selection,
        *,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        market_prices: dict[str, float] | None = None,
        limit_up_locked: bool = False,
    ) -> CandidateExecution:
        track = self.tracker.reserve_signal(
            selection,
            planned_entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        prices = dict(market_prices or {})
        prices[selection.symbol] = entry_price
        equity = self.account.equity(prices)
        exposure = self.account.exposure(prices)
        symbol_exposure = self.account.position(
            selection.symbol, entry_price
        ).market_value
        status = self.risk_manager.status(
            selection.trading_date, equity, exposure
        )
        sizing = self.risk_manager.calculate_position(
            trading_date=selection.trading_date,
            equity=equity,
            cash=self.account.cash,
            current_exposure=exposure,
            current_symbol_exposure=symbol_exposure,
            entry_price=entry_price,
            stop_price=stop_price,
        )
        if sizing.quantity == 0:
            return CandidateExecution(track, sizing, status, None)
        trade = self.broker.buy(
            trading_date=selection.trading_date,
            symbol=selection.symbol,
            quantity=sizing.quantity,
            market_price=entry_price,
            limit_up_locked=limit_up_locked,
        )
        track = self.tracker.record_fill(selection.trading_date, trade)
        return CandidateExecution(track, sizing, status, trade)
