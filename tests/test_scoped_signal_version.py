"""Clearly synthetic unit fixtures; never used as historical market evidence."""
import copy
import unittest
from stock_picker.semantic_review import derive_scoped_signal_prices


class ScopedSignalVersionTests(unittest.TestCase):
    def setUp(self):
        self.rule = {'symbol':'000035','version':'synthetic-test-only',
            'formal_gate_eligible':False,'anchor_date':'2015-05-29','end_date':'2026-09-30',
            'formula':'raw * cumulative_factor(date) / cumulative_factor(anchor)',
            'quantum':'0.00000001','rounding':'ROUND_HALF_EVEN'}
        self.factors = [{'symbol':'000035','effective_date':d,'cumulative_factor':f,
            'source_sha256':'synthetic-not-market-evidence','captured_at':'2026-10-18',
            'historical_available_at':None,'verification_status':'unknown'}
            for d,f in [('2007-01-16','1.2'),('2016-05-27','2.4'),('2026-08-20','2.5')]]
        self.rows = [{'symbol':'000035','date':d,'open':'10','high':'11','low':'9','close':'10.5',
                      'volume':1000,'amount':10500,'vwap':10.5}
                     for d in ['2015-05-29','2016-05-26','2016-05-27','2026-08-20']]

    def test_whole_and_different_segments_are_identical(self):
        expected=derive_scoped_signal_prices(self.rows,self.factors,self.rule)
        for width in (1,2,3):
            actual=sum((derive_scoped_signal_prices(self.rows[i:i+width],self.factors,self.rule)
                        for i in range(0,len(self.rows),width)),[])
            self.assertEqual(expected,actual)

    def test_time_truncation_does_not_change_past(self):
        complete=derive_scoped_signal_prices(self.rows,self.factors,self.rule)
        for cutoff in [r['date'] for r in self.rows]:
            truncated=derive_scoped_signal_prices([r for r in self.rows if r['date']<=cutoff],
                [f for f in self.factors if f['effective_date']<=cutoff],self.rule)
            self.assertEqual(truncated,[r for r in complete if r['date']<=cutoff])

    def test_raw_execution_fields_and_unknown_publication_are_preserved(self):
        before=copy.deepcopy(self.rows)
        output=derive_scoped_signal_prices(self.rows,self.factors,self.rule)
        self.assertEqual(self.rows,before)
        for source,row in zip(before,output):
            for key in source:self.assertEqual(source[key],row[key])
            self.assertIsNone(row['adjustment_lineage']['historical_available_at'])
        self.assertEqual(output[0]['signal_close'],'10.50000000')
        self.assertEqual(output[2]['signal_close'],'21.00000000')

    def test_no_future_factor_or_arbitrary_anchor(self):
        with self.assertRaises(ValueError):derive_scoped_signal_prices(self.rows,self.factors[1:],self.rule)

    def test_duplicate_source_or_adjusted_input_rejected(self):
        for rows,factors in [(self.rows+self.rows[:1],self.factors),
                             (self.rows,self.factors+self.factors[:1]),
                             ([{**self.rows[0],'signal_close':'10'}],self.factors)]:
            with self.assertRaises(ValueError):derive_scoped_signal_prices(rows,factors,self.rule)

    def test_nonfinite_factor_zero_volume_and_scope_rejected(self):
        bad=copy.deepcopy(self.factors);bad[0]['cumulative_factor']='NaN'
        with self.assertRaises(ValueError):derive_scoped_signal_prices(self.rows,bad,self.rule)
        with self.assertRaises(ValueError):derive_scoped_signal_prices([{**self.rows[0],'volume':0}],self.factors,self.rule)
        with self.assertRaises(ValueError):derive_scoped_signal_prices(self.rows,self.factors,{**self.rule,'symbol':'600000'})
        with self.assertRaises(ValueError):derive_scoped_signal_prices(self.rows,self.factors,{**self.rule,'formal_gate_eligible':True})

    def test_evidence_revision_changes_only_new_output(self):
        old=derive_scoped_signal_prices(self.rows,self.factors,self.rule)
        changed=copy.deepcopy(self.factors);changed[1]['cumulative_factor']='2.6'
        new=derive_scoped_signal_prices(self.rows,changed,self.rule)
        self.assertEqual(old[:2],new[:2]);self.assertNotEqual(old[2],new[2])
        self.assertEqual(old,derive_scoped_signal_prices(self.rows,self.factors,self.rule))

    def test_precision_cannot_be_relaxed(self):
        with self.assertRaises(ValueError):derive_scoped_signal_prices(self.rows,self.factors,{**self.rule,'quantum':'0.01'})


if __name__=='__main__':unittest.main()
