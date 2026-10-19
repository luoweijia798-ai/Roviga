"""Synthetic approval envelopes test identity guards, never real admission."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict
from stock_picker import phase4_foundation as foundation
from stock_picker.phase4_acceptance import freeze_database, ACCEPTANCE_END
from stock_picker.real_market import SQLiteMarketCache
from stock_picker.selector import SelectionConfig
from stock_picker.risk import RiskConfig
from stock_picker.trading import ExecutionConfig


class FormalBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        cache=SQLiteMarketCache(self.root/'synthetic.sqlite')
        self.snapshot=freeze_database(cache.path,self.root/'frozen.sqlite')
        self.config={'backtest':asdict(foundation.BacktestConfig()),'selector':asdict(SelectionConfig()),
                     'risk':asdict(RiskConfig()),'execution':asdict(ExecutionConfig())}
        self.binding={'schema':'roviga-formal-binding-v1','formal_interval':['2015-06-01','2026-09-30'],
            'configuration':self.config,'snapshot':self.snapshot,
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(foundation.__file__).parent.glob('*.py')},'evidence':{}}
        for name in ('full_market_admission','execution_model_validation','frozen_configuration'):
            proof=self.config if name=='frozen_configuration' else {'synthetic_test_only':True,
                'snapshot':self.snapshot,'scope':'full_market','formal_gate_eligible':True,'passed':True,'blockers':[]}
            path=self.root/(name+'.json');path.write_text(json.dumps(proof),encoding='utf-8')
            self.binding['evidence'][name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        self.path=self.root/'binding.json';self.save()

    def save(self):self.path.write_text(json.dumps(self.binding),encoding='utf-8')
    def runner(self):return foundation.Phase4FoundationRunner(self.snapshot['path'],admission_path=self.path)

    def test_matching_identity_check_is_read_only_not_a_run(self):
        before=Path(self.snapshot['path']).read_bytes()
        self.runner()._verify_formal_binding(ACCEPTANCE_END)
        self.assertEqual(before,Path(self.snapshot['path']).read_bytes())
        self.assertFalse(Path(self.snapshot['path']+'-wal').exists())

    def test_configuration_code_and_data_changes_reject_old_binding(self):
        original=json.loads(json.dumps(self.binding))
        for change in ('configuration','code','data'):
            self.binding=json.loads(json.dumps(original))
            if change=='configuration':self.binding['configuration']['backtest']['initial_cash']=99
            elif change=='code':self.binding['code_sha256']['selector.py']='different'
            else:self.binding['snapshot']['id']='sha256:changed'
            self.save()
            with self.subTest(change=change),self.assertRaises(foundation.DataCoverageError):
                self.runner()._verify_formal_binding(ACCEPTANCE_END)

    def test_pilot_report_and_changed_evidence_are_not_formal(self):
        ref=self.binding['evidence']['full_market_admission'];path=Path(ref['path'])
        proof=json.loads(path.read_text());proof['scope']='three_security_pilot'
        path.write_text(json.dumps(proof),encoding='utf-8')
        with self.assertRaisesRegex(foundation.DataCoverageError,'evidence changed'):
            self.runner()._verify_formal_binding(ACCEPTANCE_END)
        ref['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();self.save()
        with self.assertRaisesRegex(foundation.DataCoverageError,'ineligible'):
            self.runner()._verify_formal_binding(ACCEPTANCE_END)

    def test_manual_boolean_and_missing_binding_are_not_admission(self):
        self.path.write_text('{"passed":true}',encoding='utf-8')
        with self.assertRaises(foundation.DataCoverageError):self.runner()._verify_formal_binding(ACCEPTANCE_END)
        with self.assertRaises(foundation.DataCoverageError):
            foundation.Phase4FoundationRunner(self.snapshot['path'])._verify_formal_binding(ACCEPTANCE_END)


if __name__=='__main__':unittest.main()
