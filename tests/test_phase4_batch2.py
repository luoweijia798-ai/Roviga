"""Explicit isolated synthetic fixtures; never market data or return results."""
import unittest
from datetime import date
from pathlib import Path

from test_real_market import _test_directory
from stock_picker.data_audit import full_day_event_dates, load_session_explanations
from stock_picker.data_semantics import gap_accounting, baseline_dependencies
from stock_picker.historical import HistoricalBar
from stock_picker.phase4_acceptance import SnapshotCache
from stock_picker.real_market import SQLiteMarketCache, SQLiteHistoricalData, StockInfo
from stock_picker.semantic_review import corrected_chinext_inference, real_prior_row, dated_signal_prices


class Batch2EvidenceTests(unittest.TestCase):
    def test_intraday_and_forecast_resume_do_not_explain_full_day(self):
        days=['2015-06-01','2015-06-02']
        self.assertEqual(full_day_event_dates({'SUSPEND_START_TIME':'2015-06-01 10:00:00',
            'SUSPEND_END_TIME':'2015-06-01 15:00:00'},days),[])
        self.assertEqual(full_day_event_dates({'SUSPEND_START_TIME':'2015-06-01 09:00:00',
            'PREDICT_RESUME_DATE':'2015-06-03'},days),[])

    def test_explicit_full_day_bounds_and_multiday_intraday_edges(self):
        days=['2015-06-01','2015-06-02','2015-06-03']
        self.assertEqual(full_day_event_dates({'SUSPEND_START_TIME':'2015-06-01 10:00:00',
            'SUSPEND_END_TIME':'2015-06-03 14:00:00'},days),['2015-06-02'])
        self.assertEqual(full_day_event_dates({'SUSPEND_START_TIME':'bad','SUSPEND_END_TIME':'bad'},days),[])

    def test_calendar_accounting_only_accepts_verified_evidence_no_fabrication(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            cache.upsert_stocks([StockInfo('000001','fixture','SZSE',list_date=date(2015,6,1))])
            with cache.connect() as c:
                c.execute('CREATE TABLE session_evidence(symbol TEXT,trading_date TEXT,status TEXT,evidence TEXT)')
                c.executemany('INSERT INTO session_evidence VALUES (?,?,?,?)',[
                    ('000001','2015-06-01','verified_full_day_suspension','isolated test fixture'),
                    ('000001','2015-06-02','intraday_only','isolated test fixture')])
                self.assertEqual(load_session_explanations(c),{'000001':{'2015-06-01'}})
                self.assertEqual(c.execute('SELECT COUNT(*) FROM bars').fetchone()[0],0)
            result=gap_accounting(SnapshotCache(cache.path),['2015-06-01','2015-06-02'])
            self.assertEqual(result['missing_categories']['confirmed_suspension'],1)
            self.assertEqual(result['missing_categories']['unknown_active_reason'],1)
            self.assertTrue(result['date_accounting_reconciles'])

    def test_formal_view_isolates_only_approved_non_session_and_preserves_raw(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            for day in (date(2015,6,1),date(2015,6,6)):
                cache.upsert_bars([HistoricalBar(day,'000001',10,10,10,10,100,amount=1000)])
            with cache.connect() as c:
                c.execute('INSERT INTO provider_quarantine VALUES (?,?,?,?,?)',('000001','2015-06-06','fixture','fixture','isolated_not_formally_approved'))
                self.assertEqual(c.execute('SELECT COUNT(*) FROM accepted_bars').fetchone()[0],2)
                c.execute("UPDATE provider_quarantine SET review_status='confirmed_non_session_excluded'")
                self.assertEqual(c.execute('SELECT COUNT(*) FROM accepted_bars').fetchone()[0],1)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM bars').fetchone()[0],2)
            portal=SQLiteHistoricalData(cache.path).portal()
            portal.advance_to(date(2015,6,6))
            self.assertIsNone(portal.bar('000001',date(2015,6,6)))

    def test_warmup_is_available_to_previous_bar_but_not_formal_trading_dates(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/'fixture.sqlite')
            for day in (date(2015,5,28),date(2015,6,1),date(2026,10,8)):
                cache.upsert_bars([HistoricalBar(day,'000001',10,10,10,10,100,amount=1000,signal_close=20)])
            with cache.connect() as c:
                c.executemany('INSERT OR REPLACE INTO metadata VALUES (?,?)',[
                    ('formal_backtest_start','2015-06-01'),('formal_backtest_end','2026-09-30')])
            data=SQLiteHistoricalData(cache.path)
            self.assertEqual(data.trading_dates,(date(2015,6,1),))
            portal=data.portal();portal.advance_to(date(2015,6,1))
            self.assertEqual(portal.previous_bar('000001',date(2015,6,1)).trading_date,date(2015,5,28))

    def test_real_quote_units_no_estimated_vwap_and_no_future_factor(self):
        raw=['2015-05-29','10','10','11','9','1',{},'','0.5']
        factors=[{'d':'2010-01-01','f':'2'},{'d':'2015-06-01','f':'100'}]
        row=real_prior_row('000001',raw,factors)
        self.assertEqual(row[6],100);self.assertEqual(row[11],5000)
        self.assertIsNone(row[7]);self.assertEqual(row[17],20)
        with self.assertRaises(ValueError):real_prior_row('000001',raw[:8],factors)
        with self.assertRaises(ValueError):dated_signal_prices(raw,[{'d':'2015-06-01','f':'100'}])
        with self.assertRaises(ValueError):dated_signal_prices(raw,[{'d':'2010-01-01','f':'2'},{'d':'2010-01-01','f':'3'}])

    def fixture_limits(self):
        row={'symbol':'300001','trading_date':'2021-03-01','open':11,'high':11,'low':11,'close':11,
             'up_limit':10.5,'down_limit':9.5,'limit_up_locked':0,'limit_down_locked':0}
        previous={'trading_date':'2021-02-26','close':10}
        return row,previous,[{'d':'2010-01-01','f':'1'}]

    def test_recognizable_derived_limit_bug_not_price_or_tolerance_change(self):
        row,previous,factors=self.fixture_limits();original=dict(row)
        new,reason=corrected_chinext_inference(row,previous,'2010-01-01','2021-02-26',factors)
        self.assertEqual((new['up_limit'],new['down_limit']),(12,8))
        self.assertEqual(row,original);self.assertIn('20pct',reason)

    def test_exrights_resume_ipo_and_nonmatching_limits_remain_unresolved(self):
        row,previous,factors=self.fixture_limits()
        for listing,prior,fs in [('2021-02-26','2021-02-26',factors),
                                ('2010-01-01','2021-02-25',factors),
                                ('2010-01-01','2021-02-26',factors+[{'d':'2021-03-01','f':'2'}])]:
            self.assertIsNone(corrected_chinext_inference(row,previous,listing,prior,fs)[0])
        row['up_limit']=10.51
        self.assertIsNone(corrected_chinext_inference(row,previous,'2010-01-01','2021-02-26',factors)[0])

    def test_dependencies_keep_existing_lengths_without_new_factor_requirements(self):
        history=baseline_dependencies()['history_readiness']
        self.assertEqual(history['signal_close_momentum']['prior_actual_quotes'],1)
        self.assertEqual(history['market_regime_display']['pre_window_closes'],19)
        self.assertFalse(history['moving_average_breakout_volatility']['enabled'])


if __name__=='__main__':unittest.main()
