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

The original phase-one selector in `selector.py` is unchanged in phase 2.

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

## Moving to another computer

Clone or copy the repository, install Python 3.10 or newer, then run the tests
above. Runtime state such as a JSON Lines trade ledger can be copied separately;
generated data is intentionally not committed by default.
