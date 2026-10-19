# Roviga execution constraints

Read `docs/MASTER_EXECUTION_PLAN.md` and `PHASE4_STATUS.md` before work.
Latest user decision (2026-10-19): keep the execution model unchanged; deliver
data and the not-ready interface only. This limits the master mandate below:
no automatic migration expansion, 919 resume, return backtest or model changes.
Model limitations remain open, not waived by this delivery-scope decision.
The user's 2026-10-19 master mandate supersedes earlier batch-end stop rules.
Continue to the next eligible step, not merely the next report or commit.

- Work only on Roviga stocks. No live broker, real money, options, ShortAlpha,
  renaming, or cross-project access. No new stock strategy modules.
- Preserve user changes, raw evidence, old snapshots, and the live sync database.
  Repair isolated candidates using existing compare-and-set/replay tools.
- Fix the first formal interval at 2015-06-01..2026-09-30; warmup follows actual
  dependencies. Later increments are separate. Never fabricate missing history.
- Do not change selector.py/risk.py core behavior or tune parameters. Actual
  model/config conflicts require a concrete decision, not silent replacement.
- Pilot acceptance precedes 20/100/remaining migrations; fixed full-market
  admission precedes first real backtest; that precedes operational observation.
  An unused comparison field is not a gate; a real dependency cannot be waived.
- Daily at most one NEW candidate, possibly none; preserve existing overlapping
  position rules. Data failure is not strategy-driven cash/no-candidate status.
- No infinite retries. Preserve precise checkpoints and verified recovery CLI.
  Do independent work when a path is blocked. Never promise unverified background
  execution; do not create duplicate schedulers.
- Commit code/docs only. No databases, raw responses, runtime reports, caches,
  credentials or environments. Verify actual remote main after push.
- Tests, live evidence validation, replay and real backtests are different.
  Synthetic unit fixtures must never substitute for real data or real results.
