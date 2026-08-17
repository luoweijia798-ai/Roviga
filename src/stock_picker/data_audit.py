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
                      WHEN amount > 0 AND volume > 0 AND vwap IS NULL
                        THEN 'missing_vwap_with_turnover'
                      WHEN signal_open <= 0 OR signal_high <= 0
                        OR signal_low <= 0 OR signal_close <= 0
                        THEN 'invalid_signal_price'
                    END AS reason
                FROM bars
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR high < MAX(open, close) OR low > MIN(open, close)
                   OR high < low OR volume < 0 OR amount < 0
                   OR (amount > 0 AND volume > 0 AND vwap IS NULL)
                   OR signal_open <= 0 OR signal_high <= 0
                   OR signal_low <= 0 OR signal_close <= 0
                ORDER BY trading_date, symbol
                """
            ).fetchall()

        reference_dates = tuple(row["trading_date"] for row in reference_rows)
        bars_by_symbol = {row["symbol"]: row for row in bar_coverage}
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

        payload: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
            "manifest_fetched_at": manifest.fetched_at if manifest else None,
            "passed": not blockers,
            "blockers": blockers,
            "stock_inventory_count": len(stock_rows),
            "stocks_with_bars": len(bar_coverage),
            "exchange_counts": dict(Counter(row["exchange"] for row in stock_rows)),
            "date_coverage": self._serializable_coverage(),
            "benchmark_coverage": benchmark_coverage,
            "sync_status": {
                "counts": dict(state_counts),
                "source_counts": dict(source_counts),
                "incomplete": failures,
            },
            "per_symbol_missing_sessions": missing_by_symbol,
            "anomalies": {
                "count": len(anomaly_details),
                "rows": anomaly_details,
            },
        }
        self.cache.save_audit(payload)
        if output is not None:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
