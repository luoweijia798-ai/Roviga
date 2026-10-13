"""Explicitly synthetic ISOLATED test fixtures, never production replacements."""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_real_market import _test_directory, _FakeAkShare, END, pd
from stock_picker.security_master import (canonical_code, verified_date, observations_from_frame,
    SPECS, apply_master, sse_a_retired_frame, resolve_proven_b_share_date)
from stock_picker.data_semantics import baseline_dependencies, quality_flags, gap_accounting
from stock_picker.real_market import SQLiteMarketCache, StockInfo, AkShareAdapter, PHASE4_START, _infer_limits
from stock_picker.historical import HistoricalBar, BenchmarkPoint
from stock_picker.tencent_bse import price_conflict
from stock_picker.phase4_acceptance import SnapshotCache, admission_report
from stock_picker.data_audit import RealMarketDataAuditor
from stock_picker.sina_archive import archive_frames


@unittest.skipIf(pd is None, "optional pandas dependency")
class MasterSemanticsTests(unittest.TestCase):
    def observation(self, symbol="000001", listing="1991-04-03"):
        frame=pd.DataFrame([{"A股代码":symbol,"A股上市日期":listing,"板块":"主板"}])
        return observations_from_frame(frame,SPECS[0],"2026-10-13T00:00:00Z",[{"sha256":"isolated-fixture"}])[0]

    def test_code_and_date_parsing_do_not_guess_unknown_values(self):
        self.assertEqual(canonical_code("1.0"),"000001")
        self.assertIsNone(canonical_code("1e5"))
        self.assertEqual(verified_date("19910403"),"1991-04-03")
        for value in ("NaT","not-a-date","2026-02-30",None):self.assertIsNone(verified_date(value))

    def test_source_date_not_first_bar_or_automatic_code_validity(self):
        obs=self.observation()
        self.assertEqual(obs["list_date"],"1991-04-03")
        self.assertIsNone(obs["security_id"])
        self.assertIsNone(obs["code_valid_from"])
        self.assertIsNone(obs["last_trade_date"])
        self.assertEqual(obs["registry_key"],"SZSE:000001")

    def test_batch_mapping_reuses_actual_listing_column(self):
        class Client(_FakeAkShare):
            def stock_info_sz_name_code(self,**args):
                return pd.DataFrame([{"A股代码":"000001","A股上市日期":"1991-04-03"}])
        stocks=AkShareAdapter(ak_module=Client(),request_interval=0,max_attempts=1)._stock_universe(Client())
        self.assertEqual(stocks[0].list_date,date(1991,4,3))

    def test_apply_fills_nulls_retains_retired_and_records_original_evidence(self):
        with _test_directory() as tmp:
            c=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            c.upsert_stocks([StockInfo("000001","A","SZSE"),StockInfo("000002","retired","SZSE",delist_date=date(2010,1,1))])
            r=apply_master(c,[self.observation()])
            self.assertEqual(r["list_dates_filled"],1)
            self.assertEqual(len(c.stock_inventory()),2)
            with c.connect() as x:
                self.assertEqual(x.execute('select count(*) from metadata_repair_journal').fetchone()[0],1)
                self.assertEqual(x.execute('select count(*) from security_master_observations').fetchone()[0],1)
            r=apply_master(c,[self.observation(listing="1992-01-01")])
            self.assertEqual(len(r["conflicts"]),1)
            self.assertEqual(c.stock_inventory()[0].list_date,date(1991,4,3))

    def test_sync_cannot_overwrite_verified_date_with_known_conflict(self):
        with _test_directory() as tmp:
            c=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            c.upsert_stocks([StockInfo("000001","A","SZSE",list_date=date(1991,4,3))])
            c.upsert_stocks([StockInfo("000001","A","SZSE",list_date=date(2026,1,1))])
            self.assertEqual(c.stock_inventory()[0].list_date,date(1991,4,3))

    def test_sse_issuer_code_cannot_import_b_share_listing_date(self):
        raw={"result":[{"COMPANY_CODE":"600625","A_STOCK_CODE":"600625","B_STOCK_CODE":"900901","STOCK_TYPE":"2","LIST_DATE":"19941110"},
             {"COMPANY_CODE":"600625","A_STOCK_CODE":"600625","STOCK_TYPE":"1","LIST_DATE":"19930106"}]}
        frame=sse_a_retired_frame(raw)
        self.assertEqual(len(frame),1)
        self.assertEqual(frame.iloc[0]["上市日期"],"1993-01-06")
        with _test_directory() as tmp:
            c=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            c.upsert_stocks([StockInfo("600625","A","SSE",list_date=date(1994,11,10),source="AkShare.stock_info_sh_delist")])
            apply_master(c,[])
            corrected=resolve_proven_b_share_date(c,raw,"fixture-original-response")
            self.assertEqual(len(corrected),1)
            self.assertEqual(c.stock_inventory()[0].list_date,date(1993,1,6))
            self.assertEqual(resolve_proven_b_share_date(c,raw,"fixture-original-response"),[])

    def test_missing_dates_and_coverage_account_separately_without_invented_suspension(self):
        with _test_directory() as tmp:
            c=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            c.upsert_stocks([StockInfo("000001","A","SZSE",list_date=date(2015,6,3))])
            result=gap_accounting(SnapshotCache(c.path),["2015-06-01","2015-06-02","2015-06-03"])
            self.assertEqual(result["missing_categories"]["pre_listing"],2)
            self.assertEqual(result["missing_categories"]["unknown_active_reason"],1)
            self.assertEqual(result["missing_categories"]["confirmed_suspension"],0)
            self.assertTrue(result["date_accounting_reconciles"])
            self.assertTrue(result["coverage_reconciliation"]["reconciles"])

    def test_quality_counts_multiple_marks_on_one_row(self):
        r={"open":10,"high":9,"low":11,"close":10,"volume":100,"amount":0,"vwap":None,
           "tradable":1,"up_limit":9,"down_limit":11,"limit_up_locked":0,"limit_down_locked":0,
           "signal_open":10,"signal_high":11,"signal_low":9,"signal_close":10}
        flags=quality_flags(r)
        self.assertIn("invalid_ohlc",flags)
        self.assertIn("volume_without_amount",flags)
        self.assertIn("invalid_limit_order",flags)
        self.assertGreater(len(flags),1)

    def test_half_tick_equality_not_binary_float_false_conflict(self):
        self.assertGreater(abs(34.52-34.515),.005)
        self.assertFalse(price_conflict(34.52,34.515))
        self.assertTrue(price_conflict(34.52,34.5149))

    def test_chinext_ST_rule_precedence_is_date_specific(self):
        self.assertEqual(_infer_limits("300366","ST测试",date(2021,3,1),10),(12,8))
        self.assertEqual(_infer_limits("300366","ST测试",date(2020,8,23),10),(10.5,9.5))

    def test_archive_keeps_equal_real_values_on_distinct_trading_dates(self):
        rows=[{"date":d,"open":10,"high":10,"low":10,"close":10,"volume":100,"amount":1000}
              for d in ("2015-06-01","2015-06-02")]
        raw,_,_=archive_frames(rows,[{"d":"2000-01-01","f":"1"}],PHASE4_START,END)
        self.assertEqual(len(raw),2)

    def test_dependencies_are_existing_baseline_not_infinite_enhancement_gates(self):
        d=baseline_dependencies()
        self.assertIn("raw_open",d["required_current"])
        self.assertIn("VWAP",d["conditional_existing_mode"])
        self.assertIn("policy factors",d["reserved_not_baseline_gate"])
        self.assertIn("volume",d["observed_bar_attribute_reads"]["selector.py"])
        with _test_directory() as tmp:
            c=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            audit=RealMarketDataAuditor(SnapshotCache(c.path)).run(end_date=END).payload
            a=admission_report(SnapshotCache(c.path),audit,{})
            self.assertNotIn("classification_causality_unverified",a["blocker_summary"])
            self.assertFalse(a["formal_backtest_ready"])

    def test_unexpected_session_is_a_symbol_date_blocker_and_keeps_source_row(self):
        with _test_directory() as tmp:
            cache=SQLiteMarketCache(Path(tmp)/"fixture.sqlite")
            cache.upsert_stocks([StockInfo("000001","A","SZSE",list_date=date(2015,6,1))])
            cache.upsert_bars([
                HistoricalBar(date(2015,6,1),"000001",10,10,10,10,100,amount=1000),
                HistoricalBar(date(2015,6,6),"000001",10,10,10,10,100,amount=1000),
            ])
            cache.upsert_benchmarks([
                BenchmarkPoint(date(2015,6,1),"CSI300",4000),
                BenchmarkPoint(date(2015,6,1),"CSI1000",6000),
            ])
            audit=RealMarketDataAuditor(SnapshotCache(cache.path)).run(end_date=date(2015,6,6)).payload
            self.assertIn({"symbol":"000001","trading_date":"2015-06-06"},audit["unexpected_reference_sessions"])
            report=admission_report(SnapshotCache(cache.path),audit,{})
            blocker=next(x for x in report["blockers"] if x["reason"]=="unexpected_reference_session")
            self.assertEqual((blocker["symbol"],blocker["start"]),("000001","2015-06-06"))
            with cache.connect() as c:
                self.assertEqual(c.execute("select count(*) from bars where trading_date='2015-06-06'").fetchone()[0],1)


if __name__=='__main__':unittest.main()
