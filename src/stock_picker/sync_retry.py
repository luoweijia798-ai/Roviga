"""Persistent bounded retry policy; deferred rows stay failed and auditable."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone


def fingerprint(stock, start, end) -> str:
    # A changed verified identity/range re-opens review, not a changed timestamp.
    values = (stock.symbol, stock.exchange, str(stock.list_date), str(stock.delist_date),
              stock.source, str(start), str(end), "phase4-acceptance-v1")
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def eligible(cache, stock, start, end, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    with cache.connect() as c:
        row = c.execute("SELECT * FROM sync_retry_policy WHERE symbol=?", (stock.symbol,)).fetchone()
    if not row or row["fingerprint"] != fingerprint(stock, start, end):
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
