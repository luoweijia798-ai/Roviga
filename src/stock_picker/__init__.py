"""Public API for the phase-one daily stock picker."""

from .analytics import (
    BacktestAnalysis,
    BenchmarkComparison,
    PerformanceSummary,
    PeriodResult,
    RegimeStatistics,
    TestPeriod,
    WalkForwardResult,
    WalkForwardSplit,
    WalkForwardValidator,
    analyze_backtest,
)
from .backtest import (
    BacktestConfig,
    BacktestEvent,
    BacktestResult,
    CompletedTrade,
    EquityPoint,
    EventDrivenBacktester,
    ExecutionMode,
    MarketRegime,
)
from .data import InMemoryMarketData, MarketDataSource
from .historical import (
    BenchmarkPoint,
    FutureDataError,
    HistoricalBar,
    HistoricalDataPortal,
    InMemoryHistoricalData,
)
from .models import DailyBar, Selection
from .reporting import BacktestReportWriter
from .risk import PositionSizing, RiskConfig, RiskManager, RiskStatus
from .selector import NoEligibleStockError, SelectionConfig, StockSelector
from .tracking import CandidateTrack, DailyTracker, TrackingState
from .trading import (
    ExecutionConfig,
    InMemoryTradeLedger,
    JsonLinesTradeLedger,
    OrderRejected,
    PaperAccount,
    PaperBroker,
    Position,
    Side,
    Trade,
    TradeLedger,
)
from .workflow import CandidateExecution, PaperTradingWorkflow

__all__ = [
    "DailyBar",
    "BacktestAnalysis",
    "BacktestConfig",
    "BacktestEvent",
    "BacktestReportWriter",
    "BacktestResult",
    "BenchmarkComparison",
    "BenchmarkPoint",
    "CompletedTrade",
    "DailyTracker",
    "CandidateTrack",
    "CandidateExecution",
    "ExecutionConfig",
    "ExecutionMode",
    "EquityPoint",
    "EventDrivenBacktester",
    "FutureDataError",
    "HistoricalBar",
    "HistoricalDataPortal",
    "InMemoryMarketData",
    "InMemoryTradeLedger",
    "InMemoryHistoricalData",
    "JsonLinesTradeLedger",
    "MarketDataSource",
    "MarketRegime",
    "NoEligibleStockError",
    "OrderRejected",
    "PaperAccount",
    "PaperBroker",
    "PaperTradingWorkflow",
    "PerformanceSummary",
    "PeriodResult",
    "Position",
    "PositionSizing",
    "RiskConfig",
    "RiskManager",
    "RiskStatus",
    "RegimeStatistics",
    "Selection",
    "SelectionConfig",
    "Side",
    "StockSelector",
    "TrackingState",
    "TestPeriod",
    "Trade",
    "TradeLedger",
    "WalkForwardResult",
    "WalkForwardSplit",
    "WalkForwardValidator",
    "analyze_backtest",
]
