"""Synthetic empty SQLite fixtures; no market data, signals or returns."""
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
        self.identity = freeze_database(cache.path, self.root / 'snapshot.sqlite')
        self.identity_path = self.root / 'identity.json'
        self.identity_path.write_text(json.dumps(self.identity), encoding='utf-8')
        self.admission = {'snapshot': self.identity, 'formal_interval':['2015-06-01','2026-09-30'], 'counts':{}, 'securities':{}}
        self.admission_path = self.root / 'admission.json'
        self.save_admission()

    def save_admission(self):
        self.admission_path.write_text(json.dumps(self.admission), encoding='utf-8')

    def check(self):
        return pilot_readiness(self.identity_path, self.admission_path,
            now=datetime(2026,10,19,2,0,tzinfo=timezone.utc))

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


if __name__ == '__main__':unittest.main()
