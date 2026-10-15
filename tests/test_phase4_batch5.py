"""Synthetic queue fixtures only: no production replacement or return calculation."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_real_market import _test_directory
import test_phase4_batch4
from stock_picker.semantic_review import execute_batch5_warmup, collect_baostock_evidence
from stock_picker.sync_monitor import targeted_queue_status


class Batch5QueueTests(unittest.TestCase):
    def plan(self, symbols):
        overlaps, source=test_phase4_batch4.Batch4EvidenceTests().warmup()
        tasks=[{'symbol':s,'cohort':'initial_919','prior_date':'2015-05-29',
                'overlaps':overlaps,'previous_evidence':[],
                'jobs':[{'symbol':s,'start':'2015-05-29','end':'2015-06-03','adjustflag':m} for m in ('0','2')]}
               for s in symbols]
        return {'tasks':tasks,'input_snapshot':{'id':'synthetic'}}, source

    def execute(self, root, plan, collector):
        evidence=root/'calendar.json'
        evidence.write_text(json.dumps({'calendar':{'dates':['2015-05-29','2015-06-01','2015-06-02','2015-06-03']}}))
        with patch('stock_picker.semantic_review.prepare_batch5_queue',return_value=plan), \
             patch('stock_picker.semantic_review.collect_eastmoney_windows',side_effect=collector):
            return execute_batch5_warmup(root,root/'baseline',evidence)

    def collector(self, status, source=None):
        def collect(folder, jobs, **kwargs):
            job=jobs[0];folder=folder/'eastmoney';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(job['symbol']+'_'+job['adjustflag']+'.json')
            rows=[v for (s,d,m),v in (source or {}).items() if s==job['symbol'] and m==job['adjustflag']]
            path.write_text(json.dumps({'request':job,'status':status,'attempts':[], 'rows':rows}))
            return {'queries':[{'path':str(path),'request':job,'status':status}]}
        return collect

    def test_three_failed_securities_stop_source_not_queue_and_resume_retains_attempts(self):
        with _test_directory() as tmp:
            root=Path(tmp);plan,_=self.plan(['000001','000002','000003','000004'])
            first=self.execute(root,plan,self.collector('source_error'))
            self.assertEqual(first['cohorts']['initial_919']['states']['access_execution_blocked'],4)
            self.assertFalse(first['all_queries_completed'])
            attempted=json.loads((root/'warmup_results/000001.json').read_text())
            unissued=json.loads((root/'warmup_results/000004.json').read_text())
            self.assertEqual(len(attempted['attempts']),2)
            self.assertEqual(len(unissued['unissued_jobs']),2)
            self.assertFalse(unissued['attempts'])
            second=self.execute(root,plan,lambda *a,**k:self.fail('closed source retried'))
            self.assertEqual(len(json.loads((root/'warmup_results/000001.json').read_text())['attempts']),2)
            self.assertEqual(first['last_new_security_at'],second['last_new_security_at'])
            self.assertIsNone(second['last_data_success_at'])
            self.assertIsNone(second['last_candidate_write_at'])

    def test_empty_response_is_completed_query_not_proven_absence_or_qualification(self):
        with _test_directory() as tmp:
            plan,_=self.plan(['000001'])
            result=self.execute(Path(tmp),plan,self.collector('empty_not_absence_proof'))
            self.assertTrue(result['all_queries_completed'])
            self.assertEqual(result['cohorts']['initial_919']['states']['data_validation_blocked'],1)
            self.assertFalse(result['formal_gate_released'])

    def test_real_numeric_seam_remains_separate_and_replay_writes_zero(self):
        with _test_directory() as tmp:
            root=Path(tmp);plan,source=self.plan(['000001'])
            first=self.execute(root,plan,self.collector('complete',source))
            self.assertEqual(first['cohorts']['initial_919']['numeric_inputs_added'],1)
            self.assertEqual(first['cohorts']['initial_919']['states']['qualified'],0)
            second=self.execute(root,plan,lambda *a,**k:self.fail('successful segment redownloaded'))
            self.assertEqual(first['last_candidate_write_at'],second['last_candidate_write_at'])
            self.assertEqual(first['last_new_security_at'],second['last_new_security_at'])
            from stock_picker.real_market import SQLiteMarketCache
            with SQLiteMarketCache(root/'candidate.sqlite').connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM bars').fetchone()[0],1)

    def test_monitor_deduplicates_and_does_not_forge_progress(self):
        tasks=[{'symbol':'000001','cohort':'initial_919'}]*2
        result=targeted_queue_status(tasks,{}, {'last_data_success_at':None})
        self.assertEqual(result['cohorts']['initial_919']['total_unique_securities'],1)
        self.assertIsNone(result['last_data_success_at'])
        with self.assertRaises(ValueError):
            targeted_queue_status(tasks,{'000001':{'state':'qualified'}},{})

    def test_guest_login_failure_persists_unissued_scope_and_restores_socket_timeout(self):
        import socket
        jobs=[{'code':'sz.000001','start':'2015-01-01','end':'2015-01-30'}]
        before=socket.getdefaulttimeout()
        with _test_directory() as tmp, patch('baostock.login',return_value=SimpleNamespace(error_code='1',error_msg='synthetic network failure')), \
             patch('baostock.query_history_k_data_plus') as query:
            result=collect_baostock_evidence(Path(tmp),jobs)
            self.assertEqual(result['unattempted'],jobs)
            self.assertEqual(result['status'],'access_execution_blocked')
            self.assertTrue((Path(tmp)/'baostock_login_failure.json').exists())
            query.assert_not_called()
        self.assertEqual(before,socket.getdefaulttimeout())


if __name__=='__main__':unittest.main()
