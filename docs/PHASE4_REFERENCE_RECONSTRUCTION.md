# Reference-price reconstruction v2 (isolated three-stock candidate)

This version implements the already declared fixed-anchor reference-price
economic rule with independently reconstructable inputs. It does NOT change to
dividend-reinvestment HFQ, fit the old sequence, or replace the market baseline.
The v1 supplier-factor candidate and its 14 unresolved rounding/revision cases
remain preserved. This is authorized data-layer work under the master mandate,
not a selector/risk parameter change or formal admission.

## Fixed rule and inputs

Scope remains 000035/000033/000034, respective actual-quote anchors
2015-05-29 / 2015-04-29 / 2015-03-20, ending 2026-09-30 or actual delisting.
Start with K(anchor)=1. At each evidenced effective event, multiply K by
`previous_actual_raw_close / effective_reference_preclose`. Between events K
does not change. Signal OHLC remains `raw * K(date) / K(anchor)`.

The ratio definition is published in BaoStock's original adjustment-factor
description. The numerical inputs are original decimal raw close and daily
reference fields, independently reconciled with issuer announcements and
applicable exchange rules. They are NOT price ratios fitted to a desired HFQ.
All 15 post-anchor events must have complete reference/announcement evidence;
every non-event real quote is checked for unexplained reference discontinuity.

Exact decimal inputs are accumulated as rational numerator/denominator pairs.
An 80-significant-digit serialization is passed to the unchanged scoped
40-digit Decimal price converter; its existing single final 8-decimal
ROUND_HALF_EVEN storage remains fixed. An independent 100-digit evaluation
must yield exactly identical stored prices. No 6-decimal intermediate rounding
or market-quality tolerance is introduced. Raw source precision is not improved
by storing a derived price at eight decimals.

The 14 supplier residual cases become **comparison-only in v2**, because the
supplier cumulative values no longer enter its numerical chain; their internal
rounding/revision specification is still unknown, not certified by this change.
Sina HFQ is also comparison-only. No mixed-source HFQ segments are spliced.

## Historical semantics and limits

Separate effective event, original announcement date, previous actual quote,
current retrieval time and unknown historical download version. Reliable
pre-event announcements support reconstruction; do not claim contemporaneous
archiving. Events announced on/after the effective date require further timing
evidence and are rejected by this conservative reconstruction helper.

Do not generate suspension prices. An event during a verified halt changes K
from its effective date; the next actual quote uses it, and previous signal
still refers to the previous actual quote. The 2007 000035 share reform is
pre-anchor and does not enter this reference-price normalized series; its
shareholder economics differ from the signal definition and remain documented
in the preserved original investigation. No ordinary dividend formula is
retroactively substituted for that reform.

Corporate-action cash/shares/stop accounting, raw turnover scope, four VWAP
reader failures, and causal opening execution remain separate unresolved
dependencies. v2 does not repair or waive them. No price from v2 is used for
actual fills or returns. Volume, amount, raw OHLC, VWAP and legal limits are
unchanged by the v2 signal patch.

## Version and verification

Store full raw response/evidence hashes, each event input, exact products,
rule/program hashes, before/after values, derived-input differences and output
snapshot identity in the ignored runtime folder. Existing compare-and-set
manifests reject stale rows and changed evidence. Independently verify whole vs
segmented processing, future-event truncation, repeat application zero writes,
replay equality, coverage and unchanged execution fields. No formal pass follows
from these numerical tests alone. All migrations remain gated on pilot C.
