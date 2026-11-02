"""Persistent bounded retry policy; deferred rows stay failed and auditable."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone


def fingerprint(stock, start, end) -> str:
    # A changed verified identity/range re-opens review, not a changed timestamp.
    values = (stock.symbol, stock.exchange, str(stock.list_date), str(stock.delist_date),
              stock.source, str(start), str(end), "phase4-acceptance-v1")
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def eligible(cache, stock, start, end, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    with cache.connect() as c:
        row = c.execute("SELECT * FROM sync_retry_policy WHERE symbol=?", (stock.symbol,)).fetchone()
        previous = c.execute("SELECT status,requested_start,requested_end,last_error "
                             "FROM symbol_sync_status WHERE symbol=?", (stock.symbol,)).fetchone()
    if not row:
        return True
    if row["fingerprint"] != fingerprint(stock, start, end):
        # An incremental end-date extension must not reopen a reviewed error
        # in the earlier interval. The old fingerprint still proves unchanged
        # identity/source/start; a changed status error or explicit clear can
        # reopen it. Temporary cooldown failures retain the old range behavior.
        if (row["disposition"] == "source_review_required" and previous
                and previous["status"] == "failed"
                and previous["requested_start"] == str(start)
                and previous["requested_end"] < str(end)
                and previous["last_error"]
                and str(previous["last_error"]).endswith(row["last_error"])
                and row["fingerprint"] == fingerprint(
                    stock, start, date.fromisoformat(previous["requested_end"]))):
            return False
        return True
    if row["disposition"] == "source_review_required":
        return False
    return now >= datetime.fromisoformat(row["next_retry_at"])


def failed(cache, stock, start, end, error, now=None) -> None:
    persistent = ("archived trading after documented delisting" in str(error)
                  or "raw VWAP outside daily range:" in str(error))
    if stock.exchange != "BSE" and not persistent:
        return
    now = now or datetime.now(timezone.utc)
    key = fingerprint(stock, start, end)
    with cache.connect() as c:
        previous = c.execute("SELECT * FROM sync_retry_policy WHERE symbol=?", (stock.symbol,)).fetchone()
        count = previous["consecutive_failures"] + 1 if previous and previous["fingerprint"] == key else 1
        disposition = "source_review_required" if persistent or count >= 3 else "cooldown"
        next_retry = now + timedelta(hours=min(6, 2 ** (count - 1)))
        c.execute("INSERT OR REPLACE INTO sync_retry_policy VALUES (?,?,?,?,?,?,?)",
                  (stock.symbol, key, count, next_retry.isoformat(), disposition,
                   str(error)[:1000], now.isoformat()))


def clear(cache, symbol) -> None:
    with cache.connect() as c:
        c.execute("DELETE FROM sync_retry_policy WHERE symbol=?", (symbol,))
