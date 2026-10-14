"""Synthetic isolated regression fixtures, never production market substitutions."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
from pathlib import Path

from test_real_market import _test_directory
from stock_picker.real_market import SQLiteMarketCache, StockInfo
from stock_picker.historical import HistoricalBar, BenchmarkPoint
from stock_picker.semantic_review import apply_evidence_patch, verified_daily_limits, corroborated_turnover_correction, collect_baostock_evidence
from stock_picker.data_semantics import warmup_readiness_review
from stock_picker.phase4_acceptance import SnapshotCache, admission_report
from stock_picker.data_audit import RealMarketDataAuditor


class Batch3ReplayTests(unittest.TestCase):
    def test_expired_guest_session_reconnects_without_hiding_failed_query(self):
        try:
            import baostock as bs
        except ImportError:
            self.skipTest('optional market environment required for SDK adapter test')
        import baostock.util.socketutil as transport
        import baostock.common.context as context
        class Query:
            fields=['date','code'];cur_page_num=1;data=[['2015-05-29','sz.000001']]
            def __init__(self,error):self.error_code=error;self.error_msg='fixture';self.called=False
            def next(self):
                if self.called:return False
                self.called=True;return True
            def get_row_data(self):return ['2015-05-29','sz.000001']
        calls=[]
        def query(*args,**kwargs):
            transport.send_msg('explicit synthetic request');calls.append(1)
            return Query('10001001' if len(calls)==1 else '0')
        with _test_directory() as tmp, patch.object(bs,'login',return_value=SimpleNamespace(error_code='0')) as login, patch.object(bs,'logout'), patch.object(bs,'query_history_k_data_plus',side_effect=query), patch.object(transport,'send_msg',return_value='synthetic response'), patch.object(context,'default_socket',None,create=True), patch('stock_picker.semantic_review.time.sleep'):
            jobs=[{'code':'sz.000001','start':d,'end':d} for d in ['2015-05-28','2015-05-29']]
            result=collect_baostock_evidence(Path(tmp),jobs)
            self.assertEqual(result['counts'],{'source_error':1,'complete':1})
            self.assertEqual(login.call_count,2)
            saved=json.loads(Path(result['queries'][0]['path']).read_text(encoding='utf-8'))
            self.assertEqual(saved['error_code'],'10001001')

    def test_exact_shares_need_two_sources_and_do_not_estimate_vwap(self):
        old={'open':10,'high':10,'low':10,'close':10,'volume':200,'amount':1990.01}
        daily={'open':'10','high':'10','low':'10','close':'10','volume':'199',
               'amount':'1990.01','adjustflag':'3','tradestatus':'1'}
        native={**daily,'amount':1990}
        self.assertEqual(corroborated_turnover_correction(old,daily,native),{'volume':199,'vwap':None})
        native['volume']='198'
        self.assertIsNone(corroborated_turnover_correction(old,daily,native))
        native['volume']='199';daily['amount']='1990';old['amount']=1990
        self.assertEqual(corroborated_turnover_correction(old,daily,native)['vwap'],10)

    def manifest(self):
        return {'version':'isolated-fixture-v1','input_snapshot':'explicit-synthetic-fixture','source_files':[],
                'changes':[{'table':'metadata','before':None,'after':{'key':'fixture-proof','value':'verified'}}]}

    def test_repeat_is_idempotent_and_version_conflicts_fail(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite');m=self.manifest()
            self.assertEqual(apply_evidence_patch(cache,m)['applied'],1)
            revision=cache.data_revision
            self.assertEqual(apply_evidence_patch(cache,m)['applied'],0)
            self.assertEqual(cache.data_revision,revision)
            changed=copy.deepcopy(m);changed['changes'][0]['after']['value']='changed'
            with self.assertRaises(ValueError):apply_evidence_patch(cache,changed)

    def test_post_sync_mutation_is_not_silently_overwritten(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite');m=self.manifest();apply_evidence_patch(cache,m)
            with cache.connect() as c:c.execute("UPDATE metadata SET value='new-source' WHERE key='fixture-proof'")
            with self.assertRaises(ValueError):apply_evidence_patch(cache,m)
            with cache.connect() as c:self.assertEqual(c.execute("SELECT value FROM metadata WHERE key='fixture-proof'").fetchone()[0],'new-source')

    def test_stale_source_rolls_back_all_changes(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite');m=self.manifest()
            m['changes'].append({'table':'metadata','before':{'key':'nonexistent','value':'old'},'after':{'key':'nonexistent','value':'new'}})
            with self.assertRaises(ValueError):apply_evidence_patch(cache,m)
            with cache.connect() as c:self.assertIsNone(c.execute("SELECT 1 FROM metadata WHERE key='fixture-proof'").fetchone())

    def test_evidence_hash_and_duplicate_targets_are_checked(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite');m=self.manifest()
            proof=Path(tmp)/'fixture.json';proof.write_text('isolated fixture',encoding='utf-8')
            m['source_files']=[{'path':str(proof),'sha256':'0'*64}]
            with self.assertRaises(ValueError):apply_evidence_patch(cache,m)
            m['source_files']=[];m['changes']*=2
            with self.assertRaises(ValueError):apply_evidence_patch(cache,m)

    def test_same_input_and_version_produce_same_logical_result(self):
        with _test_directory() as tmp:
            outcomes=[]
            for name in ('first','second'):
                cache=SQLiteMarketCache(Path(tmp)/(name+'.sqlite'));r=apply_evidence_patch(cache,self.manifest())
                with cache.connect() as c:
                    rows=[tuple(x) for x in c.execute('SELECT * FROM metadata ORDER BY key')]
                outcomes.append((r,rows,cache.data_revision))
            self.assertEqual(*outcomes)

    def test_historical_status_and_reference_correct_only_derived_limits(self):
        old={'symbol':'000010','trading_date':'2015-06-02','open':11,'high':11,'low':10,'close':11}
        source={'adjustflag':'3','tradestatus':'1','isST':'0','preclose':'10',**{k:str(old[k]) for k in ('open','high','low','close')}}
        original=dict(old);fixed,_=verified_daily_limits(old,source,'1995-01-01')
        self.assertEqual((fixed['up_limit'],fixed['down_limit']),(11,9));self.assertEqual(old,original)
        source['preclose']='20'
        self.assertIsNone(verified_daily_limits(old,source,'1995-01-01')[0])

    def test_unknown_ST_regime_IPO_adjusted_or_conflicting_raw_is_not_guessed(self):
        old={'symbol':'000010','trading_date':'2026-01-05','open':10,'high':10,'low':10,'close':10}
        source={'adjustflag':'3','tradestatus':'1','isST':'1','preclose':'10',**{k:'10' for k in ('open','high','low','close')}}
        self.assertIsNone(verified_daily_limits(old,source,'1995-01-01')[0])
        source['isST']='0'
        self.assertIsNone(verified_daily_limits(old,source,'2026-01-01')[0])
        source['adjustflag']='1'
        self.assertIsNone(verified_daily_limits(old,source,'1995-01-01')[0])

    def test_one_prior_is_not_blanket_indicator_or_causal_readiness(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            cache.upsert_stocks([StockInfo('000001','fixture','SZSE',list_date=date(2000,1,1))])
            cache.upsert_bars([HistoricalBar(date(2015,5,27),'000001',10,10,10,10,100,amount=1000,signal_close=20),
                               HistoricalBar(date(2015,6,1),'000001',10,10,10,10,100,amount=1000,signal_close=20)])
            source=Path(tmp)/'calendar.json';source.write_text(json.dumps({'calendar':{'dates':['2015-05-27','2015-05-28','2015-05-29','2015-06-01']}}),encoding='utf-8')
            r=warmup_readiness_review(SnapshotCache(cache.path),source)
            self.assertEqual(r['numerical_inputs_ready'],1)
            self.assertEqual(r['numerically_ready_but_continuity_unverified'],1)
            self.assertEqual(r['fully_causal_ready'],0)
            self.assertFalse(r['benchmarks']['CSI300']['sufficient_for_current_dependency'])

    def test_comparison_benchmark_does_not_gain_an_unused_window_gate(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            cache.upsert_benchmarks([BenchmarkPoint(date(2015,6,1),'CSI1000',100)])
            source=Path(tmp)/'calendar.json';source.write_text(json.dumps({'calendar':{'dates':['2015-05-29','2015-06-01']}}),encoding='utf-8')
            r=warmup_readiness_review(SnapshotCache(cache.path),source)
            self.assertTrue(r['benchmarks']['CSI1000']['sufficient_for_current_dependency'])
            self.assertFalse(r['benchmarks']['CSI300']['sufficient_for_current_dependency'])

    def test_preexisting_missing_history_is_an_explicit_admission_blocker(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            cache.upsert_stocks([StockInfo('000001','fixture','SZSE',list_date=date(2000,1,1))])
            cache.upsert_bars([HistoricalBar(date(2015,6,1),'000001',10,10,10,10,100,amount=1000,signal_close=10)])
            frozen=SnapshotCache(cache.path)
            audit=RealMarketDataAuditor(frozen).run(start_date=date(2015,6,1),end_date=date(2015,6,1)).payload
            report=admission_report(frozen,audit,{'id':'isolated-fixture'})
            self.assertIn('preexisting_security_warmup_not_ready',report['blocker_summary'])


if __name__=='__main__':unittest.main()
