"""Read real Sina KLC bars without the unrelated retired-share-capital endpoint.

Decode with the pinned AKShare decoder; never forward-fill OHLCV, synthesize
sessions, or use future adjustment factors. Imports remain lazy/offline-safe.
"""
from __future__ import annotations

import json
import math
import time
from contextlib import closing
from datetime import date
from typing import Any


def archive_frames(rows: list[dict[str, Any]], factors: list[dict[str, Any]],
                   start_date: date, end_date: date) -> tuple[Any, Any, int]:
    import pandas as pd

    required = ("date", "open", "high", "low", "close", "volume", "amount")
    selected = [row for row in rows
                if start_date.isoformat() <= str(row.get("date", ""))[:10] <= end_date.isoformat()]
    if not selected:
        return pd.DataFrame(columns=required), pd.DataFrame(columns=required), 1
    if any(any(key not in row for key in required) for row in selected):
        raise ValueError("Sina archive missing required raw OHLCV/amount fields")
    raw = pd.DataFrame(selected)[list(required)].copy()
    raw["date"] = pd.to_datetime(raw["date"], utc=True).dt.date
    raw = raw.sort_values("date").reset_index(drop=True)
    if raw["date"].duplicated().any():
        raise ValueError("Sina archive contains duplicate trading dates")
    for key in required[1:]:
        raw[key] = pd.to_numeric(raw[key], errors="raise")
        if not raw[key].map(lambda value: math.isfinite(float(value))).all():
            raise ValueError(f"Sina archive non-finite {key}")
    dated_factors: dict[date, float] = {}
    for item in factors:
        effective = date.fromisoformat(str(item["d"])[:10])
        value = float(item["f"])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Sina archive invalid HFQ factor")
        if effective in dated_factors and dated_factors[effective] != value:
            raise ValueError("Sina archive conflicting HFQ factors")
        dated_factors[effective] = value
    ordered = sorted(dated_factors.items())
    adjusted = raw.copy()
    adjusted[["open", "high", "low", "close"]] = adjusted[["open", "high", "low", "close"]].astype(float)
    cursor = 0
    factor: float | None = None
    for index, row in raw.iterrows():
        while cursor < len(ordered) and ordered[cursor][0] <= row["date"]:
            factor = ordered[cursor][1]
            cursor += 1
        if factor is None:
            raise ValueError(f"Sina archive has no causal HFQ factor for {row['date']}")
        for field in ("open", "high", "low", "close"):
            adjusted.at[index, field] = round(float(row[field]) * factor, 2)
    # Raw volume is shares and amount is yuan, not inferred from prices.
    return raw, adjusted, 1


def fetch_sina_archive(*, symbol: str, start_date: str, end_date: str,
                       timeout: float = 20) -> tuple[Any, Any, int]:
    import requests
    from akshare.stock.cons import (
        hk_js_decode, zh_sina_a_stock_hist_url, zh_sina_a_stock_hfq_url,
    )
    from py_mini_racer import MiniRacer

    response = requests.get(zh_sina_a_stock_hist_url.format(symbol), timeout=timeout)
    response.raise_for_status()
    encoded = response.text.split("=", 1)[1].split(";", 1)[0].strip().strip('"')
    with closing(MiniRacer()) as decoder:
        decoder.eval(hk_js_decode)
        rows = decoder.call("d", encoded)
    if not isinstance(rows, list):
        raise ValueError("Sina archive decoder did not return a bar list")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if not any(start.isoformat() <= str(row.get("date", ""))[:10] <= end.isoformat()
               for row in rows):
        return archive_frames(rows, [], start, end)
    time.sleep(0.5)
    response = requests.get(zh_sina_a_stock_hfq_url.format(symbol), timeout=timeout)
    response.raise_for_status()
    payload = response.text.split("=", 1)[1].strip().rstrip(";")
    # The endpoint appends a JavaScript comment after its first JSON object.
    # Decode that object without eval or executing the trailing script.
    factors = json.JSONDecoder().raw_decode(payload)[0]["data"]
    return archive_frames(rows, factors, start, end)


def isolate_retired_terminal_duplicate(raw: Any, adjusted: Any, stock: Any,
                                       cache: Any) -> tuple[Any, Any]:
    """Quarantine one exact weekend echo; any other conflict remains an error.

    Preserve the original row in SQLite, never amend the exchange delist date.
    The quarantine is not formal audit approval.
    """
    if not stock.delist_date or raw.empty or max(raw.date) <= stock.delist_date:
        return raw, adjusted
    later = raw[raw.date > stock.delist_date]
    earlier = raw[raw.date < stock.delist_date]
    if (len(later) != 1 or earlier.empty or len(raw[raw.date == stock.delist_date])
            or stock.source not in {"AkShare.stock_info_sz_delist", "AkShare.stock_info_sh_delist"}):
        raise ValueError(f"{stock.symbol}: archived trading after documented delisting")
    echo, anchor = later.iloc[0], earlier.iloc[-1]
    fields = ("open", "high", "low", "close", "volume", "amount")
    if (echo.date.weekday() < 5 or (stock.delist_date - anchor.date).days > 7
            or any(float(echo[k]) != float(anchor[k]) for k in fields)):
        raise ValueError(f"{stock.symbol}: archived trading after documented delisting")
    evidence = {"original": {key: str(value) for key, value in echo.items()},
                "anchor": {key: str(value) for key, value in anchor.items()},
                "delist_date": stock.delist_date.isoformat(), "metadata_source": stock.source,
                "raw_source": "https://finance.sina.com.cn/realstock/company/" +
                              ("sh" if stock.exchange == "SSE" else "sz") + stock.symbol + "/hisdata/klc_kl.js",
                "reason": "one post-delisting weekend row exactly echoes final pre-delisting OHLCV+amount",
                "review_status": "isolated_not_formally_approved"}
    with cache.connect() as c:
        cache._invalidate_audit(c)
        c.execute("INSERT OR REPLACE INTO provider_quarantine VALUES (?,?,?,?,?)",
                  (stock.symbol, echo.date.isoformat(), "Sina.KLC", json.dumps(evidence),
                   "isolated_not_formally_approved"))
    return (raw[raw.date <= stock.delist_date].copy(),
            adjusted[adjusted.date <= stock.delist_date].copy())
