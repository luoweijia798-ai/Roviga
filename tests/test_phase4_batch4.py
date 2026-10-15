"""Explicit synthetic regression fixtures; never substitute production history."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_real_market import _test_directory
from stock_picker.semantic_review import proven_capital_echo, eastmoney_prior, collect_eastmoney_windows, apply_evidence_patch, build_batch4_patch
from stock_picker.real_market import SQLiteMarketCache, SQLiteHistoricalDataPortal, StockInfo
from stock_picker.historical import HistoricalBar
from stock_picker.phase4_acceptance import SnapshotCache
from stock_picker.data_audit import RealMarketDataAuditor


class Batch4EvidenceTests(unittest.TestCase):
    def echo(self):
        values={'open':10,'high':11,'low':9,'close':10,'volume':100,'amount':1000}
        stored={**values,'symbol':'000001','trading_date':'2015-06-30'}
        native=[{**values,'date':'2015-06-01'}]
        daily={'date':'2015-06-30','code':'sz.000001','adjustflag':'3','tradestatus':'0','volume':'0','amount':'0'}
        return stored,native,{'2015-06-30'},daily

    def test_exact_adapter_echo_needs_all_four_evidence_parts(self):
        args=self.echo();self.assertIsNotNone(proven_capital_echo(*args))
        for field,value in [('date','2015-06-29'),('code','sz.000002'),('tradestatus','1'),('volume','1'),('amount','1'),('adjustflag','1')]:
            a=copy.deepcopy(args);a[3][field]=value
            self.assertIsNone(proven_capital_echo(*a),field)
        a=copy.deepcopy(args);a[2].clear();self.assertIsNone(proven_capital_echo(*a))
        a=copy.deepcopy(args);a[1].append({**a[1][0],'date':'2015-06-30'});self.assertIsNone(proven_capital_echo(*a))
        a=copy.deepcopy(args);a[0]['amount']=999;self.assertIsNone(proven_capital_echo(*a))

    def test_echo_exclusion_preserves_raw_and_actual_previous_quote(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            cache.upsert_stocks([StockInfo('000001','fixture','SZSE',date(1991,1,1))])
            for d in (date(2015,6,1),date(2015,6,30),date(2015,7,1)):
                cache.upsert_bars([HistoricalBar(d,'000001',10,11,9,10,100,amount=1000,vwap=10,signal_close=10)])
            after={'symbol':'000001','trading_date':'2015-06-30','source':'synthetic-proof',
                   'evidence':json.dumps({'proof':proven_capital_echo(*self.echo())}),'review_status':'confirmed_suspension_echo_excluded'}
            manifest={'version':'fixture-batch4','input_snapshot':'synthetic','changes':[{'table':'provider_quarantine','before':None,'after':after}]}
            self.assertEqual(apply_evidence_patch(cache,manifest)['applied'],1)
            self.assertEqual(apply_evidence_patch(cache,manifest)['applied'],0)
            with cache.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM bars').fetchone()[0],3)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM accepted_bars').fetchone()[0],2)
            portal=SQLiteHistoricalDataPortal(cache.path)
            portal.advance_to(date(2015,7,1))
            self.assertIsNone(portal.bar('000001',date(2015,6,30)))
            self.assertFalse(portal.daily_snapshot(date(2015,6,30)))
            self.assertEqual(portal.previous_bar('000001',date(2015,7,1)).trading_date,date(2015,6,1))
            payload=RealMarketDataAuditor(SnapshotCache(cache.path)).run(start_date=date(2015,6,1),end_date=date(2015,7,1)).payload
            self.assertFalse(payload.get('provider_quarantines'))
            with cache.connect() as c:c.execute("UPDATE bars SET volume=101 WHERE trading_date='2015-06-30'")
            with self.assertRaisesRegex(ValueError,'source quote changed'):apply_evidence_patch(cache,manifest)

    def warmup(self):
        overlaps=[];source={}
        for d in ('2015-05-29','2015-06-01','2015-06-02','2015-06-03'):
            source['000001',d,'0']=[d,'10','10','11','9','2','2000']
            source['000001',d,'2']=[d,'20','20','22','18','2','2000']
            if d>='2015-06-01':overlaps.append({'trading_date':d,'open':10,'close':10,'high':11,'low':9,'signal_open':20,'signal_close':20,'signal_high':22,'signal_low':18})
        return overlaps,source

    def test_three_date_overlap_and_units_are_required(self):
        overlaps,source=self.warmup();row=eastmoney_prior('000001','2015-05-29',overlaps,source)
        self.assertEqual((row['volume'],row['amount'],row['vwap'],row['signal_close']),(200,2000,10,20))
        for subset in (overlaps[:1],overlaps[:2]):
            with self.assertRaises(ValueError):eastmoney_prior('000001','2015-05-29',subset,source)
        source['000001','2015-06-03','2'][2]='21'
        with self.assertRaises(ValueError):eastmoney_prior('000001','2015-05-29',overlaps,source)

    def test_no_future_fill_or_estimated_vwap(self):
        overlaps,source=self.warmup()
        with self.assertRaises(ValueError):eastmoney_prior('000001','2015-06-01',overlaps,source)
        source['000001','2015-05-29','0'][6]='3000'
        self.assertIsNone(eastmoney_prior('000001','2015-05-29',overlaps,source)['vwap'])
        source['000001','2015-05-29','0'][5]='0'
        with self.assertRaises(ValueError):eastmoney_prior('000001','2015-05-29',overlaps,source)

    def test_permission_denial_stops_collection_without_source_rotation(self):
        import requests
        response=requests.Response();response.status_code=403
        error=requests.HTTPError('fixture forbidden',response=response)
        jobs=[{'symbol':s,'start':'2015-05-29','end':'2015-06-03','adjustflag':'0'} for s in ('000001','000002')]
        with _test_directory() as tmp, patch('requests.get',side_effect=error) as get, patch('stock_picker.semantic_review.time.sleep'):
            result=collect_eastmoney_windows(Path(tmp),jobs)
            self.assertEqual(get.call_count,1)
            self.assertEqual(result['counts'],{'access_or_rate_limit':1})
            self.assertEqual(len(result['unattempted']),1)

    def test_response_identity_mismatch_is_not_complete(self):
        from types import SimpleNamespace
        response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'rc':0,'data':{'code':'000002','klines':['2015-05-29,10,10,11,9,2,2000']}})
        job={'symbol':'000001','start':'2015-05-29','end':'2015-06-03','adjustflag':'0'}
        with _test_directory() as tmp, patch('requests.get',return_value=response), patch('stock_picker.semantic_review.time.sleep'):
            result=collect_eastmoney_windows(Path(tmp),[job])
            self.assertEqual(result['counts'],{'identity_window_or_completeness_conflict':1})

    def test_manifest_builder_retains_http_body_hash_and_requires_prior_patch(self):
        import hashlib
        with _test_directory() as tmp:
            run=Path(tmp)/'run';baseline=Path(tmp)/'baseline'
            (baseline/'final_reaudit').mkdir(parents=True);(run/'warmup_probe/eastmoney').mkdir(parents=True)
            def save(path,obj):path.write_text(json.dumps(obj),encoding='utf-8')
            save(baseline/'final_reaudit/final_reaudit.json',{'quality':{'rows':[]}})
            save(run/'echo_manifest.json',{'input_snapshot':'explicit-synthetic-fixture'})
            evidence=run/'calendar.json';save(evidence,{'calendar':{'dates':['2015-05-29','2015-06-01','2015-06-02','2015-06-03']}})
            cache=SQLiteMarketCache(run/'candidate.sqlite')
            with cache.connect() as c:c.execute('CREATE TABLE session_evidence(symbol TEXT,trading_date TEXT,status TEXT,evidence TEXT,PRIMARY KEY(symbol,trading_date))')
            overlaps,source=self.warmup()
            save(run/'warmup_target_plan.json',[{'symbol':'000001','prior_date':'2015-05-29','overlaps':overlaps}])
            body=run/'fixture.response';body.write_bytes(b'explicit synthetic source response')
            digest=hashlib.sha256(body.read_bytes()).hexdigest()
            for mode in ('0','2'):
                save(run/'warmup_probe/eastmoney'/f'{mode}.json',{'request':{'symbol':'000001','start':'2015-05-29','end':'2015-06-03','adjustflag':mode},
                    'status':'complete','rows':[v for (s,d,m),v in source.items() if m==mode],
                    'attempts':[{'responses':[{'file':str(body.resolve()),'sha256':digest}]}]})
            manifest,review=build_batch4_patch(run,baseline,evidence)
            self.assertEqual(review['warmup_counts'],{'real_prior_added_three_raw_hfq_overlaps_passed':1})
            self.assertIn({'path':str(body.resolve()),'sha256':digest},manifest['source_files'])
            with self.assertRaisesRegex(ValueError,'prior evidence patch'):apply_evidence_patch(cache,manifest)
            apply_evidence_patch(cache,{'version':'phase4-batch4-proven-echo-v1','input_snapshot':'synthetic','changes':[]})
            self.assertEqual(apply_evidence_patch(cache,manifest)['applied'],1)
            self.assertEqual(apply_evidence_patch(cache,manifest)['applied'],0)


if __name__=='__main__':unittest.main()
