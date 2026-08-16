from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .analytics import (
    TestPeriod,
    WalkForwardSplit,
    WalkForwardValidator,
    analyze_backtest,
)
from .backtest import BacktestConfig, EventDrivenBacktester
from .historical import BenchmarkPoint, HistoricalBar, InMemoryHistoricalData
from .reporting import BacktestReportWriter


def build_demo_data() -> InMemoryHistoricalData:
    """Deterministic synthetic data for plumbing checks, never real evidence."""

    dates: list[date] = []
    current = date(2025, 1, 2)
    while len(dates) < 75:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    prices = {"AAA": 10.0, "BBB": 20.0, "CCC": 30.0}
    benchmark_prices = {"CSI300": 4_000.0, "CSI1000": 6_000.0}
    bars: list[HistoricalBar] = []
    benchmarks: list[BenchmarkPoint] = []
    for index, trading_date in enumerate(dates):
        phase = index // 25
        stock_returns = _demo_stock_returns(index, phase)
        for symbol, daily_return in stock_returns.items():
            previous = prices[symbol]
            overnight = 0.002 if index % 3 == 0 else -0.001
            open_price = previous * (1 + overnight)
            close = previous * (1 + daily_return)
            high = max(open_price, close) * 1.018
            low = min(open_price, close) * 0.982
            vwap = (open_price + close) / 2
            bars.append(
                HistoricalBar(
                    trading_date,
                    symbol,
                    open_price,
                    high,
                    low,
                    close,
                    800_000 + index * 10_000 + ord(symbol[-1]) * 1_000,
                    vwap,
                )
            )
            prices[symbol] = close

        benchmark_returns = (
            (0.006, 0.008)
            if phase == 0
            else ((-0.006, -0.008) if phase == 1 else (0.002, -0.002))
        )
        if phase == 2 and index % 2:
            benchmark_returns = tuple(-item for item in benchmark_returns)
        for name, daily_return in zip(
            ("CSI300", "CSI1000"), benchmark_returns, strict=True
        ):
            benchmark_prices[name] *= 1 + daily_return
            benchmarks.append(
                BenchmarkPoint(trading_date, name, benchmark_prices[name])
            )
    return InMemoryHistoricalData(bars, benchmarks)


def _demo_stock_returns(index: int, phase: int) -> dict[str, float]:
    if phase == 0:
        return {
            "AAA": 0.018 if index % 4 else -0.006,
            "BBB": 0.011,
            "CCC": 0.006 if index % 3 else 0.020,
        }
    if phase == 1:
        return {
            "AAA": -0.018,
            "BBB": -0.010 if index % 3 else 0.006,
            "CCC": -0.014 if index % 2 else 0.004,
        }
    direction = 1 if index % 2 == 0 else -1
    return {
        "AAA": 0.009 * direction,
        "BBB": -0.007 * direction,
        "CCC": 0.004 if index % 3 else -0.006,
    }


def run_demo(output_directory: str | Path = "outputs/phase3_demo") -> None:
    data = build_demo_data()
    config = BacktestConfig(
        stop_loss_fraction=0.04,
        take_profit_fraction=0.06,
        max_holding_sessions=4,
        regime_lookback=5,
        bull_threshold=0.015,
        bear_threshold=-0.015,
    )
    engine = EventDrivenBacktester(data, config)
    result = engine.run()
    analysis = analyze_backtest(result)
    output = Path(output_directory)
    writer = BacktestReportWriter()
    writer.write(result, output / "full", analysis)

    dates = data.trading_dates
    split = WalkForwardSplit(
        training=TestPeriod("training", dates[0], dates[24]),
        validation=TestPeriod("validation", dates[25], dates[49]),
        out_of_sample=TestPeriod("out_of_sample", dates[50], dates[74]),
    )
    walk_forward = WalkForwardValidator(data, config).run(split)
    for period_result in (
        walk_forward.training,
        walk_forward.validation,
        walk_forward.out_of_sample,
    ):
        writer.write(
            period_result.result,
            output / period_result.period.name,
            period_result.analysis,
        )

    summary = analysis.summary
    print("SYNTHETIC DEMO ONLY - not a historical market conclusion")
    print(f"period={result.start_date}..{result.end_date}")
    print(
        f"trades={summary.total_trades} win_rate={summary.win_rate:.2%} "
        f"total_return={summary.total_return:.2%} "
        f"annualized={summary.annualized_return:.2%} "
        f"max_drawdown={summary.maximum_drawdown:.2%}"
    )
    print(f"report={output.resolve()}")


def main() -> None:
    run_demo()


if __name__ == "__main__":
    main()
