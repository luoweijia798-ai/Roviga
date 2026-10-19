"""Synthetic records only; persistence is not admission or real market results."""
import json
import sqlite3
import tempfile
import unittest
import subprocess
import sys
from contextlib import closing
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from stock_picker.models import Selection
from stock_picker.tracking import DailyTracker, SQLiteDailyTracker
from stock_picker.trading import Trade, Side


DAY = date(2026, 8, 17)
CONTEXT = {'kind':'synthetic_test','data_version':'test-fixture-v1','configuration_id':'test-only'}


class TrackingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'tracking.sqlite'
        self.tracker = SQLiteDailyTracker(self.path, context=CONTEXT, create=True)
        self.selection = Selection(DAY,'TEST_ONLY',.1,.1,1.)

    def signal(self, tracker=None):
        return (tracker or self.tracker).record_signal(self.selection,
            planned_entry_price=10.,stop_price=9.,take_profit_price=12.)

    def test_restart_replays_identical_existing_calculations_and_pending_horizons(self):
        memory = DailyTracker()
        self.signal(memory); self.signal()
        trade = Trade(DAY+timedelta(days=1),'TEST_ONLY',Side.BUY,100,10.,10.,1000.,0.,0.,0.,-1000.)
        for tracker in (memory,self.tracker):
            tracker.record_fill(DAY,trade)
            tracker.update_market(DAY,trading_date=DAY+timedelta(days=1),close=10.2,high=10.3,low=10.)
        recovered = SQLiteDailyTracker(self.path, read_only=True)
        self.assertEqual(asdict(recovered.get(DAY)),asdict(memory.get(DAY)))
        self.assertEqual(set(recovered.get(DAY).performance),{1})
        self.assertEqual(recovered.inspection()['event_count'],3)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            event = json.loads(connection.execute('SELECT payload FROM tracking_events LIMIT 1').fetchone()[0])
        self.assertIn('+00:00',event['recorded_at'])

    def test_duplicate_calls_are_idempotent_but_replacements_rejected(self):
        self.signal(); self.signal()
        self.assertEqual(self.tracker.inspection()['event_count'],1)
        with self.assertRaisesRegex(ValueError,'conflicting repeat'):
            self.tracker.record_signal(Selection(DAY,'REPLACEMENT',.2,.1,1.),
                planned_entry_price=10.,stop_price=9.,take_profit_price=12.)
        self.assertEqual(self.tracker.get(DAY).signal.symbol,'TEST_ONLY')

    def test_two_instances_preserve_one_candidate_and_no_lost_updates(self):
        another = SQLiteDailyTracker(self.path)
        self.signal(); self.signal(another)
        self.tracker.update_market(DAY,trading_date=DAY+timedelta(days=1),close=10.1)
        another.update_market(DAY,trading_date=DAY+timedelta(days=2),close=10.2)
        self.assertEqual(len(self.tracker.get(DAY).observations),2)
        self.assertEqual(another.inspection()['event_count'],3)

    def test_invalid_update_rolls_back_without_dropping_previous_history(self):
        self.signal()
        with self.assertRaises(ValueError):
            self.tracker.update_market(DAY,trading_date=DAY,close=10.)
        self.assertEqual(SQLiteDailyTracker(self.path).inspection()['event_count'],1)
        with self.assertRaises(ValueError):
            self.tracker.update_market(DAY,trading_date=DAY+timedelta(days=1),close=float('nan'))
        self.assertEqual(self.tracker.inspection()['event_count'],1)

    def test_partial_transaction_is_not_committed(self):
        self.signal()
        with self.assertRaises(RuntimeError):
            with self.tracker._connection(write=True) as connection:
                connection.execute("INSERT INTO tracking_events VALUES(2,'partial','{}','bad')")
                raise RuntimeError('synthetic interrupted writer')
        self.assertEqual(SQLiteDailyTracker(self.path).inspection()['event_count'],1)

    def test_changed_context_and_corrupt_history_fail_closed(self):
        self.signal()
        with self.assertRaises(ValueError):
            SQLiteDailyTracker(self.path,context={**CONTEXT,'kind':'prospective_paper'})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE tracking_events SET payload='{}'")
        with self.assertRaises((ValueError,KeyError)):
            SQLiteDailyTracker(self.path)

    def test_read_only_inspection_does_not_create_or_modify(self):
        self.signal()
        before = self.path.read_bytes()
        recovered = SQLiteDailyTracker(self.path,read_only=True)
        recovered.inspection()
        with self.assertRaises(ValueError):self.signal(recovered)
        self.assertEqual(self.path.read_bytes(),before)
        missing = self.path.with_name('missing.sqlite')
        with self.assertRaises(sqlite3.OperationalError):SQLiteDailyTracker(missing,read_only=True)
        self.assertFalse(missing.exists())

    def test_existing_nonjournal_database_is_never_initialized(self):
        unrelated = self.path.with_name('market.sqlite')
        with closing(sqlite3.connect(unrelated)) as connection, connection:connection.execute('CREATE TABLE bars(x)')
        before = unrelated.read_bytes()
        with self.assertRaises(sqlite3.OperationalError):SQLiteDailyTracker(unrelated,context=CONTEXT,create=True)
        self.assertEqual(unrelated.read_bytes(),before)

    def test_corrupt_sequence_not_silently_skipped(self):
        self.signal()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE tracking_events SET seq=2')
        with self.assertRaisesRegex(ValueError,'non-contiguous'):SQLiteDailyTracker(self.path)

    def test_workflow_reservation_prevents_duplicate_broker_execution_on_restart(self):
        from stock_picker.workflow import PaperTradingWorkflow
        from stock_picker.trading import PaperAccount, PaperBroker
        from stock_picker.risk import RiskManager
        account = PaperAccount(10000)
        broker = PaperBroker(account)
        workflow = PaperTradingWorkflow(account,broker,RiskManager(10000,DAY),self.tracker)
        result = workflow.submit_candidate(self.selection,entry_price=10.,stop_price=9.,take_profit_price=12.)
        self.assertIsNotNone(result.track.fill)
        prior_cash = account.cash
        resumed = PaperTradingWorkflow(account,broker,RiskManager(10000,DAY),SQLiteDailyTracker(self.path))
        with self.assertRaisesRegex(ValueError,'already submitted'):
            resumed.submit_candidate(self.selection,entry_price=10.,stop_price=9.,take_profit_price=12.)
        self.assertEqual(prior_cash,account.cash)
        self.assertEqual(self.tracker.inspection()['fill_count'],1)

    def test_tracking_history_cli_reads_without_market_database(self):
        self.signal()
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable,'-m','stock_picker.phase4_foundation','tracking-history',
                                 '--tracking-ledger',str(self.path)],capture_output=True,text=True,check=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['context']['kind'],'synthetic_test')
        self.assertEqual(payload['event_count'],1)
        self.assertEqual(self.path.read_bytes(),before)


if __name__ == '__main__':unittest.main()
