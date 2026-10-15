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
            item["conversion"] = "Sina volume in shares, amount in yuan; effective-date HFQ multiplication (publication causality unverified); no capital-date outer merge or forward fill"
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


def warmup_batch(snapshot: Path, run: Path, workers: int = 6) -> dict:
    """Target the previous actual quote, preserving every response and failed job.

    Tencent supplies bounded raw quotes; dated Sina factors must reproduce the
    existing signal-price overlap before a pre-window row may be inserted.
    Numerical agreement does not establish factor publication-time causality.
    Only an isolated candidate database is written; no live checkpoints change.
    """
    import hashlib
    import math
    import sqlite3
    import threading
    import traceback
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime, timezone
    from decimal import Decimal
    import requests
    from .phase4_acceptance import freeze_database
    from .real_market import SQLiteMarketCache

    run.mkdir(parents=True, exist_ok=True)
    candidate=run/"candidate.sqlite"
    if not candidate.exists():
        identity=freeze_database(snapshot,candidate)
        (run/"initial_snapshot_identity.json").write_text(json.dumps(identity,indent=2),encoding="utf-8")
    cache=SQLiteMarketCache(candidate)
    raw_dir=run/"warmup_raw"; raw_dir.mkdir(exist_ok=True)
    jobs_dir=run/"warmup_jobs"; jobs_dir.mkdir(exist_ok=True)
    with cache.connect() as c:
        c.execute("INSERT OR REPLACE INTO metadata VALUES ('formal_backtest_start','2015-06-01')")
        c.execute("INSERT OR REPLACE INTO metadata VALUES ('formal_backtest_end','2026-09-30')")
        c.execute("CREATE TABLE IF NOT EXISTS warmup_evidence(symbol TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        stocks=[dict(r) for r in c.execute("SELECT s.* FROM stocks s WHERE s.list_date<'2015-06-01' AND EXISTS "
            "(SELECT 1 FROM bars b WHERE b.symbol=s.symbol AND b.trading_date BETWEEN '2015-06-01' AND '2026-09-30') ORDER BY s.symbol")]
        overlaps={s['symbol']:[dict(r) for r in c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date BETWEEN '2015-06-01' AND '2026-09-30' ORDER BY trading_date LIMIT 5",(s['symbol'],))] for s in stocks}
    lock=threading.Lock(); next_request=[0.0]
    def get(label,url,params=None):
        key=hashlib.sha256(json.dumps([url,params],sort_keys=True).encode()).hexdigest()
        path=raw_dir/(key+'.response'); meta=raw_dir/(key+'.json')
        if path.exists() and meta.exists():return path.read_text(encoding='utf-8'),json.loads(meta.read_text(encoding='utf-8'))
        for attempt in range(2):
            with lock:
                wait=max(0,next_request[0]-time.monotonic());time.sleep(wait);next_request[0]=time.monotonic()+.25
            try:
                r=requests.get(url,params=params,timeout=20);r.raise_for_status()
                text=r.content.decode('utf-8-sig');digest=hashlib.sha256(r.content).hexdigest()
                path.write_bytes(r.content)
                ref={'source':label,'url':r.url,'sha256':digest,'fetched_at':datetime.now(timezone.utc).isoformat(),'path':str(path.resolve())}
                meta.write_text(json.dumps(ref,indent=2),encoding='utf-8');return text,ref
            except requests.RequestException:
                if attempt:raise
                time.sleep(2)
    def job(stock):
        symbol=stock['symbol']; result={'symbol':symbol,'listing_date':stock['list_date'],'status':'source_missing','references':[],
            'previous_semantics':'last actual observed quote before formal date, not necessarily previous exchange session',
            'factor_publication_causality':'unverified; effective-date factor use alone is insufficient'}
        completed=jobs_dir/(symbol+'.json')
        if completed.exists():return json.loads(completed.read_text(encoding='utf-8'))
        try:
            prefix='sh' if stock['exchange']=='SSE' else 'sz'; code=prefix+symbol
            text,ref=get('Tencent.raw', 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',
                {'param':f'{code},day,2015-05-01,2015-06-05,20,'})
            result['references'].append(ref)
            payload=json.loads(text);rows=payload.get('data',{}).get(code,{}).get('day',[])
            # Provider can return an earlier window; clip by actual returned dates.
            rows=[r for r in rows if '1900-01-01' < r[0] <= '2015-06-05']
            prior=[r for r in rows if stock['list_date']<=r[0]<'2015-06-01']
            if not prior:raise ValueError('no independently observed pre-window quote; no suspension inference')
            raw=max(prior,key=lambda r:r[0]); result['raw_prior']=raw
            text,ref=get('Sina.HFQ.factors',f'https://finance.sina.com.cn/realstock/company/{code}/hfq.js')
            result['references'].append(ref)
            factors=json.JSONDecoder().raw_decode(text.split('=',1)[1].strip())[0]['data']
            result['factors']=factors
            def adjusted(row):
                dated=[f for f in factors if str(f['d'])<=row[0]]
                if not dated:raise ValueError('no effective factor before actual quote date')
                f=float(max(dated,key=lambda v:v['d'])['f'])
                if not math.isfinite(f) or f<=0:raise ValueError('invalid factor')
                return [round(float(row[i])*f,2) for i in (1,3,4,2)]
            mapped={r[0]:r for r in rows}; comparisons=[]
            from .tencent_bse import price_conflict
            for old in overlaps[symbol]:
                if old['trading_date'] not in mapped:continue
                r=mapped[old['trading_date']];adj=adjusted(r)
                checks=[not price_conflict(float(r[i]),old[k]) for i,k in ((1,'open'),(3,'high'),(4,'low'),(2,'close'))]
                checks += [old['signal_'+k] is not None and not price_conflict(v,old['signal_'+k]) for k,v in zip(('open','high','low','close'),adj)]
                comparisons.append({'date':old['trading_date'],'passed':all(checks),'stored':old,'raw':r,'adjusted':adj})
            result['overlap']=comparisons
            if not comparisons or not all(r['passed'] for r in comparisons):
                result['status']='overlap_unverified_or_conflicting';return result
            result['insert_row']=real_prior_row(symbol,raw,factors)
            result['status']='ready_real_prior_quote';result['prior_date']=raw[0]
        except Exception as error:
            result['error']=f'{type(error).__name__}: {error}';result['traceback']=traceback.format_exc()
        return result
    counts={}; finished=0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(job,s):s['symbol'] for s in stocks}
        for future in as_completed(futures):
            result=future.result();symbol=result['symbol']
            if result['status']=='ready_real_prior_quote':
                with cache.connect() as c:
                    c.execute('PRAGMA busy_timeout=30000')
                    existing=c.execute('SELECT * FROM bars WHERE trading_date=? AND symbol=?',result['insert_row'][:2]).fetchone()
                    if existing is None:
                        c.execute('INSERT INTO bars VALUES ('+','.join('?'*18)+')',result['insert_row']);cache._invalidate_audit(c)
                    elif tuple(existing) != tuple(result['insert_row']):
                        raise ValueError(f'{symbol}: resume would relabel a different existing quote')
                    c.execute('INSERT OR REPLACE INTO warmup_evidence VALUES (?,?)',(symbol,json.dumps(result,ensure_ascii=False)))
            (jobs_dir/(symbol+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            finished+=1;counts[result['status']]=counts.get(result['status'],0)+1
            status={'total':len(stocks),'processed':finished,'counts':counts,'latest_symbol':symbol,'candidate':str(candidate.resolve()),'formal_gate_released':False}
            (run/'warmup_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
            if finished%100==0:print(json.dumps(status),flush=True)
    return status


def dated_signal_prices(raw, factors):
    """Numerical effective-date conversion, NOT publication-time certification."""
    import math
    unique = {}
    for factor in factors:
        effective = date.fromisoformat(str(factor['d'])).isoformat()
        value = float(factor['f'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('invalid factor')
        if effective in unique and unique[effective] != value:
            raise ValueError('conflicting factors on one effective date')
        unique[effective] = value
    dated = [{'d':d,'f':v} for d,v in unique.items() if d <= raw[0]]
    if not dated:
        raise ValueError('no factor effective before actual quote')
    factor = float(max(dated, key=lambda v: v['d'])['f'])
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('invalid factor')
    return [round(float(raw[i]) * factor, 2) for i in (1, 3, 4, 2)]


def real_prior_row(symbol, raw, factors):
    """Convert a real quote; never manufacture turnover or an execution VWAP."""
    import math
    from decimal import Decimal
    op, hi, lo, cl = (float(raw[i]) for i in (1, 3, 4, 2))
    if not all(math.isfinite(v) and v > 0 for v in (op, hi, lo, cl)) or not lo <= min(op, cl) <= max(op, cl) <= hi:
        raise ValueError('invalid source OHLC')
    if date.fromisoformat(raw[0]).weekday() >= 5:
        raise ValueError('non-session quote')
    if len(raw) <= 8 or not raw[8]:
        raise ValueError('source turnover absent; do not fill with zero')
    shares = Decimal(str(raw[5])) * 100
    amount = float(Decimal(str(raw[8])) * 10000)
    if shares != shares.to_integral_value() or shares <= 0 or not math.isfinite(amount) or amount <= 0:
        raise ValueError('invalid source turnover')
    volume = int(shares)
    average = amount / volume
    vwap = average if lo <= average <= hi else None
    return [raw[0], symbol, op, hi, lo, cl, volume, vwap, 1, 0, 0, amount,
            None, None, *dated_signal_prices(raw, factors)]


def complete_warmup_overlaps(run: Path):
    """Retry only missing overlap windows, not conflicting adjustment scales."""
    import hashlib
    import traceback
    from datetime import datetime, timezone
    import requests
    from .real_market import SQLiteMarketCache
    from .tencent_bse import price_conflict
    cache = SQLiteMarketCache(run/'candidate.sqlite')
    target = run/'warmup_overlap_evidence'; target.mkdir(exist_ok=True)
    results = []
    for path in sorted((run/'warmup_jobs').glob('*.json')):
        original = json.loads(path.read_text(encoding='utf-8'))
        if original.get('overlap') or original['status'] == 'ready_real_prior_quote':
            continue
        symbol = original['symbol']; saved = target/(symbol+'.json')
        if saved.exists():
            results.append(json.loads(saved.read_text(encoding='utf-8'))); continue
        item = {'symbol': symbol, 'status': 'still_unverified', 'original_job': str(path.resolve())}
        try:
            with cache.connect() as c:
                old = dict(c.execute("SELECT * FROM accepted_bars WHERE symbol=? AND trading_date>='2015-06-01' ORDER BY trading_date LIMIT 1", (symbol,)).fetchone())
            code = ('sh' if symbol.startswith('6') else 'sz') + symbol
            time.sleep(.25)
            response = requests.get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',
                params={'param': f"{code},day,{old['trading_date']},{old['trading_date']},1,"}, timeout=20)
            response.raise_for_status()
            raw_path = target/(symbol+'.response'); raw_path.write_bytes(response.content)
            item['source'] = {'url': response.url, 'path': str(raw_path.resolve()),
                'sha256': hashlib.sha256(response.content).hexdigest(), 'fetched_at': datetime.now(timezone.utc).isoformat()}
            rows = response.json().get('data', {}).get(code, {}).get('day', [])
            raw = next((r for r in rows if r[0] == old['trading_date']), None)
            if raw is None:
                raise ValueError('requested first observed date not returned')
            signal = dated_signal_prices(raw, original['factors'])
            checks = [not price_conflict(float(raw[i]), old[k]) for i, k in ((1,'open'),(3,'high'),(4,'low'),(2,'close'))]
            checks += [old['signal_'+k] is not None and not price_conflict(v, old['signal_'+k]) for k,v in zip(('open','high','low','close'), signal)]
            item['comparison'] = {'raw': raw, 'adjusted': signal, 'stored': old, 'passed': all(checks)}
            if all(checks):
                row = real_prior_row(symbol, original['raw_prior'], original['factors'])
                item['insert_row'] = row
                item['factor_causality'] = 'publication/normalization unverified; numerical seam only'
                with cache.connect() as c:
                    exists = c.execute('SELECT * FROM bars WHERE trading_date=? AND symbol=?', row[:2]).fetchone()
                    if not exists:
                        c.execute('INSERT INTO bars VALUES ('+','.join('?'*18)+')', row)
                        cache._invalidate_audit(c)
                    elif tuple(exists) != tuple(row):
                        raise ValueError('resume candidate contains a conflicting prior quote')
                    c.execute('INSERT OR REPLACE INTO warmup_evidence VALUES (?,?)', (symbol,json.dumps(item)))
                item['status'] = 'ready_real_prior_quote'
        except Exception as error:
            item['error'] = str(error); item['traceback'] = traceback.format_exc()
        saved.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
        results.append(item)
    summary = {'targeted_missing_overlap':len(results), 'additional_ready':sum(r['status']=='ready_real_prior_quote' for r in results), 'rows':results}
    (run/'warmup_overlap_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def corrected_chinext_inference(row, previous, listing, previous_session, factors):
    """Repair a recognizable legacy *derived* rule, never an exchange quote.

    Ex-right, first-session, resumed and nonmatching derivations stay unknown.
    This does not certify historical eligibility or official reference prices.
    """
    from decimal import Decimal, ROUND_HALF_UP
    from .real_market import _infer_limits, _same_price
    day = row['trading_date']
    if not row['symbol'].startswith(('300','301')) or day < '2020-08-24':
        return None, 'outside_proven_rule'
    if not listing or (date.fromisoformat(day)-date.fromisoformat(listing)).days < 30:
        return None, 'IPO_or_listing_evidence_unresolved'
    if not previous or previous['trading_date'] != previous_session:
        return None, 'resume_or_reference_gap'
    try:
        effective = lambda d: max((f for f in factors if f['d'] <= d), key=lambda f:f['d'])['f']
        if effective(day) != effective(previous_session):
            return None, 'corporate_action_reference_unresolved'
    except (ValueError,KeyError):
        return None, 'factor_evidence_unavailable'
    old_up = float((Decimal(str(previous['close']))*Decimal('1.05')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    old_down = float((Decimal(str(previous['close']))*Decimal('.95')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    if row['up_limit'] != old_up or row['down_limit'] != old_down:
        return None, 'stored_limits_not_exact_legacy_derivation'
    up, down = _infer_limits(row['symbol'], '', date.fromisoformat(day), previous['close'])
    # Only derived metadata is changed. All raw and signal prices are untouched.
    new = {'up_limit':up, 'down_limit':down,
           'limit_up_locked':int(_same_price(row['open'],row['high'],row['low'],row['close'],up)),
           'limit_down_locked':int(_same_price(row['open'],row['high'],row['low'],row['close'],down))}
    return new, 'legacy_5pct_derivation_recomputed_under_20pct_rule'


def repair_chinext_inference(run: Path, baseline_report: Path, source_review: Path):
    import hashlib
    from collections import Counter
    from datetime import datetime, timezone
    import requests
    from .real_market import SQLiteMarketCache
    before = json.loads(baseline_report.read_text(encoding='utf-8'))
    keys = [r for r in before['quality']['rows'] if r['root']=='confirmed_chinext_ST_rule_precedence_bug']
    calendar = sorted(json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates'])
    previous_sessions = dict(zip(calendar[1:],calendar[:-1]))
    evidence = run/'limit_rule_evidence'; evidence.mkdir(exist_ok=True)
    factors_by_symbol = {}; errors = {}
    for symbol in sorted({r['symbol'] for r in keys}):
        try:
            saved = evidence/(symbol+'.response')
            if not saved.exists():
                time.sleep(.25)
                response = requests.get(f'https://finance.sina.com.cn/realstock/company/sz{symbol}/hfq.js',timeout=20)
                response.raise_for_status(); saved.write_bytes(response.content)
                (evidence/(symbol+'.json')).write_text(json.dumps({'url':response.url,
                    'sha256':hashlib.sha256(response.content).hexdigest(),'fetched_at':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
            factors_by_symbol[symbol] = json.JSONDecoder().raw_decode(saved.read_text(encoding='utf-8-sig').split('=',1)[1].strip())[0]['data']
        except Exception as error:
            errors[symbol] = str(error)
    cache = SQLiteMarketCache(run/'candidate.sqlite'); changed=[]; skipped=Counter(); unresolved=[]
    with cache.connect() as c:
        c.execute('PRAGMA busy_timeout=30000'); c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS derived_limit_repair_journal(symbol TEXT,trading_date TEXT,before_json TEXT,after_json TEXT,evidence TEXT,PRIMARY KEY(symbol,trading_date))')
        for key in keys:
            symbol,day=key['symbol'],key['date']
            if c.execute('SELECT 1 FROM derived_limit_repair_journal WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone():
                continue
            row=dict(c.execute('SELECT * FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone())
            previous=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1',(symbol,day)).fetchone()
            listing=c.execute('SELECT list_date FROM stocks WHERE symbol=?',(symbol,)).fetchone()[0]
            corrected,reason=corrected_chinext_inference(row,previous,listing,previous_sessions.get(day),factors_by_symbol.get(symbol,[]))
            if corrected is None:
                skipped[reason]+=1;unresolved.append({'symbol':symbol,'date':day,'reason':reason});continue
            basis={'rule':'SZSE ChiNext 20% from 2020-08-24, including ST; not an audit tolerance change',
                'official_notice':'https://www.szse.cn/disclosure/notice/general/t20200710_579459.html',
                'effective_date':'https://www.szse.cn/aboutus/trends/conference/t20200821_580925.html',
                'factor_response':str((evidence/(symbol+'.response')).resolve()),
                'factor_sha256':hashlib.sha256((evidence/(symbol+'.response')).read_bytes()).hexdigest(),
                'previous_stored':dict(previous),'remaining':'official per-day reference/eligibility and publication causality not certified'}
            c.execute('INSERT INTO derived_limit_repair_journal VALUES (?,?,?,?,?)',(symbol,day,json.dumps(row),json.dumps(corrected),json.dumps(basis)))
            c.execute('UPDATE bars SET up_limit=?,down_limit=?,limit_up_locked=?,limit_down_locked=? WHERE symbol=? AND trading_date=?',
                (*corrected.values(),symbol,day))
            changed.append({'symbol':symbol,'date':day,'before':{k:row[k] for k in corrected},'after':corrected,'reason':reason})
        if changed:cache._invalidate_audit(c)
    result={'target_rows':len(keys),'changed_derived_rows':len(changed),'skipped':dict(skipped),'source_errors':errors,
        'changes':changed,'unresolved':unresolved,'raw_and_signal_prices_changed':False,'official_reference_causality_verified':False}
    (run/'limit_rule_repair.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def fill_replayed_missing(run: Path):
    """Use already replayed archives only, and require matching adjacent seams."""
    import hashlib
    from contextlib import closing
    from datetime import datetime, timezone
    import requests
    from py_mini_racer import MiniRacer
    from akshare.stock.cons import hk_js_decode
    from .real_market import SQLiteMarketCache, _infer_limits, _same_price
    from .tencent_bse import price_conflict
    cache=SQLiteMarketCache(run/'candidate.sqlite');results=[]
    cases=json.loads((run/'targeted_archive_missing.json').read_text(encoding='utf-8'))
    for case in cases:
        if not case['raw_missing_dates']:continue
        symbol=case['symbol']; item={'symbol':symbol,'status':'unresolved','dates':[r['date'][:10] for r in case['raw_missing_dates']]}
        try:
            raw_path=run/'decoder_replay'/(case['raw_sha256']+'.response')
            content=raw_path.read_bytes()
            if hashlib.sha256(content).hexdigest()!=case['raw_sha256']:raise ValueError('raw response hash mismatch')
            with closing(MiniRacer()) as decoder:
                decoder.eval(hk_js_decode)
                decoded=decoder.call('d',content.decode().split('=',1)[1].split(';',1)[0].strip().strip('"'))
            mapped={r['date'][:10]:r for r in decoded}
            response=requests.get(f'https://finance.sina.com.cn/realstock/company/sz{symbol}/hfq.js',timeout=20)
            response.raise_for_status();factor_path=run/(symbol+'_targeted_factor.response');factor_path.write_bytes(response.content)
            factors=json.JSONDecoder().raw_decode(response.text.split('=',1)[1].strip())[0]['data']
            def converted(r):
                # Exact source units: shares and CNY; convert through the shared
                # quote validator without estimating turnover from prices.
                from decimal import Decimal
                raw=[r['date'][:10],r['open'],r['close'],r['high'],r['low'],
                    str(Decimal(str(r['volume']))/100),{},'',str(Decimal(str(r['amount']))/10000)]
                return real_prior_row(symbol,raw,factors)
            item['raw_response_sha256']=case['raw_sha256']
            item['factor_response']={'url':response.url,'path':str(factor_path.resolve()),'sha256':hashlib.sha256(response.content).hexdigest(),'fetched_at':datetime.now(timezone.utc).isoformat()}
            item['repaired']=[];item['unresolved']=[]
            for raw in case['raw_missing_dates']:
                day=raw['date'][:10]
                with cache.connect() as c:
                    previous=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1',(symbol,day)).fetchone()
                    following=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date>? ORDER BY trading_date LIMIT 1',(symbol,day)).fetchone()
                comparisons=[]
                for old in (previous,following):
                    if old is None or old['trading_date'] not in mapped:continue
                    row=converted(mapped[old['trading_date']])
                    checks=[not price_conflict(row[i],old[k]) for i,k in ((2,'open'),(3,'high'),(4,'low'),(5,'close'),(14,'signal_open'),(15,'signal_high'),(16,'signal_low'),(17,'signal_close'))]
                    comparisons.append({'date':old['trading_date'],'passed':all(checks),'stored':dict(old),'converted':row})
                if len(comparisons)!=2 or not all(r['passed'] for r in comparisons):
                    item['unresolved'].append({'date':day,'reason':'raw bar exists but surrounding signal/raw seam not verified','comparisons':comparisons});continue
                row=converted(raw)
                with cache.connect() as c:
                    name=c.execute('SELECT name FROM stocks WHERE symbol=?',(symbol,)).fetchone()[0]
                    up,down=_infer_limits(symbol,name,date.fromisoformat(day),previous['close'])
                    row[12:14]=[up,down]
                    row[9]=int(_same_price(*row[2:6],up));row[10]=int(_same_price(*row[2:6],down))
                    evidence={'raw':raw,'conversion':'Sina native shares/CNY; effective-date signal multiplier; no OHLC edits','inserted':row,'comparisons':comparisons,
                        'raw_sha256':case['raw_sha256'],'factor_source':item['factor_response'],
                        'remaining_blocker':'inferred limit/reference, factor publication and trading scope still require historical validation'}
                    c.execute('CREATE TABLE IF NOT EXISTS targeted_fill_journal(symbol TEXT,trading_date TEXT,evidence TEXT,PRIMARY KEY(symbol,trading_date))')
                    if c.execute('SELECT 1 FROM session_evidence WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone():
                        raise ValueError('actual quote contradicts independently recorded suspension')
                    if not c.execute('SELECT 1 FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone():
                        c.execute('INSERT INTO bars VALUES ('+','.join('?'*18)+')',row)
                        c.execute('INSERT INTO targeted_fill_journal VALUES (?,?,?)',(symbol,day,json.dumps(evidence)))
                        cache._invalidate_audit(c)
                    item['repaired'].append(evidence)
            item['status']='reviewed; unresolved causality remains'
        except Exception as error:item['error']=str(error)
        results.append(item)
    (run/'targeted_fill_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


def apply_verified_events(snapshot: Path, run: Path, source_review: Path):
    """Reconcile independent event intervals against a fixed baseline before writes."""
    from collections import Counter
    import bisect
    import hashlib
    from .data_audit import full_day_event_dates
    from .real_market import SQLiteMarketCache
    calendar=json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates']
    reference=sorted(d for d in calendar if '2015-06-01'<=d<='2026-09-30')
    events=json.loads((run/'suspension_events.json').read_text(encoding='utf-8'))
    event_digest=hashlib.sha256((run/'suspension_events.json').read_bytes()).hexdigest()
    old=SnapshotCache(snapshot);accepted={};reasons=Counter();reviews=[]
    with old.connect() as c:
        inventory={r['symbol']:dict(r) for r in c.execute('SELECT * FROM stocks')}
        for event in events['rows']:
            symbol=event.get('SECURITY_CODE');stock=inventory.get(symbol)
            full=full_day_event_dates(event,reference)
            if not stock or not full:reasons['unknown_security_or_no_full_day']+=1;continue
            end=(event.get('SUSPEND_END_TIME') or '')[:10]
            resume_index=bisect.bisect_right(reference,end)
            if resume_index>=len(reference):reasons['no_historical_resume_in_window']+=1;continue
            resume=reference[resume_index]
            full=[d for d in full if (not stock['list_date'] or d>=stock['list_date']) and (not stock['delist_date'] or d<stock['delist_date'])]
            if not full:continue
            present={r[0] for r in c.execute('SELECT trading_date FROM bars WHERE symbol=? AND trading_date BETWEEN ? AND ?',(symbol,full[0],full[-1]))}
            if present & set(full):reasons['event_conflicts_with_observed_session']+=1;continue
            row=c.execute('SELECT volume,tradable FROM bars WHERE symbol=? AND trading_date=?',(symbol,resume)).fetchone()
            if not row or row['volume']<=0 or not row['tradable']:
                reasons['resume_not_corroborated_by_actual_quote']+=1;continue
            evidence={'event':event,'observed_resume':resume,
                'source_manifest':str((run/'suspension_events.json').resolve()),
                'source_manifest_sha256':event_digest,
                'classification':'explicit event covers complete trading session; actual resume corroborated; no OHLC fabricated'}
            reviews.append({'symbol':symbol,'start':full[0],'end':full[-1],'sessions':len(full),'resume':resume})
            for day in full:accepted.setdefault((symbol,day),evidence)
    candidate=SQLiteMarketCache(run/'candidate.sqlite')
    with candidate.connect() as c:
        c.execute('PRAGMA busy_timeout=30000');c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS session_evidence(symbol TEXT,trading_date TEXT,status TEXT,evidence TEXT,PRIMARY KEY(symbol,trading_date))')
        for (symbol,day),evidence in accepted.items():
            if c.execute('SELECT 1 FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone():
                raise ValueError('candidate quote conflicts with suspension evidence')
            c.execute('INSERT OR IGNORE INTO session_evidence VALUES (?,?,?,?)',(symbol,day,'verified_full_day_suspension',json.dumps(evidence,ensure_ascii=False)))
        if accepted:candidate._invalidate_audit(c)
    replay=json.loads((run/'decoder_replay.json').read_text(encoding='utf-8'))
    isolated=[]
    with candidate.connect() as c:
        c.execute('PRAGMA busy_timeout=30000');c.execute('BEGIN IMMEDIATE')
        for item in replay['weekend_cases']:
            if item['conclusion']!='non_session_capital_merge_echo' or item['date'] in reference:continue
            item['calendar_evidence']={'independent_calendar':str(source_review.resolve()),
                'official_2017_notice':'https://www.szse.cn/disclosure/notice/general/t20170921_502167.html',
                'official_2018_calendar':'https://www.sse.com.cn/disclosure/announcement/general/c/c_20171222_4438363.shtml'}
            c.execute('INSERT OR IGNORE INTO provider_quarantine VALUES (?,?,?,?,?)',(item['symbol'],item['date'],'Sina.KLC+calendar',json.dumps(item,ensure_ascii=False),'confirmed_non_session_excluded'))
            isolated.append({'symbol':item['symbol'],'date':item['date'],'original_row_retained':True,'formal_view_excluded':True,'actual_echo_dates':item['same_values_actual_dates']})
        if isolated:candidate._invalidate_audit(c)
    result={'independent_events':len(events['rows']),'accepted_full_day_stock_dates':len(accepted),'accepted_event_intervals':reviews,
        'rejected_or_unverified_events':dict(reasons),'weekend_isolations':isolated,'no_fabricated_bars':True,
        'coverage_claim':'Only corroborated event intervals; no claim of full-market historical event coverage'}
    (run/'event_reconciliation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='accepted_event_intervals'},ensure_ascii=False),flush=True)
    return result


def collect_baostock_evidence(run: Path, jobs: list[dict]) -> dict:
    """Bounded public daily evidence; capture original protocol responses.

    Empty, failed, capped and complete results remain distinct. Cached failures
    are evidence, not invitations to endlessly repeat an identical request.
    """
    import hashlib
    import socket
    from datetime import datetime, timezone
    import baostock as bs
    import baostock.util.socketutil as transport
    from unittest.mock import patch
    folder=run/'baostock';folder.mkdir(parents=True,exist_ok=True)
    fields='date,code,open,high,low,close,preclose,volume,amount,adjustflag,tradestatus,isST'
    counts={};results=[];failures=0;old_timeout=socket.getdefaulttimeout();socket.setdefaulttimeout(12)
    try:
        login=bs.login()
        if login.error_code!='0':raise RuntimeError('BaoStock guest login failed: '+login.error_msg)
        send=transport.send_msg
        for job in jobs:
            request={'code':job['code'],'start':job['start'],'end':job['end'],'adjustflag':job.get('adjustflag','3'),'fields':fields}
            key=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            saved=folder/(key+'.json')
            if saved.exists():
                result=json.loads(saved.read_text(encoding='utf-8'))
                for raw in result.get('protocol_responses',[]):
                    if hashlib.sha256(Path(raw['path']).read_bytes()).hexdigest()!=raw['sha256']:
                        raise ValueError('cached source response hash mismatch')
            else:
                refs=[]
                def capture(message):
                    response=send(message)
                    if response is not None:
                        data=response.encode('utf-8');digest=hashlib.sha256(data).hexdigest();path=folder/(digest+'.response')
                        if not path.exists():path.write_bytes(data)
                        refs.append({'path':str(path.resolve()),'sha256':digest})
                    return response
                result={'request':request,'package_version':'0.9.1','fetched_at':datetime.now(timezone.utc).isoformat(),'rows':[], 'protocol_responses':refs}
                try:
                    time.sleep(.12)
                    with patch.object(transport,'send_msg',capture):
                        query=bs.query_history_k_data_plus(job['code'],fields,start_date=job['start'],end_date=job['end'],frequency='d',adjustflag=request['adjustflag'])
                        while query.error_code=='0' and query.next():
                            result['rows'].append(query.get_row_data())
                            if len(result['rows'])>9999:raise ValueError('unexpected full-page result; explicit pagination review required')
                    result.update(fields=query.fields,error_code=query.error_code,error_message=query.error_msg,final_page=query.cur_page_num)
                    result['status']='complete' if query.error_code=='0' and result['rows'] else ('empty_not_absence_proof' if query.error_code=='0' else 'source_error')
                    if result['status']=='complete' and (len(refs)!=1 or len(query.data)>=10000):
                        result['status']='pagination_unverified'
                except Exception as error:
                    result.update(status='source_error',exception=f'{type(error).__name__}: {error}')
                saved.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            counts[result['status']]=counts.get(result['status'],0)+1
            results.append({'job':job,'path':str(saved.resolve()),'status':result['status'],'rows':len(result['rows'])})
            status={'processed':len(results),'total':len(jobs),'counts':counts}
            (run/'evidence_collection_status.json').write_text(json.dumps(status),encoding='utf-8')
            if len(results)%100==0:print(status,flush=True)
            if result['status']=='source_error' and (not result.get('protocol_responses') or result.get('error_code')=='10001001'):
                failures+=1
                if failures>=3:break
                # A timed-out stream is not reusable: reconnect once, never
                # keep sending thousands of queries into a broken connection.
                import baostock.common.context as context
                connection=getattr(context,'default_socket',None)
                if connection:connection.close()
                if bs.login().error_code!='0':break
            else:failures=0
        bs.logout()
    finally:socket.setdefaulttimeout(old_timeout)
    summary={'queries':results,'counts':counts,'unattempted':jobs[len(results):], 'public_guest':True,'purchased_service':False,'max_page_rows':10000}
    plan_id=hashlib.sha256(json.dumps(jobs,sort_keys=True).encode()).hexdigest()[:16]
    (run/('baostock_collection_'+plan_id+'.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def verified_daily_limits(stored, source, listing_date):
    """Numerical correction from dated status/reference, not today's ST name.

    Unknown historical regimes and IPO/resumption exceptions are not waived.
    Raw OHLC must agree before this evidence can change derived metadata.
    """
    from .real_market import _infer_limits, _same_price
    from .tencent_bse import price_conflict
    import math
    day=stored['trading_date'];symbol=stored['symbol']
    if source.get('adjustflag')!='3' or source.get('tradestatus')!='1' or source.get('isST') not in {'0','1'}:
        return None,'missing_raw_trading_or_ST_evidence'
    if symbol.startswith(('4','8','9')):return None,'BSE_historical_regime_unverified'
    if not listing_date or (date.fromisoformat(day)-date.fromisoformat(listing_date)).days<30:
        return None,'IPO_exception_requires_independent_rule_evidence'
    if source['isST']=='1' and day>='2025-01-01' and not symbol.startswith(('300','301','688','689')):
        return None,'later_mainboard_ST_regime_requires_dated_rule'
    if any(price_conflict(source[k],stored[k]) for k in ('open','high','low','close')):
        return None,'raw_price_conflict'
    reference=float(source['preclose'])
    if not math.isfinite(reference) or reference<=0:return None,'invalid_reference'
    up,down=_infer_limits(symbol,'ST' if source['isST']=='1' else '',date.fromisoformat(day),reference)
    if stored['close']>up+.005 or stored['close']<down-.005:
        return None,'special_session_or_reference_still_conflicts'
    return {'up_limit':up,'down_limit':down,
            'limit_up_locked':int(_same_price(*(stored[k] for k in ('open','high','low','close')),up)),
            'limit_down_locked':int(_same_price(*(stored[k] for k in ('open','high','low','close')),down))},'dated_status_and_source_reference'


def corroborated_turnover_correction(stored, daily, native):
    """Correct proven share precision loss; never replace VWAP by a price.

    Two raw sources must agree on exact shares and on the stored OHLC. Amount
    must agree with the stored amount in the daily source; a one-yuan native
    reporting difference is evidence only, not permission to alter amount.
    """
    from decimal import Decimal
    from .tencent_bse import price_conflict
    if daily.get('adjustflag')!='3' or daily.get('tradestatus')!='1':return None
    if any(price_conflict(stored[k],daily[k]) or price_conflict(stored[k],native[k]) for k in ('open','high','low','close')):return None
    exact=Decimal(str(daily['volume']));other=Decimal(str(native['volume']))
    if exact<=0 or exact!=other or exact!=exact.to_integral_value():return None
    volume=int(exact)
    if stored['volume']==volume or stored['volume']%100!=0 or abs(stored['volume']-volume)>=100:return None
    amount=Decimal(str(daily['amount']))
    if amount!=Decimal(str(stored['amount'])) or abs(amount-Decimal(str(native['amount'])))>1:return None
    average=float(amount/exact)
    return {'volume':volume,'vwap':average if stored['low']<=average<=stored['high'] else None}


def build_batch3_patch(run: Path, baseline_run: Path):
    """Produce evidence-backed candidate changes. Does not mutate the database."""
    import hashlib
    import math
    from collections import Counter,defaultdict
    from decimal import Decimal
    from .phase4_acceptance import SnapshotCache
    from .tencent_bse import price_conflict
    baseline=json.loads((baseline_run/'final_reaudit/final_reaudit.json').read_text(encoding='utf-8'))
    cache=SnapshotCache(Path(baseline['snapshot']['path']))
    index={};conflicts=set();files={};source_counts=Counter()
    for path in sorted(run.glob('official_*.md')):
        files[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted((run/'baostock').glob('*.json')):
        result=json.loads(path.read_text(encoding='utf-8'));source_counts[result['status']]+=1
        if result['status']!='complete':continue
        files[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
        for ref in result['protocol_responses']:files[ref['path']]=ref['sha256']
        for values in result['rows']:
            if len(values)!=len(result['fields']):raise ValueError('source field count differs')
            row=dict(zip(result['fields'],values));key=(row['code'].split('.')[-1],row['date'],row['adjustflag'])
            if key in index and index[key][0]!=row:conflicts.add(key)
            else:index[key]=(row,str(path.resolve()))
    for key in conflicts:index.pop(key,None)
    changes={};quality=[];suspensions=[];warmup=[];skips=Counter();skip_rows=[]
    def put(table,before,after,evidence):
        key=(table,tuple(after[k] for k in REPAIR_KEYS[table]))
        if key in changes:raise ValueError('multiple competing repairs; merge evidence explicitly')
        changes[key]={'table':table,'before':before,'after':after,'evidence':evidence}
    with cache.connect() as c:
        stocks={r['symbol']:dict(r) for r in c.execute('SELECT * FROM stocks')}
        old_explained={(r[0],r[1]):dict(r) for r in c.execute('SELECT * FROM session_evidence')}
        calendar=[r[0] for r in c.execute("SELECT trading_date FROM benchmarks WHERE name='CSI300' AND trading_date BETWEEN '2015-06-01' AND '2026-09-30' ORDER BY trading_date")]
        calendar_set=set(calendar)
        for (symbol,day,mode),(source,path) in sorted(index.items()):
            if mode!='3' or day not in calendar_set or symbol not in stocks:continue
            stock=stocks[symbol]
            if (stock['list_date'] and day<stock['list_date']) or (stock['delist_date'] and day>=stock['delist_date']):continue
            observed=c.execute('SELECT 1 FROM accepted_bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone()
            if source.get('tradestatus')=='0' and Decimal(source.get('volume') or '0')==0 and Decimal(source.get('amount') or '0')==0:
                if observed:
                    suspensions.append({'symbol':symbol,'date':day,'status':'conflicts_with_stored_quote','source':path});continue
                if (symbol,day) in old_explained:continue
                evidence={'source':'BaoStock explicit daily tradestatus=0; not quote absence','source_file':path,'original_row':source,
                          'semantics':'daily full-session status; provider carried prices deliberately not inserted as bars'}
                after={'symbol':symbol,'trading_date':day,'status':'verified_full_day_suspension','evidence':json.dumps(evidence,sort_keys=True)}
                put('session_evidence',None,after,evidence)
                suspensions.append({'symbol':symbol,'date':day,'status':'independent_daily_suspension','source':path})
            elif source.get('tradestatus')=='1' and float(source.get('volume') or 0)>0:
                if (symbol,day) in old_explained:
                    old=old_explained[symbol,day];new={**old,'status':'conflicting_independent_daily_status',
                        'evidence':json.dumps({'prior_evidence':json.loads(old['evidence']),'new_daily_source':path,'raw':source},sort_keys=True)}
                    put('session_evidence',old,new,{'new_problem':'event evidence contradicted by independent positive-volume daily quote'})
                    suspensions.append({'symbol':symbol,'date':day,'status':'new_conflict_previously_explained','source':path})
                elif not observed:suspensions.append({'symbol':symbol,'date':day,'status':'actual_source_quote_exists_signal_seam_not_yet_verified','source':path})
        for flagged in baseline['quality']['rows']:
            symbol,day=flagged['symbol'],flagged['date'];pair=index.get((symbol,day,'3'))
            if not pair:continue
            source,path=pair;old=dict(c.execute('SELECT * FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone())
            try:fixed,reason=verified_daily_limits(old,source,stocks[symbol]['list_date'])
            except (ValueError,KeyError):fixed,reason=None,'source_field_invalid'
            if fixed and any(old[k]!=v for k,v in fixed.items()):
                previous=c.execute('SELECT close,trading_date FROM accepted_bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1',(symbol,day)).fetchone()
                causes=[]
                if 'ST' in stocks[symbol]['name'].upper() and source['isST']=='0':causes.append('current_ST_name_backcast_disproved_by_dated_status')
                if previous and price_conflict(previous['close'],source['preclose']):causes.append('previous_actual_close_not_source_reference_price')
                if not causes:causes.append('stored_derived_rule_differs_from_dated_source_reference')
                evidence={'source_file':path,'original_row':source,'previous_actual':dict(previous) if previous else None,
                    'historical_rule':'date-specific existing rule; IPO/later-mainboard-ST exceptions not guessed',
                    'confirmed_causes':causes,'official_daily_reference_certification':'not asserted; provider evidence retained'}
                new={**old,**fixed};put('bars',old,new,evidence)
                quality.append({'symbol':symbol,'date':day,'causes':causes,'source':path,'before':old,'after':new})
            elif fixed is None:
                skips[reason]+=1
                skip_rows.append({'symbol':symbol,'date':day,'reason':reason,'source':path})
        native_path=run/'native_turnover_corrections.json'
        if native_path.exists():
            files[str(native_path.resolve())]=hashlib.sha256(native_path.read_bytes()).hexdigest()
            for item in json.loads(native_path.read_text(encoding='utf-8')):
                symbol,day=item['symbol'],item['date'];pair=index.get((symbol,day,'3'))
                if not pair:continue
                old=dict(c.execute('SELECT * FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone())
                fixed=corroborated_turnover_correction(old,pair[0],item['native'])
                if fixed is None:continue
                ref=item['reference'];files[ref['path']]=ref['sha256']
                evidence={'confirmed_causes':['corroborated_stored_share_precision_loss'],
                          'daily_source':pair[1],'native_reference':ref,'native_row':item['native'],
                          'daily_row':pair[0],'conversion':'exact integer shares; amount unchanged; no estimated VWAP'}
                key=('bars',(day,symbol))
                if key in changes:
                    changes[key]['after'].update(fixed)
                    changes[key]['evidence']['turnover_correction']=evidence
                else:put('bars',old,{**old,**fixed},evidence)
                quality.append({'symbol':symbol,'date':day,'causes':evidence['confirmed_causes'],
                                'source':pair[1],'before':old,'after':changes[key]['after']})
        unresolved=json.loads((baseline_run/'batch2_comparison.json').read_text(encoding='utf-8'))['warmup']['unresolved']
        for item in unresolved:
            symbol=item['symbol'];first=dict(c.execute("SELECT * FROM bars WHERE symbol=? AND trading_date>='2015-06-01' ORDER BY trading_date LIMIT 1",(symbol,)).fetchone())
            prior=item['observed_raw_prior_date'];raw=index.get((symbol,prior,'3'));adjusted=index.get((symbol,prior,'1'))
            overlap_raw=index.get((symbol,first['trading_date'],'3'));overlap_adj=index.get((symbol,first['trading_date'],'1'))
            review={'symbol':symbol,'listing':stocks[symbol]['list_date'],'prior_date':prior,'first_signal_date':first['trading_date'],
                'category':'history_exists_source_adjustment_conflict','source_attempts':['saved Tencent raw/Sina factor seam','BaoStock raw/native HFQ'],
                'remaining_fields':['source-consistent prior signal_close','factor publication/normalization lineage'],'formal_ready':False}
            if not all((raw,adjusted,overlap_raw,overlap_adj)):
                review['category']='source_cannot_cover_requested_identity_or_date';review['reason']='One or more explicit raw/HFQ prior/overlap rows absent; not proof of objective history shortage'
            else:
                review['sources']=[v[1] for v in (raw,adjusted,overlap_raw,overlap_adj)]
                try:
                    match=all(not price_conflict(overlap_raw[0][k],first[k]) and first['signal_'+k] is not None and not price_conflict(overlap_adj[0][k],first['signal_'+k]) for k in ('open','high','low','close'))
                    if match and raw[0]['tradestatus']=='1' and adjusted[0]['tradestatus']=='1':
                        source=raw[0];volume=int(source['volume']);amount=float(source['amount']);average=amount/volume if volume>0 else None
                        prices={k:float(source[k]) for k in ('open','high','low','close')}
                        if volume<=0 or amount<=0 or not all(math.isfinite(v) and v>0 for v in prices.values()):raise ValueError('invalid real quote')
                        if not prices['low']<=min(prices['open'],prices['close'])<=max(prices['open'],prices['close'])<=prices['high']:raise ValueError('invalid OHLC')
                        new={'trading_date':prior,'symbol':symbol,**prices,'volume':volume,'amount':amount,
                            'vwap':average if prices['low']<=average<=prices['high'] else None,'tradable':1,'up_limit':None,'down_limit':None,'limit_up_locked':0,'limit_down_locked':0,
                            **{'signal_'+k:float(adjusted[0][k]) for k in prices}}
                        put('bars',None,new,{'warmup':review,'raw':source,'native_adjusted':adjusted[0],'overlap_stored':first,'not_for_warmup_trades':True})
                        review['category']='real_prior_added_native_source_overlap_passed'
                    else:review['reason']='Native source HFQ differs from stored signal scale; no arbitrary rescaling'
                except (ValueError,KeyError,ZeroDivisionError) as error:review['reason']=str(error)
            warmup.append(review)
    manifest={'version':'phase4-batch3-evidence-v1','input_snapshot':baseline['snapshot']['id'],
        'source_files':[{'path':k,'sha256':v} for k,v in sorted(files.items())],
        'changes':[changes[k] for k in sorted(changes)]}
    result={'source_result_counts':dict(source_counts),'source_conflict_keys':sorted(conflicts),
        'quality_repairs':quality,'quality_skips':dict(skips),'quality_skip_rows':skip_rows,'suspension_reviews':suspensions,'warmup_940':warmup,
        'warmup_categories':dict(Counter(x['category'] for x in warmup)),'repair_count':len(changes)}
    (run/'repair_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (run/'evidence_classification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest,result


def proven_capital_echo(stored, native_rows, capital_dates, daily):
    """Explain an adapter-created quote, not a vote between empty providers."""
    from decimal import Decimal
    day=stored['trading_date']
    if daily.get('code','').split('.')[-1]!=stored['symbol']:return None
    if daily.get('date')!=day or daily.get('adjustflag')!='3' or daily.get('tradestatus')!='0':return None
    if daily.get('volume') in (None,'') or daily.get('amount') in (None,''):return None
    if Decimal(daily.get('volume') or '0')!=0 or Decimal(daily.get('amount') or '0')!=0:return None
    if day not in capital_dates or any(str(r['date'])[:10]==day for r in native_rows):return None
    earlier=[r for r in native_rows if str(r['date'])[:10]<day]
    if not earlier:return None
    previous=max(earlier,key=lambda r:str(r['date']))
    if any(Decimal(str(previous[k]))!=Decimal(str(stored[k])) for k in ('open','high','low','close','volume','amount')):return None
    return {'cause':'share_capital_outer_join_forward_filled_quote','anchor':previous,
            'stored_false_quote':stored,'daily_full_day_status':daily,
            'capital_date':day,'native_archive_has_no_quote_on_date':True,
            'not_majority_vote':'exact original adapter transformation plus explicit daily halt; absence alone is insufficient'}


def collect_eastmoney_windows(run: Path, jobs: list[dict], *, existing_transport=False):
    """Evidence-only bounded windows on the restored existing provider path."""
    import hashlib
    import requests
    from .real_market import _call_with_requests_timeout
    from collections import Counter
    folder=run/'eastmoney';folder.mkdir(parents=True,exist_ok=True)
    outcomes=[];counts=Counter();consecutive=0
    for job in jobs:
        span=(date.fromisoformat(job['end'])-date.fromisoformat(job['start'])).days
        if span<0 or span>366 or job['adjustflag'] not in {'0','2'} or len(job['symbol'])!=6 or not job['symbol'].isdigit():
            raise ValueError('targeted source window exceeds one year')
        cache_key={'request':job,'transport':'existing_bounded_adapter' if existing_transport else 'requests'}
        key=hashlib.sha256(json.dumps(cache_key,sort_keys=True).encode()).hexdigest();path=folder/(key+'.json')
        legacy=folder/(hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest()+'.json')
        if not existing_transport and legacy.exists():path=legacy
        if path.exists():
            item=json.loads(path.read_text(encoding='utf-8'))
            for attempt in item['attempts']:
                for ref in attempt.get('responses',[]):
                    if hashlib.sha256(Path(ref['file']).read_bytes()).hexdigest()!=ref['sha256']:
                        raise ValueError('cached HTTP source response hash mismatch')
        else:
            item={'request':job,'transport':cache_key['transport'],'provider':'Eastmoney direct; AkShare wrapper is not independent evidence','attempts':[]}
            for attempt in range(2):
                try:
                    time.sleep(.35 if attempt==0 else 2)
                    with capture_responses(folder/'raw') as refs:
                        params={'secid':('1.' if job['symbol'].startswith('6') else '0.')+job['symbol'],
                                    'klt':'101','fqt':job['adjustflag'],'beg':job['start'].replace('-',''),
                                    'end':job['end'].replace('-',''),'lmt':'1000',
                                    'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}
                        def request(**kwargs):
                            return requests.get('https://push2his.eastmoney.com/api/qt/stock/kline/get',params=params,timeout=12)
                        response=_call_with_requests_timeout(request) if existing_transport else request()
                        response.raise_for_status();payload=response.json()
                    item['attempts'].append({'responses':refs,'rc':payload.get('rc')})
                    data=payload.get('data') or {};rows=[r.split(',') for r in data.get('klines',[])]
                    item.update(data=data,rows=rows,status='complete' if rows else 'empty_not_absence_proof')
                    if payload.get('rc')!=0:item['status']='provider_error'
                    if rows and (data.get('code')!=job['symbol'] or len(rows)>=1000 or
                                 len({r[0] for r in rows})!=len(rows) or
                                 any(len(r)<7 or not job['start']<=r[0]<=job['end'] for r in rows)):
                        item['status']='identity_window_or_completeness_conflict'
                    break
                except Exception as error:
                    item['attempts'].append({'error':f'{type(error).__name__}: {error}'})
                    item['status']='source_error'
                    if isinstance(error,requests.HTTPError) and error.response.status_code in (401,403,429):
                        item['status']='access_or_rate_limit';break
            path.write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8')
        counts[item['status']]+=1;outcomes.append({'path':str(path.resolve()),'request':job,'status':item['status']})
        consecutive=consecutive+1 if item['status']=='source_error' else 0
        status={'processed':len(outcomes),'total':len(jobs),'counts':dict(counts),'last':job}
        (run/'eastmoney_status.json').write_text(json.dumps(status),encoding='utf-8')
        if len(outcomes)%100==0:print(status,flush=True)
        if consecutive>=3 or item['status']=='access_or_rate_limit':break
    result={'queries':outcomes,'counts':dict(counts),'unattempted':jobs[len(outcomes):]}
    (run/('eastmoney_plan_'+hashlib.sha256(json.dumps(jobs,sort_keys=True).encode()).hexdigest()[:12]+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def collect_capital_echo_evidence(run: Path, baseline: Path, conflicts=None):
    import requests
    import traceback
    from contextlib import closing
    from py_mini_racer import MiniRacer
    from akshare.stock.cons import hk_js_decode,zh_sina_a_stock_hist_url,zh_sina_a_stock_amount_url
    from akshare.utils import demjson
    cache=SnapshotCache(baseline/'final.sqlite')
    if conflicts is None:
        conflicts=json.loads((baseline/'batch3_comparison.json').read_text(encoding='utf-8'))['quality']['source_conflicts']
    folder=run/'echo_cases';folder.mkdir(parents=True,exist_ok=True);results=[];native_cache={}
    for conflict in conflicts:
        symbol,day=conflict['symbol'],conflict['date'];path=folder/(symbol+'_'+day+'.json')
        if path.exists():results.append(json.loads(path.read_text(encoding='utf-8')));continue
        result={'symbol':symbol,'date':day,'status':'unresolved','prior_conflict':conflict}
        try:
            if symbol not in native_cache:
                code=('sh' if symbol.startswith('6') else 'sz')+symbol
                with capture_responses(folder/'raw') as refs:
                    time.sleep(.3);r=requests.get(zh_sina_a_stock_hist_url.format(code),timeout=15);r.raise_for_status()
                    encoded=r.text.split('=',1)[1].split(';',1)[0].strip().strip('"')
                    with closing(MiniRacer()) as decoder:decoder.eval(hk_js_decode);rows=decoder.call('d',encoded)
                    response=requests.get(zh_sina_a_stock_amount_url.format(code,code),timeout=15);response.raise_for_status()
                text=response.text
                capitals=demjson.decode(text[text.find('['):text.rfind(']')+1]) if '[' in text else []
                native_cache[symbol]=(rows,capitals,refs)
            rows,capitals,refs=native_cache[symbol]
            with cache.connect() as c:stored=dict(c.execute('SELECT * FROM bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone())
            saved=json.loads(Path(conflict['source']).read_text(encoding='utf-8'))
            daily=next(dict(zip(saved['fields'],r)) for r in saved['rows'] if r[0]==day and r[1].endswith(symbol))
            proof=proven_capital_echo(stored,rows,{r['date'] for r in capitals},daily)
            result.update(proof=proof,source_refs=refs,capital_rows=[r for r in capitals if r['date']==day],
                          native_count=len(rows),same_day_native=[r for r in rows if str(r['date'])[:10]==day],
                          daily_source=conflict['source'],daily_protocol=saved['protocol_responses'],
                          status='proven_adapter_echo' if proof else 'unresolved')
        except Exception:result['error']=traceback.format_exc()
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');results.append(result)
        if len(results)%10==0:print('echo evidence',len(results),flush=True)
    (run/'echo_evidence.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


def eastmoney_prior(symbol, prior, overlaps, source_rows):
    """Require three real raw/HFQ seams; this is NOT causal-factor certification."""
    import math
    from decimal import Decimal
    from .tencent_bse import price_conflict
    if prior >= '2015-06-01' or len(overlaps)!=3 or len({r['trading_date'] for r in overlaps})!=3:
        raise ValueError('pre-window quote and three actual overlaps required')
    for old in overlaps:
        if old['trading_date']<'2015-06-01' or old.get('symbol',symbol)!=symbol:
            raise ValueError('overlap security/date mismatch')
        for mode,prefix in (('0',''),('2','signal_')):
            row=source_rows.get((symbol,old['trading_date'],mode))
            if row is None or any(old[prefix+k] is None or price_conflict(row[i],old[prefix+k])
                                  for k,i in (('open',1),('close',2),('high',3),('low',4))):
                raise ValueError('three-date raw/HFQ overlap missing or conflicting')
    raw=source_rows.get((symbol,prior,'0'));adj=source_rows.get((symbol,prior,'2'))
    if raw is None or adj is None:raise ValueError('required actual prior raw/HFQ quote absent')
    prices={k:float(raw[i]) for k,i in (('open',1),('close',2),('high',3),('low',4))}
    signals={'signal_'+k:float(adj[i]) for k,i in (('open',1),('close',2),('high',3),('low',4))}
    shares=Decimal(raw[5])*100;amount=float(raw[6])
    if shares<=0 or shares!=shares.to_integral_value() or not math.isfinite(amount) or amount<=0:
        raise ValueError('missing or invalid actual turnover')
    for p in (prices,{k:signals['signal_'+k] for k in prices}):
        if not all(math.isfinite(v) and v>0 for v in p.values()) or not p['low']<=min(p['open'],p['close'])<=max(p['open'],p['close'])<=p['high']:
            raise ValueError('invalid raw or adjusted OHLC')
    volume=int(shares);average=amount/volume
    return {'trading_date':prior,'symbol':symbol,**prices,**signals,'volume':volume,'amount':amount,
            'vwap':average if prices['low']<=average<=prices['high'] else None,'tradable':1,
            'up_limit':None,'down_limit':None,'limit_up_locked':0,'limit_down_locked':0}


def build_batch4_patch(run: Path, baseline: Path, source_review: Path):
    """Reuse the evidence manifest/CAS workflow on the already isolated candidate.

    Full-day daily status is distinct from a missing quote or an event interval.
    Newly discovered contradictions never silently replace earlier evidence.
    """
    import hashlib
    from collections import Counter
    from decimal import Decimal
    from .tencent_bse import price_conflict
    cache=SnapshotCache(run/'candidate.sqlite')
    old_report=json.loads((baseline/'final_reaudit/final_reaudit.json').read_text(encoding='utf-8'))
    calendar=set(json.loads(source_review.read_text(encoding='utf-8'))['calendar']['dates'])
    files={};index={};conflicts=set();coverage=[]
    def source_file(path):
        files[str(Path(path).resolve())]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    source_file(source_review)
    for folder in ('daily_batch','quality_batch','representative_daily'):
        for path in sorted((run/folder/'baostock').glob('*.json')):
            r=json.loads(path.read_text(encoding='utf-8'));request=r['request']
            coverage.append({'request':request,'status':r['status'],'rows':len(r['rows']),'path':str(path.resolve()),
                             'fields':r.get('fields'),'pages':len(r.get('protocol_responses',[]))})
            if r['status']!='complete':continue
            source_file(path)
            for ref in r['protocol_responses']:files[ref['path']]=ref['sha256']
            seen=set()
            for v in r['rows']:
                if len(v)!=len(r['fields']):raise ValueError('daily field count mismatch')
                row=dict(zip(r['fields'],v));key=(row['code'].split('.')[-1],row['date'])
                if row['code']!=request['code'] or row['adjustflag']!='3' or not request['start']<=row['date']<=request['end'] or key in seen:
                    raise ValueError('daily identity/window/mode/duplicate conflict')
                seen.add(key)
                if key in index and index[key][0]!=row:conflicts.add(key)
                else:index[key]=(row,str(path.resolve()))
    for key in conflicts:index.pop(key,None)
    changes={};daily_reviews=[];quality=[];skips=[];warmup=[]
    def put(table,before,after,evidence):
        key=(table,tuple(after[k] for k in REPAIR_KEYS[table]))
        if key in changes:raise ValueError('competing patch targets')
        changes[key]={'table':table,'before':before,'after':after,'evidence':evidence}
    em={};em_conflicts=set();em_refs={};em_queries=[]
    for folder in ('warmup_probe','warmup_batch','warmup_transport'):
        for path in sorted((run/folder/'eastmoney').glob('*.json')):
            r=json.loads(path.read_text(encoding='utf-8'));job=r['request']
            em_queries.append({'path':str(path.resolve()),'request':job,'status':r['status']})
            if r['status']!='complete':continue
            source_file(path)
            for attempt in r['attempts']:
                for ref in attempt.get('responses',[]):files[ref['file']]=ref['sha256']
            for row in r['rows']:
                key=(job['symbol'],row[0],job['adjustflag'])
                if key in em and em[key]!=row:em_conflicts.add(key)
                else:em[key]=row;em_refs[key]=str(path.resolve())
    for key in em_conflicts:em.pop(key,None)
    with cache.connect() as c:
        stocks={r['symbol']:dict(r) for r in c.execute('SELECT * FROM stocks')}
        explanations={(r['symbol'],r['trading_date']):dict(r) for r in c.execute('SELECT * FROM session_evidence')}
        for (symbol,day),(row,path) in sorted(index.items()):
            if day not in calendar or day>'2026-09-30' or symbol not in stocks:continue
            stock=stocks[symbol]
            if (stock['list_date'] and day<stock['list_date']) or (stock['delist_date'] and day>=stock['delist_date']):continue
            observed=c.execute('SELECT 1 FROM accepted_bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone()
            evidence={'provider':'BaoStock daily; raw mode 3','source_file':path,'original_row':row,
                      'semantics':'daily tradestatus=0 plus explicit zero shares/yuan; carried halt OHLC is NOT imported'}
            status=None;old=explanations.get((symbol,day))
            if row['tradestatus']=='0' and row.get('volume') not in (None,'') and row.get('amount') not in (None,'') and Decimal(row['volume'])==0 and Decimal(row['amount'])==0:
                if observed:status='conflicts_with_stored_quote'
                elif not old:
                    put('session_evidence',None,{'symbol':symbol,'trading_date':day,'status':'verified_full_day_suspension','evidence':json.dumps(evidence,sort_keys=True)},evidence)
                    status='independent_daily_suspension'
            elif row['tradestatus']=='1' and Decimal(row.get('volume') or '0')>0:
                if old and old['status']=='verified_full_day_suspension':
                    new={**old,'status':'conflicting_independent_daily_status','evidence':json.dumps({'old':old,'new':evidence},sort_keys=True)}
                    put('session_evidence',old,new,evidence);status='new_conflict_previously_explained'
                elif not observed:status='actual_source_quote_exists_signal_seam_not_yet_verified'
            if status:daily_reviews.append({'symbol':symbol,'date':day,'status':status,'source':path})
        for flagged in old_report['quality']['rows']:
            symbol,day=flagged['symbol'],flagged['date'];pair=index.get((symbol,day))
            if not pair:continue
            stored=c.execute('SELECT * FROM accepted_bars WHERE symbol=? AND trading_date=?',(symbol,day)).fetchone()
            if stored is None:continue
            old=dict(stored);row,path=pair
            try:fixed,reason=verified_daily_limits(old,row,stocks[symbol]['list_date'])
            except (ValueError,KeyError):fixed,reason=None,'source_field_invalid'
            if fixed and any(old[k]!=v for k,v in fixed.items()):
                previous=c.execute('SELECT close,trading_date FROM accepted_bars WHERE symbol=? AND trading_date<? ORDER BY trading_date DESC LIMIT 1',(symbol,day)).fetchone()
                causes=[]
                if 'ST' in stocks[symbol]['name'].upper() and row['isST']=='0':causes.append('current_ST_name_backcast_disproved_by_dated_status')
                if previous and price_conflict(previous['close'],row['preclose']):causes.append('previous_actual_close_not_source_reference_price')
                if not causes:causes.append('stored_derived_rule_differs_from_dated_source_reference')
                evidence={'source_file':path,'original_row':row,'previous_actual':dict(previous) if previous else None,
                          'confirmed_causes':causes,'rule':'existing historical rule, no threshold change; uncertified IPO/ST exceptions excluded'}
                put('bars',old,{**old,**fixed},evidence)
                quality.append({'symbol':symbol,'date':day,'causes':causes,'before':old,'after':{**old,**fixed},'evidence':evidence})
            elif fixed is None:skips.append({'symbol':symbol,'date':day,'reason':reason,'source':path})
        for target in json.loads((run/'warmup_target_plan.json').read_text(encoding='utf-8')):
            symbol=target['symbol'];prior=target['prior_date']
            item={**target,'status':'not_yet_queried','causal_certified':False}
            queries=[q for q in em_queries if q['request']['symbol']==symbol];item['queries']=queries
            if queries:
                try:
                    if prior not in calendar:raise ValueError('prior outside verified calendar')
                    new=eastmoney_prior(symbol,prior,target['overlaps'],em)
                    evidence={'provider':'Eastmoney original raw/HFQ, not independent AkShare corroboration',
                              'conversion':'lots * 100 shares; amount yuan; no substituted VWAP',
                              'raw_prior':em[symbol,prior,'0'],'adjusted_prior':em[symbol,prior,'2'],
                              'overlap_stored':target['overlaps'],'queries':queries,
                              'causal_factor_publication_verified':False,'pre_window_orders_or_positions':False}
                    put('bars',None,new,evidence);item['status']='real_prior_added_three_raw_hfq_overlaps_passed'
                except ValueError as error:item.update(status='source_seam_or_coverage_unresolved',reason=str(error))
            warmup.append(item)
    manifest={'version':'phase4-batch4-source-evidence-v1','input_snapshot':json.loads((run/'echo_manifest.json').read_text(encoding='utf-8'))['input_snapshot'],
              'requires_prior_patch':'phase4-batch4-proven-echo-v1','source_files':[{'path':p,'sha256':s} for p,s in sorted(files.items())],
              'changes':list(changes.values())}
    report={'daily_query_coverage':coverage,'daily_duplicate_source_conflicts':[list(k) for k in sorted(conflicts)],
            'eastmoney_duplicate_source_conflicts':[list(k) for k in sorted(em_conflicts)],'daily_reviews':daily_reviews,
            'quality_repairs':quality,'quality_skip_rows':skips,'warmup_935':warmup,
            'warmup_counts':dict(Counter(r['status'] for r in warmup)),'daily_counts':dict(Counter(r['status'] for r in daily_reviews))}
    for name,value in (('source_manifest.json',manifest),('evidence_classification.json',report)):
        (run/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest,report


REPAIR_KEYS={'bars':('trading_date','symbol'),'session_evidence':('symbol','trading_date'),
             'provider_quarantine':('symbol','trading_date','source'),'metadata':('key',)}


def apply_evidence_patch(cache, manifest: dict) -> dict:
    """Existing candidate repair workflow: atomic, deterministic compare-and-set.

    The manifest is data, never SQL. A stale source or mutated already-applied
    row is a conflict, including when a journal entry exists. No silent overwrite.
    """
    import hashlib
    canonical=json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    changes=manifest['changes'];seen=set();applied=unchanged=0
    for change in changes:
        table=change['table']
        if table not in REPAIR_KEYS:raise ValueError('unsupported repair target')
        key=(table,tuple(change['after'][k] for k in REPAIR_KEYS[table]))
        if key in seen:raise ValueError('duplicate manifest target')
        seen.add(key)
    for ref in manifest.get('source_files',[]):
        if hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('repair evidence content changed')
    with cache.connect() as c:
        c.execute('PRAGMA busy_timeout=30000');c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS evidence_patch_runs(version TEXT PRIMARY KEY,manifest_sha256 TEXT,input_snapshot TEXT,change_count INTEGER)')
        prerequisite=manifest.get('requires_prior_patch')
        if prerequisite and not c.execute('SELECT 1 FROM evidence_patch_runs WHERE version=?',(prerequisite,)).fetchone():
            raise ValueError('required prior evidence patch missing')
        prior=c.execute('SELECT manifest_sha256 FROM evidence_patch_runs WHERE version=?',(manifest['version'],)).fetchone()
        if prior and prior[0]!=digest:raise ValueError('same repair version has different content')
        for change in changes:
            table=change['table'];after=change['after'];before=change['before'];keys=REPAIR_KEYS[table]
            if table=='provider_quarantine' and after.get('review_status')=='confirmed_suspension_echo_excluded':
                proof=json.loads(after['evidence']).get('proof')
                if not proof or proof.get('cause')!='share_capital_outer_join_forward_filled_quote':
                    raise ValueError('adapter echo needs explicit reproducible proof')
                expected=proof['stored_false_quote']
                observed=c.execute('SELECT * FROM bars WHERE symbol=? AND trading_date=?',(after['symbol'],after['trading_date'])).fetchone()
                if observed is None or any(observed[k]!=expected[k] for k in ('open','high','low','close','volume','amount')):
                    raise ValueError('quarantined source quote changed after evidence capture')
            columns={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            if not set(after)<=columns or (before is not None and not set(before)<=columns):raise ValueError('unknown column')
            where=' AND '.join(k+'=?' for k in keys);values=[after[k] for k in keys]
            current=c.execute('SELECT * FROM '+table+' WHERE '+where,values).fetchone()
            if current is not None and all(current[k]==v for k,v in after.items()):
                unchanged+=1;continue
            if prior:raise ValueError('already-applied data changed after repair')
            if before is None:
                if current is not None:raise ValueError('insert conflicts with existing source row')
                cols=list(after)
                c.execute('INSERT INTO '+table+' ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',[after[k] for k in cols])
            else:
                if current is None or not all(current[k]==v for k,v in before.items()):raise ValueError('source row differs from evidence baseline')
                if any(before.get(k,after[k])!=after[k] for k in keys):raise ValueError('cannot change security/date identity')
                c.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in after)+' WHERE '+where,list(after.values())+values)
            applied+=1
        if not prior:
            c.execute('INSERT INTO evidence_patch_runs VALUES (?,?,?,?)',(manifest['version'],digest,manifest['input_snapshot'],len(changes)))
        if applied:cache._invalidate_audit(c)
    return {'version':manifest['version'],'manifest_sha256':digest,'applied':applied,'already_matches':unchanged,'unique_changes':len(changes)}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warmup-snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apply-evidence',type=Path,help='independent source-review/calendar JSON')
    args=parser.parse_args()
    if args.apply_evidence:apply_verified_events(args.warmup_snapshot,args.output,args.apply_evidence)
    else:print(json.dumps(warmup_batch(args.warmup_snapshot,args.output),ensure_ascii=False),flush=True)
