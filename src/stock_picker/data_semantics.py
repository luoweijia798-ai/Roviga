"""First-batch evidence accounting, without strategy execution or gate release."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from .data_audit import RealMarketDataAuditor, stock_active_interval, _missing_ranges
from .phase4_acceptance import SnapshotCache, admission_report, write_admission, verify_snapshot


def baseline_dependencies() -> dict:
    base = Path(__file__).parent
    dependencies = {
        "baseline_mode": "OPEN (existing BacktestConfig default; not changed)",
        "required_current": {
            "trading_date,symbol,exchange/code identity,lifecycle": "daily_snapshot, previous_bar, A-share pool validity, symbol tie break and T+1 session ordering",
            "signal_close and prior signal_close": "selector.py select_one/_is_eligible; models.py momentum; SQLiteHistoricalDataPortal.daily_snapshot",
            "volume,tradable": "selector minimum volume/rank and backtest entry/exit eligibility",
            "raw_open": "backtest opening equity, OPEN entry, stop/take-profit gap execution; risk entry price",
            "raw_high,raw_low": "backtest stop-loss/take-profit decisions and tracking; HistoricalBar validates OHLC",
            "raw_close": "equity marks, stop/take-profit signal prices, max-holding exit and tracking",
            "limit_up_locked,limit_down_locked": "PaperBroker rejects locked entries/exits; cannot assume false when unverified",
            "historical_board,ST/risk-warning,IPO/corporate-action reference": "adapter derives price limits/locks; current name is NOT past ST evidence",
            "cash,equity,exposure,entry_price,stop_price,realized_trade_state": "RiskManager.calculate_position/status; account-derived inputs, not new market factors",
        },
        "conditional_existing_mode": {"VWAP": "vwap plus comparable raw OHLC/amount/volume and trade-scope evidence; supported existing execution mode, not used by OPEN default"},
        "display_or_validation": {
            "amount,vwap in OPEN": "still retained and audited; turnover/VWAP validation failures are NOT erased or defaulted",
            "CSI300,CSI1000 close": "benchmark comparison and trailing regime labels; regime is not a selector or risk filter",
            "signal_open,signal_high,signal_low": "persisted and model-validated; present selector consumes adjusted close only",
            "name,current industry": "metadata/display; current name is also used by legacy inferred-limit code, so historical ST evidence remains required",
        },
        "reserved_not_baseline_gate": ["industry/concept rotation", "policy factors", "financial fundamentals", "historical index constituent selection"],
        "known_baseline_blockers": ["unverified historical pool/code events and BSE/selected-layer eligibility",
            "unverified adjustment publication/normalization", "historical ST/reference/limit-lock evidence", "unexplained active-session gaps"],
        "source_hashes": {name: hashlib.sha256((base/name).read_bytes()).hexdigest() for name in
            ("selector.py", "risk.py", "backtest.py", "trading.py", "historical.py", "real_market.py")},
        "notes": ["No field removed/defaulted and no strategy parameter changed.",
                  "Daily volume scope must be comparable across stocks because volume affects selector ranking; OPEN not using VWAP does not waive volume/eligibility correctness.",
                  "Known listing date is not proof of historical security identity or board membership.",
                  "Industry/concept/policy requirements must not block the unchanged baseline merely because an enhancement could use them."]}
    dependencies["observed_bar_attribute_reads"] = {}
    for name in ("selector.py", "backtest.py", "historical.py", "trading.py", "risk.py"):
        tree = ast.parse((base/name).read_text(encoding="utf-8"))
        dependencies["observed_bar_attribute_reads"][name] = sorted({n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in {"bar", "previous"}})
    return dependencies


def quality_flags(row) -> list[str]:
    """All applicable existing checks, not the old SQL CASE's first reason only."""
    r = row; flags = []
    if min(r[k] for k in ("open","high","low","close")) <= 0: flags.append("non_positive_price")
    if r["high"] < max(r["open"],r["close"]) or r["low"] > min(r["open"],r["close"]) or r["high"] < r["low"]: flags.append("invalid_ohlc")
    if r["volume"] < 0 or r["amount"] < 0: flags.append("negative_volume_or_amount")
    if r["tradable"] and r["volume"] == 0: flags.append("tradable_with_zero_volume")
    if r["volume"] > 0 and r["amount"] == 0: flags.append("volume_without_amount")
    if r["amount"] > 0 and r["volume"] > 0:
        if r["vwap"] is None: flags.append("missing_vwap_with_turnover")
        elif abs(r["vwap"]-r["amount"]/r["volume"]) > .005: flags.append("inconsistent_vwap")
    if r["up_limit"] is not None and r["down_limit"] is not None and r["up_limit"] <= r["down_limit"]: flags.append("invalid_limit_order")
    if r["up_limit"] is not None and r["close"] > r["up_limit"]+.005: flags.append("close_above_limit")
    if r["down_limit"] is not None and r["close"] < r["down_limit"]-.005: flags.append("close_below_limit")
    for direction in ("up","down"):
        if r["limit_"+direction+"_locked"] and (r[direction+"_limit"] is None or any(abs(r[k]-r[direction+"_limit"]) >= .005 for k in ("open","high","low","close"))):
            flags.append("invalid_"+direction+"_limit_lock")
    if any(r["signal_"+k] is not None and r["signal_"+k] <= 0 for k in ("open","high","low","close")): flags.append("invalid_signal_price")
    return flags


def quality_summary(cache, audit):
    by_error, by_year, by_source, roots = Counter(), Counter(), Counter(), Counter()
    details, examples = [], {}
    affected = set()
    unexpected={(r['trading_date'],r['symbol']) for r in audit.get('unexpected_reference_sessions',[])}
    with cache.connect() as c:
        c.execute("CREATE TEMP TABLE flagged_keys(d TEXT,s TEXT,PRIMARY KEY(d,s))")
        c.executemany("INSERT OR IGNORE INTO flagged_keys VALUES (?,?)", ((r["trading_date"],r["symbol"]) for r in audit["anomalies"]["rows"]))
        c.executemany("INSERT OR IGNORE INTO flagged_keys VALUES (?,?)",unexpected)
        rows = c.execute("SELECT b.*, s.name, t.source FROM flagged_keys k JOIN bars b ON b.trading_date=k.d AND b.symbol=k.s "
                         "JOIN stocks s ON s.symbol=b.symbol LEFT JOIN symbol_sync_status t ON t.symbol=b.symbol ORDER BY b.trading_date,b.symbol").fetchall()
        for row in rows:
            r = dict(row); flags = quality_flags(r); affected.add(r["symbol"])
            if (r['trading_date'],r['symbol']) in unexpected:flags.append('unexpected_reference_session')
            source = r["source"] or "unknown_latest_ledger"
            by_error.update(flags); by_year[r["trading_date"][:4]] += len(flags); by_source[source] += len(flags)
            limit = any("limit" in f for f in flags)
            if 'unexpected_reference_session' in flags:
                root='nontrading_capital_date_merge_artifact_pending_raw_replay'
            elif "invalid_ohlc" in flags or "non_positive_price" in flags:
                root = "raw_ohlc_conflict"
            elif limit and "ST" in r["name"].upper() and r["symbol"].startswith(("300","301")) and r["trading_date"] >= "2020-08-24":
                root = "confirmed_chinext_ST_rule_precedence_bug"
            elif limit and "ST" in r["name"].upper():
                root = "current_ST_name_backcast_historical_status_unverified"
            elif limit:
                root = "IPO_exrights_reference_or_historical_rule_unverified"
            else:
                root = "turnover_unit_price_mode_or_trade_scope_unverified"
            roots[root] += 1
            entry = {"symbol":r["symbol"],"date":r["trading_date"],"flags":flags,"root":root,
                     "source":source,"attribution_status":"code-path evidence, not verified per-bar source lineage"}
            details.append(entry)
            if root not in examples:
                previous = c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1", (r["symbol"],r["trading_date"])).fetchone()
                examples[root] = {"stored":r, "previous_stored":dict(previous) if previous else None,
                                  "triggered_checks":flags, "source_reproduction":"source_semantics.json/raw_probes; current response does not prove original download bytes"}
    return {"legacy_first_reason_mark_count": audit["anomalies"]["count"],
        "all_applicable_check_mark_count":sum(by_error.values()),"deduplicated_stock_date_rows":len(details),
        "affected_stock_count":len(affected),"by_error":dict(by_error),"by_year":dict(by_year),"by_source":dict(by_source),
        "source_distribution_basis":"latest per-stock ledger, provisional for historical rows; per-bar original lineage is unavailable",
        "primary_root_counts_disjoint_by_row":dict(roots),"examples":examples,"rows":details,
        "zero_or_unverified_categories":{"same_stock_date_duplicates":audit["duplicates"]["count"],
            "confirmed_unit_conversion_errors":0,"confirmed_qfq_hfq_mix_errors":0,
            "segment_adjustment_consistency":"BSE overlaps conflict; original per-segment provenance absent, keep unverified",
            "OHLC_contradictions":sum(1 for d in details if 'invalid_ohlc' in d['flags'])},
        "no_price_or_vwap_rewritten":True}


def gap_accounting(cache, reference):
    counts = Counter({"pre_listing":0,"post_delisting":0,"confirmed_suspension":0,
                      "confirmed_real_missing":0,"unknown_active_reason":0})
    stocks, missing_rows, conflicts, unexpected = [], [], [], []
    reference_set = set(reference)
    with cache.connect() as c:
        inventory = c.execute("SELECT * FROM stocks ORDER BY symbol").fetchall()
        for s in inventory:
            present = {r[0] for r in c.execute("SELECT trading_date FROM bars WHERE symbol=? AND trading_date BETWEEN ? AND ?", (s["symbol"],reference[0],reference[-1]))}
            first,last = stock_active_interval(s,date.fromisoformat(reference[0]),date.fromisoformat(reference[-1]))
            active = [d for d in reference if str(first)<=d<=str(last)]
            unknown = set(active)-present
            pre = {d for d in reference if s["list_date"] and d<s["list_date"] and d not in present}
            post = {d for d in reference if s["delist_date"] and d>str(last) and d not in present}
            # Count missing sessions only; lifecycle conflicts on observed rows are separate.
            counts["pre_listing"] += len(pre); counts["post_delisting"] += len(post)
            counts["unknown_active_reason"] += len(unknown)
            bad = sorted(d for d in present if (s["list_date"] and d<s["list_date"]) or (s["delist_date"] and d>str(last)))
            if bad: conflicts.append({"symbol":s["symbol"],"observed_outside_lifecycle":bad})
            extra=sorted(present-reference_set)
            if extra: unexpected.append({"symbol":s["symbol"],"dates":extra})
            inside = first<=last
            stocks.append({"symbol":s["symbol"],"inside":inside,"has_bars":bool(present),"unknown_active_sessions":len(unknown)})
            if unknown: missing_rows.append({"symbol":s["symbol"],"category":"unknown_active_reason",
                                            "ranges":_missing_ranges(active,unknown)})
        covered = sum(len({r[0] for r in c.execute("SELECT trading_date FROM bars WHERE symbol=? AND trading_date BETWEEN ? AND ?",(s["symbol"],reference[0],reference[-1]))} & set(reference)) for s in inventory)
    inside = sum(s["inside"] for s in stocks)
    recon = {"security_total":len(stocks),"inside":inside,"outside":len(stocks)-inside,
             "inside_with_bars":sum(s["inside"] and s["has_bars"] for s in stocks),
             "inside_without_bars":sum(s["inside"] and not s["has_bars"] for s in stocks),
             "outside_with_bars":sum(not s["inside"] and s["has_bars"] for s in stocks),
             "outside_without_bars":sum(not s["inside"] and not s["has_bars"] for s in stocks)}
    recon["reconciles"] = (recon["inside"]+recon["outside"]==recon["security_total"] and
        recon["inside_with_bars"]+recon["inside_without_bars"]==recon["inside"] and
        recon["outside_with_bars"]+recon["outside_without_bars"]==recon["outside"])
    return {"missing_categories":dict(counts),"missing_category_sum":sum(counts.values()),
        "observed_calendar_stock_dates":covered,"calendar_cross_inventory":len(reference)*len(stocks),
        "date_accounting_reconciles":covered+sum(counts.values())==len(reference)*len(stocks),
        "coverage_reconciliation":recon,"lifecycle_conflicts":conflicts,"missing_ranges":missing_rows,
        "observed_outside_reference_calendar":unexpected,
        "evidence_limitations":"No absent quote is treated as suspension. Confirmed suspension/true loss remain zero without independent event or raw-row evidence."}


def run_batch_report(run: Path, original_evidence: Path, reuse=False):
    before_id=json.loads((run/'before_identity.json').read_text());after_id=json.loads((run/'after_identity.json').read_text())
    verify_snapshot(run/'before.sqlite',before_id);verify_snapshot(run/'after.sqlite',after_id)
    evidence=json.loads(original_evidence.read_text(encoding='utf-8'))
    references=sorted(d for d in evidence['calendar']['dates'] if '2015-06-01'<=d<='2026-09-30')
    outputs={}
    for label,identity in (('before',before_id),('after',after_id)):
        cache=SnapshotCache(Path(identity['path']))
        if reuse:
            outputs[label]=json.loads((run/(label+'_accounting.json')).read_text(encoding='utf-8'))
            continue
        print(label+' audit starting',flush=True)
        audit=RealMarketDataAuditor(cache).run(end_date=date(2026,9,30),output=run/(label+'_audit')).payload
        outputs[label]={'snapshot':identity,'gaps':gap_accounting(cache,references),'quality':quality_summary(cache,audit)}
        with cache.connect() as c:
            outputs[label]['missing_listing_dates']=c.execute('SELECT COUNT(*) FROM stocks WHERE list_date IS NULL').fetchone()[0]
        (run/(label+'_accounting.json')).write_text(json.dumps(outputs[label],ensure_ascii=False,indent=2),encoding='utf-8')
        if label=='after':
            admission=admission_report(cache,audit,identity,evidence);write_admission(run,admission)
        print(label+' accounting complete',flush=True)
    dependencies=baseline_dependencies();(run/'baseline_required_fields.json').write_text(json.dumps(dependencies,ensure_ascii=False,indent=2),encoding='utf-8')
    source=json.loads((run/'source_semantics.json').read_text(encoding='utf-8')) if (run/'source_semantics.json').exists() else {'bse':{}}
    verdicts=json.loads((run/'bse_semantic_verdicts.json').read_text(encoding='utf-8')) if (run/'bse_semantic_verdicts.json').exists() else {}
    for symbol, item in source['bse'].items():
        item['current_semantic_verdict']=verdicts.get(symbol,{})
        if verdicts.get(symbol,{}).get('overlap_result')=='passed_exact_unchanged_half_tick':
            item['status']='numeric_comparison_false_positive_resolved; transport replay/factor provenance not formal-approved'
    after_cache=SnapshotCache(Path(after_id['path']))
    with after_cache.connect() as c:
        warmup=[dict(r) for r in c.execute("SELECT s.symbol,s.list_date,MIN(b.trading_date) AS first_in_window, "
            "(SELECT MAX(p.trading_date) FROM bars p WHERE p.symbol=s.symbol AND p.trading_date<'2015-06-01') AS prior_available "
            "FROM stocks s JOIN bars b ON b.symbol=s.symbol WHERE s.list_date<'2015-06-01' AND b.trading_date BETWEEN '2015-06-01' AND '2026-09-30' "
            "GROUP BY s.symbol ORDER BY s.symbol")]
    (run/'baseline_previous_close_warmup.json').write_text(json.dumps(warmup,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={"acceptance_start":"2015-06-01","acceptance_end":"2026-09-30","before_snapshot":before_id,"after_snapshot":after_id,
        "before_missing_listing":outputs['before']['missing_listing_dates'],"after_missing_listing":outputs['after']['missing_listing_dates'],
        "before_gaps":outputs['before']['gaps']['missing_categories'],"after_gaps":outputs['after']['gaps']['missing_categories'],
        "before_quality":{k:v for k,v in outputs['before']['quality'].items() if k not in {'rows','examples'}},
        "after_quality":{k:v for k,v in outputs['after']['quality'].items() if k not in {'rows','examples'}},
        "coverage":outputs['after']['gaps']['coverage_reconciliation'],"bse_cases":source['bse'],
        "required_fields":dependencies,"formal_gate_released":False,"no_backtest_or_returns":True,
        "field_completion":{
            "listing_dates":"complete as observed exchange facts; not complete historical pool proof",
            "code_effective_periods_and_ISIN":"unknown where no direct source; no generated identifiers or dates",
            "last_trade_date":"distinct from delisting; unknown unless explicitly sourced; observed last bar is not official last-trade proof",
            "required_raw_OHLC_volume_tradable":"values present; volume scope, inferred tradability and source granularity remain unverified",
            "required_adjusted_close":"values present; five material BSE source conflicts and full causal factor basis remain unresolved",
            "previous_close_warmup":{"existing_before_start":len(warmup),"with_prestart_bar":sum(bool(r['prior_available']) for r in warmup),
                "note":"Actual selector reads previous signal_close. Need real pre-window last trade for existing stocks; never invent it or move acceptance start. New IPO first-day exclusion is the existing strategy rule, not an invented prior close."},
            "required_execution_locks":"present but derived from incomplete historical ST/IPO/exright evidence, not validated",
            "VWAP_mode":"not admissible while regular-auction turnover comparability remains unverified",
            "OPEN_mode":"unchanged default, not authorized; lifecycle/identity, volume and lock evidence still block",
            "CSI300_CSI1000_prices":"each 2757 sessions; display/benchmark/regime use only, not a constituent-selection requirement",
            "unused_enhancements":"industry/concept/policy/fundamental/constituent modules not required by current baseline"},
        "next_batch":["historical ST/board/IPO/exrights reference and exact execution-lock proof",
            "real pre-window previous adjusted close for existing stocks, needed by current selector (not an enhancement)",
            "independent suspension calendars and targeted real missing-row verification",
            "9 BSE adjustment/turnover-scope conflicts; authoritative corporate actions and source normalization",
            "security alias effective dates and former selected-layer/BSE eligibility",
            "HFQ publication/effective history and per-segment lineage; original source bytes missing for old bars"]}
    (run/'batch1_comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['Roviga Phase 4 数据口径第一批修复对照','验收：2015-06-01 至 2026-09-30',
        f"修复前快照：{before_id['id']}",f"修复后快照：{after_id['id']}",
        f"缺上市日期：{summary['before_missing_listing']} → {summary['after_missing_listing']}",
        f"前缺口分类：{summary['before_gaps']}",f"后缺口分类：{summary['after_gaps']}",
        f"覆盖对账：{summary['coverage']}",f"质量标记（全部检查）：{summary['after_quality']['all_applicable_check_mark_count']}",
        f"去重异常行：{summary['after_quality']['deduplicated_stock_date_rows']}；受影响股票：{summary['after_quality']['affected_stock_count']}",
        '历史质量行未删除，未放宽阈值，未修改价格/VWAP。根因详见 after_accounting.json。',
        '同一行可能命中多个检查，根因主分类按行去重，行情覆盖与质量冲突独立统计。',
        '9只北交所逐只状态：bse_semantic_verdicts.json；原始响应/权益事件/大宗交易：source_semantics.json。',
        '920396：0.005边界浮点误报已修，14日交叉比价通过；5只实质复权差异和3只成交统计范围问题仍阻塞。',
        '单位/统计范围校验不等于替换VWAP；大宗扣除后的均值只用于诊断，绝未写成执行价格。',
        '000938复查样例：缓存34300股，腾讯原始342.84手（34284股），显示量的粒度差异；不能靠调倍率/估计VWAP放行。',
        '证券观察与有效期未知字段：evidence/security_master_normalized.json；A/B日期修正：a_b_date_corrections.json。',
        '基准必需字段：baseline_required_fields.json；OPEN仍保留VWAP质量警告，VWAP模式须另满足可比成交范围。',
        f"基准信号热身：{len(warmup)}只期初已上市且区间内有行情的股票，其中{sum(bool(r['prior_available']) for r in warmup)}只有起点之前的价格；不能把首日缺previous_close当成真实无候选。详见 baseline_previous_close_warmup.json。",
        '行业/概念/政策/成分股增强未启用，不新增为本轮基准门禁；历史ST/复权/股票池证据仍必需。',
        'Sina原始压缩响应已保留，但当前Windows拒绝加载原生解码库（WinError4551）；未绕过策略，已用允许的腾讯HTTP交叉样例，并保留原源重放缺口。',
        '原始历史逐条响应已无法从当前缓存恢复，来源分布仅按最近同步台账归因，不伪称完整逐条血缘。',
        '当前不具备正式回测条件，门禁未解除，未运行收益回测。下一批阻塞：']+summary['next_batch']
    (run/'batch1_comparison.txt').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('before_missing_listing','after_missing_listing','before_gaps','after_gaps','coverage')},ensure_ascii=False),flush=True)


def run_final_snapshot_audit(snapshot: Path, source_review: Path, output: Path):
    """Re-audit an already isolated data version and emit blockers without DB writes."""
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with snapshot.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    cache = SnapshotCache(snapshot)
    identity = {"id":"sha256:"+digest.hexdigest(), "path":str(snapshot.resolve()),
                "data_revision":cache.data_revision, "method":"read-only isolated copy; no market-row edits"}
    verify_snapshot(snapshot, identity)
    evidence = json.loads(source_review.read_text(encoding="utf-8"))
    audit = RealMarketDataAuditor(cache).run(start_date=date(2015,6,1), end_date=date(2026,9,30),
                                                output=output/"preaudit")
    references = sorted(d for d in evidence["calendar"]["dates"] if "2015-06-01" <= d <= "2026-09-30")
    gaps = gap_accounting(cache, references)
    quality = quality_summary(cache, audit.payload)
    with cache.connect() as c:
        missing_listing = c.execute("SELECT COUNT(*) FROM stocks WHERE list_date IS NULL").fetchone()[0]
        stock_count = c.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        bar_dates = c.execute("SELECT MIN(trading_date),MAX(trading_date),COUNT(*) FROM bars WHERE trading_date BETWEEN '2015-06-01' AND '2026-09-30'").fetchone()
    report = admission_report(cache, audit.payload, identity, evidence)
    report_dir = output/"admission"
    report_dir.mkdir(exist_ok=True)
    write_admission(report_dir, report)
    summary = {"snapshot":identity,"acceptance_start":"2015-06-01","acceptance_end":"2026-09-30",
        "inventory_count":stock_count,"missing_listing_dates":missing_listing,
        "bar_date_coverage":{"first":bar_dates[0],"last":bar_dates[1],"rows":bar_dates[2]},
        "audit_passed":audit.passed,"audit_checks":audit.payload["audit_checks"],
        "audit_unexpected_reference_sessions":audit.payload.get("unexpected_reference_sessions",[]),
        "audit_quarantine_count":len(audit.payload.get("provider_quarantines",[])),
        "gaps":gaps,"quality":quality,"formal_backtest_ready":False,"gate_released":False,
        "no_returns_computed":True,"admission_report":str((report_dir/"phase5a_admission_report.txt").resolve()),
        "blockers_file":str((report_dir/"blockers.json").resolve())}
    (output/"final_reaudit.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["Roviga Phase 4 第一批口径修复后预审计","验收区间：2015-06-01 至 2026-09-30",
        "数据快照："+identity["id"],f"证券数：{stock_count}；缺上市日期：{missing_listing}",
        f"行情：{bar_dates[0]} 至 {bar_dates[1]}，区间记录 {bar_dates[2]}",
        "缺口分类："+json.dumps(gaps["missing_categories"],ensure_ascii=False),
        f"质量标记：{quality['all_applicable_check_mark_count']}；去重证券日期行：{quality['deduplicated_stock_date_rows']}；受影响证券：{quality['affected_stock_count']}",
        f"区间外日历记录：{len(audit.payload.get('unexpected_reference_sessions',[]))}；未批准隔离记录：{len(audit.payload.get('provider_quarantines',[]))}",
        "审计通过：否；正式回测准入：否；门禁解除：否；收益结果：未计算。",
        "逐证券/日期原因与处理方案见 admission/blockers.json；完整根因行和样例见 final_reaudit.json 及原始批次证据。"]
    (output/"final_reaudit.txt").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"snapshot":identity["id"],"audit_passed":audit.passed,
        "unexpected_sessions":len(summary["audit_unexpected_reference_sessions"]),
        "quality_marks":quality["all_applicable_check_mark_count"],
        "quality_rows":quality["deduplicated_stock_date_rows"],"blockers":report["blocker_summary"]},ensure_ascii=False),flush=True)
    enrich_final_review(output)


def enrich_final_review(output: Path):
    """Attach current baseline dependencies and BSE case verdicts to the preaudit bundle."""
    summary_path=output/"final_reaudit.json"
    summary=json.loads(summary_path.read_text(encoding="utf-8"))
    report_path=output/"admission"/"phase5a_admission_report.json"
    report=json.loads(report_path.read_text(encoding="utf-8"))
    run=output.parent
    bse_path=run/"bse_semantic_verdicts.json"
    bse=json.loads(bse_path.read_text(encoding="utf-8")) if bse_path.exists() else {}
    cache=SnapshotCache(Path(summary["snapshot"]["path"]))
    with cache.connect() as c:
        warmup=[dict(r) for r in c.execute("SELECT s.symbol,s.list_date,MIN(b.trading_date) first_in_window, "
            "(SELECT MAX(p.trading_date) FROM bars p WHERE p.symbol=s.symbol AND p.trading_date<'2015-06-01') prior_available "
            "FROM stocks s JOIN bars b ON b.symbol=s.symbol WHERE s.list_date<'2015-06-01' "
            "AND b.trading_date BETWEEN '2015-06-01' AND '2026-09-30' GROUP BY s.symbol ORDER BY s.symbol")]
    has_prior=sum(bool(r["prior_available"]) for r in warmup)
    dependencies=baseline_dependencies()
    completion={
        "required_current":dependencies["required_current"],
        "current_adjusted_close":"stored values present; causal factor publication, BSE five material overlaps and segment lineage unresolved",
        "raw_OHLC_volume_tradable":"stored values present; raw OHLC checks pass, but volume scope and inferred tradability remain unverified",
        "historical_limit_locks":"stored flags present; historical ST/board/IPO/ex-right references and exact lock values unresolved",
        "pre_window_previous_close":{"existing_listed_stocks":len(warmup),"with_real_pre_window_bar":has_prior,
            "without_pre_window_bar":len(warmup)-has_prior,"required_by":"current selector reads previous signal_close"},
        "listing_date":"complete in this snapshot; does not establish historical pool or code identity",
        "historical_universe_and_aliases":"unverified; current inventory and exchange/code are not point-in-time membership proof",
        "historical_ST_board_and_classification":"ST/board/risk state unknown where source evidence is absent; industry/concept/policy are unused enhancements, not baseline gates",
        "CSI300_CSI1000":{"rows_each":2757,"calendar_check":"passed against independent Sina calendar; constituent history not verified"},
        "vwap":"OPEN remains configured default; stored VWAP/amount checks remain visible; VWAP mode needs comparable regular-auction scope",
    }
    summary["baseline_field_review"]={"dependencies":dependencies,"completion":completion,"formal_ready":False}
    summary["bse_cases"]=bse
    report["baseline_field_review"]=summary["baseline_field_review"]
    report["bse_semantic_review"]=bse
    report["historical_evidence_gaps"]={"universe_and_aliases":"unverified",
        "classification_required_by_current_baseline":False,"historical_ST_board_and_limits":"unverified",
        "adjustment_factor_publication_and_segment_lineage":"unverified",
        "previous_close_warmup":{"existing_listed":len(warmup),"pre_window_bar":has_prior}}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    text_path=output/"final_reaudit.txt"
    text=text_path.read_text(encoding="utf-8")
    text += "\n基准必需字段与完成状态见 admission/phase5a_admission_report.json；起点前收盘热身 " \
        f"{len(warmup)} 只已有存续股票中，{has_prior} 只有真实区间前行情。" \
        "北交所9只逐只来源/复权/成交范围状态见 admission/phase5a_admission_report.json。\n"
    text_path.write_text(text,encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--reuse-accounting',action='store_true',help='reuse already generated immutable snapshot accounting')
    parser.add_argument('--snapshot',type=Path);parser.add_argument('--source-review',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--enrich',type=Path,help='attach baseline and BSE evidence to an existing final report')
    args=parser.parse_args()
    if args.enrich:
        enrich_final_review(args.enrich)
    elif args.snapshot:
        if not args.source_review or not args.output:parser.error('--snapshot requires --source-review and --output')
        run_final_snapshot_audit(args.snapshot,args.source_review,args.output)
    else:
        if not args.run or not args.evidence:parser.error('--run and --evidence are required unless --snapshot is supplied')
        run_batch_report(args.run,args.evidence,args.reuse_accounting)


if __name__=='__main__': main()
