from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .data_audit import DataAuditResult, RealMarketDataAuditor
from .real_market import PHASE4_START, SQLiteMarketCache


class Phase4SyncMonitor:
    """Writes a compact sync snapshot and audits only after all stocks settle."""

    def __init__(self, cache: SQLiteMarketCache) -> None:
        self.cache = cache

    def refresh(
        self,
        *,
        end_date: date,
        status_output: str | Path,
        audit_output: str | Path,
    ) -> tuple[dict[str, Any], DataAuditResult | None]:
        statuses = self.cache.sync_statuses()
        counts = Counter(item.status for item in statuses)
        with self.cache.connect() as connection:
            total_stocks = int(
                connection.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
            )
            coverage = connection.execute(
                """
                SELECT MIN(trading_date), MAX(trading_date), COUNT(*),
                       COUNT(DISTINCT symbol)
                FROM bars
                """
            ).fetchone()
        current = next(
            (item for item in reversed(statuses) if item.status == "running"),
            None,
        )
        errors = Counter(
            (item.status, item.last_error or "no error detail")
            for item in statuses
            if item.status != "complete"
        )
        settled = counts["complete"] + counts["failed"] + counts["unavailable"]
        sync_complete = (
            total_stocks > 0
            and len(statuses) >= total_stocks
            and settled >= total_stocks
            and counts["running"] == 0
            and counts["interrupted"] == 0
        )
        payload: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_start": PHASE4_START.isoformat(),
            "requested_end": end_date.isoformat(),
            "sync_complete": sync_complete,
            "total_stock_count": total_stocks,
            "completed_count": counts["complete"],
            "failed_count": counts["failed"],
            "unavailable_count": counts["unavailable"],
            "interrupted_count": counts["interrupted"],
            "unprocessed_count": max(total_stocks - len(statuses), 0),
            "current_stock": _status_payload(current),
            "coverage": {
                "start_date": coverage[0],
                "end_date": coverage[1],
                "bar_count": int(coverage[2]),
                "symbols_with_bars": int(coverage[3]),
                "average_trading_days": (
                    round(int(coverage[2]) / int(coverage[3]), 2)
                    if coverage[3]
                    else 0.0
                ),
            },
            "recent_error_summary": [
                {"status": key[0], "error": key[1], "count": count}
                for key, count in errors.most_common(10)
            ],
            "audit_triggered": False,
            "audit_passed": None,
        }
        audit: DataAuditResult | None = None
        if sync_complete:
            audit = RealMarketDataAuditor(self.cache).run(
                start_date=PHASE4_START,
                end_date=end_date,
                output=audit_output,
            )
            payload["audit_triggered"] = True
            payload["audit_passed"] = audit.passed
        path = Path(status_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload, audit


def _status_payload(status: Any | None) -> dict[str, Any] | None:
    if status is None:
        return None
    return {
        "symbol": status.symbol,
        "status": status.status,
        "date_checkpoint": status.synced_through.isoformat()
        if status.synced_through
        else None,
        "bar_count": status.bar_count,
        "attempts": status.attempts,
        "source": status.source,
        "last_error": status.last_error,
    }
