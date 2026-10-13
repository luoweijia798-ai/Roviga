# Daily Stock Picker

A dependency-free Python project for deterministic daily stock selection,
risk sizing, paper execution, and post-signal tracking.

> This is a research and simulation tool, not investment advice or a live
> brokerage connection.

## Current capabilities

### Phase 1 — one stock per day

- Replaceable `MarketDataSource` boundary.
- In-memory data source for examples and tests.
- Eligibility filters for invalid, suspended, and illiquid rows.
- Configurable momentum/liquidity score.
- Exactly one result per requested day, with symbol order as the stable tie-break.
- An explicit `NoEligibleStockError` when no stock qualifies.

The original phase-one selector in `selector.py` is unchanged in phases 2 and 3.

### Phase 2 — risk and paper trading

- Configurable risk per trade (default 1% of equity).
- Position sizing from entry price and long stop price.
- Per-symbol and total-exposure caps.
- Risk is reduced after three consecutive losses and signals are paused after five.
- Daily, weekly, and peak-to-current drawdown circuit breakers.
- Serializable and human-readable live risk status.
- Configurable virtual starting cash.
- Paper buys and sells with commission, sell-side stamp tax, and slippage.
- T+1 sell availability and upper/lower price-limit lock simulation.
- In-memory or append-only JSON Lines trade ledger.
- One candidate record per signal day, planned and actual fill records, 1/3/5-day
  returns, maximum gain/loss, and stop-loss/take-profit state.
- `PaperTradingWorkflow` connects an existing phase-one `Selection` to sizing,
  execution, and tracking without changing selection logic.

### Phase 3 — causal historical backtesting

- Event-driven daily simulation: T close signal, T+1 open or VWAP execution.
- A monotonic simulated clock rejects every future-date data request.
- Signals receive only current-close and prior data through the original selector API.
- Position sizing for open execution uses the T+1 open; VWAP mode fixes quantity
  from the T close before applying the next session's simulated VWAP fill.
- T+1 exits, price-limit locks, costs, slippage, stop loss, take profit, and
  maximum holding period.
- Total trades, win rate, payoff ratio, average win/loss, maximum losing streak,
  drawdown, annualized return, and monthly returns.
- CSI 300 and CSI 1000 benchmark comparison when those series are supplied.
- Bull, bear, and sideways results classified only from trailing benchmark data.
- Independent training, validation, and out-of-sample windows with frozen settings.
- JSON/CSV/SVG reports containing the equity curve, events, trades and reasons,
  monthly returns, and the largest winning and losing trades.

### Phase 4, part 1 — real A-share data foundation

Current synchronization status and the safe continuation point are recorded in
[`PHASE4_STATUS.md`](PHASE4_STATUS.md).

- A fixed research start date of `2015-06-01`; the end date defaults to today.
- AkShare-first adapter and an optional token-based Tushare adapter.
- Daily OHLC, volume, amount, raw execution prices, causal adjusted signal
  prices, suspension state, price-limit levels, and one-price limit locks.
- Current and delisted stock metadata to reduce survivorship bias.
- Point-in-time industry history where the source exposes effective/update dates.
- Current industry/concept snapshots are timestamped at download time and are
  never exposed to earlier simulated dates.
- A resumable SQLite cache rather than loading a decade of full-market rows into
  memory.
- A guarded SQLite portal with the same interface as the phase-3 in-memory data.
- A foundation runner that executes the unchanged selector and risk modules from
  `2015-06-01` and writes data-manifest/coverage audit files with the report.

Phase 4 market filtering, parameter sensitivity, five-market-period analysis,
and the final strategy report are deliberately outside part 1.

## Project layout

```text
src/stock_picker/
  data.py       market-data interface and in-memory adapter
  models.py     phase-one market and selection models
  selector.py   unchanged phase-one selector
  risk.py       risk state, circuit breakers, and sizing
  trading.py    virtual account, broker, costs, T+1, and ledgers
  tracking.py   signal/fill and 1/3/5-day performance tracking
  workflow.py   composition layer from candidate to simulated fill
  historical.py guarded OHLCV and benchmark history portal
  backtest.py   event engine and causal execution rules
  analytics.py performance, regimes, benchmarks, and walk-forward validation
  reporting.py portable JSON, CSV, and SVG reports
  backtest_demo.py deterministic synthetic end-to-end demonstration
  real_market.py AkShare/Tushare adapters and SQLite point-in-time cache
  phase4_foundation.py real-data sync/status/foundation-backtest CLI
tests/          unit and integration tests
```

## Run the minimal selection example

From the project directory on PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m stock_picker.example
```

On macOS or Linux:

```bash
PYTHONPATH=src python -m stock_picker.example
```

You can also create a virtual environment and install the project locally:

```bash
python -m venv .venv
python -m pip install -e .
daily-stock-picker
```

No third-party runtime packages are required.

## Risk and paper-trading example

```python
from datetime import date

from stock_picker import (
    DailyTracker,
    PaperAccount,
    PaperBroker,
    PaperTradingWorkflow,
    RiskConfig,
    RiskManager,
    Selection,
)

today = date(2026, 8, 17)
account = PaperAccount(initial_cash=1_000_000)
risk = RiskManager(
    initial_equity=account.initial_cash,
    as_of=today,
    config=RiskConfig(risk_per_trade=0.005),
)
broker = PaperBroker(account, risk_manager=risk)
tracker = DailyTracker()
workflow = PaperTradingWorkflow(account, broker, risk, tracker)

# `candidate` normally comes directly from StockSelector.select_one(today).
candidate = Selection(today, "AAA", score=0.12, momentum=0.10, volume_rank=1.0)
result = workflow.submit_candidate(
    candidate,
    entry_price=10.00,
    stop_price=9.50,
    take_profit_price=11.50,
)

print(result.risk_status.display())
print(result.sizing)
print(result.trade)
```

Call `risk.start_day(trading_date, opening_equity)` at each trading day's start.
During the day, request `risk.status(...)` whenever a fresh status snapshot is
needed. A broker configured with the same risk manager updates the consecutive
loss count after each simulated sell.

For persistent trade history, construct the broker with:

```python
from stock_picker import JsonLinesTradeLedger

ledger = JsonLinesTradeLedger("data/trades.jsonl")
broker = PaperBroker(account, ledger=ledger, risk_manager=risk)
```

## Causality contract

The historical portal starts without a clock. The backtester advances it exactly
once per simulated session, and the portal raises `FutureDataError` for any date
later than that clock. At the T close event, `StockSelector` receives a `DailyBar`
snapshot containing T close/volume and the prior close. The resulting order is
queued for T+1; no T+1 high, low, close, or VWAP can alter the signal.

Open-mode quantity is calculated when the T+1 open becomes available. In VWAP
mode the quantity is fixed using the known T close and the next day's VWAP is used
only as the execution benchmark. A position acquired on T+1 cannot exit until a
later session. If stop and take-profit are both touched in one daily bar, the
backtester conservatively gives stop loss priority.

## Run the backtest demonstration

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m stock_picker.backtest_demo
```

macOS or Linux:

```bash
PYTHONPATH=src python -m stock_picker.backtest_demo
```

This creates four report directories under `outputs/phase3_demo`: full period,
training, validation, and out-of-sample. Each contains:

```text
summary.json         required statistics, benchmarks, regimes, extreme trades
equity_curve.csv     daily equity, cash, exposure, regime, and benchmark closes
equity_curve.svg     portable equity chart
trades.csv           completed trades and entry/exit reasons
events.csv           signals, fills, rejections, exits, and reasons
monthly_returns.csv  monthly strategy returns
```

The bundled demonstration uses deterministic synthetic data only. Its output is
for testing the framework and report pipeline, not for evaluating investment
performance. For real testing, create `HistoricalBar` rows from point-in-time
adjusted OHLCV data and `BenchmarkPoint` rows named `CSI300` and `CSI1000`, then
pass them to `InMemoryHistoricalData`. Suspension and daily price-limit flags must
reflect what was known for each historical session.

## Walk-forward validation

`WalkForwardValidator` accepts a non-overlapping `WalkForwardSplit` containing
training, validation, and out-of-sample date windows. Each period starts with a
fresh account and risk state, while selector, risk, and execution settings remain
frozen. Parameter selection should occur using training/validation output only;
the out-of-sample period should be run once after settings are locked.

## Real A-share data setup (phase 4, part 1)

Create an isolated Python 3.11+ environment and install the pinned optional
market dependency:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-market.txt
```

`requirements-market.txt` declares the supported stable AkShare range and loads
`requirements-market-constraints.txt`, which pins the complete dependency graph
verified by the project. The current lock was validated with Python 3.12.13 and
AkShare 1.18.91; `python -m pip check` must report no broken requirements.

Sync AkShare data from 2015-06-01 through today. The SQLite cache is updated per
symbol, so a stopped download can be resumed with the same command:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation sync --provider akshare
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation status
```

The AkShare path rate-limits every provider request, retries transient failures
with exponential backoff, and downloads each symbol in bounded date segments.
Every completed segment is committed immediately. A `symbol_sync_status` ledger
records the provider, underlying endpoint, attempt count, last completed date,
and failure reason per stock; rerunning `sync` skips symbols already complete
through the requested end date. Defaults can be tuned without changing code:

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation sync `
  --provider akshare --request-interval 0.5 --max-attempts 5 `
  --retry-delay 2 --segment-days 366
```

AkShare/Eastmoney remains the primary source. If an Eastmoney history request
still fails after retries, the adapter attempts AkShare's Sina endpoint and
records the actual source used. Tushare remains an optional authenticated path
for exact limits and coverage that the public endpoints cannot supply.

After synchronization, generate the independent data audit. This command does
not run a strategy or calculate returns:

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation audit
```

The JSON audit reports stock and exchange counts, database and benchmark date
coverage, per-stock missing trading-session ranges, invalid OHLCV rows, source
coverage, and incomplete/failed symbols. A failed audit exits with status 2.
The `backtest` command refuses to run unless the saved audit passed and matches
the current sync manifest, so any subsequent data update requires a new audit.

For unattended synchronization, run the monitor every 30 minutes (for example,
through the Codex task scheduler):

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation monitor `
  --status-output phase4_sync_status.json `
  --audit-output phase4_data_audit_report
```

The compact status file records total/completed/failed/unavailable/unprocessed
stock counts, the current symbol and date checkpoint, date coverage, average
trading-day count, and the ten most frequent recent errors. The monitor runs the
audit automatically only after every inventory symbol has a settled status and
no symbol remains running or interrupted.

`phase4_data_audit_report` contains `audit_report.json`,
`missing_stocks.json`, `missing_dates.json`, and `data_anomalies.json`. Checks
cover current/historical/delisted/BSE inventory, per-symbol session counts,
OHLC logic, volume/amount consistency, VWAP availability, price-limit and lock
consistency, benchmarks, and duplicate daily rows. These runtime reports are
ignored by Git.

Industry/concept snapshots add many provider requests. They are enabled by
default; use `--skip-classifications` only when downloading price data first,
then run a later full sync to add classifications.

Tushare is optional and requires its package, an account with the relevant API
permissions, and a token supplied only through the environment:

```powershell
$env:TUSHARE_TOKEN = "your-token"
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation sync --provider tushare
```

Only after `audit` passes, run the original-strategy foundation backtest:

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation backtest
```

The default cache is `data/a_share_201506_present.sqlite`; the default output is
`phase4_real_market_report/foundation`. Both are ignored by Git because market
data and generated reports are reproducible runtime artifacts.

Data-quality rules:

- AkShare raw prices drive simulated fills. HFQ prices drive signal features so
  later corporate actions do not rewrite earlier signal history.
- AkShare limit prices are inferred from the prior raw close and board rules when
  no exact point-in-time series is available. Tushare `stk_limit` is the optional
  exact-limit path.
- Current concept membership is not historical membership. Its `available_from`
  date prevents accidental use before download time.
- No financial statement fields are fetched or exposed in part 1, so future
  publication data cannot enter the strategy.
- A sync manifest records provider, requested range, adjustment method, failures,
  and warnings. Do not treat a report as real-market evidence until the manifest
  and coverage audit show the intended period and universe.

## Run all tests

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

macOS or Linux:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Frozen Phase 4 acceptance (2026-10-12)

The first historical admission range is **2015-06-01 through 2026-09-30**.
This does not cancel continuous real-data updates. October increments use the
existing single downloader and checkpoints; the audit range never follows today.
An optional ignored `data/a_share_201506_present.sync-plan.json` declares
`historical_acceptance_end` and `incremental_target_end` for that downloader.

For the Phase 4 semantic-repair snapshot, run a fresh read-only preaudit and
produce per-security blockers, gap accounting, source/root distributions, and
baseline dependency review (no strategy or return calculation):

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m stock_picker.data_semantics `
  --snapshot <frozen-snapshot.sqlite> `
  --source-review <source-review.json> `
  --output <ignored-output-directory>
```

The output contains `final_reaudit.txt/json`, `preaudit/`, and an `admission/`
bundle with the blocker details. It is runtime evidence and stays under ignored
`outputs/`; never commit the snapshot or generated reports. A report with failed
checks is still emitted and does not release the formal-backtest gate.

Run an immediate preaudit even while retained symbols are failed:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m stock_picker.phase4_acceptance
```

The command pins a SQLite WAL read transaction, uses online backup (including
committed WAL pages), hashes the independent snapshot, and runs the existing
auditor with read-only connections. It never stops the downloader, edits live
market rows, saves a passing audit to production, or calls a strategy. Frequent
production writes cannot restart this pinned backup. A failed preaudit still
writes a report; it is a data acceptance result, not an unhandled exception.

Each ignored `outputs/phase4_acceptance/<timestamp>/` contains the frozen
snapshot, identity/revision, `preaudit/` bundle, `phase5a_admission_report.json`,
its readable `.txt` summary, `blockers.json`, and `outside_interval_review.json`.
Every blocker has a security/index scope, dates, reason, and treatment plan.
Snapshot hashes are verified before reuse. Reports are never Git artifacts.

Source review is separate from admission and writes evidence, not market bars:

```powershell
.\.venv\Scripts\python.exe -m stock_picker.source_review --snapshot <snapshot-path> --output <source-review-json>
.\.venv\Scripts\python.exe -m stock_picker.source_review --snapshot <snapshot-path> --output <source-review-json> --validate
.\.venv\Scripts\python.exe -m stock_picker.phase4_acceptance --snapshot <snapshot-path> --evidence <source-review-json> --reuse-audit
```

The independent real Sina session calendar is compared with **each** benchmark
and each applicable security. Unknown listing dates and unexplained suspensions
remain provisional blockers, never fabricated sessions. Fresh exchange metadata
is required to corroborate a whole-range exemption. Exempt records are retained
and counted separately, not as complete market history. Missing historical
universe/alias events, classifications, HFQ factor availability and exact limit
history also prevent Phase 5A admission, even if sync counters reach 100%.

AkShare/Eastmoney stays primary. The bounded Tencent BSE fallback bypasses the
unsupported AkShare start-year helper, validates raw/HFQ dates, turnover units,
OHLC/VWAP and persisted raw/HFQ overlap before switching sources. Empty BSE
responses are failures, not proof of no data. No unverified old-code mapping is
guessed; official alias evidence is still required for historical membership.

One exact post-delisting weekend echo of the final real OHLCV/amount can be
isolated only with exchange delisting metadata. The original row and comparison
evidence stay in `provider_quarantine`, the real final session is retained, and
unreviewed quarantine records **close** the formal audit gate. Other conflicts
continue failing; delist dates are never moved to fit provider artifacts.

`sync_retry_policy` retains failed states/checkpoints: persistent BSE failures
back off for 1/2 hours, then require source review after three attempts; date
conflicts require review immediately. Changed verified metadata/range can reopen
the policy. Clearing a reviewed retry decision is not approval of market data.
Repeated schema/permission errors are not retried as transient transport errors.

No baseline returns, parameter optimization, selector or risk changes are part
of this workflow. A preaudit is never a production backtest authorization.

## Moving to another computer

Clone or copy the repository, install Python 3.10 or newer, then run the tests
above. Runtime state such as a JSON Lines trade ledger can be copied separately;
generated data is intentionally not committed by default.
