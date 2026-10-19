# Roviga operations and recovery

Current state: pilot C blocked, formal gate closed. This document does not claim
the full daily paper-observation edition is finished. No real broker or funds.
Run from the Roviga repository; preserve all existing data and user changes.

## Tested now: readiness, not selection

Existing Python 3.12.14 environment passed `pip check`; no upgrade was performed.
No Streamlit structure exists in this repository, so the existing report writer
now produces a dependency-free local HTML prerequisite view.

```powershell
$env:PYTHONPATH = 'src'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation readiness --snapshot-identity outputs/phase4_pilot_final/20261019/final_reference_identity.json --admission-report outputs/phase4_pilot_final/20261019/pilot_admission.json --report outputs/phase4_pilot_final/20261019/readiness
```

Actually returned DATA_NOT_READY and zero evidence errors. Open the resulting
`outputs/phase4_pilot_final/20261019/readiness/index.html` locally. The automated
browser file-URL preview was blocked by security policy; visual review is still
unverified, not reported as a pass. Do not bypass that restriction.

Each inspection is saved separately under `readiness/records`; the latest HTML
is a view. These are not selected candidates, front-running observations, 20
trading days of history, or investment outcomes. Calendar eligibility, risk and
selection have not been evaluated, so no fake non-trading/no-candidate label is
substituted for missing readiness. A pilot pass cannot unlock this interface.

## Snapshot backup (actually exercised outside repository)

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_acceptance --cache outputs/phase4_pilot_final/20261019/final-reference-v2.sqlite --output C:/Users/Luo-l/Documents/Codex/Roviga-local-backups/20261019-pilot --backup-only
```

This creates a **new timestamp directory**, uses SQLite online backup (including
committed WAL), verifies SHA256 and SQLite integrity, and records identity.
It does not run an audit or a backtest. The tested snapshot is revision 6, hash
`82ea94b71c49c70c1ab47f944f8613506cf9c0923b70d50bd55b595d449b382a`;
tested directory `20261019T025357475006Z`, integrity `ok`.
No overwriting a previous backup. Never copy only a running main `.sqlite` file
and assume its WAL transactions were included.

Pilot evidence closure was copied to `evidence-v1` alongside this backup:
551 files / 100,208,766 bytes, source/destination SHA256 verified. See its
`backup_manifest.json` for included paths and excluded SQLite files. The live
full-market database and older snapshots remain in their original locations;
this is not an offsite backup of them. Copy verified backup/evidence to another
user-chosen storage device/location before claiming disaster recovery.

## Tests and existing commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation --help
.\.venv\Scripts\python.exe -m stock_picker.phase4_acceptance --help
.\.venv\Scripts\python.exe -m stock_picker.sync_guardian --help
```

Full suite: 150 tests, including synthetic backtest fixtures, **not** real
market returns. Focused new tests: 5 factor reconstruction, 6 readiness,
2 backup CLI, 4 formal binding. Existing guards and engine tests also ran.

The generic audit was actually invoked on the isolated candidate via the existing
`RealMarketDataAuditor(SnapshotCache(...))`, saved in `scoped_preaudit`. It failed
and was retained. Missing full-market benchmark/manifest in a deliberately
three-stock database is a scope limitation; four all-row VWAP rejections include
one warmup day outside that generic audit's formal window.

For a future full-market preaudit, this is an existing command (do not repeatedly
rerun it when inputs/evidence have not changed):

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_acceptance --cache data/a_share_201506_present.sqlite --output outputs/phase4_acceptance
```

It makes its own consistent snapshot, does not backtest, and fixes 2026-09-30.
Do not pass an arbitrary `--snapshot` path without its exact matching
`snapshot_identity.json`; hashes and complete identity are mandatory.

## Existing continuous sync: do not duplicate it

Inspected `RovigaPhase4Sync` task and guardian PID 12120. It remained in
`retry_wait`, with no worker at inspection, target 2026-10-02. The status file
contained 5,910 total, 5,900 complete and 10 failed, but this is the live sync
inventory, **not the 919 repair cohort or audited full-market completeness**.
Maximum stored date 2026-10-12 does not prove per-security October completeness.
Report refresh is not a recent successful request/write/progression.

Read `logs/phase4_guardian_state.json`, `phase4_sync_status.json`, existing task
state and actual success records before restarting. Existing CLI supports
`--cache`, `--end`, `--monitor-seconds`, `--retry-seconds`; `--help` was checked.
No new schedule was installed or enabled. An updated October target requires
coordination with the single existing worker; keep it separate from historical
candidate acceptance. This conversation did not start a background pilot job.

## Formal baseline: command exists, currently ineligible

Only after actual full-market AND model validation, the existing runner accepts:

```powershell
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation backtest --cache <verified-frozen-full-market.sqlite> --end 2026-09-30 --formal-binding <verified-formal-binding.json> --report <new-first-baseline-output-directory>
```

Angle-bracket arguments are deliberately **non-executable placeholders**, not
files claimed to exist. This command was not run against real data. No formal
binding exists yet; current data/model evidence cannot authorize it.

Binding schema `roviga-formal-binding-v1` must match snapshot SHA256/revision,
fixed dates, effective selector/risk/backtest/execution settings and all package
source hashes. Referenced full-market admission, execution validation and frozen
configuration files have their own hashes. A preaudit, pilot pass, old generic
audit or edited `passed` flag is insufficient. Snapshot/code/config changes
invalidate reuse. This guard validates identities, not the truth of absent
external evidence. No helper here manufactures an approval envelope.

OPEN remains the actual default, not an approved final fill contract. Do not use
whole-day locks/volume as if they were known at the open. Quantity, partial-fill,
cash/share entitlement/stop treatment and dated costs need completion before
first returns. Do not silently switch modes or invent parameters.

## Another computer

1. Clone the existing GitHub Roviga repository; verify local HEAD and live remote
   main. Do not create another project or hard-reset a dirty checkout.
2. Install a compatible Python 3.12 environment, create `.venv`, install with
   `python -m pip install -r requirements-market.txt`, then `pip check` and tests.
   These installation commands are established repository instructions; a fresh
   installation on another computer was NOT tested in this turn.
3. Transfer the verified candidate backup **and evidence** separately from Git.
   Git/account login does not move databases. Verify `snapshot_identity.json`,
   `backup_manifest.json` hashes and integrity before use. Never overwrite the
   live sync database with a three-stock candidate.
4. Evidence contains original absolute paths. Restore the original relative tree
   under the original workspace root, or explicitly version a path remapping and
   revalidate referenced bytes. Do not pretend copying a database alone restores
   all replay inputs. Keep code versions/line endings matching recorded hashes;
   a new program version requires new evidence bindings.
5. Run the readiness command with the restored exact identities. Reuse an existing
   authorized sync task only after checking it; never duplicate schedulers.

Open-source exports/permissions still required are itemized locally in
`outputs/phase4_pilot_final/20261019/data_requirements.json`. No password or Token
in chat; no purchased-service availability guarantee. Until these and the model
decision are resolved, the correct visible state remains DATA_NOT_READY.
