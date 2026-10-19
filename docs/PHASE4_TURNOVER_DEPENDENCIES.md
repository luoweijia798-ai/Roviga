# Remaining turnover dependencies — 2026-10-19

Read actual HEAD, not the old report's blanket consumer claim. This review
starts at bd1308e. Candidate revision 6 remains SHA256
`82ea94b71c49c70c1ab47f944f8613506cf9c0923b70d50bd55b595d449b382a`.
No raw values changed, no new historical quotes, no return calculation.

## Four anomalies, not four identical runtime dependencies

| Security/date | Raw price range (yuan) | Volume (shares) | Amount (yuan) | Current SQLite OPEN dependency |
| --- | --- | --- | --- | --- |
| 000033 / 2015-04-29 | 10.38–10.38 | 8,184,168 | 84,951,664 | Warmup: previous signal price only; this row's VWAP/volume/amount not used |
| 000034 / 2015-08-28 | 10.12–10.12 | 1,701,941 | 17,223,642 | Formal `bars_on` rejects before selection |
| 000035 / 2015-07-17 | 21.09–21.09 | 2,320,500 | 48,939,344 | Formal `bars_on` rejects before selection |
| 000035 / 2021-11-12 | 5.63–5.63 | 19,163,759 | 107,891,963 | Formal `bars_on` rejects before selection |

Raw anomaly count remains **4**, formal runtime reader blockers **3**, unused
warmup VWAP **1**. This is dependency classification, not a price repair or a
claim that source precision has been verified. Direct `previous_bar` or an
eager in-memory HistoricalBar loader still rejects the warmup row. This finding
applies only to the inspected SQLite path/current enabled indicators; recheck
if a future enabled indicator starts consuming that row's other fields.

The actual SQL `daily_snapshot` selects the previous `signal_close` with a
scalar query, not `previous_bar`. A real read-only trace on 2017-05-24 recovered
000033's prior signal close 10.38 from 2015-04-29 and read its formal bar
successfully. No selector, broker or backtester was invoked. Regression tests
cover this distinction; the HistoricalBar strict check is unchanged.

## Scope overlap and actual fields

| Security | Actual quote interval | All quote rows | Formal volume-dependent rows | Warmup price-only rows |
| --- | --- | ---: | ---: | ---: |
| 000035 | 2015-05-29..2026-09-30 | 2,455 | 2,454 | 1 |
| 000033 | 2015-04-29..2017-07-06 | 31 | 30 | 1 |
| 000034 | 2015-03-20..2026-09-30 | 2,371 | 2,370 | 1 |
| Total | Applicable periods, not calendar filling | 4,857 | 4,854 | 3 |

The four anomaly rows are all within the three scope intervals: **4,857 unique
quote rows**, not 4,861. 000033's old requirements end at delisting 2017-07-07;
its last actual quote is 2017-07-06, not a newly discovered missing day.

- `StockSelector._is_eligible` and `_volume_percentile_ranks` use current volume.
  Its cross-security ranking matters even if a stock is never purchased.
- OPEN entry price and sizing reference use raw `open`; raw `close` and price
  levels remain account/stop inputs. VWAP is not an OPEN fill or scoring factor.
- `bars_on -> _row_to_bar -> HistoricalBar` still validates present formal VWAP.
- Amount enters the ratio and quality validation, not the selector or direct
  sizing. Warmup volume/amount do not enter this scalar previous-price query.
- Supplier cumulative factors and Sina HFQ remain comparison-only for v2;
  their unresolved precision cannot be promoted into a new actual v2 input.
- OPEN is the executable default, not a formally frozen/validated fill contract.
  Whole-day locks, capacity, corporate-action account treatment and dated costs
  remain previously identified prerequisites. No mode or model changed.

## What source evidence does and does not establish

Installed AKShare 1.18.91 / BaoStock 0.9.1 / requests 2.34.2 were inspected,
not upgraded. [AKShare's primary interface documentation](https://akshare.akfamily.xyz/data/stock/stock.html)
identifies the Sina daily volume as shares and amount as yuan. It does not
specify KLC's historical auction/block/off-session inclusion or publisher rounding.
Current Sina quote/tick page labels are other interfaces, not that missing contract.
The BaoStock historical documentation retrieval failed in the web tool; that
is not evidence about its SDK/network or a reason to repeat market downloads.

Local `sina_archive.archive_frames` preserves raw decoded volume/amount, with
multiplier 1, without the SDK's unrelated share-capital merge/forward fill.
Known KLC decoder quantization is not a publisher precision guarantee. Existing
raw replay/cross-source overlaps do not establish the missing trading scope.
No rounding interval was invented, no exception was silently marked resolved.

Still needed: the four original daily aggregates plus an authoritative definition
of matching OHLC/volume/amount trade scope and historical publishing precision,
or a documented reliable replacement source for the affected actual input range.
An already licensed client's original export plus field documentation may help;
availability is unverified, no purchase or credential request is implied.

## Concrete adapter defect repaired, not a false data pass

The old `_bounded_vwap` silently clamped deviations below 0.005 to low/high and
turned larger deviations into None. That violated the no-clamping requirement.
The helper now checks the decimal raw amount/quantity ratio strictly and raises
with original amount, quantity, bounds, security and date. HistoricalBar validation
remains intact. Explicit conflicts use the existing source-review retry state on
all exchanges, rather than recurring as network failures. Valid values retain
their original semantics. Zero/missing turnover remains unavailable, not a price.

This protects new ingestion only. Existing live rows have **not** been rewritten
or certified; candidate evidence is unchanged. New failures may expose conflicts
previously hidden by the clamp. They are retained for evidence review, not skipped.
The old test that required clamping was replaced by strict rejection plus an
adapter-to-ledger regression: no clamped row inserted, failure retained, no repeat
request against unchanged evidence/range. No threshold relaxation.

## Acceptance

A coverage/replay and declared v2 B conclusions stand. All three still fail C:
formal turnover scope is unresolved, 000034/000035 also have runtime VWAP conflicts,
and the existing execution-model/configuration limitations remain. No controlled
migration/full-market admission/Phase 5A is eligible yet. Raw-data anomalies and
unused-field limitations remain recorded separately. The old reports/snapshots
are preserved; this dependency correction does not rerun the unchanged full audit.
