# Three-security price experiment: frozen rule v1

Scope: **000035, 000033, 000034 only**. Formal dates remain
2015-06-01 through 2026-09-30. This is a separate research candidate, never a
replacement for the frozen baseline or continuous-sync database. Formal
backtest gates remain closed. No return computation is part of validation.

## Source selection and economic meaning

Use already captured **Sina KLC unadjusted** OHLC, shares and yuan turnover
as one explicitly identified raw series. Do not backfill provenance from
old database values. Preserve disagreements with old rows and other providers;
choosing a reproducible source is not proof every source value is correct.
Do not insert carried suspension prices or synthetic sessions.

The primary signal follows the **BaoStock reference-price adjustment factor
definition**, not a distribution-participating total-return portfolio.
BaoStock describes a factor step as previous actual close divided by the
ex-event day's reference previous close. Its captured cumulative back factor
is the input; verify event-day references separately. Never reconstruct missing
factors from a fitted price ratio. Do not interchange this definition with
Sina's equity-event treatment merely because both are called HFQ.

Set a fixed anchor at each security's required prior actual quote:

| Symbol | Anchor | Candidate ending bound |
| --- | --- | --- |
| 000035 | 2015-05-29 | 2026-09-30 |
| 000033 | 2015-04-29 | Verified last A-share trading day before delisting |
| 000034 | 2015-03-20 | 2026-09-30 |

Let `F(t)` be the captured cumulative factor effective on or before `t`.
For every OHLC field use `signal(t) = raw(t) * F(t) / F(anchor)`.
Initial scale is exactly one at the anchor, not a fit to old prices. Earlier
events cancel only as a normalization constant under this declared rule;
this does not establish their correctness or waive the 2007 distinction.
No final-date factor enters earlier signals. A separately labelled Sina-factor
control may use the same normalization but must never be spliced into primary.

Use Decimal precision 40, quantum **0.00000001**, ROUND_HALF_EVEN. This is
storage precision, not eight-decimal source accuracy. Provider factors currently
have six decimals; raw prices retain captured precision. Determinism tests
require exact canonical equality, not relaxed market-quality tolerance.
For event-reference checks propagate half the last displayed factor digit
and raw reference-price precision; retain all residuals. No rule is selected
based on returns, old-series closeness or strategy performance.

## Events and information time

Cash dividends, ordinary bonus shares, reserve transfers and rights offerings
follow the provider reference-factor step with dated reference/event evidence.
Do not add cash to OHLC or infer a rights formula without evidence. A share
reform with no exchange ex-right reference may leave this factor unchanged
even if holders receive shares. This differs from counting the holder's extra
shares; explain the distinction, not a silently corrected factor. Unclassified
events remain explicit blockers.

Record announcement, implementation and effective dates separately from
download time. Current provider tables are retrospective evidence. A dated
announcement field is not proof of the factor table's historical publication.
`historical_available_at` remains unknown unless independently established.
Effective-date truncation consistency is necessary but **not sufficient** for
full historical point-in-time safety.

Verified full-day suspension: retain status/evidence, emit no OHLC and do not
forward-fill prices. Apply the current effective factor at the next real quote.
Previous signal still means previous **actual quote**, not previous exchange
session. Unexplained gaps remain blockers. No warmup orders or positions.

## Uses and boundaries

Selector reads current/prior signal_close momentum, positive-price eligibility,
tradability and raw share-volume rank. No nonzero absolute price cutoff or
cross-security adjusted-price rank is enabled. No ATR, moving-average or
breakout window is enabled. Regime display uses 20 CSI300 closes (19 prior);
this experiment does not replace benchmarks or waive that requirement.

Other signal OHLC remain stored/validated, not new strategy inputs. Entry,
marking, percentage stops/targets, position sizing and trading use raw prices
and currency amounts. Do not pass adjusted prices to those paths or replace
VWAP with them. No parameters change. Different daily signal changes can
alter ranking/holdings and then risk inputs. A constant positive scale alone
cancels mathematically in momentum, except declared quantization effects.

Raw stop levels across corporate actions and portfolio share/cash entitlements
need separate state reconciliation. This price-only experiment does not prove
existing order/position handling corporate-action-safe. Keep that issue explicit
without adding unenabled strategy modules.

## Reproducibility and acceptance

Reuse existing snapshots, evidence manifests and atomic compare-and-set repair.
Record inputs, rule JSON, program hash, response hashes, capture times, effective
dates and output identity. Identical input/rule yields identical logical output;
repeat application writes zero. Source revision requires a new version.
Test multiple segments and future-event removal. Coverage, numerical warmup,
temporal/source evidence and quality are separate verdicts.

Legacy read-only screen uses theoretical 366-day boundaries from 2015-06-01.
Flag opposing raw/signal one-session directions with at least **0.05** absolute
difference between their fractional changes. This predeclared diagnostic screen
is NOT a quality acceptance threshold or proof of error. Require actual adjacent
market-session rows; count skipped pairs. Corporate actions, additive formulas
and source revisions must be excluded before repairs. Missing actual segment
logs limit coverage. No scanned security or 919-queue migration is authorized.
