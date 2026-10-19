"""Synthetic consumer traces, not real prices or a return backtest."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from stock_picker.real_market import SQLiteMarketCache, SQLiteHistoricalDataPortal


class PriceFieldDependencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cache = SQLiteMarketCache(Path(self.tmp.name)/'synthetic.sqlite')
        with self.cache.connect() as connection:
            for day, vwap in [('2015-05-29',10.01),('2015-06-01',10.)]:
                connection.execute('INSERT INTO bars(trading_date,symbol,open,high,low,close,volume,vwap,tradable,limit_up_locked,limit_down_locked,amount,signal_close) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (day,'TEST_ONLY',10.,10.,10.,10.,100,vwap,1,0,0,1000.,20.))
        self.portal = SQLiteHistoricalDataPortal(self.cache.path)
        self.portal.advance_to(date(2015,6,1))

    def test_sqlite_signal_reads_only_previous_signal_price_not_warmup_vwap(self):
        daily = self.portal.daily_snapshot(date(2015,6,1))
        self.assertEqual(daily[0].previous_close,20.)
        self.assertEqual(len(self.portal.bars_on(date(2015,6,1))),1)
        with self.assertRaisesRegex(ValueError,'VWAP'):
            self.portal.previous_bar('TEST_ONLY',date(2015,6,1))

    def test_formal_bar_still_rejects_vwap_before_any_selection(self):
        with self.cache.connect() as connection:
            connection.execute("UPDATE bars SET vwap=10.01 WHERE trading_date='2015-06-01'")
        with self.assertRaisesRegex(ValueError,'VWAP'):
            self.portal.bars_on(date(2015,6,1))

    def test_current_volume_is_actual_signal_input_warmup_volume_is_not(self):
        with self.cache.connect() as connection:
            connection.execute("UPDATE bars SET volume=9999 WHERE trading_date='2015-05-29'")
        self.assertEqual(self.portal.daily_snapshot(date(2015,6,1))[0].volume,100)
        with self.cache.connect() as connection:
            connection.execute("UPDATE bars SET volume=123 WHERE trading_date='2015-06-01'")
        self.assertEqual(self.portal.daily_snapshot(date(2015,6,1))[0].volume,123)


if __name__ == '__main__':unittest.main()
