"""Explicitly synthetic SQLite fixtures; never real market history or returns."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from stock_picker.real_market import SQLiteMarketCache
from stock_picker.phase4_acceptance import freeze_database
from stock_picker.sync_monitor import pilot_readiness
from stock_picker.reporting import write_pilot_readiness


class PilotReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cache = SQLiteMarketCache(self.root / 'synthetic.sqlite')
        self.raw = dict(open=10.0, high=10.0, low=10.0, close=10.0,
                        volume=100, amount=1001.0, vwap=10.01)
        with cache.connect() as connection:
            connection.execute(
                'INSERT INTO bars(trading_date,symbol,open,high,low,close,volume,amount,vwap,'
                'tradable,limit_up_locked,limit_down_locked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('2015-05-29','TEST_ONLY',10,10,10,10,100,1001,10.01,1,0,0))
        self.identity = freeze_database(cache.path, self.root / 'snapshot.sqlite')
        self.identity_path = self.root / 'identity.json'
        self.identity_path.write_text(json.dumps(self.identity), encoding='utf-8')
        self.admission = {'snapshot': self.identity, 'formal_interval':['2015-06-01','2026-09-30'], 'counts':{}, 'securities':{}}
        self.admission_path = self.root / 'admission.json'
        self.save_admission()

    def save_admission(self):
        self.admission_path.write_text(json.dumps(self.admission), encoding='utf-8')

    def check(self, requirements_path=None):
        return pilot_readiness(self.identity_path, self.admission_path,
            requirements_path=requirements_path,
            now=datetime(2026,10,19,2,0,tzinfo=timezone.utc))

    def requirements_fixture(self):
        self.admission['counts'] = {'vwap_dates':1, 'scope_intervals':1}
        self.admission['securities'] = {'TEST_ONLY':{'quotes':1}}
        self.save_admission()
        self.requirements = {'snapshot':self.identity,
            'four_dates':[{'symbol':'TEST_ONLY','date':'2015-05-29','raw':self.raw,
                           'need':'Synthetic evidence <script>not executable</script>'}],
            'turnover_scope':[{'symbol':'TEST_ONLY','start':'2015-05-29','end':'2015-06-01',
                               'fields':['synthetic volume'], 'need':'synthetic scope'}]}
        self.requirements_path = self.root/'requirements.json'
        self.save_requirements()
        return self.requirements_path

    def save_requirements(self):
        self.requirements_path.write_text(json.dumps(self.requirements),encoding='utf-8')

    def test_read_only_timestamp_is_not_a_signal_or_data_capture(self):
        before = Path(self.identity['path']).read_bytes()
        payload = self.check()
        self.assertEqual(payload['observed_at'],'2026-10-19T10:00:00+08:00')
        self.assertEqual(payload['status'],'DATA_NOT_READY')
        self.assertIsNone(payload['candidate']); self.assertIsNone(payload['signal_date'])
        self.assertFalse(payload['strategy_evaluated']); self.assertFalse(payload['evidence_errors'])
        self.assertEqual(before,Path(self.identity['path']).read_bytes())

    def test_manual_pass_boolean_cannot_enable_selection(self):
        self.admission.update(passed=True, formal_gate_eligible=True)
        self.save_admission()
        self.assertFalse(self.check()['formal_backtest_authorized'])
        self.assertEqual(self.check()['status'],'DATA_NOT_READY')

    def test_stale_report_wrong_interval_and_changed_snapshot_fail_closed(self):
        self.admission['snapshot'] = {'id':'sha256:wrong'}; self.save_admission()
        self.assertTrue(self.check()['evidence_errors'])
        self.admission['snapshot'] = self.identity
        self.admission['formal_interval'] = ['2015-06-01','2026-10-19']; self.save_admission()
        self.assertTrue(self.check()['evidence_errors'])
        Path(self.identity['path']).write_bytes(b'synthetic changed content')
        self.assertTrue(self.check()['evidence_errors'])

    def test_missing_input_never_creates_database(self):
        missing = self.root / 'never-created.sqlite'
        payload = pilot_readiness(missing, self.admission_path)
        self.assertTrue(payload['evidence_errors']); self.assertFalse(missing.exists())

    def test_page_escapes_evidence_and_keeps_immutable_history(self):
        payload = self.check(); payload['reason']='<script>alert(1)</script>'
        output = self.root / 'ui'
        page = write_pilot_readiness(payload,output)
        first = {p.name:p.read_bytes() for p in (output/'records').glob('*.json')}
        write_pilot_readiness(payload,output)
        self.assertEqual(len(list((output/'records').glob('*.json'))),2)
        for name,data in first.items():self.assertEqual(data,(output/'records'/name).read_bytes())
        self.assertNotIn('<script>',page.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):write_pilot_readiness({**payload,'candidate':'000035'},output)

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            pilot_readiness(self.identity_path,self.admission_path,now=datetime(2026,10,19))

    def test_requirements_bind_raw_values_counts_revision_and_hash(self):
        path = self.requirements_fixture()
        before = Path(self.identity['path']).read_bytes()
        payload = self.check(path)
        self.assertEqual(payload['requirements_status'],'BOUND_TO_SNAPSHOT')
        self.assertFalse(payload['evidence_errors'])
        self.assertEqual(payload['evidence_files']['requirements_sha256'],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(payload['data_requirements']['four_dates'][0]['raw'],self.raw)
        self.assertEqual(Path(self.identity['path']).read_bytes(),before)
        self.assertEqual(payload['delivery_scope'],'DATA_AND_READINESS_ONLY')
        self.assertFalse(payload['formal_backtest_authorized'])

    def test_missing_requirements_are_not_zero_blockers(self):
        payload = self.check()
        self.assertEqual(payload['requirements_status'],'NOT_PROVIDED')
        self.assertNotIn('data_requirements',payload)
        page = write_pilot_readiness(payload,self.root/'ui').read_text(encoding='utf-8')
        self.assertIn('不表示没有阻塞',page)
        self.assertEqual(self.check(self.root/'missing.json')['requirements_status'],'INVALID')

    def test_other_snapshot_revision_or_wrong_counts_rejected(self):
        path = self.requirements_fixture()
        for key,value in [('id','sha256:wrong'),('data_revision',999)]:
            original = self.requirements['snapshot']
            self.requirements['snapshot'] = {**original,key:value}
            self.save_requirements()
            self.assertTrue(self.check(path)['evidence_errors'])
            self.requirements['snapshot'] = original
        self.save_requirements()
        self.admission['counts']['vwap_dates'] = 2
        self.save_admission()
        self.assertNotIn('data_requirements',self.check(path))

    def test_duplicates_and_wrong_raw_values_rejected_without_partial_details(self):
        path = self.requirements_fixture()
        item = self.requirements['four_dates'][0]
        self.requirements['four_dates'].append(item)
        self.save_requirements()
        self.assertTrue(self.check(path)['evidence_errors'])
        self.requirements['four_dates'].pop()
        item['raw']['amount'] = 999.0
        self.save_requirements()
        result = self.check(path)
        self.assertEqual(result['requirements_status'],'INVALID')
        self.assertNotIn('data_requirements',result)

    def test_page_shows_exact_needs_without_automatic_next_stage(self):
        payload = self.check(self.requirements_fixture())
        page = write_pilot_readiness(payload,self.root/'ui').read_text(encoding='utf-8')
        for expected in ('TEST_ONLY','2015-05-29','1001.0','10.01','不恢复 919 队列',
                         '保持现有成交模型不变','1 个异常日期','1 段统计范围'):
            self.assertIn(expected,page)
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('再进入 20 / 100',page)

    def test_corrupt_history_is_disclosed_and_retained(self):
        output = self.root/'ui'
        records = output/'records'; records.mkdir(parents=True)
        broken = records/'9999-corrupt.json'; broken.write_text('{',encoding='utf-8')
        page = write_pilot_readiness(self.check(),output).read_text(encoding='utf-8')
        self.assertIn('读取失败或格式不符：1 条',page)
        self.assertEqual(broken.read_text(encoding='utf-8'),'{')

    def test_writer_rejects_fake_trading_authorization(self):
        for key in ('formal_backtest_authorized','operational_observation'):
            with self.assertRaises(ValueError):
                write_pilot_readiness({**self.check(),key:True},self.root/'ui')

    def test_admission_revision_mismatch_rejected(self):
        self.admission['snapshot'] = {**self.identity,'data_revision':999}
        self.save_admission()
        self.assertTrue(self.check()['evidence_errors'])


if __name__ == '__main__':unittest.main()
