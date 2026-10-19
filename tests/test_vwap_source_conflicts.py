"""Synthetic raw turnover conflicts; no investment results or data replacement."""
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from stock_picker.real_market import SQLiteMarketCache, StockInfo, _bounded_vwap
from stock_picker import sync_retry


class VWAPSourceConflictTests(unittest.TestCase):
    def test_tiny_positive_and_negative_conflicts_not_clamped(self):
        for amount in (1000.000001,999.999999):
            with self.assertRaisesRegex(ValueError,'source precision/scope evidence required'):
                _bounded_vwap(amount,100,10.,10.)

    def test_valid_ratio_and_missing_turnover_do_not_invent_values(self):
        self.assertEqual(_bounded_vwap(1050,100,10.,11.),10.5)
        self.assertIsNone(_bounded_vwap(0,100,10.,11.))
        self.assertIsNone(_bounded_vwap(1050,0,10.,11.))

    def test_mainboard_conflict_requires_evidence_not_endless_time_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=SQLiteMarketCache(Path(directory)/'synthetic.sqlite')
            stock=StockInfo('TEST_ONLY','synthetic','SZSE',date(2010,1,1))
            start,end=date(2015,6,1),date(2015,6,2)
            now=datetime(2026,10,19,tzinfo=timezone.utc)
            sync_retry.failed(cache,stock,start,end,ValueError('raw VWAP outside daily range: synthetic'),now)
            self.assertFalse(sync_retry.eligible(cache,stock,start,end,now+timedelta(days=30)))
            with cache.connect() as connection:
                row=connection.execute('SELECT * FROM sync_retry_policy').fetchone()
                self.assertEqual(row['disposition'],'source_review_required')
                self.assertEqual(row['consecutive_failures'],1)
            self.assertTrue(sync_retry.eligible(cache,stock,start,end+timedelta(days=1),now))


if __name__ == '__main__':unittest.main()
