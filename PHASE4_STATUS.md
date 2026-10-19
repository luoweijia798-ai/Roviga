# Phase 4 checkpoint status

Checkpoint date: 2026-10-19

## Master mandate / pilot reconstruction and operational safeguards (2026-10-19)

The user's master mandate now governs continuation; older batch-end pause and
three-only/no-queue-resume statements below describe historical checkpoints,
not unconditional current restrictions. See [master plan](docs/MASTER_EXECUTION_PLAN.md).
Expand only after actual pilot admission, then 20/100/remaining, and run the
first real baseline only after fixed full-market admission. Neither is met yet.

- Started at local/live remote `59b06da1393459931385ad4bf836acfb35353961`, clean.
  Kept all old snapshots, raw sources and the live-sync database untouched.
- Closed **52 legal-limit dates / 104 fields** using retrieved official historical
  rule archives, dated status/reference fields and existing issuer originals.
  All 4,857 quote dates now link to the applicable rule version; 3,321 missing
  intermediate links are no longer unresolved. No raw price/turnover/lock changes.
  Revision 5: `96949ab4140d61f342d402b4205410cdedc53a73def0433463f6e503629ff886`.
- Local 40-vs-80 Decimal recomputation found zero output discrepancies across
  19,428 signal fields. The 14 old supplier numerical residuals were not caused
  by local premature rounding. Supplier precision/revisions remain unknown.
- Built isolated reference-input v2 under the same fixed-anchor economic formula:
  exact products of evidenced previous-actual-close / effective reference-price
  steps, not captured rounded provider cumulative factors. All 15 issuer events
  and every intervening reference transition reconcile. No fitted ratio, mixed
  HFQ seam, future event or altered strategy parameter. See
  [explicit v2 rule and limits](docs/PHASE4_REFERENCE_RECONSTRUCTION.md).
  The old 14 cases remain v1/comparison limitations, not falsely certified.
- Latest candidate revision **6**:
  `82ea94b71c49c70c1ab47f944f8613506cf9c0923b70d50bd55b595d449b382a`,
  `outputs/phase4_pilot_final/20261019/final-reference-v2.sqlite`.
  **3,105** signal-date rows changed: 1,044 / 30 / 2,031 for 000035 / 000033 /
  000034, plus two metadata keys. Largest signal-price differences from v1:
  0.00000304 / 0.00000304 / 0.00001141. Raw execution data and 1,242 halt
  records unchanged. Twelve segmentation and 39 cutoff checks, 19,428 exact
  100-digit independent comparisons, repeat zero writes and replay equality pass.
- A coverage/replay passes; B supported within the declared v2 reconstruction,
  with current retrieval and historical announcement dates distinct, no claimed
  historical download archive. **C still blocked for all three**: four strict
  VWAP cases and three historical turnover-scope contracts, plus existing
  corporate-action accounting/causal OPEN fill-model limitations. No generic
  tolerance, VWAP clamp, fake source precision or formal usability claim.
- Actual default configuration inventoried: OPEN, initial cash 1,000,000,
  unchanged selector/risk/cost settings. No formal configuration artifact yet.
  OPEN currently uses a full-session limit flag; opening quantity/partial-fill
  assumptions and dated account/cost handling need an explicit model contract.
  This is not evidence that every execution mode must pass simultaneously.
- Hardened the existing formal runner: read-only input inspection; require
  snapshot/config/code hashes and eligible full-market/config/model evidence.
  Revalidate before publishing output. An old generic passing audit or manual
  Boolean cannot authorize this run. No formal binding has been issued.
- Added readiness to the existing CLI/report writer: real invocation produced
  DATA_NOT_READY, no selector/broker call, append-only inspection records, local
  HTML. It is a prerequisite view, **not** the finished operational daily-candidate
  system. Automatic browser preview was security-blocked; visual QA uncompleted.
- Added backup-only mode to the existing snapshot tool. Outside-repo SQLite
  online backup verified identical SHA256 and integrity `ok`; 551 evidence
  files (100,208,766 bytes) copied and hash checked. These are local backups,
  not offsite backup or a migrated full-market database.
- Tests: **17 new focused tests pass; full suite 150 passed**. Actual candidate
  checks/replay are separate; scoped preaudit ran and failure report was retained.
  Python 3.12.14, dependency check clean. No real returns/orders were generated.
- Existing sync task/guardian retained. At inspection guardian 12120 was in
  retry_wait, no active worker; refresh timestamps are not successful requests.
  No duplicate scheduler and no newly created background repair job.
- Reports/precise source requirements locally under
  `outputs/phase4_pilot_final/20261019/`. [Operations/recovery](docs/OPERATIONS.md)
  distinguishes executed commands from gated future commands. Awaiting the
  concrete source/model dependencies; no 20/100/919 expansion or real baseline.

## Three-security remaining-evidence pilot review (2026-10-18)

- Started from verified clean HEAD
  `b93c49dcead387f6ad51af4fd5b2088b842d71a8`. Only 000035/000033/000034;
  formal interval **2015-06-01..2026-09-30** plus existing actual warmup.
  No full-market download, 919-queue resume, strategy/risk edits or backtest.
- Preserved the prior revision-2 snapshot
  `8fbf51d2179d6442f73d51fff26e2d4f7f0a4df9a262dff15152082ca253ff1b`.
  New isolated metadata-only final candidate, revision 4:
  `fdcac9039118d4b374a8c6c108ed9ac719cb3f7108bccfd2ef1836ab0ffc8100`
  (`outputs/phase4_pilot_evidence/20261018/final-v2.sqlite`). Intermediate
  revision 3, original inputs and all evidence remain separate and preserved.
- **15/15** actual post-anchor factor events now have issuer originals dated
  before use; **15/15** reference prices reconcile, including excluded-buyback
  dividend bases and 000033's explicitly announced 7.96 reference. Missing
  event-announcement count is **0**, not a claim of complete factor certification.
  One factor step is exact; **14** captured cumulative-factor steps have small
  nonzero arithmetic residuals (maximum relative 3.51073452e-7). Provider
  internal precision/rounding and known revision semantics are still unverified.
  The previous half-last-digit assumption is not a provider rounding guarantee.
  Missing historical download logs alone do not establish look-ahead; reliable
  dated announcements can support reconstruction. No frozen factor/price rule
  was changed. Sina HFQ comparison-only inputs are not primary-signal blockers.
- Three bounded historical status/reference queries returned **6,099** unique
  applicable sessions, no missing/extra dates or status conflicts:
  **4,857** actual quotes + **1,242** documented halt days. No bars were created.
- Reused the compare-and-set/replay tool to repair **17** metadata rows:
  **10** unknown lock rows resolved from dated status/reference and rules;
  **5** missed one-price limit flags corrected; **2** ex-reference price bounds
  corrected. 000033's 2017 delisting period uses its documented 10% arrangement,
  not today's no-limit first-delisting-session rule. All OHLC, volume, amount,
  VWAP and signal prices remain exactly unchanged. A legal boundary/lock flag
  is not proof that an order would fill.
- Added a data-reader guard: unknown nullable lock flags now raise instead of
  silently becoming `False`. No execution mode or quality tolerance changed.
  This protects old research candidates as well as new data reads.
- **4 VWAP cases remain blocked**: 000035/2015-07-17 and 2021-11-12,
  000033/2015-04-29, 000034/2015-08-28. Same-response decoder tracing reproduced
  all 4,857 original decoded rows, but decoder quantization is not evidence of
  publisher rounding or matching auction/block/off-session scope. No error
  interval was invented; no clamp, raw-value replacement or check bypass.
  OPEN does not execute at VWAP, but `HistoricalBar` still validates it
  unconditionally; volume remains a selector input. The OPEN configuration
  basis is the prior frozen report and unchanged default, not an invented run.
- Remaining legal-bound metadata: **52 dates = 41 missing-bound dates + 11
  ex-reference discrepancies**. Their lock flags currently agree with the
  reference hypothesis; these are not 52 proven erroneous fills. Intermediate
  rule-version links remain unfinished for **3,321 stock-days**, overlapping
  those dates, not additive. Exact lists and needed rule editions are local.
  Provider trading-scope definitions remain open for three covered intervals;
  **541** cross-source turnover-difference dates remain unchanged. The previous
  corporate-action position/share/cash/stop reconciliation limitation is retained,
  not silently dropped or treated as an unused enhancement.
- Validation: **3 new targeted tests + 8 existing scoped-price tests passed**;
  **full suite 133 passed**. Both metadata manifests independently replayed
  exactly and repeated with **0 writes**. All 4,857 final bars were checked;
  only the same four VWAP cases reject construction. Price/volume/signal fields
  and all 1,242 halt records match the preserved prior candidate. Prior price
  segmentation/cutoff checks remain applicable because their inputs/rule hashes
  did not change; this turn did not rebuild those price sequences.
- Local-only delivery: `pilot_acceptance_report.txt`, `initial_blockers.json`,
  `blockers.json`, `pilot_admission.json`, per-event/4-VWAP/52-date evidence,
  manifests and validation under `outputs/phase4_pilot_evidence/20261018/`.
  **A coverage/reproducibility passes; B remains partial; C remains blocked**
  for all three. No formal usability or migration expansion approved. The
  326-security/528-boundary investigation list remains untouched and separate.
  Git delivery/live remote verification is recorded locally in `delivery.json`.
  Stop after this review; no background run or automatic next phase.

## Three-security independent price version (2026-10-18, research only)

- Started at actual HEAD `8240894d8f9b9f9142fc470769d08f21ebb4e3a7`,
  with a clean worktree. Existing attribution and exact input identity were
  read; no reset, baseline replacement or full-market migration occurred.
- Preserved input snapshot:
  `481cae3da8aa651657b99b85e9df7f46127dc8c96fd9d05ae7b93ccb662038fd`
  (`outputs/phase4_access/20261018/final.sqlite`, revision 81908).
- New isolated three-security snapshot:
  `8fbf51d2179d6442f73d51fff26e2d4f7f0a4df9a262dff15152082ca253ff1b`
  (`outputs/phase4_three_security/20261018/final.sqlite`, revision 2).
  Formal interval remains **2015-06-01..2026-09-30**. October is excluded.
- Frozen rule is documented in
  [PHASE4_THREE_SECURITY_PRICE_RULE.md](docs/PHASE4_THREE_SECURITY_PRICE_RULE.md):
  Sina KLC raw OHLC/volume/amount; BaoStock reference-price factor;
  `signal(t) = raw(t) * F(t) / F(fixed prior-quote anchor)`. This is not a
  dividend-reinvestment total-return claim. A separately stored Sina-factor
  control is never spliced into the primary sequence. Selection was based on
  explicit semantics and reproducibility, not performance or old-price fit.

### Actual coverage and evidence

| Security | Real price range | Real rows | Formal rows | Prior rows | Full-day halt evidence | Unknown dates |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 000035 | 2015-05-29..2026-09-30 | 2,455 | 2,454 | 1 | 303 | 0 |
| 000033 | 2015-04-29..2017-07-06 | 31 | 30 | 1 | 504 | 0 |
| 000034 | 2015-03-20..2026-09-30 | 2,371 | 2,370 | 1 | 435 | 0 |

- **6,099 applicable sessions = 4,857 real quotes + 1,242 documented halt
  days**. No synthetic/carry-forward bars. 000033's final trade 2017-07-06
  remains distinct from its delisting date 2017-07-07.
- Raw history was reused, not downloaded again. **46** bounded daily status/
  event-reference queries completed; **16** annual event queries yielded
  **14** nonempty results and **2** successful empty responses for 000033,
  not evidence of no event. Issuer originals supplied the latter explanation.
- Current enabled momentum requires one previous **actual** quote, not a
  previous calendar session. Intervening pre-first-signal halt sessions are
  0/504/111 respectively. Numerical warmup and daily continuity pass;
  historical causal qualification remains unproved. No MA/ATR/breakout is
  enabled. Existing benchmark 19-prior-close counts were checked read-only;
  benchmarks are not replaced/copied into this three-stock experiment.
- 000035's original 2007 issuer announcement was extracted and visually
  reviewed: eligible tradable shareholders receive the reserve transfer;
  the special no-ex-right-reference arrangement explains why reference-price
  and share-distribution adjustments differ. Pre-anchor normalization does
  not erase this distinction or assert identical economic meaning.
- On **2026-06-08/09**, raw close is **5.21 -> 5.09**, legacy signal
  **24.79 -> 26.26**, new signal **10.72487746 -> 10.47785533**.
  Both captured factor sources have no step at this boundary; Bao reference
  previous close is 5.21. The 2026 distribution effective date is August 20,
  not June 9. Legacy segment mixing is strongly suspected, but exact old
  provider/segment lineage remains unknown; no unsupported provenance claim.
- 000033 issuer originals distinguish the **2016-04-15** capital-transfer
  date from reference-price adjustment on resumption, **2017-05-24**.
  The issuer's published reference is **7.96**, not prior actual **10.38**.
  Supplemental issuer evidence is separately hashed, not a silent factor or
  price-version rewrite. 000034's nine in-window factor events were checked,
  including an effective event during suspension without creating a price row.

### Validation and remaining blockers

- Both complete sequences: **24 segment comparisons** and **78 time-cutoff
  comparisons** exact; repeated derivation exact; raw fields unchanged.
  All **15** in-window primary factor steps match reference-price arithmetic
  within predeclared source-digit precision propagation, not relaxed quality
  thresholds. Effective-date invariance is not proof of historical availability.
- Independent database replay matches every row of bars (4,857), session
  evidence (1,242), stocks (3), metadata (8), and patch journal (1).
  Reapplying the 6,106-change manifest writes **0** rows. No duplicate prices.
- **Targeted tests: 8 passed; full suite: 130 passed.** Clearly synthetic
  unit fixtures remain separate from actual provider validation. No real
  backtest, orders, positions or investment returns were produced.
- **541** overlapping stock-days retain cross-source turnover differences;
  volume differs on 55 rows (maximum 3 shares), amount on 514 (maximum 64 yuan).
  These overlap; they are not 569 unique anomalies. Precision is a lead, not
  proof of equal trading scope. Four strict VWAP/range marks remain unchanged.
- Seven raw OHLC differences from legacy are corroborated by current Sina
  and targeted Bao observations and retained with old/new values. Unknown
  legacy origin stays unknown. Three new prior quotes plus those seven rows
  have unknown limit-lock states, stored as NULL in the isolated research
  schema; inherited legacy limits elsewhere are still unverified.
- Historical factor publication/revision evidence, historical ST/limit rules,
  turnover precision/scope, and corporate-action reconciliation of raw stop/
  holding inputs remain blockers. No selector/risk change or parameter tuning.
- Read-only legacy screen: **46,746** pairs / **5,752** other securities at
  **11 theoretical** segment boundaries; **528 suspect pairs / 326 securities**.
  Actual per-segment logs are missing. Pending event/affine-formula/source
  explanations mean these are not 326 confirmed bad securities. No rewrites.
- All original evidence, two failed empty initialization databases and the
  independent replay are retained locally. Existing CAS/snapshot tools were
  reused, not replaced with a new framework. Final source/snapshot/strategy
  hashes and the unchanged frozen 919-task-list hash were checked.
- Local detailed delivery: `outputs/phase4_three_security/20261018/` contains
  `three_security_report.txt`, frozen rules, raw/source manifests, primary and
  control prices, event evidence, old/new differences, validation/replay/closing
  checks, readonly scan and final identity. These data/reports are ignored by Git.
- **Formal gate stays CLOSED for all three and the market.** Do not subtract
  this scoped experiment from old full-market audit counts or mark the 919
  queue complete. Recommend resolving the named evidence issues before any
  broader migration; no queue restart or background continuation is promised.

The older checkpoint below remains historical context, not the current online
access verdict. Code/document delivery and live remote hash are recorded locally
in this experiment's `delivery.json` after commit/push.

## Phase 4 targeted warmup queue, batch 5 (2026-10-15, execution blocked)

### Scope, actual execution and checkpoint

- Starting HEAD was clean `98d610337feb76878e15f406e3e5b9623d53390f`.
  A real remote query returned the same hash before this batch's commit.
  No reset, strategy edits, parameter changes, full-market download or return
  backtest occurred. Acceptance remains **2015-06-01..2026-09-30**; October is separate.
- Frozen exact lists: **919** previously unqueried, **2** previously unresolved
  (000033/000034), and **75** numerical-but-continuity-unverified. Every queue
  entry retains required dates, raw/native-HFQ fields, three accepted formal
  overlaps, prior evidence, attempted and unissued segments. Successful existing
  responses are reused with their original body hashes.
- **The 919-query task is NOT complete.** Only **000035** received new requests
  in that cohort; **918** received none because the common source was blocked.
  All 919 have explicit access/execution-blocked outcomes, **0** completed
  queries, **0** newly added numerical inputs, **0** newly qualified securities.
  A recorded blocker is not a completed query or proof that history is unavailable.
- Both separate securities were actually requested. 000033's cached prior
  raw/HFQ responses were reused; its 2017-05-24..26 formal overlaps still failed.
  000034's 2015-03-20..2015-09-01 raw/HFQ requests failed. Their former generic
  seam/coverage label does NOT establish a price mismatch: required responses
  are absent owing to access failure.
- Across 000033/000034/000035, **6 bounded mode queries / 12 failed attempts**
  ended in `RemoteDisconnected`. The existing circuit stops after three
  distinct securities; it does not issue another 918 identical-failure probes.
  One separate installed-AKShare native-contract check also failed. Homepage
  HTTP success does not mean the historical endpoint works.
- BaoStock failed at public guest login (`网络接收错误` / timeout), before any
  of **800** prepared targeted history queries. The 75 continuity cases retain
  **795** unexplained intervening dates. Their evidence is still missing, not
  proved suspension. The queue prioritizes these cases and then existing gap/
  quality groups; already covered segments are excluded, not fully redownloaded.
- Login failure now persists exact unissued scope and traceback. Queue status
  categories are mutually exclusive by unique security. Resume preserves old
  attempts, successful segments and CAS manifests. Refreshing a status file or
  reclassifying a source-blocked stock does not advance success timestamps.
  In this batch, last successful new market-data acquisition and candidate
  write are both **null**. Last actual new-security attempt was
  **2026-10-15 16:39:18 Asia/Shanghai**. No claim of ongoing background progress.

### Fresh preaudit and real-data results

| Measurement | Batch 4 | Batch 5 |
| --- | ---: | ---: |
| Missing numerical warmup history | 921 | 921 |
| Numerical inputs present, continuity unverified | 75 | 75 |
| Unique securities in these disjoint unresolved cohorts | 996 | 996 |
| Unknown active stock-days | 120,256 | 120,256 |
| Distinct anomalous stock-days | 27,039 | 27,039 |
| Quality marks | 27,070 | 27,070 |
| BSE special cases not wholly qualified | 9 | 9 |

- **120,256 = 0 evidence closures + 0 real quotes filled + 0 mapping/calendar
  closures + 120,256 original unknown**; newly discovered unknown gaps **0**.
  Original abnormal rows resolved **0**, newly flagged rows **0**. No category
  migration or data change is disguised as completion.
- New isolated candidate at `outputs/phase4_batch5/20261015/final.sqlite` has
  hash **`4f85d61157d9638c49791288bcbbc939c3497491909a76b21539a5cd5c262f4d`**,
  revision **81907**: byte-identical to preserved batch 4 because no new source
  values were safely imported. This is a fresh audit execution, NOT a claimed
  repaired data version. The continuous-sync database was not overwritten.
- Same-snapshot accounting: 5,907 securities = 5,820 inside + 87 outside;
  16,285,599 calendar-stock cells = 4,101,050 pre-listing + 452,183 post-delisting
  + 133,106 confirmed suspensions + 120,256 unknown + 11,479,004 accepted dates.
  Physical formal rows **11,479,114 = 11,479,004 + 102 proven echoes + 8 non-sessions**.
- Actual read-only consumer checks passed for all **110** exclusions, including
  the requested additional **51** echoes: raw values/evidence retained; accepted
  view, `bar`, daily signal snapshot, symbol history and previous-actual-bar
  reads exclude them. No strategy or trade simulation was executed to test this.
- 600568 / 2015-11-23 remains blocked. Issuer original announcement **2015-090**
  from CNINFO, published 2015-11-24, was saved with hash and visually checked:
  stock resumption is **2015-11-24**, agreement signing is **2015-11-23**, and
  agreement effectiveness requires signing/seals. These are distinct semantics.
  The original exchange auction-cancellation notice remains missing; issuer
  resumption alone cannot prove the disputed 11-23 quote valid or invalid.
- BSE: 920014/920639/920765/920833/920970 retain normalization/factor conflicts;
  920396 retains the already repaired boundary false-positive but not complete
  causal qualification; 920371/920375/920701 retain comparable auction-volume/
  amount requirements. No unsupported BaoStock BSE requests or restricted
  official-page workarounds were repeated. Per-security dated evidence and
  earlier provider results remain in the admission bundle.
- Existing dependencies unchanged: previous actual signal close (not assumed
  previous exchange session), current signal close and continuity/causal evidence;
  CSI300 display's 20 closes including 19 prior sessions and CSI1000 first
  formal comparison close remain numerically sufficient. No new module gate.

### Validation, delivery and recovery conditions

- Targeted tests: **74 passed**. Full suite: **122 passed**, including five new
  queue/login/empty-response/replay/progress regression tests. Fixtures are
  synthetic unit tests only, not replacements for real market history.
- Live checks are separate: Eastmoney historical access **failed**, BaoStock
  guest login **failed**, issuer PDF **obtained**, 110 isolation-consumer checks
  **passed**. Unit-test success is not a successful provider replay.
- Ignored local delivery: `outputs/phase4_batch5/20261015/` contains frozen
  queue, 921 per-security outcomes, separate unfinished-query and evidence-
  blocker lists, source errors, original announcement, data requirements,
  isolation checks, new preaudit/admission and before/after comparison.
- `phase4_sync_status.json` and `unfinished_queries.json` contain the exact
  resume command (`semantic_review --batch5 ... --recheck-source`). Reuse that
  output directory only after a genuine access change and a successful bounded
  representative request. Existing public sources need no purchase or new token.
  If they remain inaccessible, an existing licensed local export with original
  identifiers, field definitions and adjustment provenance can be evaluated;
  its suitability is unknown until verified. No paid service is authorized.
- **Formal admission remains denied; gate remains closed.** This is an honestly
  incomplete, recoverable execution stage. Pause after reporting; no automatic
  retry monitor or return backtest is started. Only code, tests and this document
  are committed; database, reports, raw responses, caches and credentials excluded.

## Phase 4 source feasibility and targeted repair, batch 4 (2026-10-15)

### Protected scope and version

- Actual starting HEAD was clean `3f48ba1690ac47aa586009c578d8115e98008f9b`;
  a live remote query also returned that hash before this batch's commit.
  No reset, live-database replacement, duplicate full-market sync, strategy
  edits, parameter changes, return backtest or gate release occurred.
- Formal acceptance stays **2015-06-01..2026-09-30**. Warmup is earlier real
  history; October updates remain separate. `selector.py` and `risk.py` unchanged.
- Input is batch 3 snapshot `ff1344cd625f0bbe0510c9d4b32487f30bafdb23016dcc2d675e0a18895b5335`.
  New isolated snapshot is **`4f85d61157d9638c49791288bcbbc939c3497491909a76b21539a5cd5c262f4d`**,
  revision **81907**, at ignored `outputs/phase4_batch4/20261015/final.sqlite`.
  Prior snapshots, original responses, quarantine records and live checkpoints
  are preserved. This candidate has NOT been promoted to the continuous-sync DB.

### Reconciled outcomes

| Measurement | Batch 3 | Batch 4 |
| --- | ---: | ---: |
| Securities missing numerical pre-window inputs | 935 | 921 |
| Numerical inputs present, prior-quote continuity unverified | 213 | 75 |
| Unique securities in those two unresolved cohorts | 1,148 | 996 |
| Unknown active stock-days | 188,697 | 120,256 |
| Applicable quality marks | 47,318 | 27,070 |
| Distinct anomalous stock-days | 47,285 | 27,039 |
| Unresolved original 52 source conflicts | 52 | 1 |
| BSE special-case securities not wholly qualified | 9 | 9 |

- The original **935 and 213 sets are disjoint**. Of the original 213, **142**
  now have complete intervening-day evidence and **71** still do not. Of 14 new
  numerical warmups, 10 have continuity evidence and 4 do not, hence **75 = 71+4**.
  None receives blanket causal-factor approval. Cohort lists retain every stock
  and every unexplained intervening date.
- Added real prior observations for **000009, 000010, 000011, 000016, 000017,
  000018, 000019, 000020, 000021, 000023, 000025, 000029, 001872, 001914**.
  All three first actual formal raw/HFQ OHLC overlaps must match unchanged
  half-tick rules. No rescaling, forward-filled quote, estimated VWAP or warmup
  order/position/return is generated. The verified former codes 000022/000043
  remain the same securities, not new listings.
- Existing dependencies are unchanged: previous **actual** positive signal
  close plus current close; no enabled MA/breakout/volatility requirement.
  CSI300's 20-close display window, including 19 exact prior sessions, and
  CSI1000's first formal comparison close remain sufficient numerically.
- **188,697 = 68,441 independently explained + 0 formal quotes filled
  + 0 mapping/calendar closures + 120,256 remaining original unknown**.
  No new unknown gap is hidden in the net reduction. There are **75,037** new
  daily suspension evidence rows: 68,441 formal gaps and 6,596 pre-window days.

### Proven common causes, with original evidence retained

- The old Sina/AKShare capital-data outer join followed by forward-fill created
  false quotes on capital dates. A record is excluded only when explicit daily
  halt/zero-turnover evidence, no native KLC quote on that date, an exact match
  to the last actual KLC OHLC/volume/amount, and the capital-date response all
  agree. Absence or provider majority alone is insufficient.
- **51 of the original 52** conflicts have that proof. A further **51 newly
  discovered conflicts** were separately captured and all 51 proved to have the
  same cause. All **102** original rows remain physically stored; only the
  accepted view excludes them and records verified full-day suspension evidence.
  They were NOT originally in the 188,697-gap set, so are not counted as closing
  those gaps. Original 52 also intersected zero original quality dates; their
  51 distinct securities intersected 50 missing-warmup and one continuity case.
- **600568 / 2015-11-23** remains blocked. Native Sina contains 26.38 / 265,500
  shares / 7,003,890 yuan while daily status says halted. A contemporaneous
  report describes invalidated opening-auction trades, but the original exchange
  cancellation/issuer notice has not been obtained. This is a concrete evidence
  lead, not permission to delete the row or decide by counting interfaces.
- Corrected **20,256 derived limit/lock rows**, with raw OHLC, adjusted prices,
  volume, amount and VWAP unchanged. Dated status disproves today's ST-name
  backcast on **19,367** rows; previous actual close differs from source ex-right
  reference on **169** rows. These causal sets overlap. Another **822** changes
  have a verified dated-reference discrepancy without an independently isolated
  root cause. Remaining audit root labels are hypotheses, not per-row proof.
- **20,246** original anomalous dates clear all current checks; zero newly
  flagged dates. Ten repaired dates retain another issue. Remaining marks are
  3,026 missing comparable VWAP, 9,668 closes above derived limits and 14,376
  below; **27,039** distinct dates across **3,782** securities. This differs from
  legacy first-reason blocker counts; neither counter substitutes for the other.

### Source feasibility and remaining needs

- Representative BaoStock daily queries covered early history, retired 000024,
  long suspension 600145, former code 000022 and dated ST/reference 600381.
  Two targeted groups of 600 requests then returned **1,198 complete / 2 recorded
  network failures**. Original protocol responses, window/code/mode, terminal
  page and returned-date checks are retained. Carried halt OHLC is never imported.
  Supported SH/SZ windows have NOT established full-market or BSE coverage.
- Eastmoney's original-provider raw/HFQ path succeeded on representative and
  some targeted windows, unlike the incompatible alternative native HFQ scales.
  After repeated proxy errors, the existing bounded transport's direct fallback
  was also tested; repeated failures stopped that path. Of the original 935,
  14 were imported, 2 remain unresolved after source checks, and 919 have not
  completed the targeted queries. **Unqueried is not unavailable or no-data.**
  Further bounded public-source collection needs no new paid authorization.
- AKShare is the wrapper, not an independent provider. Sina, Eastmoney,
  Tencent and BaoStock are identified separately; alternate interfaces to one
  provider are not independent votes. BaoStock's upstream exchange-feed lineage
  itself is not independently certified. Its existing explicit BSE rejection
  was not retried unchanged. Sina MiniRacer decoding ran without security bypass.
- BSE official pages returned HTTP 403 in this environment; no access workaround
  was attempted. Public rule evidence includes the July 6, 2026 rule revision
  and August 31 risk-warning implementation. Block volume enters daily total
  but not instantaneous quotes; that does NOT establish vendor amount scope or
  permit an estimated auction VWAP. Old rules are not applied blindly to 2026.
- Remaining BSE per-security quality-date / unknown-gap counts:
  **920014 9/0; 920396 23/0; 920639 0/0; 920765 10/0; 920833 1/0;
  920970 10/0; 920371 1/0; 920375 4/0; 920701 2/7**.
  920396's previous half-tick false positive stays fixed, but causal lineage is
  unverified. 920014/639/765/833/970 still need dated factor/segment normalization.
  920371/375/701 need comparable regular-auction OHLC, shares and yuan for the
  September 4/11/28 cases. Zero quality flags for 920639 is not full approval.
- Tushare `suspend_d` documentation was retrieved: daily S/R semantics, intraday
  timing, documented start 2000-01-03, 5,000-row cap and entitlement requirements.
  There is no configured authorization or live entitlement verification. If the
  user already has an eligible subscription, the minimal optional action is
  local credential configuration and permission for a small read-only sample.
  Do not paste secrets in chat. Purchase is neither authorized nor proven to
  solve all remaining needs. BSE licensed quote exports are also unverified.
- Ignored `data_requirements.json` retains securities, known former codes (null
  means unknown), exact date spans/dates, fields, attempted query evidence,
  candidate-source limits and minimal actions. Validated-but-unqueried windows,
  temporary network failures, access denial and unsupported identities are
  separate outcomes. Historical pool/board/ST and factor publication chronology
  remain blockers; no unused industry/concept/policy module was added to the gate.

### Same-snapshot accounting, replay and validation

- **16,285,599 - 4,101,050 pre-listing - 452,183 post-delisting
  - 133,106 verified suspension - 120,256 unknown = 11,479,004 accepted rows**.
  Physical formal rows **11,479,114 = 11,479,004 + 8 non-session + 102 echoes**.
  No raw deletion; accepted non-session dates and duplicates are zero.
- Securities **5,907 = 5,820 inside + 87 evidence-supported outside**; all 5,820
  inside have some data, not necessarily complete/clean data. Coverage-only
  categories change from 3,230 complete / 2,590 missing-or-conflicting to
  **3,301 / 2,519**, with 87 whole-interval exemptions and zero segment exemptions.
  Quality and causal qualification remain separate. Both benchmarks have all
  **2,757** formal sessions, checked individually.
- Replayed, in order, `echo_manifest.json`, `source_manifest.json` and
  `additional_echo_manifest.json` from a new copy of the original batch 3 input.
  **All 16 table counts and ordered-content SHA-256 digests match the new candidate**,
  including 11,497,597 total bars. Repeated applications write **zero** rows.
  Evidence hashes, prerequisite versions, changed source bars, competing repairs
  and post-repair mutations fail explicitly; there is no silent source overwrite.
- Targeted regression suite: **57 passed**. Full existing suite plus new tests:
  **117 passed**. `pip check` passed. These use explicitly synthetic test fixtures
  only, not replacement production history. Source field replay and full-data
  rebuild checks are reported separately from unit-test success.
- Git uses the complete MinGit 2.53.0 installation with its own HTTPS helper and
  system GitHub credential flow. Historical tracked paths and 124 historical
  blobs were checked for database/cache artifacts and common credential/private
  key patterns; no matches. Only code/tests/this document are committed; all DBs,
  reports, protocol responses, caches and credentials remain outside Git.
  Remote backup is considered verified only after push and a fresh `ls-remote`
  matches the actual local commit, not the cached tracking ref.

Local deliverables: ignored `outputs/phase4_batch4/20261015/` containing
`batch4_comparison.json/.txt`, `source_feasibility.json`,
`blocker_reconciliation_before.json`, `data_requirements.json`,
`warmup_readiness_after.json`, `bse_semantic_verdicts.json`,
`replay_verification.json`, the three manifests and original response folders.
Latest admission is `final_reaudit/admission/phase5a_admission_report.txt` with
`blockers.json`. **Formal admission remains blocked; pause after this batch.**

Primary source references: [BaoStock daily definitions](https://www.baostock.com/helpDocsHome?file=stockKData.md),
[Tushare daily suspension interface](https://tushare.pro/document/2?doc_id=214),
[BSE 2026 rules](https://www.bse.cn/jygl_list/200028217.html),
[BSE risk-warning effective date](https://www.bse.cn/jygl_list/200029142.html).

## Phase 4 concentrated blocker repair, batch 3 (2026-10-14)

### Scope and immutable version

- Starting HEAD was clean `94d7b3102734cd40f1fa6100e0575f602d802716`.
  No reset, strategy changes, parameter tuning, return backtest or gate release.
  Acceptance remains **2015-06-01..2026-09-30**; October is separate.
- All writes targeted an isolated candidate. The live sync process/database,
  prior snapshots, checkpoints, raw responses and quarantine evidence were not
  replaced or stopped. The candidate is **not** promoted to the live database.
- Output snapshot: `sha256:ff1344cd625f0bbe0510c9d4b32487f30bafdb23016dcc2d675e0a18895b5335`,
  revision **81904**. Ignored `outputs/phase4_batch3/20261014/final.sqlite` and
  `audit_snapshot.sqlite` have the same byte hash. The latter was independently
  read by the preaudit. Input remains batch 2 revision 81903, hash
  `43f4b0fa8c825f0e747ccf63862d726649a5d509a306ab7169ec17f4f3ba5906`.

### Actual changes, not blanket approval

| Measurement | Before | After |
| --- | ---: | ---: |
| Existing securities missing pre-window history | 940 | 935 |
| Unknown active stock-days | 221,550 | 188,697 |
| Applicable quality marks | 61,665 | 47,318 |
| Distinct unresolved quality stock-days | 61,630 | 47,285 |
| Numerically ready but prior-quote continuity unverified | 216 | 213 |

- Added five real prior quotes: **000498, 002735, 002747, 002749, 600146**.
  Both raw OHLC and native HFQ overlap agree with the stored first signal row;
  no arbitrary factor rescaling or warmup orders/positions/returns were used.
- All **1,793** previously supplemented securities were rechecked, not simply
  counted by row existence. Existing selector momentum needs one **previous
  actual quote's positive signal close**, plus the current positive signal close;
  it does not mean the immediately previous exchange session. There is no enabled
  MA, breakout or volatility window. The current volume/tradable eligibility is
  reported separately, unchanged. There are now 1,798 numerical-ready securities,
  but 213 still have unexplained intervening sessions; none receives blanket
  causal approval while factor publication/lineage remains unknown.
- CSI300's existing regime display needs **20 valid closes including June 1**.
  Its 19 prior closes exactly match May 5..29 exchange sessions. CSI1000 currently
  needs the first formal comparison close; its additional 19 prior closes were
  also verified, without introducing an unused-window gate. Risk state starts
  empty at the formal start. Required fields remain documented by
  `baseline_dependencies()` and the latest admission report.
- Remaining 935: **933 native HFQ normalization conflicts**, plus **2 verified
  code-change cases with recovered raw history but conflicting HFQ**. Issuer/
  exchange evidence identifies 001872's former 000022 and 001914's former 000043;
  eight bounded former-code queries succeeded. Their raw overlap agrees, but
  source HFQ first closes 75.8474871 / 93.30425384 differ from stored 61.38 / 87.16.
  They are not new listings or objectively short histories. No remaining case
  was excused as proven suspension or objective insufficient history without proof.

### Suspension coverage and reconciliation

- Eastmoney's event query was fully paged: **9 pages / 4,304 rows**, with count
  and uniqueness checks. It returned exactly one event per stock, not complete
  historical daily suspension coverage. Empty, capped, permission/session and
  network failures remain distinct; no interval exemption is inferred from two
  empty price sources or from an intraday event.
- Added a pinned public guest evidence client, BaoStock **0.9.1**, without
  replacing AkShare as primary sync source. Official definitions specify daily
  `tradestatus`, shares, yuan and ex-right reference `preclose`:
  [K-line definitions](https://www.baostock.com/helpDocsHome?file=stockKData.md).
  Bounded queries retain request scope, final-page state, errors, original
  protocol responses and hashes. Only explicit daily suspended status with zero
  turnover and no contradictory stored quote explains a missing date. Provider
  carried-forward halt OHLC is **never** inserted as market bars.
- **221,550 = 32,853 evidence-explained + 0 real formal quotes filled
  + 0 mapping/calendar closures + 188,697 remaining original unknown**.
  Formal calendar coverage and quality conflicts are independent counts.
- **52 new source-status versus stored-quote conflicts** are separate blockers,
  not part of the net reduction. One genuine positive-volume source quote,
  000007 on 2026-09-29, remains unimported because its signal adjustment seam
  has not passed. Remaining gaps are grouped by stock, continuous interval,
  year, exchange and latest stock-source ledger. Original per-segment lineage
  is absent; nominal segment boundaries are not asserted to be proven causes.
- Full-market historical suspension coverage is still **unverified**. A guest
  session expiry was diagnosed and recovered in a new bounded evidence run;
  501 of 502 affected queries completed, one remained a recorded network failure.
  Earlier failed responses are retained, never relabeled as no data. The SDK
  adapter now reconnects expired sessions and stops after bounded failures.

### Quality causes and the nine BSE securities

- Three confirmed causes, with overlapping counts explicitly non-additive:
  **14,183** rows disprove today's ST-name backcast using dated status;
  **112** show previous actual close differs from the source's ex-right reference;
  **13** have exact-share precision loss corroborated by native Sina and daily
  BaoStock raw prices/turnover. Another 157 dated-reference derived-rule changes
  have no independently isolated root attribution; they are not forced into a
  confirmed causal category. Remaining audit root labels are hypotheses.
- Changed derived limit/lock metadata and 13 corroborated volume values across
  **14,374 distinct existing rows**. Existing raw OHLC, signal prices and amounts
  were not rewritten. Twelve corrected one-price rows still have an actual
  amount/share ratio outside OHLC and retain missing VWAP; only one exact ratio
  became usable. No closing-price substitution, tolerance relaxation or removal
  of quality checks. Preaudit removes **14,345** formerly abnormal date rows;
  a corrected field is not automatically a fully resolved row/security.
- Historical rule handling uses dated status/reference and existing effective
  board-rule dates, excludes uncertain IPO/later main-board ST exceptions, and
  leaves official per-date execution certification blocked where evidence lacks.
- BSE **920396** retains its repaired half-tick boundary result, but not full
  causal qualification. **920014, 920639, 920765, 920833, 920970** retain real
  HFQ-source conflicts. **920371 (09-04), 920375 (09-11), 920701 (09-28)** retain
  regular-auction versus negotiated-trade turnover-scope blockers. A separate
  raw/HFQ query for each BSE security returned explicit `10004011` unsupported
  `bj` identity, not no-data. No repeated identical requests or BSE exclusion.
  Required next evidence is dated corporate actions/normalization and separately
  defined regular-auction volume/amount; diagnostic residual averages remain
  diagnostic only, never execution VWAP.

### Replay, audit and delivery

- Evidence manifest version `phase4-batch3-evidence-v1`, digest
  `327059d3e8843a2019ded25fc01400b8cf5d7a7601509ad6068fb2e7d51bd177`:
  **47,232 unique changes**; second application **0 writes**, unchanged revision.
  Independent reconstruction from the verified same input and manifest matches
  the entire logical bars/evidence/quarantine/metadata/journal content, digest
  `a45f6b278b709c3dfed69e66aac07502647c58c65feda029114f2aff763b86bd`.
  Atomic compare-and-set rejects changed source rows, changed evidence hashes,
  duplicate targets, changed manifest contents under the same version and
  post-sync mutations. It does not silently overwrite a newer source database.
- Replay procedure reuses `build_batch3_patch`, `verify_snapshot`,
  `freeze_database` and `apply_evidence_patch`: verify the immutable input first,
  build a new isolated candidate, verify source hashes, apply once, repeat to
  test no-op behavior, freeze and preaudit. For a different input, reassess
  conflicts and create a new repair version; do not copy this candidate over live.
- Same snapshot: **5,907 = 5,820 interval-inside + 87 interval-outside**.
  **16,285,599 = 4,101,050 pre-list + 452,183 post-delist + 64,563 evidenced
  suspension + 188,697 unknown + 11,479,106 observed calendar stock-days**.
  Physical formal bars **11,479,114 = 11,479,106 accepted + 8 retained isolated
  non-session rows**. No security was deleted or reclassified to force approval.
- Local ignored deliverables: `batch3_comparison.json/.txt`,
  `warmup_readiness_before.json`, `warmup_readiness_after.json`,
  `suspension_evidence_coverage.json`, `repair_manifest.json`,
  `replay_verification.json`, `bse_semantic_verdicts.json`, and
  `final_reaudit/admission/phase5a_admission_report.txt` plus `blockers.json`.
  These contain per-security dates, raw/source references, before/after values,
  unresolved fields, attempts and required next sources; none is uploaded.
- Validation: **50 targeted tests passed; 110 full-suite tests passed**.
  These include explicitly isolated synthetic fixtures, not substitute real
  history. Real-source collection, real-snapshot replay and preaudit are reported
  independently. `pip check` passes. The prior approved Sina native-response
  decoding evidence was reused; no new claim of platform-wide decoder equivalence.
- **Formal admission remains blocked** by unresolved warmup/continuity, gaps,
  quality conflicts, historical security identity/universe and factor publication
  lineage. No unused industry/concept/policy module gate was introduced. Stop
  after this batch; no automatic Phase5A, backtest or further retry loop.


## Phase 4 data-semantics repair, batch 2 (2026-10-13)

### Version, scope and safeguards

- Actual starting HEAD was clean `d5483bce59be68cfdaa5cd74a17145dab656831e`;
  no reset or overwrite of previous work. Formal acceptance remains
  **2015-06-01..2026-09-30**. October incremental synchronization is separate.
- All data writes were serialized on a new isolated candidate, not the live
  synchronization database. The previous snapshot, checkpoints, source responses,
  quarantine records and reports are retained. No synchronization process was
  stopped. No selector/risk changes, parameter changes, return backtest or gate
  release occurred; this batch pauses after repair and preaudit.
- New immutable SQLite online-backup snapshot:
  `sha256:43f4b0fa8c825f0e747ccf63862d726649a5d509a306ab7169ec17f4f3ba5906`,
  revision **81903**, under ignored `outputs/phase4_batch2/20261013/final.sqlite`.
  The live database was deliberately not replaced by this candidate.

### Actual repairs and reconciled results

| Measurement | Before | After |
| --- | ---: | ---: |
| Securities missing pre-window history | 2,733 | 940 |
| Unexplained active stock-days | 253,264 | 221,550 |
| All applicable quality marks | 68,819 | 61,665 |
| Distinct unresolved stock-date rows | 68,783 | 61,630 |
| Affected securities (quality) | 3,817 | 3,816 |
| Non-session rows in formal data view | 8 | 0 |
| Listing dates missing | 0 | 0 |

- Added **1,793 real prior quotes**: 1,627 bounded Tencent/Sina-factor overlaps
  passed initially; 166 more passed after checking the first existing quote
  rather than assuming a stock traded in the first June week. Original jobs and
  follow-up responses remain separately saved. The remaining 940 have observed
  raw prior history but unresolved/unverified adjusted-price seams; none is
  excused by inventing suspension, zero prices, future prices, or later starts.
  Numerical seam agreement does **not** certify factor publication-time causality.
- Actual baseline history dependency: selector momentum needs **one previous
  actual quote**, not necessarily the preceding exchange session. No enabled
  moving-average, breakout or volatility window was found. Existing market-regime
  display uses **20 CSI300 closes including the current date**; 19 real pre-window
  closes were added to each benchmark, with all five June overlap closes checked.
  This display is not a selector/risk filter. Formal trading-date iteration is
  bounded by snapshot metadata; earlier quotes remain readable for initialization,
  not warmup orders, positions, trade counts or returns.
- Independent Eastmoney suspension-event responses contained 4,043 records.
  Only explicit full-session start/end bounds, absence of contradictory actual
  bars, and corroborating positive-volume resumed quotes were accepted.
  Forecast resume dates and intraday-only suspensions were not used as exemptions.
  Event coverage is demonstrably partial, not assumed market-wide.
  **253,264 = 31,710 evidenced full-day suspensions + 4 real quotes filled
  + 0 mapping/calendar reclassifications + 221,550 unknown.**
- The four filled quotes are 000415, 000711, 000796 and 002051 on 2026-09-29.
  Their saved native KLC responses contain the real missing bars; raw/adjusted
  overlaps on both sides match. No existing OHLC, signal price, volume, amount or
  VWAP was changed. Newly inferred execution-limit metadata remains subject to
  historical-reference validation, not silently certified.
- Corrected **7,145 recognizable legacy-derived limit rows**, not source prices:
  old fields exactly reproduced the former 5% calculation; consecutive-session
  references, listing age and unchanged dated adjustment factor were required.
  The [SZSE risk-warning rule](https://www.szse.cn/disclosure/notice/general/t20200710_579459.html)
  and [2020-08-24 implementation notice](https://www.szse.cn/aboutus/trends/conference/t20200821_580925.html)
  establish ChiNext's 20% rule. This is not a relaxed audit threshold. Before/after
  fields and evidence are journaled. **82 remain unresolved**: 8 corporate-action
  references, 58 resumed/reference-gap cases and 16 IPO/listing-age cases.
  Official per-day execution references and historical eligibility remain gated.
- Remaining disjoint quality root rows: current ST-name backcast **51,573**;
  IPO/ex-right/reference uncertainty **6,983**; turnover/unit/price-mode/trade-scope
  uncertainty **2,992**; remaining ChiNext special cases **82**. Root evidence,
  raw-to-conversion-to-stored examples and source/year/error distributions are
  retained in the local report. Source labels are latest stock-ledger labels,
  **not** invented per-segment lineage.
- All 8 weekend rows were replayed against native raw archives and independently
  checked against the calendar. The bogus dates are absent from the raw date set
  and exactly echo older real OHLCV/amount rows: 300462 2017-09-30→2017-04-20;
  000415 2018-06-30→2018-01-16; 000711→2018-03-23; 000796→2018-01-18;
  002051→2018-04-04; 002082→2017-12-15; 300238→2018-02-01;
  300324 2018-09-30→2018-05-29. The six middle entries share 2018-06-30.
  Originals remain in physical `bars`; only evidenced non-sessions are excluded
  by the shared formal read view. No entire security is removed.
- Same-snapshot reconciliation:
  **16,285,599 - 4,101,050 - 452,183 - 31,710 - 221,550 = 11,479,106**
  calendar/accepted rows. Physical in-window rows **11,479,114 = 11,479,106 + 8**
  preserved isolated rows; duplicate stock-dates **0**. Inventory **5,907 = 5,820
  in-window + 87 outside-window**, and all 5,820 have at least one real bar.
  The 13 earlier unapproved quarantine cases remain separate from these counts.
- Coverage/quality classification changes from 2,529 complete / 87 whole-window
  exemptions / 3,291 missing-or-conflicting to **3,193 / 87 / 2,627**.
  This classification is not causal or formal-backtest approval. CSI300 and
  CSI1000 still each cover all **2,757 formal sessions**, besides warmup records.

### BSE cases, environment and validation

- 920396: unchanged exact half-tick comparison fixes the boundary false positive;
  numeric raw/HFQ overlap passes, but factor publication and full trade-scope
  provenance remain unapproved. It is not counted as an entirely qualified stock.
- 920014, 920639, 920765, 920833, 920970: material HFQ normalization conflicts
  remain; raw overlap alone cannot establish causal signal-price comparability.
- 920371 (09-04), 920375 (09-11), 920701 (09-28): negotiated-trade evidence
  supports incompatible OHLC versus aggregate-turnover scope. Comparable
  regular-auction volume/amount is still needed. Diagnostic residual averages
  were never written as VWAP or treated as execution prices. All nine remain.
- Sina现场重放: unchanged Python 3.12.14 / AkShare 1.18.91 / MiniRacer 0.14.1
  successfully loads the original native decoder in this permitted environment.
  Three **exact saved, SHA-verified original responses** were replayed successfully,
  plus eight targeted weekend archives. No alternative decoder or security-policy
  change was used. DLL path/hash, versions, call chain and original WinError4551
  messages are retained. The old full traceback was not retained and is explicitly
  marked unavailable, not reconstructed as original evidence. This is not a claim
  of validating every Sina response or every execution environment.
- **Targeted tests: 22 passed. Full suite: 98 passed.** These are isolated unit
  tests, not real-data returns.现场重放 results above are separately recorded;
  unit passes do not stand in for source or causal certification.
- Git diagnosis: the originally selected bundled Git 2.53.0.windows.3 lacks
  its HTTPS helper. A complete official MinGit of that same version was separately
  downloaded and verified against release SHA256
  `0d7c85a26e45668b35d0d0aeb763289376cfc039e55e0938a617ed0dfa32e433`.
  Its own executable/helper/DLL tree is used together, never mixed with the
  incomplete distribution. HTTPS helper is in its `mingw64/bin` directory.
  GitHub CLI keyring authentication and live REST ref queries work. Initial Git
  smart-HTTP attempts encountered connection resets/timeouts, a separate network
  problem, not invalid credentials. The final bounded HTTP/1.1 push succeeded:
  code commit `314f70ffcf19e778138502c6e0e6512fec53df0b` was verified on remote
  `refs/heads/main` by **both live ls-remote and GitHub REST**, matching local HEAD
  at that checkpoint (this documentation confirmation follows it). No password
  or token was printed. Future commands should use the complete executable at
  `../work/tools/mingit-2.53.0.3/runtime/cmd/git.exe`, not the incomplete runtime
  still selected by the preexisting system PATH. The successful command used
  per-command GitHub CLI keyring credential handling; no global Git/DLL/PATH change.
- Reachable-history scan examined **109 source blobs**, and staged-content plus
  tracked-path checks found no matching credential patterns, databases, runtime
  environments, caches or generated reports. Ignore rules additionally cover
  nested SQLite sidecars, `.env`, logs and offline bundles. This is a bounded
  pattern/content review, not a claim that every possible secret format is detectable.
- Additional offline backup outside the repository:
  `../work/backups/Roviga-314f70f-phase4-batch2-20261013.bundle`.
  `git bundle verify` passed and confirms complete history through the code commit.
  SHA256 `f01d539d2de3a515e67773b5a450ffc2ffc85f4178fd32e59b2ba2a79184aa02`.
  It is a local recovery artifact, not itself off-site backup; the separate
  successful GitHub push above establishes remote code backup.

### Local deliverables and remaining work

- Ignored local bundle: `outputs/phase4_batch2/20261013/`, including
  `batch2_comparison.txt/.json`, `final_reaudit/final_reaudit.txt/.json`,
  `final_reaudit/admission/phase5a_admission_report.txt/.json`, `blockers.json`,
  `warmup_jobs/`, `warmup_overlap_evidence/`, `suspension_events.json`,
  `event_reconciliation.json`, `limit_rule_repair.json`, `targeted_fill_result.json`,
  `decoder_replay.json`, `source_semantics.json`, and nine per-security verdicts.
  Reports/databases/cache/credentials are not Git artifacts.
- Original gaps are grouped by security, continuous range, year, exchange,
  latest stock source and nominal 366-day download boundaries. Boundary matches
  are explicitly heuristic: original segment provenance is unavailable.
  Largest original daily concentrations are 2015-07-09 (1,442), 07-10 (1,385),
  07-08 (1,316), 07-13 (1,031), 07-14 (781); remaining dates are not automatically
  called suspensions merely because the 2015 halt wave is plausible.
- Next batch: remaining 940 adjustment seams; independently documented missing
  sessions (especially historical halt clusters); historical ST/official reference
  evidence for the dominant 51,573 rows; comparable BSE trade statistics and dated
  adjustment normalization; point-in-time stock identities/universe. Unused
  industry/concept/policy/rotation factors are not new admission gates.
- **Fresh preaudit fails; formal backtest conditions are not met. Gate remains
  closed. No automatic Phase 5A or return backtest follows this report.**

## Phase 4 data-semantics repair, batch 1 (2026-10-13)

- Working baseline verified at `684ce4683802b0e6d56044a5106e3fd12c94a522`.
  The historical acceptance interval remains **2015-06-01..2026-09-30**;
  October synchronization remains a separate track. No selector/risk logic or
  strategy parameter changed. No returns or formal backtest were run.
- Read-only after-version audit snapshot: `sha256:650ad3103fd017595c5cfc57af4ad47cc167bf62365fa0a68adb906f9d4291f6`,
  revision 80101. It contains 5,907 securities and 11,479,110 bars in range,
  spanning 2015-06-01..2026-09-30. The admission bundle classifies 2,529
  histories complete, 87 whole-interval exemptions supported by separate
  evidence, and 3,291 missing or conflicting. Exemptions are not counted as
  downloaded history. CSI300 and CSI1000 each have 2,757 sessions and match the
  independent calendar; historical index constituents are still unverified.
- Batch exchange metadata filled the 5,225 missing listing dates to zero in the
  5,907-security snapshot. Three SSE A-share dates previously mapped from
  issuer-level B-share rows were corrected using an A-only raw exchange response;
  old observations remain journaled. Security IDs/ISIN, code-validity periods,
  and official last-trade dates remain unknown where no direct source was found.
  Listing date was never inferred from the first local bar.
- Missing-session accounting now reconciles all 16,285,599 security-calendar
  pairs: 4,101,050 pre-listing, 452,183 post-delisting, 253,264 active but
  unexplained, 0 independently confirmed suspensions, and 0 proven real losses.
  Thus zero confirmed loss/suspension does not mean the 253,264 gaps are explained.
  Coverage is separately reconciled as 5,820 inside-range securities and 87
  outside-range securities; all 5,820 have at least one bar, with no bars for
  the 87 verified whole-interval exemptions.
- Quality accounting preserves the earlier 68,775 first-reason marks and
  identifies 68,819 all-applicable marks on 68,783 distinct security-date rows
  across 3,817 securities. Marks: missing VWAP 3,027; close above limit 31,395;
  close below limit 34,388; invalid limit ordering 1; unexpected reference
  session 8. Disjoint primary root counts: turnover/unit/mode/scope unresolved
  2,992 rows; current ST-name backcast 51,573; IPO/ex-right/reference/rule
  unknown 6,983; Chinext ST-priority bug 7,227; weekend capital-date merge
  artifact pending original-byte replay 8. Same-date duplicates and OHLC
  contradictions are zero in the persisted checks. No price, volume, amount, or
  VWAP was rewritten. Source/year/error distributions and reproducible samples
  are in the ignored audit output.
- The 8 extra weekend dates are retained as individual blockers: 300462 on
  2017-09-30; 000415, 000711, 000796, 002051, 002082, 300238 on 2018-06-30;
  and 300324 on 2018-09-30. The pattern matches the former AkShare Sina path's
  share-capital-date outer merge/forward fill; per-bar original responses are
  unavailable, so the exact historical cause remains pending raw replay. The
  live adapter now selects actual KLC quote dates without that merge. Its native
  decoder could not be live-validated in this Windows run (`WinError4551` blocks
  loading MiniRacer); mocked unit coverage passed and no security policy was
  bypassed. These rows are neither deleted nor approved for trading.
- BSE review: 920396's 14-day raw/adjusted overlap now passes the unchanged
  half-tick Decimal comparison; source-factor causality remains unapproved.
  920014, 920639, 920765, 920833, and 920970 still have material HFQ conflicts.
  920371 (2026-09-04), 920375 (2026-09-11), and 920701 (2026-09-28) show
  negotiated-trade scope evidence for volume/amount mismatches; diagnostic
  residual averages are not execution VWAPs. All 9 remain in the per-case review.
- Current baseline dependency review found 2,733 securities already listed at
  the acceptance start with in-range bars but no pre-window bar. The selector
  reads prior `signal_close`, so the first-session input is unresolved for
  these securities. OHLC/volume/tradability/lock fields are stored, but volume
  scope, historical execution locks, point-in-time stock universe, and causal
  adjustment history remain unverified. Industry/concept/policy/fundamental and
  constituent-selection data are not consumed by the current baseline and are
  not added as gates. See `baseline_required_fields.json` for actual field reads.
- 51 focused unit tests pass, including a regression test that creates an
  unexpected-session blocker while retaining the stored source row. The fresh
  audit output and detailed blocker bundle are under ignored
  `outputs/phase4_batch1/20261013T042113774108Z/final_reaudit/`; no database,
  report, cache, environment, or credentials are Git artifacts. Formal return
  backtesting remains blocked; this batch does not release the gate or start
  Phase 5A.

## Frozen historical acceptance and source review (2026-10-12)

- First acceptance range is fixed at **2015-06-01..2026-09-30**. Continuous
  updating remains required; October is a separate incremental track, not a
  moving historical acceptance boundary. No baseline return calculation occurs.
- Immediately ran the existing auditor even with 32 retained failures. The
  initial frozen snapshot reported 68,776 quality flags, not a successful audit.
  A failed preaudit still emits its reports and blocking checklist.
- Added `phase4_acceptance`: pinned WAL read transaction, online backup of
  committed SQLite data, SHA-256/revision identity, read-only snapshot audit,
  individual-stock and individual-benchmark session comparisons, four-way
  range-disposition accounting, and a Phase 5A admission/blocker bundle.
  Snapshot audit metadata cannot be used to authorize the production runner.
  The source review has a separate hash. All runtime files remain under ignored
  `outputs/`; no SQLite data, reports, logs, environments or credentials upload.
- Online backup initially restarted repeatedly while the downloader committed.
  Replaced only that audit job with a pinned WAL snapshot; the downloader and
  guardian were never stopped. A regression test checks a concurrent commit.
- Both CSI300 and CSI1000 have **2,757** sessions for the acceptance interval.
  Each matches the independently downloaded real Sina session calendar with no
  missing/unexpected sessions and no non-positive index closes. This checks index
  price series, not point-in-time historical constituent membership.
- All **85** original pre-range delisting decisions were rechecked against fresh
  SZSE/SSE metadata: real complete in-range history **0**, segment-only exemption
  **0**, whole-interval exemption **85**, missing/conflicting exemption proof **0**.
  None is counted as downloaded complete history. Stock identity/inventory stays.
  BSE official metadata separately dates `920157` to **2026-10-09**: exempt from
  this September historical interval, but real October rows are required and
  have started downloading. Current snapshot therefore has 86 whole-range
  exemptions, not 86 completed histories.
- Investigated all 28 BSE failures with specific secid, prefix, date bounds,
  exchange listing dates, direct Eastmoney and Tencent probes. Eastmoney still
  disconnects; Sina A-share is unsupported. Tencent raw BSE requests work while
  AkShare's preliminary start-year lookup fails. Official code-mapping pages
  returned HTTP 403: old/new code identity remains unverified, never guessed.
  Tushare was not enabled without supplied credentials/permission.
- Added a bounded Tencent BSE fallback with real OHLCV/turnover and HFQ requests,
  lot/share and 10,000-yuan/yuan validation, explicit date clipping, duplicate and
  raw/adjusted-date checks, and persisted source-switch overlap reconciliation.
  Empty required BSE segments stay failed, never become proof of no data.
- Validation identified six HFQ disagreements (`920014`, `920396`, `920639`,
  `920765`, `920833`, `920970`) and three turnover/VWAP disagreements
  (`920371` 2026-09-04, `920375` 2026-09-11, `920701` 2026-09-28).
  All nine are retained failed with source-review-required policy. Some disputed
  fallback rows had already been written by the preserved worker before the
  overlap investigation finished; they remain intact and are explicitly marked
  for reconciliation in `provider_quarantine`. They are NOT accepted history.
  No adjustment multiplier was guessed and no disputed market row was deleted.
- For `300028`, `300104`, `300216`, `300431`, the fresh exchange list/delist dates
  agree with cached metadata. Each raw KLC archive appends one **2021-06-27 Sunday**
  echo identical in all OHLCV/amount fields to its actual final session. Real last
  dates are respectively **2020-07-31, 2020-07-20, 2020-09-15, 2020-11-09**.
  The echo is preserved as evidence in SQLite quarantine; it is not imported as
  a trading day, and the stock/delisting date is not removed or rewritten.
  Recovered counts are **551, 626, 917, 1,033** real bars. Isolation is not formal
  approval: unreviewed quarantine records continue blocking the audit.
- BSE transport failures now have persistent 1/2-hour cooldowns and require
  source review after three failures; metadata conflicts require review directly.
  Failed ledger/checkpoints remain visible. Data/schema/permission failures no
  longer burn identical transient retry budgets. Other transport recovery stays.
- The existing single worker naturally loaded the fixes and explicit local sync
  plan, targeting **2026-10-12** incrementally from preserved checkpoints. At
  17:00 China time: **5,896 complete, 9 failed, 1 running** (5,906 inventory),
  with real October rows already present. Counts are download states, not market
  completeness. No second downloader, strategy change or parameter tuning.
- Post-repair frozen snapshot identity:
  `sha256:8296e35dd87057aa62475cc0bc54432b6b076313040a48a37fc4b204be7a22a0`,
  data revision **58,043**, captured 2026-10-12 17:04:52..17:05:08 China time.
  Its historical range contains **11,479,110** bars across **5,820** applicable
  stocks; all 248 required delisted stocks and 348 required BSE stocks have some
  rows, which does NOT prove their daily completeness. There are **5,224** unknown
  listing dates, **5,279** stocks with unexplained/provisional session gaps, and
  **3,649,033** unexplained/provisional sessions (not confirmed lost bars).
  Exchange removal dates are not counted as expected trading sessions; this
  avoids treating the 248 required delistings themselves as missing trading days.
- The same frozen range still has **68,775** quality flags: 3,027 missing VWAP,
  31,360 closes above inferred limits, 34,387 below inferred limits and one invalid
  inferred-limit order. These flags require raw-source and point-in-time rule
  review, not widening limits or calling every flag a bad market price.
- Classifications are empty; historical universe/alias events, suspension/risk
  warning history, exact limits and adjustment-factor availability are not yet
  verified. **Phase 5A admission is blocked; formal backtest gate stays closed.**
  The local report includes each blocking security/index scope, date, reason and
  treatment plan. Only code/document changes are intended for Git.
- At this checkpoint, 38 acceptance/recovery tests and 10 selected existing
  market tests pass, without executing a return-producing backtest. `pip check`
  passes. `selector.py` and `risk.py` are untouched. After handoff, this work pauses
  for instructions; existing real synchronization remains preserved and chat
  heartbeat stays paused.

Local reports: `outputs/phase4_acceptance/20261012T090452083792Z/`.
Source evidence: initial snapshot's `source_review.json`, also copied into the
post-repair report bundle. Use the README commands for reproducible re-auditing.

Sources: [BSE listing interface](https://www.bse.cn/nqxxController/nqxxCnzq.do),
[BSE code correspondence](https://www.bse.cn/service/code_mapping.html),
[SZSE retired inventory](https://www.szse.cn/api/report/ShowReport),
[AKShare source documentation](https://akshare.akfamily.xyz/data/stock/stock.html).

## Retired-history recovery fix (2026-10-11)

- Investigation found that all 281 non-BSE failures were delisted stocks.
  AkShare's Sina decoder successfully downloaded their raw KLC OHLCV, but then
  crashed in the unrelated retired outstanding-share endpoint (`demjson`
  "No value to decode"). Increasing retries cannot repair that expired endpoint.
- Added a lazy real Sina archive reader using the existing pinned AKShare KLC
  decoder and the provider's HFQ factor series. It does not request outstanding
  shares, execute downloaded JavaScript, synthesize bars, forward-fill sessions,
  or apply future factors to earlier dates. Volume remains shares; amount remains
  yuan. Missing/invalid factors, duplicate dates, and source gaps retain failures.
- Five live read-only conversion checks succeeded:
  `000004` 2,463 bars, `000018` 1,083, `600068` 1,516, `600069` 1,148, and
  `000024` 41. These are verified provider results, not a production import claim.
  All five converted with non-missing VWAP; no return calculation was performed.
- A failed delisted stock now rebuilds its in-range history rather than trusting
  an old checkpoint that had advanced beyond delisting while earlier gaps remained.
  Once fallback is needed, the archive is fetched once per stock and segmented
  locally. Requests stop at the documented delisting boundary; conflicting
  archive dates remain explicit metadata failures rather than silently discarded.
- The failed inventory includes 85 stocks documented as delisted before
  2015-06-01. They have no required sessions in this requested range, are retained
  in inventory with explicit `outside_requested_range` provenance, and are not
  reported as newly downloaded history. Audits disclose the outside-range count
  and continue to require every in-range delisted stock. Conflicting cached bars
  retain failures. No SQLite rows or failed stock identities are deleted.
- Windows resolved an implicit system proxy at localhost:7890 despite no proxy
  environment variables. Requests now try a direct route once after a system
  proxy failure, restore the session afterwards, and preserve explicitly supplied
  proxy configurations. System proxy settings and TLS verification are unchanged.
- Both proxied and direct Eastmoney probes still failed during verification.
  Transport failures now open a temporary five-minute endpoint cooldown and
  automatically probe again; symbol-specific data errors do not open the circuit.
  BSE does not use the unsupported Sina A-share source. The 28 retained BSE
  failures remain unresolved; a Tencent BSE probe was also unsuccessful and
  Tencent was not enabled as an unverified substitute.
- All 32 selected market/recovery tests passed, including 10 new tests for
  archive units, causal factors, date bounds, gaps, duplicates, metadata exclusions,
  temporary transport recovery, proxy restoration, extended-range cache refresh,
  and contradictions between bar dates and listing metadata. `pip check` passed.
  Tests use isolated fixtures; production data is never replaced by test data.
- The active old downloader and its guardian were not terminated. The guardian
  starts a fresh Python worker after natural batch exit, so the next retry loads
  the new implementation automatically. No overlapping production writer was
  started. Immediate activation is not claimed while the old worker is alive.
- Snapshot before deployment: 5,906 stocks, 5,596 complete, 309 failed, 1 running,
  11,337,606 bars; latest bar 2026-09-30. The fixed batch end remains 2026-10-02.
  Audit has not passed. No backtest, parameter tuning, `selector.py` or `risk.py`
  changes were made. Chat heartbeat remains paused as the user requested.

Reference: [AKShare stock documentation](https://akshare.akfamily.xyz/data/stock/stock.html).

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
