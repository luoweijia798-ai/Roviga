from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .data_audit import DataAuditResult, RealMarketDataAuditor
from .real_market import PHASE4_START, SQLiteMarketCache


class Phase4SyncMonitor:
    """Writes a compact sync snapshot and audits only after all stocks settle."""

    def __init__(self, cache: SQLiteMarketCache) -> None:
        self.cache = cache

    def refresh(
        self,
        *,
        end_date: date,
        status_output: str | Path,
        audit_output: str | Path,
        audit_when_settled: bool = True,
    ) -> tuple[dict[str, Any], DataAuditResult | None]:
        statuses = self.cache.sync_statuses()
        counts = Counter(item.status for item in statuses)
        with self.cache.connect() as connection:
            total_stocks = int(
                connection.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
            )
            outside_range = int(connection.execute(
                "SELECT COUNT(*) FROM stocks WHERE delist_date < ? OR list_date > ?",
                (PHASE4_START.isoformat(), end_date.isoformat()),
            ).fetchone()[0])
            coverage = connection.execute(
                """
                SELECT MIN(trading_date), MAX(trading_date), COUNT(*),
                       COUNT(DISTINCT symbol)
                FROM bars
                """
            ).fetchone()
        current = max(
            (item for item in statuses if item.status == "running"),
            key=lambda item: item.updated_at, default=None,
        )
        errors = Counter(
            (item.status, item.last_error or "no error detail")
            for item in statuses
            if item.status != "complete"
        )
        settled = counts["complete"] + counts["failed"] + counts["unavailable"]
        target_pending = sum(
            item.requested_start > PHASE4_START or item.requested_end < end_date
            or (item.status == "complete" and (
                not item.synced_through or item.synced_through < end_date
            )) for item in statuses
        )
        scan_complete = (
            total_stocks > 0
            and len(statuses) >= total_stocks
            and settled >= total_stocks
            and counts["running"] == 0
            and counts["interrupted"] == 0
            and target_pending == 0
        )
        sync_complete = scan_complete and counts["failed"] == 0 and counts["unavailable"] == 0
        payload: dict[str, Any] = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_start": PHASE4_START.isoformat(),
            "requested_end": end_date.isoformat(),
            "sync_complete": sync_complete,
            "scan_complete": scan_complete,
            "target_pending_count": target_pending,
            "total_stock_count": total_stocks,
            "outside_requested_range_count": outside_range,
            "completed_count": counts["complete"],
            "failed_count": counts["failed"],
            "unavailable_count": counts["unavailable"],
            "interrupted_count": counts["interrupted"],
            "unprocessed_count": max(total_stocks - len(statuses), 0),
            "current_stock": _status_payload(current),
            "coverage": {
                "start_date": coverage[0],
                "end_date": coverage[1],
                "bar_count": int(coverage[2]),
                "symbols_with_bars": int(coverage[3]),
                "average_trading_days": (
                    round(int(coverage[2]) / int(coverage[3]), 2)
                    if coverage[3]
                    else 0.0
                ),
            },
            "recent_error_summary": [
                {"status": key[0], "error": key[1], "count": count}
                for key, count in errors.most_common(10)
            ],
            "audit_triggered": False,
            "audit_passed": None,
        }
        path = Path(status_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_status(path, payload)
        audit: DataAuditResult | None = None
        if scan_complete and audit_when_settled:
            audit = RealMarketDataAuditor(self.cache).run(
                start_date=PHASE4_START,
                end_date=end_date,
                output=audit_output,
            )
            payload["audit_triggered"] = True
            payload["audit_passed"] = audit.passed
        _write_status(path, payload)
        return payload, audit


def targeted_queue_status(tasks, outcomes, events, *, current=None, waiting=None):
    """Same status writer, explicit unique-security repair progress (not liveness).

    Successful response/write timestamps are supplied by the actions themselves;
    refreshing this report must never advance them.
    """
    states=('not_started','partial','awaiting_validation','qualified','data_validation_blocked','access_execution_blocked')
    cohorts={}
    for cohort in sorted({t['cohort'] for t in tasks}):
        symbols={t['symbol'] for t in tasks if t['cohort']==cohort};counts={k:0 for k in states}
        for symbol in symbols:
            state=outcomes.get(symbol,{}).get('state','not_started')
            if state not in counts:raise ValueError('unknown targeted state')
            if state=='qualified' and not outcomes[symbol].get('causal_price_verified'):
                raise ValueError('numeric availability is not causal qualification')
            counts[state]+=1
        cohorts[cohort]={'total_unique_securities':len(symbols),'states':counts,'reconciles':sum(counts.values())==len(symbols),
                         'query_complete':sum(bool(outcomes.get(s,{}).get('query_complete')) for s in symbols),
                         'numeric_inputs_added':sum(bool(outcomes.get(s,{}).get('numeric_inputs_added')) for s in symbols)}
    return {'schema_version':2,'kind':'phase4_targeted_repair','generated_at':datetime.now(timezone.utc).isoformat(),
            'cohorts':cohorts,**events,'current_stock':current,'waiting_reason':waiting,
            'process_exists_is_not_progress':True,'audit_triggered':False}


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _status_payload(status: Any | None) -> dict[str, Any] | None:
    if status is None:
        return None
    return {
        "symbol": status.symbol,
        "status": status.status,
        "date_checkpoint": status.synced_through.isoformat()
        if status.synced_through
        else None,
        "bar_count": status.bar_count,
        "attempts": status.attempts,
        "source": status.source,
        "last_error": status.last_error,
    }


def daily_update_check(cache_path: Path, session_date: date, *, calendar_evidence: Path | None = None, now=None) -> dict:
    """Read a single database transaction; inventory freshness is not admission.

    No synchronizer, selector, audit or broker. Missing rows are not inferred
    suspensions. The inventory is not certified historical pool membership.
    """
    import hashlib
    import sqlite3
    from datetime import timedelta
    from .phase4_acceptance import SnapshotCache
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('update-check timestamp must be timezone-aware')
    local = instant.astimezone(timezone(timedelta(hours=8)))
    result = {'kind':'daily_update_check','observed_at':local.isoformat(),
        'requested_session':session_date.isoformat(),'calendar_status':'UNKNOWN',
        'timing':'FUTURE_DATE' if session_date > local.date() else
                 'BEFORE_REGULAR_CLOSE' if session_date == local.date() and local.hour < 15 else
                 'AFTER_REGULAR_CLOSE',
        'status':'DATA_NOT_READY','strategy_evaluated':False,'orders_run':False,
        'inventory_is_not_point_in_time_admission':True,
        'last_successful_request_at':None,'last_successful_write_at':None,
        'success_time_limitation':'existing status timestamps are not request/write event timestamps',
        'errors':[]}
    try:
        if calendar_evidence is not None:
            raw = calendar_evidence.read_bytes()
            evidence = json.loads(raw)['calendar']
            sessions = {date.fromisoformat(item) for item in evidence['dates']}
            verified = date.fromisoformat(evidence['verified_through'])
            if not sessions or verified > max(sessions) or not evidence['source'] or not evidence['url']:
                raise ValueError('invalid calendar coverage evidence')
            result['calendar_evidence'] = {'sha256':hashlib.sha256(raw).hexdigest(),
                'source':evidence['source'],'url':evidence['url'],'verified_through':verified.isoformat()}
            if min(sessions) <= session_date <= verified:
                result['calendar_status'] = 'LISTED_SESSION' if session_date in sessions else 'NOT_LISTED_IN_COVERED_CALENDAR'
        with SnapshotCache(Path(cache_path)).connect() as connection:
            connection.execute('BEGIN')
            revision = connection.execute("SELECT value FROM metadata WHERE key='data_revision'").fetchone()
            rows = connection.execute('SELECT symbol,list_date,delist_date FROM stocks').fetchall()
            requested = session_date.isoformat()
            present = {r[0] for r in connection.execute('SELECT symbol FROM accepted_bars WHERE trading_date=?',(requested,))}
            known_active, unknown, outside = set(), set(), set()
            for row in rows:
                if row['list_date'] is None:
                    unknown.add(row['symbol'])
                elif row['list_date'] > requested or (row['delist_date'] and row['delist_date'] < requested):
                    outside.add(row['symbol'])
                else:
                    known_active.add(row['symbol'])
            latest = connection.execute('SELECT MAX(trading_date) FROM bars').fetchone()[0]
            statuses = connection.execute('SELECT symbol,status,synced_through,requested_end,updated_at FROM symbol_sync_status').fetchall()
            counts = Counter(r['status'] for r in statuses)
            inventory = {r['symbol'] for r in rows}
            missing_status = inventory - {r['symbol'] for r in statuses}
            pending_target = missing_status | {r['symbol'] for r in statuses
                if r['symbol'] in inventory and (not r['requested_end'] or r['requested_end'] < requested
                    or not r['synced_through'] or r['synced_through'] < requested)}
            result.update(data_revision=revision[0] if revision else None,
                latest_any_stored_date=latest,inventory_total=len(rows),
                known_active_inventory=len(known_active),unknown_listing_inventory=len(unknown),
                outside_inventory=len(outside),quote_symbols_on_requested_date=len(present),
                known_active_with_quote=len(known_active & present),
                known_active_without_quote=sorted(known_active-present),
                no_quote_reason='UNKNOWN: absence alone is not suspension evidence',
                sync_state_counts=dict(counts),sync_target_or_checkpoint_pending=len(pending_target),
                inventory_without_sync_status=len(missing_status),
                last_sync_status_update=max((r['updated_at'] for r in statuses),default=None),
                inventory_reconciles=len(known_active)+len(unknown)+len(outside)==len(rows))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        result['errors'].append(str(error))
    return result


def pilot_readiness(identity_path: Path, admission_path: Path, *, requirements_path: Path | None = None, now=None) -> dict:
    """Read-only pilot prerequisite check, NOT the operational daily selector.

    A pilot pass cannot authorize full-market observations. Never call selector,
    broker, synchronizer or an auditor here. This status cannot become a strategy
    cash/no-candidate decision by editing an admission boolean.
    """
    import hashlib
    import sqlite3
    from datetime import timedelta
    from .phase4_acceptance import SnapshotCache, verify_snapshot
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('readiness timestamp must be timezone-aware')
    local = instant.astimezone(timezone(timedelta(hours=8), name='Asia/Shanghai'))
    payload = {'schema_version': 1, 'kind': 'pilot_readiness_check',
        'observed_at': local.isoformat(), 'timezone': 'Asia/Shanghai',
        'signal_date': None, 'status': 'DATA_NOT_READY', 'candidate': None,
        'strategy_evaluated': False, 'risk_status': 'NOT_EVALUATED',
        'formal_backtest_authorized': False, 'operational_observation': False,
        'delivery_scope': 'DATA_AND_READINESS_ONLY',
        'execution_model_changed': False,
        'requirements_status': 'NOT_PROVIDED' if requirements_path is None else 'INVALID',
        'last_successful_signal_at': None,
        'reason': '三只试点不能替代全市场准入和首次基准回测；未执行选股。',
        'evidence_errors': [], 'data_latest_date': None}
    try:
        identity_bytes = identity_path.read_bytes()
        identity = json.loads(identity_bytes)
        snapshot_path = Path(identity['path'])
        if not snapshot_path.is_absolute():
            raise ValueError('snapshot identity must use a full absolute path')
        verify_snapshot(snapshot_path, identity)
        admission_bytes = admission_path.read_bytes()
        admission = json.loads(admission_bytes)
        if admission['snapshot']['id'] != identity['id']:
            raise ValueError('admission belongs to a different snapshot')
        if admission['snapshot'].get('data_revision') != identity['data_revision']:
            raise ValueError('admission belongs to a different data revision')
        if admission.get('formal_interval') != ['2015-06-01', '2026-09-30']:
            raise ValueError('unexpected pilot interval')
        with SnapshotCache(snapshot_path).connect() as connection:
            coverage = connection.execute('SELECT COUNT(*), COUNT(DISTINCT symbol), MAX(trading_date) FROM bars').fetchone()
        payload.update(snapshot_id=identity['id'], data_revision=identity['data_revision'],
            data_latest_date=coverage[2], quote_rows=coverage[0], security_count=coverage[1],
            counts=admission.get('counts', {}), securities=admission.get('securities', {}),
            evidence_files={'identity_sha256': hashlib.sha256(identity_bytes).hexdigest(),
                            'admission_sha256': hashlib.sha256(admission_bytes).hexdigest()},
            admission_generated_at=admission.get('generated_at'),
            formal_interval=admission['formal_interval'],
            data_capture_time_claim='unknown; file/report refresh is not a download timestamp')
        if requirements_path is not None:
            payload['requirements_status'] = 'INVALID'
            requirements_bytes = requirements_path.read_bytes()
            requirements = json.loads(requirements_bytes)
            if (requirements['snapshot']['id'] != identity['id']
                    or requirements['snapshot'].get('data_revision') != identity['data_revision']):
                raise ValueError('data requirements belong to a different snapshot/revision')
            dates = requirements['four_dates']
            scopes = requirements['turnover_scope']
            if not isinstance(dates, list) or not isinstance(scopes, list):
                raise ValueError('data requirements must contain lists')
            date_keys = {(item['symbol'], item['date']) for item in dates}
            scope_keys = {(item['symbol'], item['start'], item['end']) for item in scopes}
            if len(date_keys) != len(dates) or len(scope_keys) != len(scopes):
                raise ValueError('duplicate data requirements would inflate blocker counts')
            if (len(dates) != admission['counts']['vwap_dates']
                    or len(scopes) != admission['counts']['scope_intervals']):
                raise ValueError('data requirements counts do not reconcile with admission')
            fields = ('open', 'high', 'low', 'close', 'volume', 'amount', 'vwap')
            with SnapshotCache(snapshot_path).connect() as connection:
                for item in dates:
                    actual = connection.execute(
                        'SELECT open, high, low, close, volume, amount, vwap FROM bars '
                        'WHERE symbol=? AND trading_date=?',
                        (item['symbol'], item['date'])).fetchone()
                    if actual is None or any(actual[i] != item['raw'][name]
                                             for i, name in enumerate(fields)):
                        raise ValueError('requirement raw values differ from candidate')
                    if not item['need']:
                        raise ValueError('requirement must state missing evidence')
            for item in scopes:
                if (item['symbol'] not in admission['securities']
                        or date.fromisoformat(item['start']) > date.fromisoformat(item['end'])
                        or not item['fields'] or not item['need']):
                    raise ValueError('invalid turnover scope requirement')
            payload.update(requirements_status='BOUND_TO_SNAPSHOT',
                           data_requirements=requirements)
            payload['evidence_files']['requirements_sha256'] = hashlib.sha256(requirements_bytes).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        payload['evidence_errors'].append(str(error))
        payload['reason'] = '数据或验收证据读取失败；未执行选股，不表示策略主动空仓。'
    return payload
