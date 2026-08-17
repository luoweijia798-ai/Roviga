from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .real_market import PHASE4_START, SQLiteMarketCache


REQUIRED_BENCHMARKS = ("CSI300", "CSI1000")


@dataclass(frozen=True, slots=True)
class DataAuditResult:
    passed: bool
    payload: dict[str, Any]


class RealMarketDataAuditor:
    """Audits only persisted provider data; it never fabricates missing rows."""

    def __init__(self, cache: SQLiteMarketCache) -> None:
        self.cache = cache

    def run(
        self,
        *,
        start_date: date = PHASE4_START,
        end_date: date | None = None,
        output: str | Path | None = None,
    ) -> DataAuditResult:
        end_date = end_date or date.today()
        manifest = self.cache.load_manifest()
        statuses = self.cache.sync_statuses()
        with self.cache.connect() as connection:
            stock_rows = connection.execute(
                "SELECT * FROM stocks ORDER BY symbol"
            ).fetchall()
            benchmark_rows = connection.execute(
                """
                SELECT name, MIN(trading_date) AS first_date,
                       MAX(trading_date) AS last_date, COUNT(*) AS row_count
                FROM benchmarks GROUP BY name ORDER BY name
                """
            ).fetchall()
            reference_rows = connection.execute(
                """
                SELECT trading_date FROM benchmarks WHERE name='CSI300'
                  AND trading_date BETWEEN ? AND ? ORDER BY trading_date
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            bar_coverage = connection.execute(
                """
                SELECT symbol, MIN(trading_date) AS first_date,
                       MAX(trading_date) AS last_date, COUNT(*) AS row_count
                FROM bars GROUP BY symbol ORDER BY symbol
                """
            ).fetchall()
            anomaly_rows = connection.execute(
                """
                SELECT trading_date, symbol,
                    CASE
                      WHEN open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                        THEN 'non_positive_price'
                      WHEN high < MAX(open, close) OR low > MIN(open, close)
                        OR high < low THEN 'invalid_ohlc'
                      WHEN volume < 0 OR amount < 0 THEN 'negative_volume_or_amount'
                      WHEN tradable = 1 AND volume = 0
                        THEN 'tradable_with_zero_volume'
                      WHEN volume > 0 AND amount = 0
                        THEN 'volume_without_amount'
                      WHEN amount > 0 AND volume > 0 AND vwap IS NULL
                        THEN 'missing_vwap_with_turnover'
                      WHEN up_limit IS NOT NULL AND down_limit IS NOT NULL
                        AND up_limit <= down_limit THEN 'invalid_limit_order'
                      WHEN up_limit IS NOT NULL AND close > up_limit + 0.005
                        THEN 'close_above_limit'
                      WHEN down_limit IS NOT NULL AND close < down_limit - 0.005
                        THEN 'close_below_limit'
                      WHEN limit_up_locked = 1 AND (
                        up_limit IS NULL OR ABS(open - up_limit) >= 0.005
                        OR ABS(high - up_limit) >= 0.005
                        OR ABS(low - up_limit) >= 0.005
                        OR ABS(close - up_limit) >= 0.005
                      ) THEN 'invalid_up_limit_lock'
                      WHEN limit_down_locked = 1 AND (
                        down_limit IS NULL OR ABS(open - down_limit) >= 0.005
                        OR ABS(high - down_limit) >= 0.005
                        OR ABS(low - down_limit) >= 0.005
                        OR ABS(close - down_limit) >= 0.005
                      ) THEN 'invalid_down_limit_lock'
                      WHEN signal_open <= 0 OR signal_high <= 0
                        OR signal_low <= 0 OR signal_close <= 0
                        THEN 'invalid_signal_price'
                    END AS reason
                FROM bars
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR high < MAX(open, close) OR low > MIN(open, close)
                   OR high < low OR volume < 0 OR amount < 0
                   OR (tradable = 1 AND volume = 0)
                   OR (volume > 0 AND amount = 0)
                   OR (amount > 0 AND volume > 0 AND vwap IS NULL)
                   OR (up_limit IS NOT NULL AND down_limit IS NOT NULL
                       AND up_limit <= down_limit)
                   OR (up_limit IS NOT NULL AND close > up_limit + 0.005)
                   OR (down_limit IS NOT NULL AND close < down_limit - 0.005)
                   OR (limit_up_locked = 1 AND (
                       up_limit IS NULL OR ABS(open - up_limit) >= 0.005
                       OR ABS(high - up_limit) >= 0.005
                       OR ABS(low - up_limit) >= 0.005
                       OR ABS(close - up_limit) >= 0.005))
                   OR (limit_down_locked = 1 AND (
                       down_limit IS NULL OR ABS(open - down_limit) >= 0.005
                       OR ABS(high - down_limit) >= 0.005
                       OR ABS(low - down_limit) >= 0.005
                       OR ABS(close - down_limit) >= 0.005))
                   OR signal_open <= 0 OR signal_high <= 0
                   OR signal_low <= 0 OR signal_close <= 0
                ORDER BY trading_date, symbol
                """
            ).fetchall()
            duplicate_rows = connection.execute(
                """
                SELECT trading_date, symbol, COUNT(*) AS row_count
                FROM bars GROUP BY trading_date, symbol HAVING COUNT(*) > 1
                ORDER BY trading_date, symbol
                """
            ).fetchall()

        reference_dates = tuple(row["trading_date"] for row in reference_rows)
        bars_by_symbol = {row["symbol"]: row for row in bar_coverage}
        delisted_symbols = {
            row["symbol"] for row in stock_rows if row["delist_date"]
        }
        bse_symbols = {
            row["symbol"] for row in stock_rows if row["exchange"] == "BSE"
        }
        missing_by_symbol: list[dict[str, Any]] = []
        for stock in stock_rows:
            active_start = max(start_date, _optional_iso_date(stock["list_date"]) or start_date)
            active_end = min(end_date, _optional_iso_date(stock["delist_date"]) or end_date)
            if active_start > active_end:
                continue
            with self.cache.connect() as connection:
                present = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT trading_date FROM bars WHERE symbol=?
                          AND trading_date BETWEEN ? AND ?
                        """,
                        (stock["symbol"], active_start.isoformat(), active_end.isoformat()),
                    )
                }
            expected = [
                value for value in reference_dates
                if active_start.isoformat() <= value <= active_end.isoformat()
            ]
            missing = [value for value in expected if value not in present]
            coverage = bars_by_symbol.get(stock["symbol"])
            missing_by_symbol.append(
                {
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "exchange": stock["exchange"],
                    "first_bar": coverage["first_date"] if coverage else None,
                    "last_bar": coverage["last_date"] if coverage else None,
                    "bar_count": int(coverage["row_count"]) if coverage else 0,
                    "expected_sessions": len(expected),
                    "missing_count": len(missing),
                    "missing_trading_date_ranges": _missing_ranges(
                        expected, set(missing)
                    ),
                }
            )

        benchmark_coverage = {
            row["name"]: {
                "first_date": row["first_date"],
                "last_date": row["last_date"],
                "row_count": int(row["row_count"]),
            }
            for row in benchmark_rows
        }
        state_counts = Counter(item.status for item in statuses)
        source_counts = Counter(item.source or "unknown" for item in statuses)
        failures = [
            {
                "symbol": item.symbol,
                "status": item.status,
                "synced_through": item.synced_through.isoformat()
                if item.synced_through else None,
                "source": item.source,
                "last_error": item.last_error,
            }
            for item in statuses
            if item.status != "complete"
        ]
        anomaly_details = [dict(row) for row in anomaly_rows]
        duplicate_details = [dict(row) for row in duplicate_rows]
        missing_stocks = [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "exchange": item["exchange"],
                "expected_sessions": item["expected_sessions"],
            }
            for item in missing_by_symbol
            if item["bar_count"] == 0
        ]
        blockers: list[str] = []
        if manifest is None:
            blockers.append("missing completed sync manifest")
        elif manifest.start_date > start_date or manifest.end_date < end_date:
            blockers.append("manifest does not cover the requested date range")
        if not statuses:
            blockers.append("missing per-symbol sync status")
        if failures:
            blockers.append(f"{len(failures)} symbols are not completely synchronized")
        for name in REQUIRED_BENCHMARKS:
            coverage = benchmark_coverage.get(name)
            if coverage is None:
                blockers.append(f"missing benchmark {name}")
            elif (
                coverage["first_date"] > start_date.isoformat()
                or coverage["last_date"]
                < (end_date - timedelta(days=7)).isoformat()
            ):
                blockers.append(f"benchmark {name} does not cover requested dates")
        if anomaly_details:
            blockers.append(f"{len(anomaly_details)} invalid OHLCV rows")
        if duplicate_details:
            blockers.append(f"{len(duplicate_details)} duplicate daily bars")

        audit_checks = {
            "sync_manifest_covers_requested_range": manifest is not None
            and manifest.start_date <= start_date
            and manifest.end_date >= end_date,
            "all_symbols_have_complete_status": bool(statuses) and not failures,
            "all_inventory_symbols_have_bars": not missing_stocks,
            "delisted_stocks_have_data": not delisted_symbols
            or all(symbol in bars_by_symbol for symbol in delisted_symbols),
            "bse_stocks_have_data": not bse_symbols
            or all(symbol in bars_by_symbol for symbol in bse_symbols),
            "required_benchmarks_present": all(
                name in benchmark_coverage for name in REQUIRED_BENCHMARKS
            ),
            "ohlcv_and_limit_checks_pass": not anomaly_details,
            "no_duplicate_daily_bars": not duplicate_details,
        }

        payload: dict[str, Any] = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
            "manifest_fetched_at": manifest.fetched_at if manifest else None,
            "passed": not blockers,
            "blockers": blockers,
            "stock_inventory_count": len(stock_rows),
            "stocks_with_bars": len(bar_coverage),
            "exchange_counts": dict(Counter(row["exchange"] for row in stock_rows)),
            "stock_coverage": {
                "covered_count": len(bar_coverage),
                "missing_count": len(missing_stocks),
                "coverage_ratio": (
                    len(bar_coverage) / len(stock_rows) if stock_rows else 0.0
                ),
                "delisted_count": len(delisted_symbols),
                "delisted_with_bars": sum(
                    symbol in bars_by_symbol for symbol in delisted_symbols
                ),
                "bse_count": len(bse_symbols),
                "bse_with_bars": sum(
                    symbol in bars_by_symbol for symbol in bse_symbols
                ),
            },
            "date_coverage": self._serializable_coverage(),
            "average_trading_days_per_covered_stock": (
                sum(int(row["row_count"]) for row in bar_coverage)
                / len(bar_coverage)
                if bar_coverage
                else 0.0
            ),
            "benchmark_coverage": benchmark_coverage,
            "audit_checks": audit_checks,
            "passed_items": [name for name, passed in audit_checks.items() if passed],
            "failed_items": [name for name, passed in audit_checks.items() if not passed],
            "sync_status": {
                "counts": dict(state_counts),
                "source_counts": dict(source_counts),
                "incomplete": failures,
            },
            "per_symbol_missing_sessions": missing_by_symbol,
            "missing_stocks": missing_stocks,
            "anomalies": {
                "count": len(anomaly_details),
                "rows": anomaly_details,
            },
            "duplicates": {
                "count": len(duplicate_details),
                "rows": duplicate_details,
            },
        }
        self.cache.save_audit(payload)
        if output is not None:
            _write_audit_report(Path(output), payload)
        return DataAuditResult(not blockers, payload)

    def _serializable_coverage(self) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in self.cache.coverage().items()
        }


def _optional_iso_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def _missing_ranges(
    expected_dates: list[str], missing_dates: set[str]
) -> list[dict[str, object]]:
    ranges: list[dict[str, object]] = []
    start: str | None = None
    finish: str | None = None
    count = 0
    for value in expected_dates:
        if value in missing_dates:
            if start is None:
                start = value
            finish = value
            count += 1
        elif start is not None:
            ranges.append({"start": start, "end": finish, "sessions": count})
            start = finish = None
            count = 0
    if start is not None:
        ranges.append({"start": start, "end": finish, "sessions": count})
    return ranges


def _write_audit_report(path: Path, payload: dict[str, Any]) -> None:
    if path.suffix.lower() == ".json":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return
    path.mkdir(parents=True, exist_ok=True)
    documents = {
        "audit_report.json": payload,
        "missing_stocks.json": payload["missing_stocks"],
        "missing_dates.json": payload["per_symbol_missing_sessions"],
        "data_anomalies.json": {
            "anomalies": payload["anomalies"],
            "duplicates": payload["duplicates"],
        },
    }
    for name, document in documents.items():
        (path / name).write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
