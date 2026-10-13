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


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warmup-snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apply-evidence',type=Path,help='independent source-review/calendar JSON')
    args=parser.parse_args()
    if args.apply_evidence:apply_verified_events(args.warmup_snapshot,args.output,args.apply_evidence)
    else:print(json.dumps(warmup_batch(args.warmup_snapshot,args.output),ensure_ascii=False),flush=True)
