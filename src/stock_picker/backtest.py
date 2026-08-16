from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .historical import HistoricalBar, InMemoryHistoricalData
from .models import Selection
from .risk import RiskConfig, RiskManager, RiskStatus
from .selector import NoEligibleStockError, SelectionConfig, StockSelector
from .tracking import DailyTracker
from .trading import ExecutionConfig, OrderRejected, PaperAccount, PaperBroker, Trade


class ExecutionMode(str, Enum):
    OPEN = "OPEN"
    VWAP = "VWAP"


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    execution_mode: ExecutionMode = ExecutionMode.OPEN
    stop_loss_fraction: float = 0.05
    take_profit_fraction: float = 0.10
    max_holding_sessions: int = 5
    regime_benchmark: str = "CSI300"
    regime_lookback: int = 20
    bull_threshold: float = 0.03
    bear_threshold: float = -0.03

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        if not 0 < self.stop_loss_fraction < 1:
            raise ValueError("stop loss fraction must be in (0, 1)")
        if self.take_profit_fraction <= 0:
            raise ValueError("take profit fraction must be positive")
        if self.max_holding_sessions < 1 or self.regime_lookback < 2:
            raise ValueError("holding sessions and regime lookback are invalid")
        if self.bear_threshold >= self.bull_threshold:
            raise ValueError("bear threshold must be below bull threshold")


@dataclass(frozen=True, slots=True)
class BacktestEvent:
    trading_date: date
    event_type: str
    symbol: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class EquityPoint:
    trading_date: date
    equity: float
    cash: float
    exposure: float
    regime: MarketRegime
    benchmark_closes: dict[str, float]
    risk_status: RiskStatus


@dataclass(frozen=True, slots=True)
class CompletedTrade:
    symbol: str
    signal_date: date
    entry_date: date
    exit_date: date
    quantity: int
    entry_price: float
    exit_price: float
    net_profit: float
    return_fraction: float
    entry_reason: str
    exit_reason: str
    signal_regime: MarketRegime


@dataclass(frozen=True, slots=True)
class BacktestResult:
    config: BacktestConfig
    start_date: date
    end_date: date
    initial_equity: float
    final_equity: float
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[CompletedTrade, ...]
    events: tuple[BacktestEvent, ...]
    tracker: DailyTracker


@dataclass(slots=True)
class _PendingSignal:
    selection: Selection
    execute_on: date
    signal_close: float
    stop_price: float
    take_profit_price: float
    regime: MarketRegime


@dataclass(slots=True)
class _OpenTrade:
    pending: _PendingSignal
    entry: Trade
    entry_session_index: int


class EventDrivenBacktester:
    """Daily event engine with close-to-next-session signal causality."""

    def __init__(
        self,
        data: InMemoryHistoricalData,
        config: BacktestConfig | None = None,
        *,
        selector_config: SelectionConfig | None = None,
        risk_config: RiskConfig | None = None,
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self.data = data
        self.config = config or BacktestConfig()
        self.selector_config = selector_config
        self.risk_config = risk_config
        self.execution_config = execution_config

    def run(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> BacktestResult:
        dates = tuple(
            item
            for item in self.data.trading_dates
            if (start_date is None or item >= start_date)
            and (end_date is None or item <= end_date)
        )
        if len(dates) < 2:
            raise ValueError("a backtest needs at least two trading sessions")

        portal = self.data.portal()
        account = PaperAccount(self.config.initial_cash)
        risk = RiskManager(self.config.initial_cash, dates[0], self.risk_config)
        broker = PaperBroker(
            account,
            config=self.execution_config,
            risk_manager=risk,
        )
        selector = StockSelector(portal, self.selector_config)
        tracker = DailyTracker()
        pending_signals: list[_PendingSignal] = []
        open_trades: dict[str, _OpenTrade] = {}
        completed: list[CompletedTrade] = []
        events: list[BacktestEvent] = []
        equity_curve: list[EquityPoint] = []

        for index, trading_date in enumerate(dates):
            portal.advance_to(trading_date)
            bars = {bar.symbol: bar for bar in portal.bars_on(trading_date)}
            opening_prices = {symbol: bar.open for symbol, bar in bars.items()}
            opening_equity = account.equity(opening_prices)
            risk.start_day(trading_date, opening_equity)

            self._execute_pending_entries(
                trading_date=trading_date,
                session_index=index,
                pending_signals=pending_signals,
                open_trades=open_trades,
                bars=bars,
                account=account,
                risk=risk,
                broker=broker,
                tracker=tracker,
                events=events,
                opening_prices=opening_prices,
            )
            self._update_tracks(tracker, trading_date, bars)
            self._execute_exits(
                trading_date=trading_date,
                session_index=index,
                open_trades=open_trades,
                bars=bars,
                broker=broker,
                completed=completed,
                events=events,
            )

            closing_prices = {symbol: bar.close for symbol, bar in bars.items()}
            equity = account.equity(closing_prices)
            exposure = account.exposure(closing_prices)
            regime = self._market_regime(portal, trading_date)
            status = risk.status(trading_date, equity, exposure)
            benchmark_closes = {
                name: value
                for name in self.data.benchmark_names
                if (value := portal.benchmark_close(name, trading_date)) is not None
            }
            equity_curve.append(
                EquityPoint(
                    trading_date,
                    equity,
                    account.cash,
                    exposure,
                    regime,
                    benchmark_closes,
                    status,
                )
            )

            self._generate_close_signal(
                trading_date=trading_date,
                next_date=dates[index + 1] if index + 1 < len(dates) else None,
                selector=selector,
                portal=portal,
                tracker=tracker,
                regime=regime,
                pending_signals=pending_signals,
                events=events,
            )

        return BacktestResult(
            config=self.config,
            start_date=dates[0],
            end_date=dates[-1],
            initial_equity=self.config.initial_cash,
            final_equity=equity_curve[-1].equity,
            equity_curve=tuple(equity_curve),
            trades=tuple(completed),
            events=tuple(events),
            tracker=tracker,
        )

    def _execute_pending_entries(
        self,
        *,
        trading_date: date,
        session_index: int,
        pending_signals: list[_PendingSignal],
        open_trades: dict[str, _OpenTrade],
        bars: dict[str, HistoricalBar],
        account: PaperAccount,
        risk: RiskManager,
        broker: PaperBroker,
        tracker: DailyTracker,
        events: list[BacktestEvent],
        opening_prices: dict[str, float],
    ) -> None:
        due = [item for item in pending_signals if item.execute_on == trading_date]
        pending_signals[:] = [
            item for item in pending_signals if item.execute_on != trading_date
        ]
        for item in due:
            symbol = item.selection.symbol
            bar = bars.get(symbol)
            if bar is None or not bar.tradable:
                events.append(
                    BacktestEvent(trading_date, "ENTRY_REJECTED", symbol, "not_tradable")
                )
                continue
            if symbol in open_trades:
                events.append(
                    BacktestEvent(
                        trading_date, "ENTRY_REJECTED", symbol, "existing_position"
                    )
                )
                continue
            market_price = (
                bar.open
                if self.config.execution_mode is ExecutionMode.OPEN
                else bar.vwap
            )
            if market_price is None:
                events.append(
                    BacktestEvent(trading_date, "ENTRY_REJECTED", symbol, "missing_vwap")
                )
                continue
            sizing_reference = (
                market_price
                if self.config.execution_mode is ExecutionMode.OPEN
                else item.signal_close
            )
            if sizing_reference <= item.stop_price:
                events.append(
                    BacktestEvent(
                        trading_date, "ENTRY_REJECTED", symbol, "entry_below_stop"
                    )
                )
                continue
            equity = account.equity(opening_prices)
            exposure = account.exposure(opening_prices)
            sizing = risk.calculate_position(
                trading_date=trading_date,
                equity=equity,
                cash=account.cash,
                current_exposure=exposure,
                current_symbol_exposure=account.position(
                    symbol, opening_prices.get(symbol, market_price)
                ).market_value,
                entry_price=sizing_reference,
                stop_price=item.stop_price,
            )
            if sizing.quantity == 0:
                reason = ",".join(sizing.limited_by) or "zero_position"
                events.append(
                    BacktestEvent(trading_date, "ENTRY_REJECTED", symbol, reason)
                )
                continue
            try:
                trade = broker.buy(
                    trading_date=trading_date,
                    symbol=symbol,
                    quantity=sizing.quantity,
                    market_price=market_price,
                    limit_up_locked=bar.limit_up_locked,
                )
            except OrderRejected as error:
                events.append(
                    BacktestEvent(trading_date, "ENTRY_REJECTED", symbol, str(error))
                )
                continue
            tracker.record_fill(item.selection.trading_date, trade)
            open_trades[symbol] = _OpenTrade(item, trade, session_index)
            events.append(
                BacktestEvent(
                    trading_date,
                    "ENTRY_FILLED",
                    symbol,
                    f"T+1 {self.config.execution_mode.value.lower()} execution",
                )
            )

    def _execute_exits(
        self,
        *,
        trading_date: date,
        session_index: int,
        open_trades: dict[str, _OpenTrade],
        bars: dict[str, HistoricalBar],
        broker: PaperBroker,
        completed: list[CompletedTrade],
        events: list[BacktestEvent],
    ) -> None:
        for symbol, position in tuple(open_trades.items()):
            if position.entry.trading_date >= trading_date:
                continue
            bar = bars.get(symbol)
            if bar is None or not bar.tradable:
                continue
            exit_reason: str | None = None
            exit_market_price: float | None = None
            if bar.low <= position.pending.stop_price:
                exit_reason = "stop_loss"
                exit_market_price = min(bar.open, position.pending.stop_price)
            elif bar.high >= position.pending.take_profit_price:
                exit_reason = "take_profit"
                exit_market_price = max(bar.open, position.pending.take_profit_price)
            elif (
                session_index - position.entry_session_index
                >= self.config.max_holding_sessions
            ):
                exit_reason = "max_holding_period"
                exit_market_price = bar.close
            if exit_reason is None or exit_market_price is None:
                continue
            try:
                exit_trade = broker.sell(
                    trading_date=trading_date,
                    symbol=symbol,
                    quantity=position.entry.quantity,
                    market_price=exit_market_price,
                    limit_down_locked=bar.limit_down_locked,
                )
            except OrderRejected as error:
                events.append(
                    BacktestEvent(trading_date, "EXIT_REJECTED", symbol, str(error))
                )
                continue
            entry_cost = -position.entry.cash_change
            net_profit = exit_trade.realized_profit or 0.0
            completed.append(
                CompletedTrade(
                    symbol=symbol,
                    signal_date=position.pending.selection.trading_date,
                    entry_date=position.entry.trading_date,
                    exit_date=trading_date,
                    quantity=position.entry.quantity,
                    entry_price=position.entry.execution_price,
                    exit_price=exit_trade.execution_price,
                    net_profit=net_profit,
                    return_fraction=net_profit / entry_cost,
                    entry_reason=(
                        f"daily winner score={position.pending.selection.score:.6f}"
                    ),
                    exit_reason=exit_reason,
                    signal_regime=position.pending.regime,
                )
            )
            del open_trades[symbol]
            events.append(
                BacktestEvent(trading_date, "EXIT_FILLED", symbol, exit_reason)
            )

    def _generate_close_signal(
        self,
        *,
        trading_date: date,
        next_date: date | None,
        selector: StockSelector,
        portal: object,
        tracker: DailyTracker,
        regime: MarketRegime,
        pending_signals: list[_PendingSignal],
        events: list[BacktestEvent],
    ) -> None:
        try:
            selection = selector.select_one(trading_date)
        except NoEligibleStockError:
            events.append(
                BacktestEvent(trading_date, "NO_SIGNAL", None, "no_eligible_stock")
            )
            return
        bar = portal.bar(selection.symbol, trading_date)
        if bar is None:
            raise RuntimeError("selected symbol has no current historical bar")
        stop_price = bar.close * (1 - self.config.stop_loss_fraction)
        take_profit_price = bar.close * (1 + self.config.take_profit_fraction)
        tracker.record_signal(
            selection,
            planned_entry_price=bar.close,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        events.append(
            BacktestEvent(
                trading_date,
                "SIGNAL",
                selection.symbol,
                "generated after close from current-and-prior data",
            )
        )
        if next_date is not None:
            pending_signals.append(
                _PendingSignal(
                    selection,
                    next_date,
                    bar.close,
                    stop_price,
                    take_profit_price,
                    regime,
                )
            )
        else:
            events.append(
                BacktestEvent(
                    trading_date,
                    "ENTRY_CANCELLED",
                    selection.symbol,
                    "no_next_session_in_test_window",
                )
            )

    def _update_tracks(
        self,
        tracker: DailyTracker,
        trading_date: date,
        bars: dict[str, HistoricalBar],
    ) -> None:
        for track in tracker.all():
            if track.signal.trading_date >= trading_date:
                continue
            bar = bars.get(track.signal.symbol)
            if bar is None:
                continue
            tracker.update_market(
                track.signal.trading_date,
                trading_date=trading_date,
                close=bar.close,
                high=bar.high,
                low=bar.low,
            )

    def _market_regime(self, portal: object, trading_date: date) -> MarketRegime:
        values = portal.benchmark_history(
            self.config.regime_benchmark,
            trading_date,
            self.config.regime_lookback,
        )
        if len(values) < self.config.regime_lookback:
            return MarketRegime.SIDEWAYS
        trailing_return = values[-1] / values[0] - 1.0
        if trailing_return >= self.config.bull_threshold:
            return MarketRegime.BULL
        if trailing_return <= self.config.bear_threshold:
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS
