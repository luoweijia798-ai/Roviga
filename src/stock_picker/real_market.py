from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Protocol

from .historical import BenchmarkPoint, FutureDataError, HistoricalBar
from .models import DailyBar
from .sina_archive import fetch_sina_archive, isolate_retired_terminal_duplicate
from . import sync_retry
from .tencent_bse import fetch_tencent_bse, verify_overlap


PHASE4_START = date(2015, 6, 1)


@dataclass(frozen=True, slots=True)
class StockInfo:
    symbol: str
    name: str
    exchange: str
    list_date: date | None = None
    delist_date: date | None = None
    industry: str | None = None
    source: str = ""


@dataclass(frozen=True, slots=True)
class ClassificationRecord:
    """A classification is usable only on/after `available_from`."""

    symbol: str
    classification_type: str
    classification_name: str
    effective_from: date
    available_from: date
    effective_to: date | None = None
    source: str = ""


@dataclass(frozen=True, slots=True)
class DataManifest:
    provider: str
    start_date: date
    end_date: date
    fetched_at: str
    adjustment_method: str
    symbol_count: int
    bar_count: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SymbolSyncStatus:
    symbol: str
    provider: str
    status: str
    requested_start: date
    requested_end: date
    synced_through: date | None = None
    bar_count: int = 0
    attempts: int = 0
    source: str = ""
    last_error: str | None = None
    updated_at: str = ""


class RealMarketAdapter(Protocol):
    def sync(
        self,
        cache: SQLiteMarketCache,
        start_date: date,
        end_date: date,
    ) -> DataManifest: ...


class _ClosingConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3, then release the Windows file handle."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


class SQLiteMarketCache:
    """Portable disk cache sized for a decade of full-market daily bars."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert_bars(self, bars: Iterable[HistoricalBar]) -> int:
        rows = list(bars)
        with self.connect() as connection:
            if rows:
                self._invalidate_audit(connection)
            connection.executemany(
                """
                INSERT OR REPLACE INTO bars (
                    trading_date, symbol, open, high, low, close, volume, vwap,
                    tradable, limit_up_locked, limit_down_locked, amount,
                    up_limit, down_limit, signal_open, signal_high, signal_low,
                    signal_close
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        bar.trading_date.isoformat(),
                        bar.symbol,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        bar.vwap,
                        int(bar.tradable),
                        int(bar.limit_up_locked),
                        int(bar.limit_down_locked),
                        bar.amount,
                        bar.up_limit,
                        bar.down_limit,
                        bar.signal_open,
                        bar.signal_high,
                        bar.signal_low,
                        bar.signal_close,
                    )
                    for bar in rows
                ],
            )
        return len(rows)

    def upsert_benchmarks(self, points: Iterable[BenchmarkPoint]) -> int:
        rows = list(points)
        with self.connect() as connection:
            if rows:
                self._invalidate_audit(connection)
            connection.executemany(
                "INSERT OR REPLACE INTO benchmarks VALUES (?, ?, ?)",
                [
                    (point.trading_date.isoformat(), point.name, point.close)
                    for point in rows
                ],
            )
        return len(rows)

    def upsert_stocks(self, stocks: Iterable[StockInfo]) -> int:
        rows = list(stocks)
        with self.connect() as connection:
            if rows:
                self._invalidate_audit(connection)
            connection.executemany(
                """
                INSERT INTO stocks (
                    symbol, name, exchange, list_date, delist_date, industry, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name, exchange=excluded.exchange,
                    list_date=COALESCE(excluded.list_date, stocks.list_date),
                    delist_date=COALESCE(excluded.delist_date, stocks.delist_date),
                    industry=COALESCE(excluded.industry, stocks.industry),
                    source=excluded.source
                """,
                [
                    (
                        item.symbol,
                        item.name,
                        item.exchange,
                        _iso(item.list_date),
                        _iso(item.delist_date),
                        item.industry,
                        item.source,
                    )
                    for item in rows
                ],
            )
        return len(rows)

    def upsert_classifications(
        self, records: Iterable[ClassificationRecord]
    ) -> int:
        rows = list(records)
        with self.connect() as connection:
            if rows:
                self._invalidate_audit(connection)
            connection.executemany(
                """
                INSERT OR REPLACE INTO classifications (
                    symbol, classification_type, classification_name,
                    effective_from, available_from, effective_to, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.symbol,
                        item.classification_type,
                        item.classification_name,
                        item.effective_from.isoformat(),
                        item.available_from.isoformat(),
                        _iso(item.effective_to),
                        item.source,
                    )
                    for item in rows
                ],
            )
        return len(rows)

    def save_manifest(self, manifest: DataManifest) -> None:
        payload = asdict(manifest)
        payload["start_date"] = manifest.start_date.isoformat()
        payload["end_date"] = manifest.end_date.isoformat()
        payload["warnings"] = list(manifest.warnings)
        with self.connect() as connection:
            self._invalidate_audit(connection)
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('manifest', ?)",
                (json.dumps(payload, ensure_ascii=False),),
            )

    def load_manifest(self) -> DataManifest | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='manifest'"
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["value"])
        payload["start_date"] = date.fromisoformat(payload["start_date"])
        payload["end_date"] = date.fromisoformat(payload["end_date"])
        payload["warnings"] = tuple(payload.get("warnings", ()))
        return DataManifest(**payload)

    def latest_bar_date(self, symbol: str) -> date | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(trading_date) FROM bars WHERE symbol=?", (symbol,)
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def stock_inventory(self) -> tuple[StockInfo, ...]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM stocks ORDER BY symbol").fetchall()
        return tuple(
            StockInfo(row["symbol"], row["name"], row["exchange"],
                      _optional_date(row["list_date"]),
                      _optional_date(row["delist_date"]), row["industry"], row["source"])
            for row in rows
        )

    def save_sync_status(self, status: SymbolSyncStatus) -> None:
        with self.connect() as connection:
            self._invalidate_audit(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO symbol_sync_status (
                    symbol, provider, status, requested_start, requested_end,
                    synced_through, bar_count, attempts, source, last_error,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    status.symbol,
                    status.provider,
                    status.status,
                    status.requested_start.isoformat(),
                    status.requested_end.isoformat(),
                    _iso(status.synced_through),
                    status.bar_count,
                    status.attempts,
                    status.source,
                    status.last_error,
                    status.updated_at or datetime.now(timezone.utc).isoformat(),
                ),
            )

    def sync_statuses(self) -> tuple[SymbolSyncStatus, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM symbol_sync_status ORDER BY symbol"
            ).fetchall()
        return tuple(
            SymbolSyncStatus(
                symbol=row["symbol"],
                provider=row["provider"],
                status=row["status"],
                requested_start=date.fromisoformat(row["requested_start"]),
                requested_end=date.fromisoformat(row["requested_end"]),
                synced_through=date.fromisoformat(row["synced_through"])
                if row["synced_through"] else None,
                bar_count=int(row["bar_count"]),
                attempts=int(row["attempts"]),
                source=row["source"],
                last_error=row["last_error"],
                updated_at=row["updated_at"],
            )
            for row in rows
        )

    def symbol_bar_count(self, symbol: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol=?", (symbol,)
            ).fetchone()
        return int(row[0])

    def save_audit(self, payload: dict[str, object]) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            revision = self._revision(connection)
            if payload.get("data_revision") != revision:
                payload["passed"] = False
                payload.setdefault("blockers", []).append(
                    "data changed during audit; repeat after sync is idle"
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('data_audit', ?)",
                (json.dumps(payload, ensure_ascii=False),),
            )

    def load_audit(self) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='data_audit'"
            ).fetchone()
        return json.loads(row[0]) if row else None

    @property
    def data_revision(self) -> int:
        with self.connect() as connection:
            return self._revision(connection)

    @staticmethod
    def _revision(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key='data_revision'"
        ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _invalidate_audit(connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM metadata WHERE key='data_audit'")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('data_revision', '1') "
            "ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1"
        )

    def coverage(self) -> dict[str, object]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT MIN(trading_date), MAX(trading_date), COUNT(*),
                       COUNT(DISTINCT symbol), COUNT(DISTINCT trading_date)
                FROM bars
                """
            ).fetchone()
            classification_count = connection.execute(
                "SELECT COUNT(*) FROM classifications"
            ).fetchone()[0]
        return {
            "start_date": date.fromisoformat(row[0]) if row[0] else None,
            "end_date": date.fromisoformat(row[1]) if row[1] else None,
            "bar_count": int(row[2]),
            "symbol_count": int(row[3]),
            "trading_session_count": int(row[4]),
            "classification_count": int(classification_count),
        }

    def as_historical_data(self) -> SQLiteHistoricalData:
        return SQLiteHistoricalData(self.path)

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS bars (
                    trading_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    vwap REAL,
                    tradable INTEGER NOT NULL,
                    limit_up_locked INTEGER NOT NULL,
                    limit_down_locked INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    up_limit REAL,
                    down_limit REAL,
                    signal_open REAL,
                    signal_high REAL,
                    signal_low REAL,
                    signal_close REAL,
                    PRIMARY KEY (trading_date, symbol)
                );
                CREATE INDEX IF NOT EXISTS idx_bars_symbol_date
                    ON bars(symbol, trading_date);
                CREATE TABLE IF NOT EXISTS benchmarks (
                    trading_date TEXT NOT NULL,
                    name TEXT NOT NULL,
                    close REAL NOT NULL,
                    PRIMARY KEY (trading_date, name)
                );
                CREATE TABLE IF NOT EXISTS stocks (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    list_date TEXT,
                    delist_date TEXT,
                    industry TEXT,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS classifications (
                    symbol TEXT NOT NULL,
                    classification_type TEXT NOT NULL,
                    classification_name TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    available_from TEXT NOT NULL,
                    effective_to TEXT,
                    source TEXT NOT NULL,
                    PRIMARY KEY (
                        symbol, classification_type, classification_name,
                        effective_from, available_from
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_classification_asof
                    ON classifications(symbol, available_from, effective_from);
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS symbol_sync_status (
                    symbol TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_start TEXT NOT NULL,
                    requested_end TEXT NOT NULL,
                    synced_through TEXT,
                    bar_count INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_status_state
                    ON symbol_sync_status(status, symbol);
                CREATE TABLE IF NOT EXISTS provider_quarantine (
                    symbol TEXT NOT NULL, trading_date TEXT NOT NULL, source TEXT NOT NULL,
                    evidence TEXT NOT NULL, review_status TEXT NOT NULL,
                    PRIMARY KEY(symbol, trading_date, source)
                );
                CREATE TABLE IF NOT EXISTS sync_retry_policy (
                    symbol TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    consecutive_failures INTEGER NOT NULL, next_retry_at TEXT NOT NULL,
                    disposition TEXT NOT NULL, last_error TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                """
            )


class SQLiteHistoricalData:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @property
    def trading_dates(self) -> tuple[date, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT trading_date FROM bars ORDER BY trading_date"
            ).fetchall()
        return tuple(date.fromisoformat(row[0]) for row in rows)

    @property
    def benchmark_names(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT name FROM benchmarks ORDER BY name"
            ).fetchall()
        return tuple(row[0] for row in rows)

    def portal(self) -> SQLiteHistoricalDataPortal:
        return SQLiteHistoricalDataPortal(self.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection


class SQLiteHistoricalDataPortal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._clock: date | None = None

    @property
    def clock(self) -> date | None:
        return self._clock

    def advance_to(self, trading_date: date) -> None:
        if self._clock is not None and trading_date < self._clock:
            raise FutureDataError("historical clock cannot move backwards")
        self._clock = trading_date

    def bars_on(self, trading_date: date) -> tuple[HistoricalBar, ...]:
        self._guard(trading_date)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bars WHERE trading_date=? ORDER BY symbol",
                (trading_date.isoformat(),),
            ).fetchall()
        return tuple(_row_to_bar(row) for row in rows)

    def bar(self, symbol: str, trading_date: date) -> HistoricalBar | None:
        self._guard(trading_date)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM bars WHERE trading_date=? AND symbol=?",
                (trading_date.isoformat(), symbol),
            ).fetchone()
        return _row_to_bar(row) if row else None

    def daily_snapshot(self, trading_date: date) -> Sequence[DailyBar]:
        self._guard(trading_date)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT current.*,
                    (
                        SELECT COALESCE(previous.signal_close, previous.close)
                        FROM bars AS previous
                        WHERE previous.symbol=current.symbol
                          AND previous.trading_date < current.trading_date
                        ORDER BY previous.trading_date DESC LIMIT 1
                    ) AS previous_signal_close
                FROM bars AS current
                WHERE current.trading_date=?
                ORDER BY current.symbol
                """,
                (trading_date.isoformat(),),
            ).fetchall()
        return tuple(
            DailyBar(
                trading_date,
                row["symbol"],
                row["signal_close"] or row["close"],
                row["previous_signal_close"],
                int(row["volume"]),
                bool(row["tradable"]),
            )
            for row in rows
            if row["previous_signal_close"] is not None
        )

    def previous_bar(
        self, symbol: str, before_date: date
    ) -> HistoricalBar | None:
        self._guard(before_date)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM bars WHERE symbol=? AND trading_date<?
                ORDER BY trading_date DESC LIMIT 1
                """,
                (symbol, before_date.isoformat()),
            ).fetchone()
        return _row_to_bar(row) if row else None

    def symbol_history(
        self, symbol: str, through_date: date, lookback: int
    ) -> tuple[HistoricalBar, ...]:
        self._guard(through_date)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM bars WHERE symbol=? AND trading_date<=?
                ORDER BY trading_date DESC LIMIT ?
                """,
                (symbol, through_date.isoformat(), lookback),
            ).fetchall()
        return tuple(_row_to_bar(row) for row in reversed(rows))

    def benchmark_close(self, name: str, trading_date: date) -> float | None:
        self._guard(trading_date)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT close FROM benchmarks WHERE name=? AND trading_date=?",
                (name, trading_date.isoformat()),
            ).fetchone()
        return float(row[0]) if row else None

    def benchmark_history(
        self, name: str, through_date: date, lookback: int
    ) -> tuple[float, ...]:
        self._guard(through_date)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT close FROM benchmarks
                WHERE name=? AND trading_date<=?
                ORDER BY trading_date DESC LIMIT ?
                """,
                (name, through_date.isoformat(), lookback),
            ).fetchall()
        return tuple(float(row[0]) for row in reversed(rows))

    def classifications_as_of(
        self, symbol: str, as_of: date
    ) -> tuple[ClassificationRecord, ...]:
        self._guard(as_of)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM classifications
                WHERE symbol=? AND available_from<=? AND effective_from<=?
                  AND (effective_to IS NULL OR effective_to>=?)
                ORDER BY classification_type, classification_name
                """,
                (symbol, as_of.isoformat(), as_of.isoformat(), as_of.isoformat()),
            ).fetchall()
        return tuple(
            ClassificationRecord(
                row["symbol"],
                row["classification_type"],
                row["classification_name"],
                date.fromisoformat(row["effective_from"]),
                date.fromisoformat(row["available_from"]),
                date.fromisoformat(row["effective_to"])
                if row["effective_to"]
                else None,
                row["source"],
            )
            for row in rows
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def _guard(self, requested_date: date) -> None:
        if self._clock is None:
            raise FutureDataError("historical clock has not started")
        if requested_date > self._clock:
            raise FutureDataError(
                f"requested {requested_date.isoformat()} beyond simulated "
                f"clock {self._clock.isoformat()}"
            )


class AkShareAdapter:
    """AKShare-first adapter. Import and network access are intentionally lazy."""

    def __init__(
        self,
        *,
        ak_module: Any | None = None,
        symbol_limit: int | None = None,
        include_classifications: bool = True,
        history_source: str = "auto",
        request_interval: float = 0.25,
        max_attempts: int = 4,
        retry_delay: float = 1.0,
        segment_days: int = 366,
        sleeper: Any = time.sleep,
    ) -> None:
        if history_source not in {"auto", "sina"}:
            raise ValueError("history_source must be 'auto' or 'sina'")
        self._ak = ak_module
        self.symbol_limit = symbol_limit
        self.include_classifications = include_classifications
        self.history_source = history_source
        if request_interval < 0 or retry_delay < 0:
            raise ValueError("request delays cannot be negative")
        if max_attempts < 1 or segment_days < 1:
            raise ValueError("max_attempts and segment_days must be positive")
        self.request_interval = request_interval
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.segment_days = segment_days
        self._sleep = sleeper
        self._last_request_at: float | None = None
        self._request_attempts = 0
        self._last_history_source = ""
        self._eastmoney_retry_at = 0.0
        self._eastmoney_last_error: Exception | None = None
        self._archive_cache: tuple[str, Any, Any, int] | None = None
        self._bse_verified: set[str] = set()
        self._eastmoney_history_available: bool | None = (
            False if history_source == "sina" else None
        )

    def sync(
        self,
        cache: SQLiteMarketCache,
        start_date: date = PHASE4_START,
        end_date: date | None = None,
    ) -> DataManifest:
        end_date = end_date or date.today()
        self._sync_start, self._sync_end = start_date, end_date
        self._cache = cache
        self._archive_cache = None
        self._bse_verified = set()
        ak = self._module()
        stocks = self._stock_universe(ak)
        if self.symbol_limit is not None:
            stocks = stocks[: self.symbol_limit]
        cache.upsert_stocks(stocks)
        if self.symbol_limit is None:
            # A temporary provider inventory omission must not drop a retained
            # historical/delisted symbol from the retry queue.
            stocks = list(cache.stock_inventory())
        previous_statuses = {item.symbol: item for item in cache.sync_statuses()}
        for item in previous_statuses.values():
            if item.status == "running":
                cache.save_sync_status(
                    SymbolSyncStatus(
                        item.symbol,
                        item.provider,
                        "interrupted",
                        item.requested_start,
                        item.requested_end,
                        item.synced_through,
                        item.bar_count,
                        item.attempts,
                        item.source,
                        "previous sync stopped; queued for resume",
                    )
                )
        new_bars = 0
        failed_symbols: list[str] = []
        warnings = [
            "AKShare concept memberships are current snapshots and are never "
            "exposed before their fetch date.",
            "Daily price limits are inferred when an exact point-in-time limit "
            "series is unavailable; use Tushare stk_limit for exact limits.",
            "AkShare Eastmoney daily history is preferred; the AkShare Sina "
            "history endpoint is used automatically when Eastmoney is unavailable.",
        ]
        pending: list[tuple[StockInfo, date]] = []
        for stock in stocks:
            previous = previous_statuses.get(stock.symbol)
            latest = cache.latest_bar_date(stock.symbol)
            outside_range = ((stock.delist_date and stock.delist_date < start_date)
                             or (stock.list_date and stock.list_date > end_date))
            if outside_range:
                with cache.connect() as connection:
                    in_range = connection.execute("SELECT COUNT(*) FROM bars WHERE symbol=? "
                        "AND trading_date BETWEEN ? AND ?", (stock.symbol, start_date.isoformat(), end_date.isoformat())).fetchone()[0]
                if in_range:
                    cache.save_sync_status(SymbolSyncStatus(
                        stock.symbol, "AkShare", "failed", start_date, end_date,
                        previous.synced_through if previous else None,
                        cache.symbol_bar_count(stock.symbol),
                        previous.attempts if previous else 0, stock.source,
                        "delisting metadata conflicts with cached bars; retained for review",
                    ))
                    failed_symbols.append(stock.symbol + ":MetadataConflict")
                    continue
                if (previous and previous.status == "complete"
                        and previous.requested_start <= start_date
                        and previous.synced_through and previous.synced_through >= end_date
                        and previous.source.endswith(":outside_requested_range")):
                    continue
                cache.save_sync_status(SymbolSyncStatus(
                    stock.symbol, "AkShare", "complete", start_date, end_date,
                    end_date, cache.symbol_bar_count(stock.symbol),
                    previous.attempts if previous else 0,
                    stock.source + ":outside_requested_range",
                    "No requested sessions: exchange listing/delisting metadata outside requested interval",
                ))
                continue
            if (previous and previous.status == "complete"
                    and previous.requested_start <= start_date
                    and previous.synced_through
                    and previous.synced_through >= end_date):
                continue
            if previous and previous.status == "failed" and not sync_retry.eligible(cache, stock, start_date, end_date):
                failed_symbols.append(stock.symbol + ":DeferredSourceReview")
                continue
            checkpoint = (
                previous.synced_through
                if previous and previous.requested_start <= start_date
                and previous.synced_through and previous.status != "unavailable"
                else latest
            )
            fetch_start = max(start_date, checkpoint + timedelta(days=1)) if checkpoint else start_date
            if stock.list_date:
                fetch_start = max(fetch_start, stock.list_date)
            if previous and previous.requested_start > start_date:
                fetch_start = start_date
            if stock.delist_date and previous and previous.status != "complete":
                # Old failures may have advanced beyond delisting despite holes
                # in earlier segments. Verify/recover the whole active history.
                fetch_start = max(start_date, stock.list_date or start_date)
            if fetch_start > end_date:
                # Never clear a retained failure merely because its final row
                # happens to reach the end date. Revalidate the last segment.
                fetch_start = end_date
            pending.append((stock, fetch_start))
        pending.sort(key=lambda item: (
            0 if (previous_statuses.get(item[0].symbol) is None
                  or previous_statuses[item[0].symbol].status != "complete") else 1,
            item[0].symbol,
        ))
        completed = len(stocks) - len(pending)
        for stock, fetch_start in pending:
            request_attempt_start = self._request_attempts
            failed = False
            previous = previous_statuses.get(stock.symbol)
            source = previous.source if previous else ""
            previous_attempts = previous.attempts if previous else 0
            checkpoint = fetch_start - timedelta(days=1) if fetch_start > start_date else None
            cache.save_sync_status(
                SymbolSyncStatus(
                    stock.symbol, "AkShare", "running", start_date, end_date,
                    checkpoint,
                    cache.symbol_bar_count(stock.symbol),
                    previous_attempts, source,
                )
            )
            for segment_start, segment_end in _date_segments(
                fetch_start, min(end_date, stock.delist_date or end_date), self.segment_days
            ):
                try:
                    bars = self._fetch_symbol_bars(
                        ak, stock, segment_start, segment_end
                    )
                    source = self._last_history_source or source
                    new_bars += cache.upsert_bars(bars)
                    checkpoint = segment_end
                    cache.save_sync_status(
                        SymbolSyncStatus(
                            stock.symbol, "AkShare", "running", start_date,
                            end_date, segment_end,
                            cache.symbol_bar_count(stock.symbol),
                            previous_attempts + self._request_attempts - request_attempt_start,
                            source,
                        )
                    )
                except Exception as error:
                    failed = True
                    sync_retry.failed(cache, stock, start_date, end_date, error)
                    failed_symbols.append(
                        f"{stock.symbol}:{type(error).__name__}"
                    )
                    cache.save_sync_status(
                        SymbolSyncStatus(
                            stock.symbol, "AkShare", "failed", start_date,
                            end_date, checkpoint,
                            cache.symbol_bar_count(stock.symbol),
                            previous_attempts + self._request_attempts - request_attempt_start,
                            source, f"{type(error).__name__}: {error}",
                        )
                    )
                    break
            if not failed:
                sync_retry.clear(cache, stock.symbol)
                total_bars = cache.symbol_bar_count(stock.symbol)
                final_status = "complete" if total_bars else "unavailable"
                cache.save_sync_status(
                    SymbolSyncStatus(
                        stock.symbol, "AkShare", final_status, start_date,
                        end_date, end_date if total_bars else None, total_bars,
                        previous_attempts + self._request_attempts - request_attempt_start, source,
                        "provider returned no rows" if not total_bars else None,
                    )
                )
            completed += 1
            if completed % 50 == 0 or completed == len(stocks):
                print(
                    f"market sync {completed}/{len(stocks)} symbols "
                    f"bars_written={new_bars} failures={len(failed_symbols)}",
                    flush=True,
                )
        cache.upsert_benchmarks(
            self._fetch_benchmark(ak, "CSI300", "sh000300", start_date, end_date)
        )
        cache.upsert_benchmarks(
            self._fetch_benchmark(ak, "CSI1000", "csi000852", start_date, end_date)
        )
        if self.include_classifications:
            classification_errors = self._sync_current_classifications(
                ak, cache, date.today()
            )
            if classification_errors:
                warnings.append(
                    f"classification snapshot failures: {','.join(classification_errors)}"
                )
        if failed_symbols:
            warnings.append(
                f"failed symbols ({len(failed_symbols)}): {','.join(failed_symbols[:20])}"
            )
        coverage = cache.coverage()
        manifest = DataManifest(
            provider="AkShare",
            start_date=start_date,
            end_date=end_date,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            adjustment_method="raw execution + HFQ causal signal prices",
            symbol_count=int(coverage["symbol_count"]),
            bar_count=int(coverage["bar_count"]),
            warnings=tuple(warnings),
        )
        cache.save_manifest(manifest)
        return manifest

    def _sync_current_classifications(
        self, ak: Any, cache: SQLiteMarketCache, available_from: date
    ) -> list[str]:
        failures: list[str] = []
        history_function = getattr(ak, "stock_industry_clf_hist_sw", None)
        if history_function is not None:
            try:
                cache.upsert_classifications(
                    self._industry_history_records(self._request(history_function))
                )
            except Exception as error:
                failures.append(f"industry_history:{type(error).__name__}")
        specifications = (
            (
                "industry",
                "stock_board_industry_name_em",
                "stock_board_industry_cons_em",
            ),
            (
                "concept",
                "stock_board_concept_name_em",
                "stock_board_concept_cons_em",
            ),
        )
        for classification_type, names_method, members_method in specifications:
            names_function = getattr(ak, names_method, None)
            members_function = getattr(ak, members_method, None)
            if names_function is None or members_function is None:
                failures.append(f"{classification_type}:unsupported")
                continue
            try:
                names_frame = self._request(names_function)
                name_column = _column(
                    names_frame, "板块名称", "概念名称", "行业名称", "name"
                )
            except Exception as error:
                failures.append(f"{classification_type}:{type(error).__name__}")
                continue
            for name in names_frame[name_column].astype(str).tolist():
                try:
                    members = self._request(members_function, symbol=name)
                    code_column = _column(
                        members, "代码", "证券代码", "股票代码", "code"
                    )
                    records = [
                        ClassificationRecord(
                            symbol=str(value).zfill(6),
                            classification_type=classification_type,
                            classification_name=name,
                            effective_from=available_from,
                            available_from=available_from,
                            source=f"AkShare.{members_method}",
                        )
                        for value in members[code_column].astype(str).tolist()
                    ]
                    cache.upsert_classifications(records)
                except Exception as error:
                    failures.append(
                        f"{classification_type}/{name}:{type(error).__name__}"
                    )
        return failures

    @staticmethod
    def _industry_history_records(frame: Any) -> list[ClassificationRecord]:
        grouped: dict[str, list[tuple[date, date, str]]] = {}
        for _, row in frame.iterrows():
            symbol = str(row[_column(frame, "symbol", "证券代码")]).zfill(6)
            effective = _as_date(row[_column(frame, "start_date", "计入日期")])
            available = _as_date(row[_column(frame, "update_time", "更新日期")])
            industry = str(row[_column(frame, "industry_code", "行业代码")])
            grouped.setdefault(symbol, []).append((effective, available, industry))
        records: list[ClassificationRecord] = []
        for symbol, changes in grouped.items():
            ordered = sorted(changes, key=lambda item: item[0])
            for index, (effective, available, industry) in enumerate(ordered):
                effective_to = (
                    ordered[index + 1][0] - timedelta(days=1)
                    if index + 1 < len(ordered)
                    else None
                )
                records.append(
                    ClassificationRecord(
                        symbol,
                        "industry_sw",
                        industry,
                        effective,
                        available,
                        effective_to,
                        "AkShare.stock_industry_clf_hist_sw",
                    )
                )
        return records

    def _module(self) -> Any:
        if self._ak is not None:
            return self._ak
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError(
                "AkShare is not installed; install the optional 'akshare' extra "
                "or load an existing SQLite cache"
            ) from error
        return ak

    def _stock_universe(self, ak: Any) -> list[StockInfo]:
        frame = self._request(ak.stock_info_a_code_name)
        stocks = {
            str(row[_column(frame, "code", "证券代码", "股票代码")]).zfill(6): StockInfo(
                symbol=str(row[_column(frame, "code", "证券代码", "股票代码")]).zfill(6),
                name=str(row[_column(frame, "name", "证券简称", "股票简称")]),
                exchange=_exchange_for_symbol(
                    str(row[_column(frame, "code", "证券代码", "股票代码")]).zfill(6)
                ),
                source="AkShare.stock_info_a_code_name",
            )
            for _, row in frame.iterrows()
        }
        specifications = (
            ("stock_info_sh_delist", "全部", "公司代码", "公司简称", "暂停上市日期"),
            (
                "stock_info_sz_delist",
                "终止上市公司",
                "证券代码",
                "证券简称",
                "终止上市日期",
            ),
        )
        for method_name, argument, code_column, name_column, delist_column in specifications:
            function = getattr(ak, method_name, None)
            if function is None:
                continue
            try:
                delisted = self._request(function, symbol=argument)
            except Exception:
                continue
            for _, row in delisted.iterrows():
                symbol = str(row[code_column]).zfill(6)
                if not _is_a_share_symbol(symbol):
                    continue
                stocks[symbol] = StockInfo(
                    symbol,
                    str(row[name_column]),
                    _exchange_for_symbol(symbol),
                    _optional_date(row.get("上市日期")),
                    _optional_date(row.get(delist_column)),
                    source=f"AkShare.{method_name}",
                )
        bse_function = getattr(ak, "stock_info_bj_name_code", None)
        if bse_function is not None:
            try:
                bse = self._request(bse_function)
                for _, row in bse.iterrows():
                    symbol = str(row["证券代码"]).zfill(6)
                    stocks[symbol] = StockInfo(symbol, str(row["证券简称"]), "BSE",
                        list_date=_optional_date(row.get("上市日期")),
                        source="AkShare.stock_info_bj_name_code")
            except Exception:
                pass  # Preserve inventory; audit identifies unverified dates.
        return sorted(stocks.values(), key=lambda item: item.symbol)

    def _fetch_symbol_bars(
        self,
        ak: Any,
        stock: StockInfo,
        start_date: date,
        end_date: date,
    ) -> tuple[HistoricalBar, ...]:
        arguments = {
            "symbol": stock.symbol,
            "period": "daily",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
        }
        raw, adjusted, volume_multiplier = self._fetch_history_frames(
            ak, stock, arguments
        )
        if raw.empty:
            return ()
        adjusted_date_column = _optional_column(adjusted, "日期", "date")
        adjusted_by_date = (
            {
                _as_date(row[adjusted_date_column]): row
                for _, row in adjusted.iterrows()
            }
            if adjusted_date_column is not None
            else {}
        )
        bars: list[HistoricalBar] = []
        previous_close: float | None = None
        for _, row in raw.iterrows():
            trading_date = _as_date(row[_column(raw, "日期", "date")])
            adjusted_row = adjusted_by_date.get(trading_date)
            open_price = float(row[_column(raw, "开盘", "open")])
            close = float(row[_column(raw, "收盘", "close")])
            high = float(row[_column(raw, "最高", "high")])
            low = float(row[_column(raw, "最低", "low")])
            volume = int(
                float(row[_column(raw, "成交量", "volume")]) * volume_multiplier
            )
            amount_column = _optional_column(raw, "成交额", "amount")
            amount = float(row[amount_column]) if amount_column else 0.0
            up_limit, down_limit = _infer_limits(
                stock.symbol, stock.name, trading_date, previous_close
            )
            locked_up = bool(
                up_limit is not None
                and _same_price(open_price, high, low, close, up_limit)
            )
            locked_down = bool(
                down_limit is not None
                and _same_price(open_price, high, low, close, down_limit)
            )
            signal = adjusted_row if adjusted_row is not None else row
            signal_frame = adjusted if adjusted_row is not None else raw
            bars.append(
                HistoricalBar(
                    trading_date=trading_date,
                    symbol=stock.symbol,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    vwap=_bounded_vwap(amount, volume, low, high),
                    tradable=volume > 0,
                    limit_up_locked=locked_up,
                    limit_down_locked=locked_down,
                    amount=amount,
                    up_limit=up_limit,
                    down_limit=down_limit,
                    signal_open=float(signal[_column(signal_frame, "开盘", "open")]),
                    signal_high=float(signal[_column(signal_frame, "最高", "high")]),
                    signal_low=float(signal[_column(signal_frame, "最低", "low")]),
                    signal_close=float(signal[_column(signal_frame, "收盘", "close")]),
                )
            )
            previous_close = close
        return tuple(bars)

    def _fetch_history_frames(
        self,
        ak: Any,
        stock: StockInfo,
        arguments: dict[str, str],
    ) -> tuple[Any, Any, int]:
        eastmoney_error: Exception | None = None
        if stock.delist_date and self._archive_cache and self._archive_cache[0] == stock.symbol:
            return self._archive_segment(arguments)
        if (self._eastmoney_history_available is not False
                and time.monotonic() >= self._eastmoney_retry_at):
            try:
                raw = self._request(
                    ak.stock_zh_a_hist, **arguments, adjust=""
                )
                if raw.empty:
                    if stock.delist_date or stock.exchange == "BSE":
                        raise ValueError("Eastmoney empty required history; checking verified fallback")
                    self._last_history_source = "AkShare.Eastmoney"
                    return raw, raw, 100
                adjusted = self._request(
                    ak.stock_zh_a_hist, **arguments, adjust="hfq"
                )
                self._eastmoney_history_available = True
                self._last_history_source = "AkShare.Eastmoney"
                # Eastmoney reports volume in lots; the project stores shares.
                return raw, adjusted, 100
            except Exception as error:
                eastmoney_error = error
                self._eastmoney_last_error = error
                # Transport failures affect the endpoint, not each retired stock.
                # Probe again after five minutes rather than burning the same
                # retry budget for every segment. Symbol/data errors do not trip it.
                try:
                    import requests
                    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
                        self._eastmoney_retry_at = time.monotonic() + 300
                except ImportError:
                    pass
        else:
            eastmoney_error = self._eastmoney_last_error
        if stock.delist_date:
            prefix = "sh" if stock.exchange == "SSE" else "sz"
            raw, adjusted, multiplier = self._request(
                fetch_sina_archive, symbol=prefix + stock.symbol,
                start_date=getattr(self, "_sync_start", PHASE4_START).isoformat(),
                end_date=getattr(self, "_sync_end", _as_date(arguments["end_date"])).isoformat(),
            )
            if not raw.empty and max(raw["date"]) > stock.delist_date:
                if not hasattr(self, "_cache"):
                    raise ValueError(f"{stock.symbol}: archived trading after documented delisting")
                raw, adjusted = isolate_retired_terminal_duplicate(raw, adjusted, stock, self._cache)
            if raw.empty:
                raise RuntimeError(f"{stock.symbol}: no retired archive rows in requested range; retained source gap")
            self._archive_cache = (stock.symbol, raw, adjusted, multiplier)
            return self._archive_segment(arguments)
        if stock.exchange == "BSE":
            if hasattr(self, "_cache") and stock.list_date:
                if stock.symbol not in self._bse_verified:
                    with self._cache.connect() as connection:
                        overlap = connection.execute("SELECT * FROM bars WHERE symbol=? AND trading_date<? "
                            "ORDER BY trading_date DESC LIMIT 14", (stock.symbol, _as_date(arguments["start_date"]).isoformat())).fetchall()
                    if overlap:
                        old_raw, old_adjusted, _ = self._request(fetch_tencent_bse, symbol=stock.symbol,
                            start_date=overlap[-1]["trading_date"], end_date=overlap[0]["trading_date"])
                        verify_overlap(old_raw, old_adjusted, overlap, stock.symbol)
                    self._bse_verified.add(stock.symbol)
                raw, adjusted, multiplier = self._request(fetch_tencent_bse,
                    symbol=stock.symbol,
                    start_date=_as_date(arguments["start_date"]).isoformat(),
                    end_date=_as_date(arguments["end_date"]).isoformat())
                self._last_history_source = "AkShare-primary/Tencent.BSE.raw+HFQ"
                return raw, adjusted, multiplier
            raise RuntimeError(
                "BSE history unavailable from Eastmoney; Sina A-share fallback "
                "does not support this exchange. Retained for source recovery. "
                f"Primary error: {eastmoney_error}"
            ) from eastmoney_error
        sina_function = getattr(ak, "stock_zh_a_daily", None)
        if sina_function is None:
            if eastmoney_error is not None:
                raise eastmoney_error
            raise RuntimeError("no AkShare daily-history endpoint is available")
        prefix = "sh" if stock.symbol.startswith("6") else "sz"
        if stock.symbol.startswith(("4", "8")):
            prefix = "bj"
        sina_arguments = {
            "symbol": f"{prefix}{stock.symbol}",
            "start_date": arguments["start_date"],
            "end_date": arguments["end_date"],
        }
        raw = self._request(sina_function, **sina_arguments, adjust="")
        adjusted = self._request(sina_function, **sina_arguments, adjust="hfq")
        self._last_history_source = "AkShare.Sina"
        # Sina reports volume in shares.
        return raw, adjusted, 1

    def _archive_segment(self, arguments: dict[str, str]) -> tuple[Any, Any, int]:
        assert self._archive_cache is not None
        _, raw, adjusted, multiplier = self._archive_cache
        start, end = _as_date(arguments["start_date"]), _as_date(arguments["end_date"])
        self._last_history_source = "AkShare.SinaArchive.KLC+HFQ"
        return (raw[(raw["date"] >= start) & (raw["date"] <= end)].copy(),
                adjusted[(adjusted["date"] >= start) & (adjusted["date"] <= end)].copy(), multiplier)

    def _request(self, function: Any, **arguments: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._request_attempts += 1
            if self._last_request_at is not None and self.request_interval:
                elapsed = time.monotonic() - self._last_request_at
                if elapsed < self.request_interval:
                    self._sleep(self.request_interval - elapsed)
            try:
                result = _call_with_optional_timeout(function, **arguments)
                self._last_request_at = time.monotonic()
                return result
            except Exception as error:
                self._last_request_at = time.monotonic()
                last_error = error
                # Data/schema/permission errors cannot be repaired by repeating
                # the identical request five times. Outer sync retains the row.
                if isinstance(error, (ValueError, KeyError, TypeError)):
                    break
                if getattr(getattr(error, "response", None), "status_code", None) in {400, 401, 403, 404}:
                    break
                if attempt < self.max_attempts:
                    self._sleep(self.retry_delay * (2 ** (attempt - 1)))
        assert last_error is not None
        raise last_error

    def _fetch_benchmark(
        self,
        ak: Any,
        name: str,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[BenchmarkPoint, ...]:
        try:
            if self._eastmoney_history_available is False or time.monotonic() < self._eastmoney_retry_at:
                raise RuntimeError("Eastmoney history circuit is open")
            frame = self._request(
                ak.stock_zh_index_daily_em,
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )
        except Exception as eastmoney_error:
            sina_function = getattr(ak, "stock_zh_index_daily", None)
            if sina_function is None:
                raise eastmoney_error
            sina_symbol = "sh000852" if symbol == "csi000852" else symbol
            frame = self._request(sina_function, symbol=sina_symbol)
            date_column = _column(frame, "date", "日期")
            frame = frame[
                frame[date_column].map(
                    lambda value: start_date <= _as_date(value) <= end_date
                )
            ]
        return tuple(
            BenchmarkPoint(
                _as_date(row[_column(frame, "date", "日期")]),
                name,
                float(row[_column(frame, "close", "收盘")]),
            )
            for _, row in frame.iterrows()
        )


class TushareAdapter:
    """Optional exact-limit adapter; requires a user-provided Tushare token."""

    def __init__(self, token: str | None = None, *, pro_client: Any | None = None) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        self._pro_client = pro_client

    def sync(
        self,
        cache: SQLiteMarketCache,
        start_date: date = PHASE4_START,
        end_date: date | None = None,
    ) -> DataManifest:
        end_date = end_date or date.today()
        pro = self._client()
        stocks = self._fetch_stocks(pro)
        cache.upsert_stocks(stocks)
        cache.upsert_classifications(
            ClassificationRecord(
                item.symbol,
                "industry",
                item.industry,
                end_date,
                end_date,
                source="Tushare.stock_basic",
            )
            for item in stocks
            if item.industry
        )
        calendar = pro.trade_cal(
            exchange="SSE",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            is_open="1",
        )
        dates = sorted(str(value) for value in calendar["cal_date"].tolist())
        for value in dates:
            daily = pro.daily(trade_date=value)
            limits = pro.stk_limit(trade_date=value)
            factors = pro.adj_factor(trade_date=value)
            limit_map = {
                str(row["ts_code"]): (float(row["up_limit"]), float(row["down_limit"]))
                for _, row in limits.iterrows()
            }
            factor_map = {
                str(row["ts_code"]): float(row["adj_factor"])
                for _, row in factors.iterrows()
            }
            day_bars: list[HistoricalBar] = []
            for _, row in daily.iterrows():
                ts_code = str(row["ts_code"])
                symbol = ts_code.split(".")[0]
                up_limit, down_limit = limit_map.get(ts_code, (None, None))
                open_price = float(row["open"])
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                factor = factor_map.get(ts_code, 1.0)
                bar = HistoricalBar(
                    date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}"),
                    symbol,
                    open_price,
                    high,
                    low,
                    close,
                    int(float(row["vol"]) * 100),
                    float(row["amount"]) * 1000 / (float(row["vol"]) * 100)
                    if float(row["vol"])
                    else None,
                    True,
                    bool(
                        up_limit is not None
                        and _same_price(open_price, high, low, close, up_limit)
                    ),
                    bool(
                        down_limit is not None
                        and _same_price(open_price, high, low, close, down_limit)
                    ),
                    float(row["amount"]) * 1000,
                    up_limit,
                    down_limit,
                    open_price * factor,
                    high * factor,
                    low * factor,
                    close * factor,
                )
                day_bars.append(bar)
            cache.upsert_bars(day_bars)
        for name, ts_code in (("CSI300", "000300.SH"), ("CSI1000", "000852.SH")):
            frame = pro.index_daily(
                ts_code=ts_code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )
            cache.upsert_benchmarks(
                BenchmarkPoint(
                    _as_date(str(row["trade_date"])), name, float(row["close"])
                )
                for _, row in frame.iterrows()
            )
        for stock in stocks:
            latest = cache.latest_bar_date(stock.symbol)
            count = cache.symbol_bar_count(stock.symbol)
            cache.save_sync_status(
                SymbolSyncStatus(
                    stock.symbol,
                    "Tushare",
                    "complete" if count else "unavailable",
                    start_date,
                    end_date,
                    latest,
                    count,
                    source="Tushare.daily",
                    last_error=None if count else "provider returned no rows",
                )
            )
        coverage = cache.coverage()
        manifest = DataManifest(
            provider="Tushare",
            start_date=start_date,
            end_date=end_date,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            adjustment_method="raw execution + causal cumulative adj_factor signals",
            symbol_count=int(coverage["symbol_count"]),
            bar_count=int(coverage["bar_count"]),
            warnings=("Tushare permissions and rate limits depend on account points.",),
        )
        cache.save_manifest(manifest)
        return manifest

    def _client(self) -> Any:
        if self._pro_client is not None:
            return self._pro_client
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is required for the Tushare adapter")
        try:
            import tushare as ts
        except ImportError as error:
            raise RuntimeError("Tushare is not installed") from error
        return ts.pro_api(self.token)

    def _fetch_stocks(self, pro: Any) -> list[StockInfo]:
        stocks: dict[str, StockInfo] = {}
        for status in ("L", "D", "P"):
            frame = pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,symbol,name,industry,list_date,delist_date,exchange",
            )
            for _, row in frame.iterrows():
                symbol = str(row["symbol"]).zfill(6)
                stocks[symbol] = StockInfo(
                    symbol,
                    str(row["name"]),
                    str(row.get("exchange", _exchange_for_symbol(symbol))),
                    _optional_date(row.get("list_date")),
                    _optional_date(row.get("delist_date")),
                    str(row.get("industry")) if row.get("industry") else None,
                    "Tushare.stock_basic",
                )
        return sorted(stocks.values(), key=lambda item: item.symbol)


def _row_to_bar(row: sqlite3.Row) -> HistoricalBar:
    return HistoricalBar(
        trading_date=date.fromisoformat(row["trading_date"]),
        symbol=row["symbol"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
        vwap=float(row["vwap"]) if row["vwap"] is not None else None,
        tradable=bool(row["tradable"]),
        limit_up_locked=bool(row["limit_up_locked"]),
        limit_down_locked=bool(row["limit_down_locked"]),
        amount=float(row["amount"]),
        up_limit=float(row["up_limit"]) if row["up_limit"] is not None else None,
        down_limit=float(row["down_limit"])
        if row["down_limit"] is not None
        else None,
        signal_open=float(row["signal_open"])
        if row["signal_open"] is not None
        else None,
        signal_high=float(row["signal_high"])
        if row["signal_high"] is not None
        else None,
        signal_low=float(row["signal_low"])
        if row["signal_low"] is not None
        else None,
        signal_close=float(row["signal_close"])
        if row["signal_close"] is not None
        else None,
    )


def _call_with_optional_timeout(function: Any, **arguments: str) -> Any:
    return _call_with_requests_timeout(function, **arguments)


def _call_with_requests_timeout(function: Any, **arguments: str) -> Any:
    """Apply a timeout to provider functions that hide requests internally."""

    try:
        import requests
    except ImportError:
        return function(**arguments)
    original = requests.sessions.Session.request

    def request_with_timeout(
        session: Any, method: str, url: str, **request_arguments: Any
    ) -> Any:
        if request_arguments.get("timeout") is None:
            request_arguments["timeout"] = 20
        try:
            return original(session, method, url, **request_arguments)
        except requests.exceptions.ProxyError:
            if request_arguments.get("proxies") or getattr(session, "proxies", None):
                raise
            # Windows registry proxies exist even without *_PROXY variables.
            # Try a direct route once, without mutating system settings or TLS.
            previous = session.trust_env
            session.trust_env = False
            try:
                return original(session, method, url, **request_arguments)
            finally:
                session.trust_env = previous

    requests.sessions.Session.request = request_with_timeout
    try:
        try:
            return function(**arguments, timeout=20)
        except TypeError as error:
            if "timeout" not in str(error):
                raise
            return function(**arguments)
    finally:
        requests.sessions.Session.request = original


def _column(frame: Any, *names: str) -> str:
    result = _optional_column(frame, *names)
    if result is None:
        raise ValueError(f"none of the required columns exist: {names}")
    return result


def _optional_column(frame: Any, *names: str) -> str | None:
    columns = {str(value): str(value) for value in frame.columns}
    for name in names:
        if name in columns:
            return columns[name]
    return None


def _infer_limits(
    symbol: str,
    name: str,
    trading_date: date,
    previous_close: float | None,
) -> tuple[float | None, float | None]:
    if previous_close is None:
        return None, None
    if "ST" in name.upper():
        ratio = Decimal("0.05")
    elif symbol.startswith(("300", "301")) and trading_date >= date(2020, 8, 24):
        ratio = Decimal("0.20")
    elif symbol.startswith(("688", "689")):
        ratio = Decimal("0.20")
    elif symbol.startswith(("4", "8", "9")):
        ratio = Decimal("0.30")
    else:
        ratio = Decimal("0.10")
    previous = Decimal(str(previous_close))
    up = (previous * (Decimal("1") + ratio)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    down = (previous * (Decimal("1") - ratio)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(up), float(down)


def _same_price(*values: float) -> bool:
    return max(values) - min(values) < 0.005


def _bounded_vwap(
    amount: float, volume: int, low: float, high: float
) -> float | None:
    """Normalize only sub-tick provider rounding; reject material mismatches."""

    if amount <= 0 or volume <= 0:
        return None
    value = amount / volume
    half_tick = 0.005
    if value < low:
        return low if low - value < half_tick else None
    if value > high:
        return high if value - high < half_tick else None
    return value


def _exchange_for_symbol(symbol: str) -> str:
    if symbol.startswith(("4", "8", "9")):
        return "BSE"
    if symbol.startswith(("5", "6", "688", "689")):
        return "SSE"
    return "SZSE"


def _is_a_share_symbol(symbol: str) -> bool:
    return (
        len(symbol) == 6
        and symbol.startswith(
            ("000", "001", "002", "003", "300", "301", "4", "6", "8", "9")
        )
        and not symbol.startswith(("200", "900"))
    )


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return date.fromisoformat(text)


def _optional_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return date.fromisoformat(text[:10])


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date_segments(
    start_date: date, end_date: date, segment_days: int
) -> Iterable[tuple[date, date]]:
    cursor = start_date
    while cursor <= end_date:
        segment_end = min(end_date, cursor + timedelta(days=segment_days - 1))
        yield cursor, segment_end
        cursor = segment_end + timedelta(days=1)
