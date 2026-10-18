"""Synthetic data-layer fixtures, not real history or a return backtest."""
import unittest
from stock_picker.real_market import _row_to_bar


class UnknownMarketStateTests(unittest.TestCase):
    def row(self):
        return dict(trading_date='2015-06-01', symbol='000035',
                    open=10., high=11., low=9., close=10., volume=1000,
                    amount=10000., vwap=10., tradable=1,
                    limit_up_locked=0, limit_down_locked=0,
                    up_limit=11., down_limit=9., signal_open=20.,
                    signal_high=22., signal_low=18., signal_close=20.)

    def test_unknown_lock_is_not_false(self):
        for field in ('limit_up_locked', 'limit_down_locked'):
            row=self.row();row[field]=None
            with self.assertRaisesRegex(ValueError, 'unknown '+field):
                _row_to_bar(row)

    def test_known_flags_and_raw_signal_prices_are_unchanged(self):
        for flags in ((0,0),(1,0),(0,1)):
            row=self.row();row['limit_up_locked'],row['limit_down_locked']=flags
            bar=_row_to_bar(row)
            self.assertEqual((bar.limit_up_locked,bar.limit_down_locked),tuple(map(bool,flags)))
            self.assertEqual(bar.open,10.);self.assertEqual(bar.signal_open,20.)

    def test_vwap_validation_not_waived_for_open_execution(self):
        row=self.row();row['vwap']=8.99999999
        with self.assertRaisesRegex(ValueError,'VWAP must be inside'):
            _row_to_bar(row)


if __name__=='__main__':unittest.main()
