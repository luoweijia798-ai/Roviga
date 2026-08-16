# Phase 4 checkpoint status

Checkpoint date: 2026-08-17

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

## Data status (not committed)

- `data/a_share_201506_present.sqlite` contains the discovered stock metadata,
  including current and delisted records, but the full daily-bar sync is not
  complete.
- A small ignored smoke-test cache proved that real 2015-06-01 onward daily
  bars can be written to SQLite. It is diagnostic data only.
- All SQLite files, virtual environments, generated reports, and temporary
  outputs remain excluded by `.gitignore`.
- No API key, token, credential, or real-market return result is stored in this
  checkpoint.

## Known blocker

- Eastmoney began closing long-history and repeated requests after initial
  successful connectivity checks, consistent with provider throttling or an
  incompatible local proxy path.
- The Sina fallback works for ordinary listed Shanghai/Shenzhen stocks but did
  not cover several early delisted symbols and a Beijing Stock Exchange smoke
  test. It therefore cannot yet be treated as a complete full-market source.
- A Windows multi-thread experiment was rejected because AkShare's embedded
  JavaScript runtime crashed under threads. The production sync remains
  single-threaded and resumable.
- Because universe and benchmark coverage have not passed audit, no real-market
  backtest or performance conclusion has been generated.

## Next step

1. Add a rate-limited, retrying Eastmoney path (or configure the optional exact
   Tushare adapter locally) that covers delisted and Beijing listings.
2. Resume the ignored SQLite cache and complete stock bars, amount/volume,
   price limits, stock metadata, classifications, CSI 300, and CSI 1000.
3. Generate and review the data audit. Do not run the real backtest while any
   required-symbol or benchmark coverage failure remains.
4. After the audit passes, run the unchanged baseline backtest and create the
   phase-4 real-market report.
