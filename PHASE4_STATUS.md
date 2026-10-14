# Phase 4 checkpoint status

Checkpoint date: 2026-10-14

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
