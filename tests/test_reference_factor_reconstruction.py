"""Synthetic unit fixtures only, not historical source evidence."""
import copy
import unittest
from fractions import Fraction
from stock_picker.semantic_review import reconstruct_reference_factors, derive_scoped_signal_prices


class ReferenceFactorTests(unittest.TestCase):
    def setUp(self):
        self.rule = {'symbol': '000035', 'anchor_date': '2015-05-29',
            'end_date': '2026-09-30', 'version': 'synthetic-v2',
            'formal_gate_eligible': False, 'factor_construction': 'reference-step-product-v2',
            'formula': 'raw * cumulative_factor(date) / cumulative_factor(anchor)',
            'quantum': '0.00000001', 'rounding': 'ROUND_HALF_EVEN'}
        self.events = [dict(symbol='000035', effective_date=d, announcement_date=a,
            previous_actual_date=p, previous_actual_close=c, reference_preclose=r,
            source_sha256='synthetic-announcement', reference_evidence_sha256='synthetic-reference',
            captured_at='2026-10-19') for d,a,p,c,r in [
                ('2016-05-27','2016-05-21','2016-05-26','12.78','6.39'),
                ('2022-06-16','2022-06-09','2022-06-15','5.17','5.08')]]

    def test_exact_product_not_six_decimal_provider_rounding(self):
        factors = reconstruct_reference_factors(self.events, self.rule)
        self.assertEqual(factors[1]['cumulative_factor'], '2')
        self.assertEqual(Fraction(int(factors[-1]['exact_numerator']), int(factors[-1]['exact_denominator'])), Fraction(517,254))
        self.assertIsNone(factors[-1]['historical_available_at'])

    def test_cutoff_and_repeat_and_no_mutation(self):
        source = copy.deepcopy(self.events)
        all_f = reconstruct_reference_factors(self.events, self.rule)
        self.assertEqual(all_f[:2], reconstruct_reference_factors(self.events[:1], self.rule))
        self.assertEqual(all_f, reconstruct_reference_factors(self.events, self.rule))
        self.assertEqual(self.events, source)

    def test_derived_segments_preserve_raw_fields(self):
        rows = [dict(symbol='000035', date=d, open='10', high='11', low='9', close='10.5', volume=100, amount=1050)
                for d in ['2015-05-29','2016-05-27','2022-06-16']]
        factors = reconstruct_reference_factors(self.events, self.rule)
        whole = derive_scoped_signal_prices(rows, factors, self.rule)
        self.assertEqual(whole, sum((derive_scoped_signal_prices([r], factors, self.rule) for r in rows), []))
        for row, derived in zip(rows, whole):
            for key, value in row.items(): self.assertEqual(derived[key], value)

    def test_unknown_late_duplicate_and_invalid_inputs_rejected(self):
        for patch in [{'announcement_date':'2016-05-27'}, {'announcement_date':'2017-01-01'},
                      {'reference_preclose':'0'}, {'reference_preclose':'NaN'},
                      {'previous_actual_close':12.78}, {'source_sha256':None},
                      {'reference_evidence_sha256':None}, {'previous_actual_date':'2016-05-27'},
                      {'symbol':'000033'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                reconstruct_reference_factors([{**self.events[0], **patch}], self.rule)
        with self.assertRaises(ValueError): reconstruct_reference_factors(self.events*2, self.rule)

    def test_no_market_wide_or_approved_rule(self):
        for patch in [{'symbol':'600000'}, {'formal_gate_eligible':True}, {'factor_construction':'fitted-ratio'}]:
            with self.assertRaises(ValueError): reconstruct_reference_factors(self.events, {**self.rule, **patch})


if __name__ == '__main__': unittest.main()
