# Roviga master execution plan

Mandate: user master brief, 2026-10-19 (Asia/Shanghai). Continue until the
usable daily paper-observation edition, or precise unavoidable blockers.
Old batch-end pauses/three-only/no-919 rules are superseded CONDITIONALLY.
No real broker or funds. Do not treat completion of this plan as completion
of its implementation.

## Latest user decision: data and readiness delivery only

2026-10-19: the user explicitly chose “先保持模型不变，仅交付数据与未就绪界面”.
This narrows the current execution scope. Keep the actual OPEN model unchanged;
do not change fills, fees, strategy or risk behavior. No return backtest, 919
resume or migration expansion is authorized by this continuation. The broader
stages below remain a roadmap, not automatic current work. No model decision
is awaiting an answer: the user selected a limited deliverable, not validation
or waiver of OPEN's unresolved causal/capacity/accounting limitations.

Continue read-only data verification and readiness delivery. Preserve candidate
revision 6 and its existing evidence. Remaining four VWAP dates and three
turnover-scope intervals still need source material; duplicate requests without
new evidence are not useful progress. Runtime reports stay local and ignored.

## Verified checkpoint

- Initial local HEAD and live remote main:
  `59b06da1393459931385ad4bf836acfb35353961`; clean worktree.
- Latest pilot input: `outputs/phase4_pilot_evidence/20261018/final-v2.sqlite`,
  SHA256 `fdcac9039118d4b374a8c6c108ed9ac719cb3f7108bccfd2ef1836ab0ffc8100`,
  revision 4. Read its full identity record, never infer filenames from a prefix.
- Prior report: `outputs/phase4_pilot_evidence/20261018/pilot_acceptance_report.txt`.
- Historical formal interval 2015-06-01..2026-09-30; later updates separate.
- No formal configuration artifact frozen yet. `phase4_foundation.main` invokes
  `Phase4FoundationRunner` without an override; it constructs `BacktestConfig()`.
  Defaults are executable behavior, not proof of an approved final config.
- Pilot still blocked: 14 actual cumulative-factor numerical provenance cases,
  52 stock-date limit pairs (104 fields), 4 strict VWAP cases, trade-scope input
  definitions; precise overlap/causal/model dependencies are being reconciled.

## Dependency-ordered work

| Stage | State | Acceptance/next dependency |
| --- | --- | --- |
| Restore/config call-path audit | In progress | Record effective settings, hashes, actual use; consolidate unresolved core decisions |
| Three-stock pilot | In progress | 14 factor classifications, 52 limit pairs, 4 VWAP + volume scope, layered acceptance and replay |
| Controlled 20, then 100 | Waiting on pilot | Evidence-based representative sample, each independently passes same checks |
| Remaining existing queues | Waiting on controlled batches | Refresh unique queue membership; resume verified segments, no full redownload |
| Full-market frozen admission | Waiting on data | Point-in-time pool, warmup, calendar, indices, quality, actual execution fields; hashes bound to config/code/snapshot |
| First baseline Phase 5A | Waiting on admission | No optimization; causal declared fills/costs/actions; complete first results, including losses |
| Daily paper observation | Engineering can proceed; operational gate closed | At most one candidate; explicit not-ready/risk/no-trade states, append-only records, no real orders |
| UI/restore/backup | Independent engineering available | Verify local readiness workflow and actual CLIs; no fake history/results; no background claim |
| Phase 5B stress | After baseline | Audited-window analysis first; old/global crises optional separate work |
| Rotation experiments | After baseline | Separate configuration, historical classifications, never replace baseline automatically |
| Cross-market | Roadmap only | No connection or implementation in this mandate |

## Freeze before any real return result

Freeze actual pool rules, selector and risk source hashes, ranking/thresholds,
capital/execution/cost/slippage/holding settings, split dates and metric semantics.
Use existing explicit settings where unambiguous. User fallback split is research
2015-06-01..2020-12-31, validation 2021-01-01..2023-12-31, holdout
2024-01-01..2026-09-30, unless a pre-existing pre-results split is found.
Known previously inspected periods must not be relabelled untouched holdout.
Current runtime model and source-contract limitations must not be hidden by a
new configuration file. Snapshot/config/code changes invalidate admission.

## Execution and recovery

Reuse `phase4_foundation`, `phase4_acceptance`, `data_semantics`, `semantic_review`
and the existing sync guardian. No second scheduler or audit framework.
Runtime work/evidence for this mandate stays under ignored
`outputs/phase4_pilot_final/20261019/`; update this plan with completed steps,
exact identities, concrete blocking materials and the next verified command.

Verified existing safe entry (prints CLI help, does not run a strategy):

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation --help
```

## 2026-10-19 completed execution (supersedes initial checkpoint counts)

- All 52 remaining legal-limit pairs / 104 fields repaired; 4,857 actual
  quote-date rule links verified. Intermediate revision-5 candidate preserved:
  `96949ab4140d61f342d402b4205410cdedc53a73def0433463f6e503629ff886`.
- Same fixed-anchor reference-price formula, independently evidenced exact
  step products in isolated v2, documented in
  `PHASE4_REFERENCE_RECONSTRUCTION.md`. No supplier-factor fit or strategy tuning.
  15 events; 3,105 changed signal-date rows; raw execution fields unchanged.
  The 14 supplier precision/revision cases remain unresolved in v1/control;
  supplier cumulative factors are demonstrably absent from v2's input chain.
- Latest revision-6 identity:
  `outputs/phase4_pilot_final/20261019/final_reference_identity.json`;
  SHA256 `82ea94b71c49c70c1ab47f944f8613506cf9c0923b70d50bd55b595d449b382a`.
  Twelve segmentation / 39 cutoff checks, 19,428 exact independent precision
  comparisons, independent replay and zero repeat writes passed.
- A coverage/replay passes; B is supported for the declared v2 historical
  reconstruction (not a contemporaneous source archive claim). C remains
  blocked: four VWAP reader errors, three turnover-scope intervals, causal OPEN
  fill/capacity and corporate-action account handling. Exact requirements in
  local `data_requirements.json`. No 20/100/919 migration is yet eligible.
- Scoped preaudit completed and failed as recorded; not skipped. Three-stock
  candidates intentionally lack full-market indices/manifest; do not turn those
  scope limitations into new pilot evidence demands or waive them for full-market.
- Independent engineering: read-only readiness HTML and immutable check records,
  snapshot/config/code/evidence-bound formal runner guard, online backup-only CLI.
  Actual readiness command returned DATA_NOT_READY without selector or broker.
  Browser file preview blocked by tool security policy; no workaround, visual
  validation not completed. This is NOT the completed daily simulation edition.
- Verification: 17 new focused tests; full suite 150 passed; Python 3.12.14,
  pip check clean. Synthetic tests are separate from real candidate validation.
- Existing `RovigaPhase4Sync` task/guardian 12120 retained, current phase
  `retry_wait`, no worker at inspection. Status refresh is NOT download progress.
  Its target remained 2026-10-02; do not call that current incremental coverage.
  No duplicate task or new background pilot job created.
- Verified SQLite online backup outside repository:
  `C:/Users/Luo-l/Documents/Codex/Roviga-local-backups/20261019-pilot/20261019T025357475006Z/`.
  Integrity `ok`, identical candidate hash. Evidence-v1: 551 files / 100,208,766
  bytes independently SHA256 checked. Local only, no offsite claim.

## Next actionable recovery and affected-path blockers

See `OPERATIONS.md` for tested entry points. Safe current continuation:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m stock_picker.phase4_foundation readiness --snapshot-identity outputs/phase4_pilot_final/20261019/final_reference_identity.json --admission-report outputs/phase4_pilot_final/20261019/pilot_admission.json --data-requirements outputs/phase4_pilot_final/20261019/data_requirements.json --report outputs/phase4_pilot_final/20261019/readiness
```

Needed source evidence: original same-trade-scope raw OHLC/quantity/amount and
publisher precision for 000035 2015-07-17 / 2021-11-12, 000033 2015-04-29,
000034 2015-08-28; endpoint historical coverage definitions for all three
applicable intervals. Existing KLC original decoder, Bao overlaps and official
exchange definitions do not establish KLC publishing quantization/scope.
Do not re-request the same prices expecting a contract to appear.

The consolidated execution question has been answered: keep the model untouched
and deliver data/readiness only. Do not request the same choice again or infer
permission to switch mode or invent capacity/partial-fill parameters. Cash/share/
payment entitlements across the 15 events and dated costs remain unresolved
future execution prerequisites, outside the current repair authorization.

Independent engineering above is completed to its stated boundary. The remaining
operational candidate/fill/tracking paths depend on the unresolved source/model
contract, not merely another batch/report. No formal run or background promise.

## Pause criteria

Pause only affected paths for login/paid authorization, specifically exhausted
legal source evidence, core behavior changes, destructive/conflicting work or
actual execution limits. Finish independent safe work. Save exact recovery state;
do not replace evidence with repeated waiting or claim background progress without
a separately created and verified task.
