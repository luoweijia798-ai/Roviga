"""Real bounded Tencent BSE fallback, bypassing unsupported start-year lookup."""
from __future__ import annotations

import math
import time
from datetime import date

URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"


def frame_from_payload(payload, symbol, start_date, end_date, *, adjusted=False):
    import pandas as pd
    if payload.get("code") != 0 or "bj" + symbol not in payload.get("data", {}):
        raise ValueError(f"{symbol}: Tencent does not acknowledge BSE identity")
    data = payload["data"]["bj" + symbol]
    # For an HFQ request the provider returns 'day' when no adjustment exists,
    # just as the pinned AkShare parser does. Never fall back to qfqday.
    key = "hfqday" if adjusted and "hfqday" in data else "day"
    if key not in data:
        raise ValueError(f"{symbol}: Tencent missing requested {key}")
    rows = []
    for values in data[key]:
        trading_date = date.fromisoformat(values[0])
        if not start_date <= trading_date <= end_date:
            continue  # Tencent may return older rows; do not import outside segment.
        if len(values) < 9:
            raise ValueError(f"{symbol}: Tencent missing turnover fields")
        row = dict(date=trading_date, open=float(values[1]), close=float(values[2]),
                   high=float(values[3]), low=float(values[4]), volume=float(values[5]),
                   amount=float(values[8]) * 10000)
        if not all(math.isfinite(row[k]) for k in row if k != "date"):
            raise ValueError(f"{symbol}: Tencent non-finite OHLCV")
        if (row["low"] <= 0 or row["high"] < max(row["open"], row["close"])
                or row["low"] > min(row["open"], row["close"])
                or row["volume"] < 0 or row["amount"] < 0):
            raise ValueError(f"{symbol}: Tencent invalid OHLCV")
        if not adjusted and row["volume"] > 0:
            # The pinned provider implementation documents BSE volume in lots
            # and amount in 10,000 yuan. Require raw VWAP to corroborate units.
            vwap = row["amount"] / (row["volume"] * 100)
            if not row["low"] - 0.005 <= vwap <= row["high"] + 0.005:
                raise ValueError(f"{symbol}: Tencent volume/amount units fail raw VWAP validation on {trading_date}: "
                                 f"vwap={vwap}, low={row['low']}, high={row['high']}, volume_lots={row['volume']}, amount_yuan={row['amount']}")
        rows.append(row)
    frame = pd.DataFrame(rows, columns=("date", "open", "high", "low", "close", "volume", "amount"))
    if frame["date"].duplicated().any():
        raise ValueError(f"{symbol}: Tencent duplicate trading dates")
    return frame.sort_values("date").reset_index(drop=True)


def fetch_tencent_bse(*, symbol: str, start_date: str, end_date: str, timeout=20):
    import requests
    if not symbol.startswith(("4", "8", "92")) or len(symbol) != 6:
        raise ValueError("Tencent BSE fallback requires a BSE symbol")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if (end - start).days > 366:
        raise ValueError("Tencent BSE history must be segmented (maximum 367 calendar days)")
    frames = []
    for adjust in ("", "hfq"):
        if adjust:
            time.sleep(0.5)
        response = requests.get(URL, params={"param":
            f"bj{symbol},day,{start},{end},640,{adjust}"}, timeout=timeout)
        response.raise_for_status()
        frames.append(frame_from_payload(response.json(), symbol, start, end, adjusted=bool(adjust)))
    if frames[0].empty:
        raise RuntimeError(f"{symbol}: Tencent empty segment is not verified absence of data")
    if set(frames[0].date) != set(frames[1].date):
        raise ValueError(f"{symbol}: Tencent raw/HFQ date sets differ")
    return frames[0], frames[1], 100


def verify_overlap(raw, adjusted, persisted, symbol) -> None:
    """Do not splice different HFQ conventions into a persisted signal series."""
    raw_by_date = {str(r.date): r for _, r in raw.iterrows()}
    adjusted_by_date = {str(r.date): r for _, r in adjusted.iterrows()}
    for old in persisted:
        day = old["trading_date"]
        if day not in raw_by_date or day not in adjusted_by_date:
            raise ValueError(f"{symbol}: source-switch overlap missing {day}")
        row, adj = raw_by_date[day], adjusted_by_date[day]
        if (any(abs(row[k]-old[k]) > .005 for k in ("open", "high", "low", "close"))
                or int(row.volume * 100) != old["volume"] or abs(row.amount-old["amount"]) > 51):
            raise ValueError(f"{symbol}: source-switch raw units/prices conflict on {day}")
        if any(old["signal_"+k] is None or abs(adj[k]-old["signal_"+k]) > .005
               for k in ("open", "high", "low", "close")):
            raise ValueError(f"{symbol}: source-switch HFQ convention conflicts on {day}; retain for factor reconciliation")
