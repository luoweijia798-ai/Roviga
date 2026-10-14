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

from .data_audit import RealMarketDataAuditor, stock_active_interval, _missing_ranges, load_session_explanations
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
        "history_readiness": {
            "signal_close_momentum": {"prior_actual_quotes":1, "semantics":"last observed quote, not automatically previous exchange session", "ready":"real pre-window quote with verified numerical adjusted-price seam; factor publication causality remains separate"},
            "market_regime_display": {"total_closes":20,"pre_window_closes":19,"current_day_included":True,"benchmark":"CSI300","role":"existing display label, not a strategy eligibility filter"},
            "benchmark_comparison": {"formal_first_close_required":True,"warmup_returns_excluded":True},
            "moving_average_breakout_volatility": {"enabled":False,"additional_warmup_requirement":0},
            "orders_positions_returns": "none during warmup; fixed formal trading_dates 2015-06-01 through 2026-09-30; portal history can read earlier real observations"
        },
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
        session_explanations=load_session_explanations(c)
        for s in inventory:
            present = {r[0] for r in c.execute("SELECT trading_date FROM accepted_bars WHERE symbol=? AND trading_date BETWEEN ? AND ?", (s["symbol"],reference[0],reference[-1]))}
            first,last = stock_active_interval(s,date.fromisoformat(reference[0]),date.fromisoformat(reference[-1]))
            active = [d for d in reference if str(first)<=d<=str(last)]
            unknown = set(active)-present
            confirmed=unknown & session_explanations.get(s['symbol'],set())
            counts['confirmed_suspension']+=len(confirmed)
            unknown-=confirmed
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
        covered = sum(len({r[0] for r in c.execute("SELECT trading_date FROM accepted_bars WHERE symbol=? AND trading_date BETWEEN ? AND ?",(s["symbol"],reference[0],reference[-1]))} & set(reference)) for s in inventory)
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
        "evidence_limitations":"No absent quote is treated as suspension. Only separately stored, independently corroborated full-session event evidence explains missing quotes; event coverage is not assumed complete."}


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
    lines=["Roviga Phase 4 口径修复后预审计","验收区间：2015-06-01 至 2026-09-30",
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


def batch2_comparison(output: Path, baseline_report: Path, source_review: Path):
    """Reconcile immutable before/after reports; never infer progress across runs."""
    before=json.loads(baseline_report.read_text(encoding='utf-8'))
    after=json.loads((output/'final_reaudit.json').read_text(encoding='utf-8'))
    run=output.parent;cache=SnapshotCache(Path(after['snapshot']['path']))
    reference=sorted(d for d in json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates'] if '2015-06-01'<=d<='2026-09-30')
    def expanded(report):
        return {(s['symbol'],d) for s in report['gaps']['missing_ranges'] for r in s['ranges'] for d in reference if r['start']<=d<=r['end']}
    original=expanded(before);remaining=expanded(after)
    by_year=Counter();by_exchange=Counter();by_source=Counter();by_date=Counter();by_symbol=Counter();ranges=[]
    from datetime import timedelta
    with cache.connect() as c:
        inventory={r['symbol']:dict(r) for r in c.execute('SELECT * FROM stocks')}
        sources={r['symbol']:r['source'] for r in c.execute('SELECT symbol,source FROM symbol_sync_status')}
        explained={(s,d) for s,days in load_session_explanations(c).items() for d in days} & original
        filled={(r[0],r[1]) for r in c.execute('SELECT symbol,trading_date FROM targeted_fill_journal')} & original
        physical=c.execute("SELECT COUNT(*) FROM bars WHERE trading_date BETWEEN '2015-06-01' AND '2026-09-30'").fetchone()[0]
        accepted=c.execute("SELECT COUNT(*) FROM accepted_bars WHERE trading_date BETWEEN '2015-06-01' AND '2026-09-30'").fetchone()[0]
        journals=c.execute('SELECT COUNT(*) FROM derived_limit_repair_journal').fetchone()[0]
        for symbol,day in original:
            by_year[day[:4]]+=1;by_exchange[inventory[symbol]['exchange']]+=1
            by_source[sources.get(symbol) or 'unknown_latest_ledger']+=1;by_date[day]+=1;by_symbol[symbol]+=1
        for item in before['gaps']['missing_ranges']:
            symbol=item['symbol'];listing=inventory[symbol]['list_date']
            start=max(date(2015,6,1),date.fromisoformat(listing)) if listing else date(2015,6,1)
            boundaries=set()
            while start<=date(2026,9,30):
                boundaries.add(str(start));boundaries.add(str(start+timedelta(days=365)));start+=timedelta(days=366)
            for r in item['ranges']:
                ranges.append({'symbol':symbol,**r,'exchange':inventory[symbol]['exchange'],
                    'latest_source_not_per_segment':sources.get(symbol),
                    'nominal_366day_boundary_match':r['start'] in boundaries or r['end'] in boundaries,
                    'boundary_evidence':'heuristic only; original segment request lineage absent, not a confirmed cause'})
    removed=original-remaining
    if explained & filled or removed != explained|filled or remaining-original:
        raise ValueError('before/after gap categories are not disjoint and exhaustive')
    old_quality={(r['symbol'],r['date']) for r in before['quality']['rows']}
    new_quality={(r['symbol'],r['date']) for r in after['quality']['rows']}
    warmup=after['baseline_field_review']['completion']['pre_window_previous_close']
    jobs=[json.loads(p.read_text(encoding='utf-8')) for p in (run/'warmup_jobs').glob('*.json')]
    unresolved_warmup=[]
    with cache.connect() as c:
        for j in jobs:
            if not c.execute("SELECT 1 FROM accepted_bars WHERE symbol=? AND trading_date<'2015-06-01'",(j['symbol'],)).fetchone():
                unresolved_warmup.append({'symbol':j['symbol'],'listing':j['listing_date'],
                    'observed_raw_prior_date':j.get('raw_prior',[None])[0],
                    'reason':'real raw history observed; numerical adjustment seam missing or conflicting',
                    'next_step':'reconcile dated factor normalization and a second raw/adjusted overlap; never guess a scale',
                    'source_job':str((run/'warmup_jobs'/(j['symbol']+'.json')).resolve())})
    result={'acceptance_start':'2015-06-01','acceptance_end':'2026-09-30',
        'before_snapshot':before['snapshot'],'after_snapshot':after['snapshot'],
        'warmup':{'before_missing':2733,'after_missing':warmup['without_pre_window_bar'],'real_prior_added':warmup['with_real_pre_window_bar'],
            'unresolved':unresolved_warmup,'benchmark_prior_closes_each':19,'factor_publication_not_certified':True},
        'gap_reconciliation':{'original_unknown':len(original),'independently_explained_full_day_suspension':len(explained),
            'real_quotes_filled':len(filled),'mapping_or_calendar_reclassified':0,'remaining_unknown':len(remaining),'reconciles':True,
            'formula':f'{len(original)} = {len(explained)} + {len(filled)} + 0 + {len(remaining)}'},
        'original_gap_aggregations':{'by_year':dict(by_year),'by_exchange':dict(by_exchange),'by_latest_stock_source':dict(by_source),
            'by_symbol':dict(by_symbol),'top_dates':by_date.most_common(20),'continuous_ranges':ranges,
            'nominal_segment_boundary_ranges':sum(r['nominal_366day_boundary_match'] for r in ranges)},
        'quality':{'before_marks':before['quality']['all_applicable_check_mark_count'],'after_marks':after['quality']['all_applicable_check_mark_count'],
            'before_distinct_rows':len(old_quality),'after_distinct_rows':len(new_quality),'removed_from_unresolved':len(old_quality-new_quality),
            'newly_flagged_rows':len(new_quality-old_quality),'derived_limit_rows_repaired':journals,
            'roots_before':before['quality']['primary_root_counts_disjoint_by_row'],'roots_after':after['quality']['primary_root_counts_disjoint_by_row'],
            'resolved_keys':sorted(old_quality-new_quality),'new_keys':sorted(new_quality-old_quality)},
        'same_snapshot_accounting':{'inventory_calendar_pairs':after['gaps']['calendar_cross_inventory'],
            'categories':after['gaps']['missing_categories'],'observed_calendar_rows':after['gaps']['observed_calendar_stock_dates'],
            'physical_rows_in_window':physical,'formal_view_rows_in_window':accepted,'isolated_preserved_rows':physical-accepted,
            'duplicates':after['quality']['zero_or_unverified_categories']['same_stock_date_duplicates'],
            'calendar_reconciles':after['gaps']['date_accounting_reconciles'],'security_reconciliation':after['gaps']['coverage_reconciliation']},
        'bse_cases':after['bse_cases'],'weekends':json.loads((run/'event_reconciliation.json').read_text(encoding='utf-8'))['weekend_isolations'],
        'gate_released':False,'formal_backtest_run':False,'live_database_modified':False}
    (run/'batch2_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['Roviga Phase 4 第二批修复对账（非收益回测）',
        '固定验收区间：2015-06-01 至 2026-09-30；10月增量单独保留。',
        '快照：'+after['snapshot']['id'],
        f"缺预热证券：2733 → {warmup['without_pre_window_bar']}；真实补齐 {warmup['with_real_pre_window_bar']}。剩余名单、原因与来源见 JSON warmup.unresolved。",
        '未知缺口对账：'+result['gap_reconciliation']['formula'],
        f"质量标记：{result['quality']['before_marks']} → {result['quality']['after_marks']}；异常证券日期行：{len(old_quality)} → {len(new_quality)}。",
        f'旧规则推导字段修正 {journals} 条；不改 OHLC、信号价格、成交量、成交额或 VWAP。',
        f'原始区间行情 {physical} = 正式视图 {accepted} + 保留隔离 {physical-accepted}；重复 0。',
        '8条周末记录及9只北交所逐项证据见 JSON；其余逐股逐日阻塞和处理方案见 final_reaudit/admission/blockers.json。',
        '历史股票池、历史ST/参考价及复权发布时点仍未通过；不新增未启用模块门禁。',
        '仅完成候选数据版本修复，不覆盖持续同步数据库。审计未通过，门禁保持关闭；本轮结束后暂停。']
    (run/'batch2_comparison.txt').write_text('\n'.join(text),encoding='utf-8')
    return result


def warmup_readiness_review(cache, source_review: Path) -> dict:
    """Separate numerical inputs, calendar continuity and causal certification.

    No selector or backtest is executed; existing eligibility is described, not
    changed. A single stored prior row is not blanket indicator approval.
    """
    import math
    from .backtest import BacktestConfig
    from .selector import SelectionConfig
    config=BacktestConfig();selection=SelectionConfig()
    full_calendar=sorted(json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates'])
    rows=[];benchmarks={}
    with cache.connect() as c:
        explained=load_session_explanations(c)
        stocks=c.execute("SELECT s.*,MIN(b.trading_date) first_signal FROM stocks s JOIN accepted_bars b ON b.symbol=s.symbol WHERE s.list_date<'2015-06-01' AND b.trading_date BETWEEN '2015-06-01' AND '2026-09-30' GROUP BY s.symbol ORDER BY s.symbol").fetchall()
        for stock in stocks:
            first=stock['first_signal'];symbol=stock['symbol']
            current=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date=?',(symbol,first)).fetchone()
            prior=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1',(symbol,first)).fetchone()
            current_ok=current['signal_close'] is not None and math.isfinite(current['signal_close']) and current['signal_close']>0
            prior_ok=prior is not None and prior['signal_close'] is not None and math.isfinite(prior['signal_close']) and prior['signal_close']>0
            intervening=[d for d in full_calendar if (prior['trading_date'] if prior else '2015-05-29')<d<first]
            unexplained=sorted(set(intervening)-explained.get(symbol,set()))
            rows.append({'symbol':symbol,'first_signal_day':first,'previous_actual_quote':prior['trading_date'] if prior else None,
                'required_prior_actual_quotes':1,'prior_positive_adjusted_close':bool(prior_ok),'current_positive_adjusted_close':bool(current_ok),
                'numerical_momentum_inputs_ready':bool(prior_ok and current_ok),
                'current_volume_and_tradable_eligible':bool(current['tradable'] and current['volume']>=selection.min_volume),
                'intervening_calendar_sessions':len(intervening),'unexplained_intervening_dates':unexplained,
                'latest_actual_quote_continuity_verified':not unexplained,
                'adjustment_publication_causality_verified':False,'all_formal_requirements_ready':False})
        needed=config.regime_lookback-1
        expected=[d for d in full_calendar if d<'2015-06-01'][-needed:]
        for name in ('CSI300','CSI1000'):
            points=c.execute("SELECT trading_date,close FROM benchmarks WHERE name=? AND trading_date<='2015-06-01' ORDER BY trading_date DESC LIMIT ?",(name,config.regime_lookback)).fetchall()
            actual=sorted(r['trading_date'] for r in points)
            benchmarks[name]={'required_closes_including_signal_day':config.regime_lookback if name==config.regime_benchmark else 1,
                'regime_indicator_enabled':name==config.regime_benchmark,'observed_closes':len(points),'dates':actual,
                'previous_19_exact_calendar_match':actual==expected+['2015-06-01'],
                'all_values_positive_finite':all(math.isfinite(r['close']) and r['close']>0 for r in points),
                'sufficient_for_current_dependency':(actual==expected+['2015-06-01'] and all(math.isfinite(r['close']) and r['close']>0 for r in points)) if name==config.regime_benchmark else any(r['trading_date']=='2015-06-01' and math.isfinite(r['close']) and r['close']>0 for r in points)}
    return {'dependencies':baseline_dependencies()['history_readiness'],'securities':rows,'benchmarks':benchmarks,
        'existing_at_start':len(rows),'numerical_inputs_ready':sum(r['numerical_momentum_inputs_ready'] for r in rows),
        'numerically_ready_but_continuity_unverified':sum(r['numerical_momentum_inputs_ready'] and not r['latest_actual_quote_continuity_verified'] for r in rows),
        'fully_causal_ready':0,'notes':['No enabled MA/breakout/volatility or new module window.',
            'New IPO without an actual previous bar remains excluded by existing portal/selector rules; missing old-stock downloads are explicit blockers.',
            'Regime uses valid benchmark observations including today, with exact session continuity checked separately; no future observations.',
            'Risk state starts empty at the formal start; no orders, positions or returns generated during warmup.']}


def batch3_comparison(output: Path, baseline: Path, source_review: Path) -> dict:
    """Extend the existing preaudit bundle, keeping newly found conflicts separate."""
    run=output.parent
    before=json.loads((baseline/'final_reaudit/final_reaudit.json').read_text(encoding='utf-8'))
    after=json.loads((output/'final_reaudit.json').read_text(encoding='utf-8'))
    repairs=json.loads((run/'evidence_classification.json').read_text(encoding='utf-8'))
    alias_file=run/'alias_mapping_evidence.json'
    aliases=json.loads(alias_file.read_text(encoding='utf-8')) if alias_file.exists() else {'proof':[]}
    for proof in aliases['proof']:
        for item in repairs['warmup_940']:
            if item['symbol']==proof['symbol'] and proof.get('raw_overlap_pass') and not proof.get('signal_overlap_pass'):
                item.update(category='verified_code_change_raw_history_recovered_adjustment_conflict',
                            alias_evidence=proof,reason='Official issuer code-change evidence and former-code raw overlap pass; native HFQ still disagrees, not a new listing or objective short history.')
    repairs['warmup_categories']=dict(Counter(x['category'] for x in repairs['warmup_940']))
    reference=sorted(d for d in json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates'] if '2015-06-01'<=d<='2026-09-30')
    def unknown(report):
        return {(x['symbol'],d) for x in report['gaps']['missing_ranges'] if x['category']=='unknown_active_reason'
                for span in x['ranges'] for d in reference if span['start']<=d<=span['end']}
    original=unknown(before);remaining=unknown(after);removed=original-remaining
    cache=SnapshotCache(Path(after['snapshot']['path']))
    with cache.connect() as c:
        explanations=load_session_explanations(c)
        closed={key for key in removed if key[1] in explanations.get(key[0],set())}
        filled={key for key in removed-closed if c.execute('SELECT 1 FROM accepted_bars WHERE symbol=? AND trading_date=?',key).fetchone()}
        if removed!=closed|filled:raise ValueError('unexplained gap category movement')
        stocks={r['symbol']:dict(r) for r in c.execute('SELECT * FROM stocks')}
        latest_sources={r['symbol']:r['source'] for r in c.execute('SELECT symbol,source FROM symbol_sync_status')}
        physical=c.execute("SELECT COUNT(*) FROM bars WHERE trading_date BETWEEN '2015-06-01' AND '2026-09-30'").fetchone()[0]
        accepted=c.execute("SELECT COUNT(*) FROM accepted_bars WHERE trading_date BETWEEN '2015-06-01' AND '2026-09-30'").fetchone()[0]
    readiness=warmup_readiness_review(cache,source_review)
    (run/'warmup_readiness_after.json').write_text(json.dumps(readiness,ensure_ascii=False,indent=2),encoding='utf-8')
    old_quality={(r['symbol'],r['date']) for r in before['quality']['rows']}
    new_quality={(r['symbol'],r['date']) for r in after['quality']['rows']}
    causes={};examples={}
    for row in repairs['quality_repairs']:
        for cause in row['causes']:
            causes.setdefault(cause,set()).add((row['symbol'],row['date']))
            examples.setdefault(cause,[])
            if len(examples[cause])<3:examples[cause].append(row)
    newly_conflicting=[r for r in repairs['suspension_reviews'] if r['status'] in {'conflicts_with_stored_quote','new_conflict_previously_explained'}]
    quotes_waiting=[r for r in repairs['suspension_reviews'] if r['status']=='actual_source_quote_exists_signal_seam_not_yet_verified']
    aggregations={name:Counter() for name in ('year','exchange','symbol','latest_stock_source_not_segment_provenance')}
    for symbol,day in remaining:
        aggregations['year'][day[:4]]+=1;aggregations['exchange'][stocks[symbol]['exchange']]+=1;aggregations['symbol'][symbol]+=1
        aggregations['latest_stock_source_not_segment_provenance'][latest_sources.get(symbol) or 'unknown']+=1
    # Exact query scope, including recovery attempts and failures; never equate
    # a terminal API response with proof of full historical source coverage.
    query_rows=[];query_counts=Counter();observed_year=Counter();observed_market=Counter();symbols=set()
    for path in sorted((run/'baostock').glob('*.json')):
        r=json.loads(path.read_text(encoding='utf-8'));query_counts[r['status']]+=1
        query_rows.append({'path':str(path.resolve()),'request':r['request'],'status':r['status'],
                           'returned':len(r['rows']),'protocol_pages':len(r.get('protocol_responses',[])),
                           'error_code':r.get('error_code'),'error':r.get('error_message',r.get('exception'))})
        if r['status']=='complete':
            symbols.add(r['request']['code'])
            for values in r['rows']:
                item=dict(zip(r['fields'],values));observed_year[item['date'][:4]]+=1;observed_market[item['code'].split('.')[0]]+=1
    evidence_coverage={'eastmoney':json.loads((run/'event_coverage.json').read_text(encoding='utf-8')),
        'daily_source':{'queries':query_rows,'attempt_counts_including_recovered_errors':dict(query_counts),
            'observed_securities':len(symbols),'observed_row_counts_by_year_including_overlap_queries':dict(observed_year),
            'observed_row_counts_by_market':dict(observed_market),'single_page_cap':10000,
            'semantics':'Explicit daily trading status, not interval inference from missing quotes; no copied halt OHLC inserted.',
            'completeness':'Only listed bounded requests; terminal response, no full page, protocol retained. Empty/error never absence proof.',
            'official_definition':'https://www.baostock.com/helpDocsHome?file=stockKData.md'},
        'market_wide_suspension_history_complete':False}
    (run/'suspension_evidence_coverage.json').write_text(json.dumps(evidence_coverage,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'acceptance_start':'2015-06-01','acceptance_end':'2026-09-30','before_snapshot':before['snapshot'],'after_snapshot':after['snapshot'],
        'warmup':{'before_missing':940,'after_missing':after['baseline_field_review']['completion']['pre_window_previous_close']['without_pre_window_bar'],
            'categories':repairs['warmup_categories'],'per_security':repairs['warmup_940'],
            'readiness_review':str((run/'warmup_readiness_after.json').resolve()),
            'existing_at_start':readiness['existing_at_start'],'numerical_ready':readiness['numerical_inputs_ready'],
            'continuity_unverified':readiness['numerically_ready_but_continuity_unverified'],'benchmarks':readiness['benchmarks']},
        'gap_reconciliation':{'original_unknown':len(original),'evidence_explained':len(closed),'real_quotes_filled':len(filled),
            'mapping_calendar_closed':0,'remaining_original_unknown':len(original & remaining),'new_unknown':len(remaining-original),
            'total_remaining_unknown':len(remaining),'new_source_conflicts_separately':len(newly_conflicting),
            'formula':f'{len(original)} = {len(closed)} + {len(filled)} + 0 + {len(original & remaining)}'},
        'remaining_gap_aggregations':{k:dict(v) for k,v in aggregations.items()},
        'continuous_gap_ranges':after['gaps']['missing_ranges'],
        'real_source_quotes_waiting_for_adjustment_validation':quotes_waiting,
        'source_and_segment_lineage':'Latest stock source is not original per-segment provenance; original segment-boundary attribution remains unknown, not a confirmed cause.',
        'quality':{'before_marks':before['quality']['all_applicable_check_mark_count'],'after_marks':after['quality']['all_applicable_check_mark_count'],
            'before_rows':len(old_quality),'after_rows':len(new_quality),'resolved_rows':len(old_quality-new_quality),'newly_flagged_rows':len(new_quality-old_quality),
            'confirmed_cause_counts_may_overlap':{k:len(v) for k,v in causes.items()},'reproducible_examples':examples,
            'three_confirmed_roots':{k:len(causes.get(k,set())) for k in ('current_ST_name_backcast_disproved_by_dated_status','previous_actual_close_not_source_reference_price','corroborated_stored_share_precision_loss')},
            'other_derived_rule_changes_root_not_independently_attributed':len(causes.get('stored_derived_rule_differs_from_dated_source_reference',set())),
            'remaining_unverified_hypotheses_not_confirmed_causes':after['quality']['primary_root_counts_disjoint_by_row'],
            'source_conflicts':newly_conflicting,'unresolved_field_reasons':repairs['quality_skip_rows']},
        'same_snapshot_accounting':{'cross_inventory':after['gaps']['calendar_cross_inventory'],'categories':after['gaps']['missing_categories'],
            'observed_calendar_rows':after['gaps']['observed_calendar_stock_dates'],'physical_formal_rows':physical,'accepted_rows':accepted,
            'preserved_isolations':physical-accepted,'calendar_reconciles':after['gaps']['date_accounting_reconciles'],
            'securities':after['gaps']['coverage_reconciliation']},
        'bse_cases':after['bse_cases'],'replay':json.loads((run/'replay_verification.json').read_text(encoding='utf-8')),
        'next_required_sources':['Original Eastmoney HFQ normalization and dated factor lineage for incompatible warmup overlaps; restore bounded endpoint access or separately authorize a compatible source.',
            'Independent historical daily suspension coverage for the exact remaining ranges, including delisted/BSE identities; daily source explicitly rejects bj codes.',
            'Official ex-right/reference, historical ST/IPO/resumption exceptions and source raw trade-scope evidence for remaining flagged dates.',
            'Point-in-time security identity/universe and factor publication chronology remain unverified; no automatic defaults or exclusions.'],
        'formal_backtest_ready':False,'gate_released':False,'no_returns_computed':True,'live_database_modified':False}
    (run/'batch3_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    # Newly discovered contradictions must remain admission blockers even when
    # old OHLC-only tests happen to pass.
    admission=output/'admission';report=json.loads((admission/'phase5a_admission_report.json').read_text(encoding='utf-8'))
    additions=[{'reason':'independent_daily_status_conflict','symbol':x['symbol'],'start':x['date'],'end':x['date'],
                'detail':x['status'],'evidence':x['source'],'treatment_plan':'Compare exchange daily status and original positive-volume quote; do not overwrite either source.'} for x in newly_conflicting]
    continuity=[{'reason':'previous_actual_quote_continuity_unverified','symbol':x['symbol'],
                 'start':x['unexplained_intervening_dates'][0],'end':x['unexplained_intervening_dates'][-1],
                 'dates':x['unexplained_intervening_dates'],'treatment_plan':'Verify daily suspension or real missing quotes between prior actual quote and first signal; numerical inputs alone do not certify continuity.'}
                for x in readiness['securities'] if x['numerical_momentum_inputs_ready'] and x['unexplained_intervening_dates']]
    report['batch3_review']={'comparison':str((run/'batch3_comparison.json').resolve()),'warmup_readiness':readiness,
                             'new_source_conflict_blockers':additions,'formal_ready':False}
    pending_quotes=[{'reason':'real_source_quote_adjustment_seam_unverified','symbol':x['symbol'],'start':x['date'],'end':x['date'],
                    'evidence':x['source'],'treatment_plan':'Validate native raw and adjusted neighboring overlaps with stored signal scale before importing this real quote.'} for x in quotes_waiting]
    report['blockers']=[x for x in report['blockers'] if x['reason'] not in {'independent_daily_status_conflict','previous_actual_quote_continuity_unverified','real_source_quote_adjustment_seam_unverified'}]+additions+continuity+pending_quotes
    report['blocker_summary']=dict(Counter(x['reason'] for x in report['blockers']))
    (admission/'phase5a_admission_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (admission/'blockers.json').write_text(json.dumps(report['blockers'],ensure_ascii=False,indent=2),encoding='utf-8')
    text=['Roviga Phase 4 第三批修复与预审计（非收益回测）','固定验收：2015-06-01 至 2026-09-30',
        '快照：'+after['snapshot']['id'],f"缺预热证券：940 → {result['warmup']['after_missing']}；逐只结果见 batch3_comparison.json。",
        '未知缺口对账：'+result['gap_reconciliation']['formula'],
        f"质量标记：{result['quality']['before_marks']} → {result['quality']['after_marks']}；异常行：{len(old_quality)} → {len(new_quality)}。",
        f'另发现 {len(newly_conflicting)} 个独立日状态与已有行情冲突，不混入净减少数。',
        'CSI300 当前20收盘价依赖及CSI1000首日比较依赖已检查；股票复权时点因果性仍未通过。',
        '重放与重复应用验证见 replay_verification.json。9只北交所、逐股日期与下一步来源见 JSON。',
        '正式准入：不通过；门禁未解除；未运行收益回测；不覆盖持续同步库；本批完成后暂停。']
    (run/'batch3_comparison.txt').write_text('\n'.join(text),encoding='utf-8')
    report_text=admission/'phase5a_admission_report.txt'
    base_text=report_text.read_text(encoding='utf-8').split('\n\n'+text[0],1)[0]
    report_text.write_text(base_text+'\n\n'+'\n'.join(text),encoding='utf-8')
    return result


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
