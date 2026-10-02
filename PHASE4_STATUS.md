# Phase 4 checkpoint status

Checkpoint date: 2026-10-02

## Recovery checkpoint (2026-10-02)

- The active downloader was preserved. At 11:49 China time the live cache had
  5,905 inventory stocks: 5,233 complete, 668 failed, 1 interrupted, 1 running,
  and 2 without ledger records. It contained 11,238,830 bars for 5,710 stocks,
  dated 2015-06-01 through 2026-09-30. These are runtime observations, not a
  claim that all complete statuses cover the new target 2026-10-02.
- Reproducing `KeyError: 'date'` showed that the 347 such retained failures
  were BSE symbols entering Sina's unsupported A-share decoder. The earlier
  empty-adjusted-frame fix did NOT resolve this upstream failure. BSE now
  retains an explicit source-coverage failure instead of invoking that fallback.
  Eastmoney remains primary, but availability is not claimed for BSE.
- Retries prioritize failed/interrupted/unprocessed stocks before advancing
  previously complete stocks to the latest date. Segment-end checkpoints now
  include successful empty segments, so pre-listing date ranges do not repeat
  after a later failure. Provider inventory omissions cannot remove retained
  historical stocks; existing listing/delisting metadata is preserved.
- `stock_picker.sync_guardian` maintains a fixed batch end date, one-writer
  lock, 30-minute snapshots, and 15-minute retries after incomplete scans or
  worker failure. A zero worker exit code is NOT full-market completion.
  Windows task `RovigaPhase4Sync` now has a 30-minute restart opportunity and
  login trigger. The new guardian waits for the existing legacy supervisor
  to finish naturally; no active downloader was terminated or duplicated.
- `phase4_sync_status.json` is written atomically in the repository root.
  `scan_complete`, `sync_complete`, and `target_pending_count` are separate.
  Old completed ledgers cannot make a newer requested end date look complete.
- Audit gates now fail on every failed coverage check and unexplained missing
  session, check VWAP against amount/share volume, and invalidate prior audits
  whenever persisted market data or sync metadata changes. A revision check
  prevents an audit from passing if data changes while it is running.
  Missing sessions before an unknown listing date, or on unverified suspension
  dates, are explicitly provisional; they are not fabricated or waved through.
- All 12 new recovery tests and the 11 existing market-module tests passed
  using isolated test caches. No real-market backtest was run. Test fixtures
  are never mixed into the production SQLite cache.
- The prior September 27 audit failed (including 696 incomplete symbols and
  62,785 flagged rows); it is stale and is not a current audit result. Inferred
  historical price limits, missing VWAP, listing metadata, suspended sessions,
  delisted and BSE source coverage still need investigation. No passing audit
  and no delivery date are claimed.
- The existing Codex 30-minute Phase 4 heartbeat is active again, uses the
  corrected root snapshot, and reports meaningful changes or completion.
  On audit completion the guardian waits for instructions; it cannot invoke
  a backtest. `selector.py` and `risk.py` remain unchanged.

The earlier sections below are historical checkpoints, not live counters.

## Completed and saved

- Phase 4 part 1 remains complete: the real-market adapters, SQLite cache,
  point-in-time data portal, and foundation backtest entry point are present.
- The isolated `.venv` has the pinned AkShare market dependencies installed.
  The environment is ignored by Git and is not part of this commit.
- External access was verified for PyPI and the Eastmoney market endpoint when
  commands run with approved network access.
- The AkShare adapter now:
  - applies a 20-second timeout when the provider supports it;
  - records visible progress every 50 processed symbols;
  - stores AkShare/Eastmoney volume in shares rather than lots;
  - can fall back to AkShare's Sina daily/index endpoints;
  - supports `--history-source sina` for controlled diagnostics.
- The original `selector.py` and `risk.py` strategy logic is unchanged.
- Phase 4 part 2 sync/audit foundation is implemented:
  - all AkShare requests are rate limited and use bounded exponential retry;
  - stock history is downloaded in configurable date segments and committed
    after every segment;
  - reruns resume from SQLite and skip stocks already complete through the
    requested end date;
  - SQLite records per-stock state, provider endpoint, attempts, progress, and
    the last failure;
  - Eastmoney remains primary and Sina is a recorded fallback; Tushare remains
    the optional authenticated source for exact limits and coverage gaps;
  - the standalone `audit` command reports inventory, dates, benchmarks,
    compressed missing-session ranges per stock, invalid rows, and sources;
  - the real backtest is now hard-gated on a passing audit tied to the current
    sync manifest.
- The market environment was rebuilt and verified with Python 3.12.13,
  AkShare 1.18.91, and a fully pinned transitive constraint file. `pip check`
  reports no broken requirements.
- Provider functions that hide HTTP calls now receive a 20-second default at
  the underlying Requests session, preventing unbounded waits.
- Sina one-price sessions can report aggregate amount/volume values a fraction
  of a price tick outside the OHLC range. Sub-half-tick rounding is now clamped
  to the observed boundary; material mismatches retain OHLCV with missing VWAP
  and are explicit audit failures rather than fabricated execution prices.
- A restarted sync marks stale `running` rows as `interrupted` before resuming,
  so stopped processes cannot masquerade as concurrent active downloads.

## Data status (not committed)

- A new real-data sync is actively building
  `data/a_share_201506_present.sqlite`; the database and environment remain
  ignored runtime artifacts and are not committed.
- The real universe currently contains 5,876 stock metadata records. At the
  recorded checkpoint, `000001` was complete with 2,725 real daily bars from
  2015-06-01 through the latest available session 2026-08-14, and `000002` had
  started. The recorded bar source was AkShare/Sina after the primary
  Eastmoney path exhausted its bounded retries.
- The full-market sync is not complete and no passing data audit is claimed.
  The background sync remains resumable, retains failures in the per-symbol
  ledger, and does not delete existing rows.
- A later status snapshot contained 119,584 bars across 82 symbols. The first
  live run exposed provider-rounding VWAP failures; after the normalization fix,
  the same cache was restarted and those retained failures began reprocessing.
- A 30-minute monitor now writes `phase4_sync_status.json` and triggers the
  independent audit only after all inventory symbols reach a settled state.
  The audit bundle separates the main report, missing stocks, missing dates,
  and data anomalies. SQLite, logs, caches, and generated reports remain ignored.
- Latest implementation-validation snapshot: 5,877 inventory symbols, 205
  complete, 28 failed, 10 unavailable, 5,633 not yet processed; current symbol
  `000657` was at 2024-06-06. Audit was correctly not triggered.
- All SQLite files, virtual environments, generated reports, and temporary
  outputs remain excluded by `.gitignore`.
- No API key, token, credential, or real-market return result is stored in this
  checkpoint.

## Known blocker

- The code now mitigates Eastmoney throttling with rate limiting, retries,
  segmented requests, persistent progress, timeout enforcement, and fallback.
  The live run confirms Sina fallback writes real daily bars, while full-universe
  Eastmoney/Beijing/delisted coverage still requires completion and audit.
- The Sina fallback works for ordinary listed Shanghai/Shenzhen stocks but did
  not cover several early delisted symbols and a Beijing Stock Exchange smoke
  test. It therefore cannot yet be treated as a complete full-market source.
- A Windows multi-thread experiment was rejected because AkShare's embedded
  JavaScript runtime crashed under threads. The production sync remains
  single-threaded and resumable.
- Because universe and benchmark coverage have not passed audit, no real-market
  backtest or performance conclusion has been generated.

## Next step

1. Allow the active resumable sync to complete stock bars, amount/volume,
   price limits, stock metadata, classifications, CSI 300, and CSI 1000.
2. Rerun the same sync command until every retained failed/incomplete symbol has
   either completed or has a documented unavailable-source disposition.
3. Run and review the standalone data audit. Do not run the real backtest while any
   required-symbol or benchmark coverage failure remains.
4. After the audit passes, run the unchanged baseline backtest and create the
   phase-4 real-market report.
