from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from .analytics import BacktestAnalysis, analyze_backtest
from .backtest import BacktestResult


class BacktestReportWriter:
    """Writes a complete, dependency-free backtest report directory."""

    def write(
        self,
        result: BacktestResult,
        output_directory: str | Path,
        analysis: BacktestAnalysis | None = None,
    ) -> Path:
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        analysis = analysis or analyze_backtest(result)
        self._write_summary(output / "summary.json", result, analysis)
        self._write_equity(output / "equity_curve.csv", result)
        self._write_trades(output / "trades.csv", result)
        self._write_events(output / "events.csv", result)
        self._write_monthly(output / "monthly_returns.csv", analysis)
        self._write_svg(output / "equity_curve.svg", result)
        return output

    def _write_summary(
        self, path: Path, result: BacktestResult, analysis: BacktestAnalysis
    ) -> None:
        payload = {
            "period": {
                "start": result.start_date,
                "end": result.end_date,
            },
            "initial_equity": result.initial_equity,
            "final_equity": result.final_equity,
            "performance": analysis.summary,
            "benchmarks": analysis.benchmarks,
            "market_regimes": analysis.regimes,
            "maximum_profit_trade": analysis.maximum_profit_trade,
            "maximum_loss_trade": analysis.maximum_loss_trade,
        }
        path.write_text(
            json.dumps(_jsonable(payload), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_equity(self, path: Path, result: BacktestResult) -> None:
        benchmark_names = sorted(
            {
                name
                for point in result.equity_curve
                for name in point.benchmark_closes
            }
        )
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "date",
                    "equity",
                    "cash",
                    "exposure",
                    "regime",
                    *benchmark_names,
                ]
            )
            for point in result.equity_curve:
                writer.writerow(
                    [
                        point.trading_date.isoformat(),
                        point.equity,
                        point.cash,
                        point.exposure,
                        point.regime.value,
                        *[
                            point.benchmark_closes.get(name, "")
                            for name in benchmark_names
                        ],
                    ]
                )

    def _write_trades(self, path: Path, result: BacktestResult) -> None:
        fields = [
            "symbol",
            "signal_date",
            "entry_date",
            "exit_date",
            "quantity",
            "entry_price",
            "exit_price",
            "net_profit",
            "return_fraction",
            "entry_reason",
            "exit_reason",
            "signal_regime",
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for trade in result.trades:
                row = asdict(trade)
                row["signal_date"] = trade.signal_date.isoformat()
                row["entry_date"] = trade.entry_date.isoformat()
                row["exit_date"] = trade.exit_date.isoformat()
                row["signal_regime"] = trade.signal_regime.value
                writer.writerow(row)

    def _write_events(self, path: Path, result: BacktestResult) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["date", "event_type", "symbol", "reason"])
            for event in result.events:
                writer.writerow(
                    [
                        event.trading_date.isoformat(),
                        event.event_type,
                        event.symbol or "",
                        event.reason,
                    ]
                )

    def _write_monthly(self, path: Path, analysis: BacktestAnalysis) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["month", "return"])
            writer.writerows(analysis.monthly_returns.items())

    def _write_svg(self, path: Path, result: BacktestResult) -> None:
        width, height, padding = 960, 420, 50
        values = [point.equity for point in result.equity_curve]
        minimum, maximum = min(values), max(values)
        spread = maximum - minimum or 1.0
        count = max(1, len(values) - 1)
        coordinates = [
            (
                padding + index * (width - 2 * padding) / count,
                height
                - padding
                - (value - minimum) * (height - 2 * padding) / spread,
            )
            for index, value in enumerate(values)
        ]
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <line x1="{padding}" y1="{height-padding}" x2="{width-padding}" y2="{height-padding}" stroke="#94a3b8"/>
  <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height-padding}" stroke="#94a3b8"/>
  <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2.5"/>
  <text x="{padding}" y="28" font-family="sans-serif" font-size="18" fill="#0f172a">Equity Curve</text>
  <text x="{padding}" y="{height-14}" font-family="sans-serif" font-size="12" fill="#475569">{result.start_date.isoformat()}</text>
  <text x="{width-padding-70}" y="{height-14}" font-family="sans-serif" font-size="12" fill="#475569">{result.end_date.isoformat()}</text>
  <text x="{padding+5}" y="{padding+15}" font-family="sans-serif" font-size="12" fill="#475569">{maximum:.2f}</text>
  <text x="{padding+5}" y="{height-padding-8}" font-family="sans-serif" font-size="12" fill="#475569">{minimum:.2f}</text>
</svg>
"""
        path.write_text(svg, encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {
            (key.value if isinstance(key, Enum) else str(key)): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
