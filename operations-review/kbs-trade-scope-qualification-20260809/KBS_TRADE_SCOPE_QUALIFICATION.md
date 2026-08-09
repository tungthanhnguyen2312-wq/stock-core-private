# KBS Trade-Scope (Market-Composition) Qualification

**Milestone:** `GENERIC_MARKET_BASIS_UNLOCK` — price authority + volume trade-scope.
**Date:** 2026-08-09. **Provider:** KBS only. **Session tested:** 2026-08-07. **Tickers:** HPG, VNM, VCB.

## The finding, in one paragraph

Two KBS endpoints already installed via `vnstock` 4.0.4 — the price board (`stock/iss`,
`vnstock.explorer.kbs.trading.Trading.price_board`) and the intraday trade tape
(`trade/history/{symbol}`, `vnstock.explorer.kbs.quote.Quote.intraday`) — were never
examined by the closed P0-Z lane, which tested only the daily chart endpoint (`data_day`).
For three tickers on one session, the intraday tape's full trading day (09:15–14:45,
matching HOSE's own session bounds) sums exactly — continuous buy/sell trades plus the
handful of side-less, auction-cleared trades — to the price board's `volume_accumulated`
(the field this repository already established is numerically identical to the
already-qualified daily `v`). The separately-reported `put_through_qty` plays no part in
that sum, in all three reconciliations, with zero residual.

## Exact numbers (frozen in `kbs_trade_scope_qualification.FROZEN_RECONCILIATIONS`)

| ticker | tape rows | continuous vol | auction vol | tape total | volume_accumulated | residual | put_through_qty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HPG | 2,751 | 11,630,500 | 1,387,600 | 13,018,100 | 13,018,100 | **0** | 200,000 |
| VNM | 4,132 | 12,888,200 | 351,300 | 13,239,500 | 13,239,500 | **0** | 500,000 |
| VCB | 2,684 | 6,330,800 | 191,400 | 6,522,200 | 6,522,200 | **0** | 857,000 |

Each ticker's tape carries exactly 2 side-less trades (one near session open, one near
session close) — consistent with one opening-auction and one closing-auction print per
session, which is how VN call auctions work.

## What this does and does not establish

**Established, `empirically_deduced` tier:**
- `continuous_matching_inclusion`: included.
- `auction_inclusion`: included (opening + closing combined; see below for why not split).
- `negotiated_trade_inclusion`: **excluded** — the headline finding. KBS's daily reported
  volume does not include put-through/negotiated trades.

**Not established, stays `unknown`:**
- `odd_lot_inclusion`: no reachable free-tier KBS surface distinguishes it. The installed
  library's own module docstring (`vnstock/explorer/kbs/__init__.py`) names a dedicated
  odd-lot detail endpoint as part of the paid `vnstock_data` Sponsor package, not the
  installed free tier. Not probed — this repository does not reach for an endpoint that
  is not already installed and reachable.

**A deliberate scope narrowing:** the intraday tape's raw `LC` (side) field is empty on
exactly the auction-cleared rows, but *which* auction (opening vs. closing) a given
side-less row is comes from `vnstock.core.utils.transform.process_match_types` — a
third-party library time-window heuristic (9:13–9:17 / 14:43–14:47 clock windows), not a
first-party KBS field. This module never relies on that split; it qualifies one combined
`auction_inclusion` dimension precisely because the *inclusion* fact (structurally, a call
auction has no directional aggressor, which is why continuous trades carry a side and
auction trades do not) is first-party-grounded while the ATO/ATC label is not.

**A corroboration that did not hold up, and was set aside:** the price board's `PMQ`/`PMP`
("previous match qty/price") fields were checked as a possible second, independent field
pinning the put-through print specifically (mirroring how VCI's ATO finding needed a second
field). They matched exactly for HPG, only on price for VNM, and not at all for VCB —
consistent with `PMQ`/`PMP` being a live "most recent trade at snapshot time" field rather
than a stable reference to the put-through print. Not relied on in the qualification.

## Evidence retained

`operations-review/kbs-trade-scope-qualification-20260809/raw/`: 4 raw HTTP response
bodies (1 price-board batch request for all 3 tickers, 3 intraday-tape requests), each with
a `.meta.json` sidecar recording URL, status, redacted request/response headers, retrieval
timestamp, and SHA-256. `kbs_trade_scope_qualification.verify_against_retained_evidence()`
reproduces `FROZEN_RECONCILIATIONS` and `FROZEN_ARTIFACT_HASHES` from these files exactly;
run it to confirm the frozen constants were not hand-edited.

11 bounded, read-only GET/POST requests were made in total across this investigation (an
initial exploratory price-board probe, three exploratory intraday pulls at increasing
page sizes, and the final 4-request evidence-retention pass), all to
`kbbuddywts.kbsec.com.vn` — the same host `kbs_empirical_basis.py` already qualified for
empirical testing — for the same three tickers that lane already scoped
(`kbs_empirical_basis.ALLOWED_TICKERS`). No production database was written; no scheduled
or repeated acquisition was set up.

## Scope limitations (carried in the empirical record, not just here)

- **One session only** (2026-08-07). `coverage_generalization` stays
  `limited_to_tested_windows`; `provider_methodology` stays `unknown`. This is not yet
  validated to hold on other trading days, market conditions, or for tickers with different
  liquidity profiles.
- **KBS-scoped only.** This finding says nothing about VCI's own volume composition, which
  remains `partially_observed_but_not_qualified` (`vci_volume_composition.py`), unchanged
  and not re-probed this pass (already exhaustively examined in the 2026-08-04 "Ninety-six
  fields" finding).
- **Not production-relevant today.** All 11 currently-served production tickers are
  100%-VCI-sourced (verified in the prior milestone) — this finding does not change any
  currently-served ticker's usable volume semantics, since none of them use KBS as their
  retained OHLCV source. It matters for KBS as the designated OHLCV failover provider, and
  for any future ticker/session that is KBS-sourced.
- **Does not by itself open any liquidity capability.** `days_to_liquidate`,
  `participation_rate_sizing`, `market_impact_estimation` and friends remain
  `unavailable_by_contract` in `kbs_capability_matrix.py` — `odd_lot_inclusion` is still
  unknown, and a single session is not enough evidence to trust a standing methodology
  claim even for the three dimensions that are resolved.

## What changed in the codebase

New `kbs_trade_scope_qualification.py` (pure classification + frozen, evidence-verified
contract, mirroring `vci_volume_composition.py`'s shape). One new capability,
`kbs_volume_composition_disclosure`, in `kbs_capability_matrix.py` (`CLASS_DESCRIPTIVE`,
available). One new, additive `volume_trade_scope` field in `kbs_capability_matrix.
matrix_snapshot()` — the pre-existing, separately-guarded `volume_market_scope` field
(sourced from the *different*, narrower `data_day`-only finding) is untouched, still
correctly reports `unknown`, and its own fail-closed assertion is unchanged.
