"""Frozen, read-only historical acceptance. Never invokes a backtest."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from .data_audit import RealMarketDataAuditor
from .data_audit import _missing_ranges, stock_active_interval
from .real_market import PHASE4_START, SQLiteMarketCache, _ClosingConnection

ACCEPTANCE_END = date(2026, 9, 30)


class SnapshotCache(SQLiteMarketCache):
    """No schema initialization or audit metadata writes on the frozen copy."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro",
                                     uri=True, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def save_audit(self, payload: dict[str, object]) -> None:
        payload["report_kind"] = "preaudit"
        payload["formal_gate_eligible"] = False


def freeze_database(source: Path, destination: Path, *, progress=None) -> dict[str, object]:
    """SQLite online backup includes committed WAL data, not a raw file copy."""
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("snapshot destination must be a new, separate file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as live:
        # Pin a WAL read version before chunked backup. Without this, frequent
        # downloader commits may repeatedly restart the backup and starve it.
        live.execute("BEGIN")
        live.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        with closing(sqlite3.connect(destination)) as frozen:
            live.backup(frozen, pages=4096, sleep=0.05, progress=progress)
            frozen.execute("PRAGMA journal_mode=DELETE")
        live.rollback()
    digest = hashlib.sha256()
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    cache = SnapshotCache(destination)
    return {"id": "sha256:" + digest.hexdigest(), "path": str(destination.resolve()),
            "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
            "method": "sqlite_online_backup", "data_revision": cache.data_revision}


def verify_snapshot(path: Path, identity: dict) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != identity["id"]:
        raise ValueError("frozen snapshot content changed; cannot reuse its identity")


def admission_report(cache: SnapshotCache, audit: dict, snapshot: dict,
                     evidence: dict | None = None) -> dict:
    """Per-security coverage plus explicit unknowns; maximum date is not proof."""
    evidence = evidence or {}
    start, end = audit["requested_start"], audit["requested_end"]
    calendar = evidence.get("calendar", {})
    calendar_covers = (calendar.get("verified_through", "") >= end
                       and bool(calendar.get("dates")))
    blockers, warnings = [], []

    def block(symbol, first, last, reason, plan, **details):
        blockers.append(dict(symbol=symbol, start=first, end=last, reason=reason,
                             treatment_plan=plan, **details))

    with cache.connect() as c:
        stocks = [dict(r) for r in c.execute("SELECT * FROM stocks ORDER BY symbol")]
        statuses = {r["symbol"]: dict(r) for r in c.execute("SELECT * FROM symbol_sync_status")}
        benchmark_dates = {name: {r[0] for r in c.execute(
            "SELECT trading_date FROM benchmarks WHERE name=? AND trading_date BETWEEN ? AND ?",
            (name, start, end))} for name in ("CSI300", "CSI1000")}
        reference = sorted({d for d in calendar.get("dates", []) if start <= d <= end}
                           if calendar_covers else set().union(*benchmark_dates.values()))
        if not calendar_covers:
            block("ALL", start, end, "independent_calendar_unverified",
                  "Fetch independently sourced exchange trading sessions; union of index dates is provisional only")
        else:
            warnings.append("Independent Sina calendar corroborates sessions; retain official exchange calendar reconciliation before final acceptance")
        benchmarks = {}
        for name, present in benchmark_dates.items():
            missing = set(reference) - present
            unexpected = sorted(present - set(reference))
            invalid = [dict(r) for r in c.execute("SELECT trading_date,close FROM benchmarks "
                "WHERE name=? AND trading_date BETWEEN ? AND ? AND (close IS NULL OR close<=0)", (name, start, end))]
            ranges = _missing_ranges(reference, missing)
            benchmarks[name] = {"rows": len(present), "expected_sessions": len(reference),
                "first": min(present) if present else None, "last": max(present) if present else None,
                "missing_ranges": ranges, "unexpected_dates": unexpected, "invalid_rows": invalid,
                "session_check_passed": calendar_covers and not missing and not unexpected and not invalid}
            for r in ranges:
                block(name, r["start"], r["end"], "missing_benchmark_sessions", "Re-download real index series and reconcile calendar", sessions=r["sessions"])
            for d in unexpected:
                block(name, d, d, "unexpected_benchmark_session", "Verify official calendar and raw index source")
            for r in invalid:
                block(name, r["trading_date"], r["trading_date"], "invalid_benchmark_close", "Verify and replace only from corroborated source")
        categories = Counter({"real_history_complete": 0, "segment_exempt": 0,
                              "whole_interval_exempt": 0, "missing_or_conflicting": 0})
        outside_review, per_stock = [], []
        for stock in stocks:
            symbol = stock["symbol"]
            listing, delisting = stock["list_date"], stock["delist_date"]
            status = statuses.get(symbol, {})
            observed = {r[0] for r in c.execute("SELECT trading_date FROM bars WHERE symbol=? "
                "AND trading_date BETWEEN ? AND ?", (symbol, start, end))}
            active_first, active_last = stock_active_interval(stock, date.fromisoformat(start), date.fromisoformat(end))
            active_start, active_end = str(active_first), str(active_last)
            expected = [d for d in reference if active_start <= d <= active_end]
            missing = set(expected) - observed
            ranges = _missing_ranges(expected, missing)
            outside = active_start > active_end
            source_review = evidence.get("stocks", {}).get(symbol, {})
            if outside:
                key = "sh_retired_metadata" if stock["exchange"] == "SSE" else "retired_metadata"
                proof = evidence.get(key, {}).get("rows", {}).get(symbol, {})
                independent = (delisting and proof.get("delist_date") == delisting)
                if listing and listing > end:
                    independent = source_review.get("official_listing_date") == listing
                category = "whole_interval_exempt" if independent and not observed else "missing_or_conflicting"
                outside_review.append({"symbol": symbol, "category": category,
                    "list_date": listing, "delist_date": delisting, "bars_in_interval": len(observed),
                    "metadata_source": stock["source"], "independent_metadata": proof,
                    "evidence_verified": bool(independent), "counted_as_complete_market_history": False})
                if category == "missing_or_conflicting":
                    block(symbol, start, end, "range_exemption_unverified_or_conflicting",
                          "Reconcile fresh exchange metadata and raw history; retain stock, do not infer absence")
            else:
                category = "real_history_complete" if (listing and not missing and observed
                    and status.get("status") == "complete") else "missing_or_conflicting"
                if not listing:
                    block(symbol, start, end, "unknown_listing_date",
                          "Fetch exchange listing event and historical identity; pre-listing gaps remain provisional")
                for r in ranges:
                    block(symbol, r["start"], r["end"], "unexplained_sessions",
                          "Verify listing, suspension/resumption and delisting events; re-fetch only genuine gaps, never fill prices",
                          sessions=r["sessions"], provisional_without_listing=not bool(listing))
                if status.get("status") != "complete":
                    block(symbol, max(start, status.get("synced_through") or active_start), active_end,
                          "sync_incomplete", "Recover verified source or request authorized data access; keep failed ledger",
                          last_error=status.get("last_error"), source_review=source_review if stock["exchange"] == "BSE" else
                          {k: v for k, v in source_review.items() if k != "raw_rows"})
            categories[category] += 1
            per_stock.append({"symbol": symbol, "exchange": stock["exchange"], "category": category,
                "list_date": listing, "delist_date": delisting, "first": min(observed) if observed else None,
                "last": max(observed) if observed else None, "row_count": len(observed),
                "expected_sessions": len(expected), "missing_count": len(missing), "missing_ranges": ranges,
                "source": status.get("source"), "sync_status": status.get("status"),
                "complete_status_is_not_audit_pass": True})
        extra = [dict(r) for r in c.execute("SELECT symbol,trading_date FROM bars WHERE trading_date BETWEEN ? AND ? "
            "AND (signal_open IS NULL OR signal_high IS NULL OR signal_low IS NULL OR signal_close IS NULL)", (start, end))]
        for r in extra:
            block(r["symbol"], r["trading_date"], r["trading_date"], "missing_adjusted_price",
                  "Fetch actual HFQ factor/price, verify as-of availability, never substitute raw silently")
        classification_rows = c.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
        classification_historical = c.execute("SELECT COUNT(*) FROM classifications WHERE available_from<=?", (start,)).fetchone()[0]
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        quarantines = [dict(r) for r in c.execute("SELECT * FROM provider_quarantine")] if "provider_quarantine" in tables else []
        deferred = [dict(r) for r in c.execute("SELECT * FROM sync_retry_policy")] if "sync_retry_policy" in tables else []
    for r in audit["anomalies"]["rows"]:
        if start <= r["trading_date"] <= end:
            plan = ("Verify historical ST/IPO/board/delisting rules and ex-right reference price; obtain exact point-in-time limits"
                    if "limit" in r["reason"] else "Reconcile raw turnover units/OHLC and actual amount/volume; preserve conflicting rows")
            block(r["symbol"], r["trading_date"], r["trading_date"], r["reason"], plan)
    for r in audit["duplicates"]["rows"]:
        block(r["symbol"], r["trading_date"], r["trading_date"], "duplicate_bar", "Resolve source provenance before any deduplication")
    for r in audit["stock_date_conflicts"]:
        block(r["symbol"], r["first_bar"], r["last_bar"], "listing_metadata_conflict",
              "Verify exchange events and retain original rows in quarantine, not delete stock", evidence=r)
    for r in quarantines:
        if r["review_status"] != "approved":
            block(r["symbol"], r["trading_date"], r["trading_date"], "quarantine_not_formally_approved",
                  "Review saved original weekend echo and official final-session evidence; do not silently approve", evidence=json.loads(r["evidence"]))
    # Current inventory + retained delists is not proof of a point-in-time universe.
    for reason, plan in (
        ("historical_universe_unverified", "Reconcile exchange historical listing/delisting/renaming events, BSE and NEEQ identities; archive evidence with availability dates"),
        ("classification_causality_unverified", "Obtain effective/available-dated industry and membership history; current snapshots cannot be backdated"),
        ("adjustment_causality_unverified", "Reconcile source HFQ factor history and publication dates, cross-source normalization and source switches; HFQ label alone is insufficient"),
        ("exact_limit_and_suspension_history_unverified", "Obtain historical risk-warning states, corporate actions, suspension sessions and exact price limits"),
    ):
        block("ALL", start, end, reason, plan)
    warnings.append("CSI300/CSI1000 checks verify index price series, not historical constituent membership; constituent scope remains unverified")
    for symbol, review in evidence.get("stocks", {}).items():
        listing = review.get("official_listing_date")
        if (review.get("exchange") == "BSE" and listing and listing <= end
                and listing < "2024-04-22" and review.get("old_code") is None):
            block(symbol, max(start, listing), min(end, "2025-10-08"), "historical_code_mapping_unverified",
                  "Obtain official old/new code correspondence and switch-effective dates; current 920 quote support does not prove historical identity")
    if not audit["passed"]:
        block("ALL", start, end, "existing_audit_failed", "Resolve all original audit failures in preaudit/audit_report.json; no manual gate override")
    for symbol, validation in evidence.get("recovery_validation", {}).items():
        if validation.get("error"):
            block(symbol, validation.get("failure_trading_date") or max(start, evidence["stocks"][symbol].get("official_listing_date") or start),
                  validation.get("failure_trading_date") or end,
                  "backup_source_validation_failed", "Retain failed ledger; verify original turnover units before source switch", evidence=validation)
        for day in validation.get("hfq_overlap_mismatches", []):
            block(symbol, day, day, "cross_source_hfq_conflict", "Reconcile factor normalization and publication dates; do not rescale prices by guessing", evidence=validation)
        for day in validation.get("raw_unit_overlap_mismatches", []):
            block(symbol, day, day, "cross_source_raw_conflict", "Reconcile original OHLCV/amount and security identity before merge", evidence=validation)
    reasons = Counter(r["reason"] for r in blockers)
    return {"report_kind": "phase5a_admission_preaudit", "generated_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_start": start, "acceptance_end": end, "continuous_update_goal": "through latest available real session; October tracked separately",
        "universe": "retained Shanghai/Shenzhen historical A shares and delisted securities plus BSE; no options/ShortAlpha",
        "snapshot": snapshot, "formal_backtest_ready": False, "gate_released": False,
        "decision": "BLOCKED: incomplete coverage and unverified causal provenance; no returns computed",
        "inventory_count": len(stocks), "market_history_categories": dict(categories),
        "stock_coverage": per_stock, "outside_interval_review": outside_review,
        "benchmark_coverage": benchmarks, "calendar": {k:v for k,v in calendar.items() if k!='dates'},
        "causal_requirements": {"historical_universe_verified": False, "classification_history_verified": False,
            "hfq_factor_availability_verified": False, "classification_rows": classification_rows,
            "classification_rows_available_at_start": classification_historical},
        "passed_items": audit["passed_items"], "warnings": warnings,
        "blocker_summary": dict(reasons), "blockers": blockers,
        "provider_quarantine": quarantines, "persistent_retry_dispositions": deferred,
        "source_review_file": "source_review.json",
        "source_review_sha256": hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
        "legacy_audit_passed": audit["passed"]}


def write_admission(run: Path, report: dict) -> None:
    (run / "phase5a_admission_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "blockers.json").write_text(json.dumps(report["blockers"], ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "outside_interval_review.json").write_text(json.dumps(report["outside_interval_review"], ensure_ascii=False, indent=2), encoding="utf-8")
    text = ["Roviga Phase 5A 首轮准入预审计", f"验收区间：{report['acceptance_start']} 至 {report['acceptance_end']}",
            f"快照：{report['snapshot']['id']}", "股票池：沪深历史 A 股、退市股票及北交所；不含期权或 ShortAlpha。",
            f"库存数量：{report['inventory_count']}；逐股分类：{report['market_history_categories']}",
            "正式回测条件：不具备。门禁：未解除。未计算任何收益。", "基准逐日核对："]
    text += [f"{name}: {data}" for name, data in report["benchmark_coverage"].items()]
    text += ["通过项：" + ", ".join(report["passed_items"]), "警告项："] + report["warnings"]
    text += ["阻塞汇总："] + [f"{k}: {v}" for k,v in report["blocker_summary"].items()]
    text += ["逐股票/基准/全市场的日期、原因、处理方案详见 blockers.json。",
             "85只原区间外记录及后来确认的区间外股票逐项证据详见 outside_interval_review.json。",
             "原始预审计详见 preaudit/audit_report.json；专项接口和原始行情证据见 source_review.json。",
             "停牌和未知上市日期造成的缺口未经解释，不能直接称为行情丢失或补造。",
             "十月份增量与固定历史验收隔离；快照不会随生产更新而移动。"]
    (run / "phase5a_admission_report.txt").write_text("\n".join(text), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/a_share_201506_present.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("outputs/phase4_acceptance"))
    parser.add_argument("--snapshot", type=Path, help="reuse a previously frozen snapshot")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--reuse-audit", action="store_true")
    args = parser.parse_args()
    run = args.snapshot.parent if args.snapshot else args.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    identity = run / "snapshot_identity.json"
    snapshot = json.loads(identity.read_text(encoding="utf-8")) if args.snapshot else freeze_database(args.cache, run / "snapshot.sqlite")
    if args.snapshot:
        verify_snapshot(args.snapshot, snapshot)
    print(json.dumps({"snapshot": snapshot}, ensure_ascii=False), flush=True)
    cache = SnapshotCache(Path(snapshot["path"]))
    audit = (json.loads((run / "preaudit/audit_report.json").read_text(encoding="utf-8")) if args.reuse_audit else
             RealMarketDataAuditor(cache).run(start_date=PHASE4_START, end_date=ACCEPTANCE_END, output=run / "preaudit").payload)
    identity.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else {}
    if args.evidence and args.evidence.resolve() != (run / "source_review.json").resolve():
        (run / "source_review.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    report = admission_report(cache, audit, snapshot, evidence)
    write_admission(run, report)
    print(json.dumps({"report": str(run.resolve()), "passed": audit["passed"],
                      "blockers": audit["blockers"], "anomalies": audit["anomalies"]["count"],
                      "admission_blockers": report["blocker_summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
