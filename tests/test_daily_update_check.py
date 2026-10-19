"""Synthetic update inventories, not historical pool certification."""
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from stock_picker.phase4_acceptance import freeze_database
from stock_picker.real_market import SQLiteMarketCache
from stock_picker.sync_monitor import daily_update_check


class DailyUpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        cache=SQLiteMarketCache(self.root/'source.sqlite')
        with cache.connect() as connection:
            for symbol,listed,delisted in [('A','2010-01-01',None),('B','2010-01-01',None),
                                           ('C',None,None),('D','2010-01-01','2015-01-01')]:
                connection.execute('INSERT INTO stocks(symbol,name,exchange,list_date,delist_date,source) VALUES(?,?,?,?,?,?)',
                                   (symbol,'synthetic','TEST',listed,delisted,'fixture'))
            connection.execute('INSERT INTO bars(trading_date,symbol,open,high,low,close,volume,vwap,tradable,limit_up_locked,limit_down_locked,amount) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                               ('2026-10-19','A',10,10,10,10,100,10,1,0,0,1000))
            connection.execute('INSERT INTO symbol_sync_status(symbol,provider,status,requested_start,requested_end,synced_through,updated_at) VALUES(?,?,?,?,?,?,?)',
                               ('A','fixture','complete','2015-06-01','2026-10-19','2026-10-19','2026-10-19T07:00:00Z'))
        self.snapshot=self.root/'snapshot.sqlite';freeze_database(cache.path,self.snapshot)
        self.calendar=self.root/'calendar.json'
        self.calendar.write_text(json.dumps({'calendar':{'dates':['2026-10-16','2026-10-19'],
            'verified_through':'2026-10-19','source':'synthetic','url':'https://example.invalid/test'}}),encoding='utf-8')

    def check(self, day=date(2026,10,19), now=None):
        return daily_update_check(self.snapshot,day,calendar_evidence=self.calendar,
                                  now=now or datetime(2026,10,19,8,tzinfo=timezone.utc))

    def test_latest_market_date_is_not_full_inventory_coverage(self):
        result=self.check()
        self.assertEqual(result['known_active_without_quote'],['B'])
        self.assertEqual(result['unknown_listing_inventory'],1)
        self.assertEqual(result['outside_inventory'],1)
        self.assertTrue(result['inventory_reconciles'])
        self.assertEqual(result['status'],'DATA_NOT_READY')
        self.assertIsNone(result['last_successful_write_at'])
        self.assertFalse(result['strategy_evaluated'])
        self.assertEqual(result['inventory_without_sync_status'],3)
        self.assertEqual(result['sync_target_or_checkpoint_pending'],3)

    def test_calendar_and_timing_are_separate_from_readiness(self):
        self.assertEqual(self.check()['calendar_status'],'LISTED_SESSION')
        self.assertEqual(self.check(date(2026,10,18))['calendar_status'],'NOT_LISTED_IN_COVERED_CALENDAR')
        self.assertEqual(self.check(date(2026,10,20))['calendar_status'],'UNKNOWN')
        before=datetime(2026,10,19,6,tzinfo=timezone.utc)
        self.assertEqual(self.check(now=before)['timing'],'BEFORE_REGULAR_CLOSE')
        self.assertEqual(self.check(date(2026,10,20))['timing'],'FUTURE_DATE')

    def test_read_only_and_missing_database_never_created(self):
        before=self.snapshot.read_bytes(); self.check()
        self.assertEqual(before,self.snapshot.read_bytes())
        missing=self.root/'missing.sqlite'
        result=daily_update_check(missing,date(2026,10,19))
        self.assertTrue(result['errors']);self.assertFalse(missing.exists())

    def test_invalid_calendar_does_not_claim_nontrading_day(self):
        self.calendar.write_text('{}',encoding='utf-8')
        result=self.check()
        self.assertEqual(result['calendar_status'],'UNKNOWN')
        self.assertTrue(result['errors'])

    def test_timezone_is_mandatory(self):
        with self.assertRaises(ValueError):self.check(now=datetime(2026,10,19))


if __name__ == '__main__':unittest.main()
