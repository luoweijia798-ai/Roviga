from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from .backtest import (
    BacktestConfig,
    BacktestResult,
    CompletedTrade,
    EventDrivenBacktester,
    MarketRegime,
)
from .historical import InMemoryHistoricalData
from .risk import RiskConfig
from .selector import SelectionConfig
from .trading import ExecutionConfig


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_loss_ratio: float | None
    average_profit: float
    average_loss: float
    maximum_consecutive_losses: int
    maximum_drawdown: float
    total_return: float
    annualized_return: float


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    name: str
    total_return: float
    annualized_return: float
    excess_total_return: float


@dataclass(frozen=True, slots=True)
class RegimeStatistics:
    regime: MarketRegime
    total_trades: int
    win_rate: float
    average_return: float
    net_profit: float


@dataclass(frozen=True, slots=True)
class BacktestAnalysis:
    summary: PerformanceSummary
    monthly_returns: dict[str, float]
    benchmarks: dict[str, BenchmarkComparison]
    regimes: dict[MarketRegime, RegimeStatistics]
    maximum_profit_trade: CompletedTrade | None
    maximum_loss_trade: CompletedTrade | None


def analyze_backtest(result: BacktestResult) -> BacktestAnalysis:
    trades = result.trades
    winners = [trade for trade in trades if trade.net_profit > 0]
    losers = [trade for trade in trades if trade.net_profit < 0]
    average_profit = _mean([trade.net_profit for trade in winners])
    average_loss = _mean([trade.net_profit for trade in losers])
    profit_loss_ratio = (
        average_profit / abs(average_loss)
        if winners and losers and average_loss != 0
        else None
    )
    values = [result.initial_equity, *[point.equity for point in result.equity_curve]]
    total_return = result.final_equity / result.initial_equity - 1.0
    sessions = max(1, len(result.equity_curve) - 1)
    annualized = (1.0 + total_return) ** (252 / sessions) - 1.0
    summary = PerformanceSummary(
        total_trades=len(trades),
        winning_trades=len(winners),
        losing_trades=len(losers),
        win_rate=len(winners) / len(trades) if trades else 0.0,
        profit_loss_ratio=profit_loss_ratio,
        average_profit=average_profit,
        average_loss=average_loss,
        maximum_consecutive_losses=_maximum_loss_streak(trades),
        maximum_drawdown=_maximum_drawdown(values),
        total_return=total_return,
        annualized_return=annualized,
    )
    monthly = _monthly_returns(result)
    benchmarks = _benchmark_comparisons(result, total_return)
    regimes = {
        regime: _regime_statistics(regime, trades) for regime in MarketRegime
    }
    return BacktestAnalysis(
        summary=summary,
        monthly_returns=monthly,
        benchmarks=benchmarks,
        regimes=regimes,
        maximum_profit_trade=max(trades, key=lambda item: item.net_profit, default=None),
        maximum_loss_trade=min(trades, key=lambda item: item.net_profit, default=None),
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _maximum_loss_streak(trades: tuple[CompletedTrade, ...]) -> int:
    maximum = 0
    current = 0
    for trade in sorted(trades, key=lambda item: (item.exit_date, item.symbol)):
        if trade.net_profit < 0:
            current += 1
            maximum = max(maximum, current)
        elif trade.net_profit > 0:
            current = 0
    return maximum


def _maximum_drawdown(values: list[float]) -> float:
    peak = values[0]
    maximum = 0.0
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, (peak - value) / peak)
    return maximum


def _monthly_returns(result: BacktestResult) -> dict[str, float]:
    month_ends: dict[str, float] = {}
    for point in result.equity_curve:
        month_ends[point.trading_date.strftime("%Y-%m")] = point.equity
    previous = result.initial_equity
    returns: dict[str, float] = {}
    for month, equity in month_ends.items():
        returns[month] = equity / previous - 1.0
        previous = equity
    return returns


def _benchmark_comparisons(
    result: BacktestResult, strategy_total_return: float
) -> dict[str, BenchmarkComparison]:
    by_name: dict[str, list[float]] = {}
    for point in result.equity_curve:
        for name, close in point.benchmark_closes.items():
            by_name.setdefault(name, []).append(close)
    sessions = max(1, len(result.equity_curve) - 1)
    comparisons: dict[str, BenchmarkComparison] = {}
    for name, closes in by_name.items():
        if len(closes) < 2:
            continue
        total_return = closes[-1] / closes[0] - 1.0
        annualized = (1.0 + total_return) ** (252 / sessions) - 1.0
        comparisons[name] = BenchmarkComparison(
            name,
            total_return,
            annualized,
            strategy_total_return - total_return,
        )
    return comparisons


def _regime_statistics(
    regime: MarketRegime, trades: tuple[CompletedTrade, ...]
) -> RegimeStatistics:
    selected = [trade for trade in trades if trade.signal_regime is regime]
    wins = [trade for trade in selected if trade.net_profit > 0]
    return RegimeStatistics(
        regime=regime,
        total_trades=len(selected),
        win_rate=len(wins) / len(selected) if selected else 0.0,
        average_return=_mean([trade.return_fraction for trade in selected]),
        net_profit=sum(trade.net_profit for trade in selected),
    )


@dataclass(frozen=True, slots=True)
class TestPeriod:
    name: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("period start must not exceed end")


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    training: TestPeriod
    validation: TestPeriod
    out_of_sample: TestPeriod

    def __post_init__(self) -> None:
        if not (
            self.training.end_date < self.validation.start_date
            and self.validation.end_date < self.out_of_sample.start_date
        ):
            raise ValueError("training, validation, and out-of-sample must not overlap")


@dataclass(frozen=True, slots=True)
class PeriodResult:
    period: TestPeriod
    result: BacktestResult
    analysis: BacktestAnalysis


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    training: PeriodResult
    validation: PeriodResult
    out_of_sample: PeriodResult


class WalkForwardValidator:
    """Runs frozen strategy/risk settings independently on three date windows."""

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
        self.config = config
        self.selector_config = selector_config
        self.risk_config = risk_config
        self.execution_config = execution_config

    def run(self, split: WalkForwardSplit) -> WalkForwardResult:
        periods = (split.training, split.validation, split.out_of_sample)
        results = [self._run_period(period) for period in periods]
        return WalkForwardResult(*results)

    def _run_period(self, period: TestPeriod) -> PeriodResult:
        engine = EventDrivenBacktester(
            self.data,
            self.config,
            selector_config=self.selector_config,
            risk_config=self.risk_config,
            execution_config=self.execution_config,
        )
        result = engine.run(period.start_date, period.end_date)
        return PeriodResult(period, result, analyze_backtest(result))
