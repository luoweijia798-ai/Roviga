"""Bounded raw-source evidence for nine BSE conflicts and reproducible samples."""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from .phase4_acceptance import SnapshotCache
from .real_market import AkShareAdapter
from .security_master import capture_responses

BSE_CASES = {"920014": "2026-09-01", "920396": "2026-09-10", "920639": "2026-09-09",
             "920765": "2026-09-01", "920833": "2026-09-01", "920970": "2026-09-01",
             "920371": "2026-09-04", "920375": "2026-09-11", "920701": "2026-09-28"}


def investigate(run: Path, snapshot: Path) -> dict:
    import requests
    from akshare.stock.cons import hk_js_decode, zh_sina_a_stock_hist_url, zh_sina_a_stock_hfq_url
    from py_mini_racer import MiniRacer
    from contextlib import closing
    cache = SnapshotCache(snapshot)
    adapter = AkShareAdapter(max_attempts=1, request_interval=.5)
    report = {"bse": {}, "sina_samples": {}, "errors": [], "response_refs": []}
    def get(url, **params):
        with capture_responses(run / "raw_probes") as refs:
            r = adapter._request(requests.get, url=url, **({"params": params} if params else {}))
            r.raise_for_status()
        report["response_refs"].extend(refs)
        return r
    def save():
        (run / "source_semantics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for symbol, day in BSE_CASES.items():
        item = {"symbol": symbol, "sample_date": day, "status": "blocked_pending_scope_and_factor_evidence"}
        with cache.connect() as c:
            stored = c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date=?", (symbol, day)).fetchone()
        item["stored"] = dict(stored) if stored else None
        for adjust in ("", "hfq", "qfq"):
            try:
                payload = get("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                    param=f"bj{symbol},day,2026-09-01,2026-09-30,640,{adjust}").json()
                value = payload.get("data", {}).get("bj"+symbol, {})
                key = next((k for k in ("hfqday", "qfqday", "day") if k in value), None)
                rows = value.get(key, [])
                selected = next((r for r in rows if r[0] == day), None)
                item[adjust or "unadjusted"] = {"response_key": key, "rows": rows,
                    "selected_raw_row": selected, "adjustment_metadata": {k:v for k,v in value.items() if k not in {"day", "hfqday", "qfqday", "qt"}},
                    "conversion": "OHLC from requested price mode; shares=volume_lots*100; yuan=amount_10k*10000"}
                if adjust == "" and selected:
                    volume, amount = float(selected[5])*100, float(selected[8])*10000
                    item["unadjusted"]["diagnostic_vwap_not_execution_substitute"] = amount/volume if volume else None
                    item["unadjusted"]["raw_matches_stored_ohlc"] = bool(stored and
                        all(abs(float(selected[i])-stored[k]) <= .005 for i,k in ((1,"open"),(2,"close"),(3,"high"),(4,"low"))))
            except Exception as error:
                item[adjust or "unadjusted"] = {"error": f"{type(error).__name__}: {error}"}
        try:
            payload = get("https://datacenter-web.eastmoney.com/api/data/v1/get", reportName="RPT_SHAREBONUS_DET",
                columns="ALL", filter=f'(SECURITY_CODE="{symbol}")', pageSize="500", pageNumber="1").json()
            item["equity_events"] = payload
            if (payload.get("result") or {}).get("pages", 1) > 1:
                item["events_warning"] = "additional pages not fetched; incomplete evidence"
        except Exception as error:
            item["equity_events"] = {"error": f"{type(error).__name__}: {error}"}
        if symbol in {"920371", "920375", "920701"}:
            try:
                item["block_trades"] = get("https://datacenter-web.eastmoney.com/api/data/v1/get", reportName="RPT_DATA_BLOCKTRADE",
                    columns="ALL", filter=f'(SECURITY_CODE="{symbol}")(TRADE_DATE=\'{day}\')', pageSize="500", pageNumber="1").json()
            except Exception as error:
                item["block_trades"] = {"error": f"{type(error).__name__}: {error}"}
            item["next_step"] = "Verify whether turnover includes negotiated/block/off-auction trades; obtain comparable regular-auction OHLC and turnover. No estimated VWAP."
        else:
            item["next_step"] = "Reconcile equity-event effective/publication dates and each source HFQ normalization; verify overlapping segments before targeted repair. Do not guess rescaling."
        report["bse"][symbol] = item; save()
        print(f"semantics {symbol}: raw modes/events evidence saved", flush=True)
    # Small reproducible samples only, not a universe history re-download.
    for symbol, day in (("000938", "2015-06-01"), ("002759", "2021-03-01"), ("300366", "2021-03-01")):
        prefix = "sh" if symbol.startswith("6") else "sz"
        item = {"sample_date": day}
        with cache.connect() as c:
            row = c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date=?", (symbol, day)).fetchone()
            item["stored"] = dict(row) if row else None
        try:
            response = get(zh_sina_a_stock_hist_url.format(prefix+symbol))
            encoded = response.text.split("=",1)[1].split(";",1)[0].strip().strip('"')
            with closing(MiniRacer()) as decoder:
                decoder.eval(hk_js_decode); rows = decoder.call("d", encoded)
            item["decoded_raw_rows"] = [r for r in rows if str(r.get("date", ""))[:10] == day]
            factors = get(zh_sina_a_stock_hfq_url.format(prefix+symbol)).text.split("=",1)[1].strip()
            item["provider_factors"] = json.JSONDecoder().raw_decode(factors)[0]
            with cache.connect() as c:
                row = c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date=?", (symbol, day)).fetchone()
                item["stored"] = dict(row) if row else None
            item["conversion"] = "Sina volume in shares, amount in yuan; causal dated HFQ multiplication; no capital-date outer merge or forward fill"
        except Exception as error:
            item["error"] = f"{type(error).__name__}: {error}"
            # Do not bypass Windows native-library policy. A separate permitted
            # HTTP source can corroborate a bounded sample; it does not decode
            # or silently replace the blocked Sina payload.
            try:
                payload = get("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                    param=f"{prefix}{symbol},day,{day},{day},640,").json()
                data = payload.get("data", {}).get(prefix+symbol, {})
                sample = next((r for r in data.get("day", []) if r[0] == day), None)
                item["alternate_tencent_raw_sample"] = sample
                item["alternate_conversion"] = "shares=volume_lots*100; yuan=amount_10k*10000 when provider turnover columns exist; no inferred replacement"
            except Exception as fallback_error:
                item["alternate_error"] = str(fallback_error)
        report["sina_samples"][symbol] = item; save()
    return report
