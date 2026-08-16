# Daily Stock Picker — Phase 1

This phase contains a dependency-free Python core that:

- reads a daily market snapshot through a replaceable data interface;
- removes untradable or invalid rows;
- ranks the remaining symbols with a configurable momentum/liquidity score;
- returns exactly one deterministic selection for a requested trading day.

## Run the minimal example

From this directory:

```powershell
python -m stock_picker.example
```

If the package has not been installed, point Python at `src` first:

```powershell
$env:PYTHONPATH = "src"
python -m stock_picker.example
```

## Run tests

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The in-memory source is intentionally small. A later phase can add a real
market-data adapter without changing the selector.

