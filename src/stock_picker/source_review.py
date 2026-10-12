"""Bounded live source investigation; evidence only, never writes market bars."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .phase4_acceptance import ACCEPTANCE_END, SnapshotCache
from .real_market import AkShareAdapter
from .sina_archive import fetch_sina_archive
from .sina_archive import isolate_retired_terminal_duplicate
from .tencent_bse import fetch_tencent_bse
from .real_market import SQLiteMarketCache, StockInfo


def investigate(snapshot: Path, output: Path) -> dict[str, object]:
    import akshare as ak
    import requests
    cache = SnapshotCache(snapshot)
    adapter = AkShareAdapter(max_attempts=1, request_interval=0.5)
    evidence: dict[str, object] = {"generated_at": datetime.now(timezone.utc).isoformat(),
                                 "stocks": {}, "global_probes": {}}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    def probe(name, function, **kwargs):
        try:
            result = adapter._request(function, **kwargs)
            return result, None
        except Exception as error:
            return None, {"probe": name, "type": type(error).__name__, "error": str(error)[:700]}

    calendar, error = probe("Sina trading calendar", ak.tool_trade_date_hist_sina)
    evidence["calendar"] = ({"source": "AkShare.tool_trade_date_hist_sina",
                             "url": "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt",
                             "dates": [str(d) for d in calendar.trade_date],
                             "verified_through": str(calendar.trade_date.max())}
                            if error is None else {"error": error})
    for url in ("https://www.bse.cn/service/code_mapping.html",
                "https://www.bseinfo.net/service/code_mapping.html"):
        def read_url(url, timeout=20):
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        response, error = probe(url, read_url, url=url)
        evidence["global_probes"][url] = error or {"status": response.status_code,
             "sha256": hashlib.sha256(response.content).hexdigest()}
    inventory, error = probe("BSE inventory", ak.stock_info_bj_name_code)
    bse_dates = {} if error else {str(r["证券代码"]).zfill(6): str(r["上市日期"])
                                for _, r in inventory.iterrows()}
    evidence["global_probes"]["bse_inventory"] = error or {"count": len(inventory),
            "source": "https://www.bse.cn/nqxxController/nqxxCnzq.do"}
    # All 85 out-of-range decisions must retain an independent current metadata
    # check, not just a suffix in the sync ledger.
    metadata, error = probe("SZSE retired inventory", ak.stock_info_sz_delist, symbol="终止上市公司")
    retired = {} if error else {str(r["证券代码"]).zfill(6): {
        "list_date": str(r["上市日期"]), "delist_date": str(r["终止上市日期"])}
        for _, r in metadata.iterrows()}
    evidence["retired_metadata"] = {"source": "https://www.szse.cn/api/report/ShowReport",
                                    "rows": retired, "error": error}
    sh_metadata, error = probe("SSE retired inventory", ak.stock_info_sh_delist, symbol="全部")
    evidence["sh_retired_metadata"] = {
        "source": "https://query.sse.com.cn/commonQuery.do", "error": error,
        "rows": {} if error else {str(r["公司代码"]).zfill(6): {
            "list_date": str(r.get("上市日期", "")),
            "delist_date": str(r["暂停上市日期"])} for _, r in sh_metadata.iterrows()}}
    save()
    with cache.connect() as c:
        failed = c.execute("SELECT s.*, t.synced_through, t.last_error FROM stocks s "
                           "JOIN symbol_sync_status t USING(symbol) WHERE t.status='failed'").fetchall()
    for row in failed:
        symbol = row["symbol"]
        item = {"symbol": symbol, "exchange": row["exchange"],
                "list_date": row["list_date"], "delist_date": row["delist_date"],
                "metadata_source": row["source"], "ledger_error": row["last_error"]}
        if row["exchange"] == "BSE":
            start = max(date(2015, 6, 1), date.fromisoformat(row["synced_through"]) + timedelta(days=1)) if row["synced_through"] else date(2015, 6, 1)
            item.update(request_start=str(start), request_end=str(ACCEPTANCE_END),
                        eastmoney_secid="0." + symbol, tencent_symbol="bj" + symbol,
                        official_listing_date=bse_dates.get(symbol),
                        old_code=None, code_mapping_status="unverified: official mapping page unavailable",
                        sina_support=False)
            raw, error = probe("AkShare.Eastmoney", ak.stock_zh_a_hist, symbol=symbol,
                              start_date=start.strftime("%Y%m%d"), end_date="20260930", adjust="")
            item["eastmoney_probe"] = error or {"rows": len(raw), "empty_is_not_no_data": True}
            # Do not call AkShare's Tencent helper: its unsupported start-year
            # helper crashes before the actual BSE request. Inspect bounded raw
            # response instead; do not ingest unverified units/adjustments.
            def tencent(symbol, timeout=20):
                response = requests.get("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                    params={"param": f"bj{symbol},day,2026-09-18,2026-09-30,100,"}, timeout=timeout)
                response.raise_for_status()
                return response.json()
            payload, error = probe("Tencent raw BSE", tencent, symbol=symbol)
            item["tencent_probe"] = error or {"payload": payload,
                    "ingested": False, "note": "units and causal adjustments not verified"}
            item["tushare"] = "not probed: authenticated permission/token not supplied by task"
        else:
            frames, error = probe("Sina KLC+HFQ", fetch_sina_archive, symbol="sz" + symbol,
                                 start_date="2015-06-01", end_date="2026-09-30")
            if error:
                item["archive_error"] = error
            else:
                raw, adjusted, _ = frames
                rows = raw.astype(str).to_dict("records")
                item.update(raw_rows=rows, raw_sha256=hashlib.sha256(
                    json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                    first_raw=str(raw.date.min()), last_raw=str(raw.date.max()),
                    independent_retired_metadata=retired.get(symbol))
        evidence["stocks"][symbol] = item
        save()
        print(f"source review {symbol}: evidence saved", flush=True)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate", action="store_true", help="validate recovered sources against frozen real rows")
    parser.add_argument("--symbols", help="comma-separated validation subset")
    args = parser.parse_args()
    if args.validate:
        validate_recovery(args.snapshot, args.output, set(args.symbols.split(",")) if args.symbols else None)
    else:
        investigate(args.snapshot, args.output)


def validate_recovery(snapshot: Path, evidence_path: Path, symbols=None) -> None:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    cache = SnapshotCache(snapshot)
    quarantine_cache = SQLiteMarketCache(evidence_path.parent / "source_validation.sqlite")
    adapter = AkShareAdapter(max_attempts=1, request_interval=0.5)
    validations = evidence.get("recovery_validation", {}).copy()
    for symbol, item in evidence["stocks"].items():
        if symbols is not None and symbol not in symbols:
            continue
        try:
            if item["exchange"] == "BSE":
                listing = date.fromisoformat(item["official_listing_date"])
                # Also verify the newly listed October stock, without changing
                # the fixed September historical admission decision.
                end = date.today() if listing > ACCEPTANCE_END else ACCEPTANCE_END
                start = max(listing, date(2026, 9, 1))
                raw, adjusted, multiplier = adapter._request(fetch_tencent_bse,
                    symbol=symbol, start_date=str(start), end_date=str(end))
                overlaps, mismatches, adjusted_mismatches = 0, [], []
                with cache.connect() as c:
                    for _, row in raw.iterrows():
                        old = c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date=?",
                                        (symbol, str(row.date))).fetchone()
                        if old:
                            overlaps += 1
                            if (any(abs(float(row[k]) - old[k]) > .005 for k in ("open", "high", "low", "close"))
                                or int(row.volume * multiplier) != old["volume"]
                                or abs(row.amount - old["amount"]) > 51):
                                mismatches.append(str(row.date))
                            adj = adjusted[adjusted.date == row.date].iloc[0]
                            if old["signal_close"] is None or abs(adj.close-old["signal_close"]) > .005:
                                adjusted_mismatches.append(str(row.date))
                validations[symbol] = dict(provider="Tencent.BSE", rows=len(raw), first=str(raw.date.min()),
                    last=str(raw.date.max()), historical_interval_applicable=listing <= ACCEPTANCE_END,
                    overlap_rows=overlaps, raw_unit_overlap_mismatches=mismatches,
                    hfq_overlap_mismatches=adjusted_mismatches, production_ingested=False)
            else:
                metadata = item["independent_retired_metadata"]
                stock = StockInfo(symbol, symbol, "SZSE", list_date=date.fromisoformat(metadata["list_date"]),
                    delist_date=date.fromisoformat(metadata["delist_date"]), source="AkShare.stock_info_sz_delist")
                raw, adj, _ = adapter._request(fetch_sina_archive, symbol="sz"+symbol,
                                              start_date="2015-06-01", end_date="2026-09-30")
                cleaned, _ = isolate_retired_terminal_duplicate(raw, adj, stock, quarantine_cache)
                validations[symbol] = dict(provider="Sina.KLC", raw_rows=len(raw), accepted_rows=len(cleaned),
                    final_session=str(cleaned.date.max()), delist_date=str(stock.delist_date),
                    quarantined_rows=len(raw)-len(cleaned), production_ingested=False)
        except Exception as error:
            match = re.search(r"on (\d{4}-\d{2}-\d{2})", str(error))
            validations[symbol] = {"error": f"{type(error).__name__}: {error}", "production_ingested": False,
                                   "failure_trading_date": match.group(1) if match else None}
        evidence["recovery_validation"] = validations
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"recovery validation {symbol}: {validations[symbol]}", flush=True)


if __name__ == "__main__":
    main()
