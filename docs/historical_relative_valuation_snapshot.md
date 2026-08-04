# Historical Relative Valuation Snapshot (HPG, FY2024 year-end)

> **Superseded 2026-08-04.** The reasoning below is wrong in both of its steps and the
> citation it rests on is now rejected. `raw_as_quoted_no_adjustment_applied` records that
> *this repository* applied no adjustment, not that VCI returned none; and a
> back-adjustment comes from events **after** the cited date, so "the 2024 action had
> already settled" looks the wrong way down the timeline. HPG's 2025-06-26 and 2026-05-25
> share issues both post-date 2024-12-31, and 19,830 is not on the 50 VND HOSE tick, so it
> was never a matched order price. See `provider_price_basis_registry` and
> `operations-review/vci-contract-reconciliation-20260804/`.

Bounded to HPG, one valuation date: the last trading session on or before
2024-12-31, which is 2024-12-31 itself (a valid session, no fallback search
needed). Never the live/current price or `issue_share`.

## Qualified price

`data/official-evidence/market_price_citations.jsonl`: ticker HPG, exchange
HSX, trading_date 2024-12-31, close 19,830 VND, provider VCI, from the
`ohlcv` table (`dashboard-runtime/vn_stock.db`, read-only; never written to).
`adjustment_status: raw_as_quoted_no_adjustment_applied` -- HPG's only 2024
corporate action (a 10% stock-dividend bonus issue) settled by 2024-06-27,
well before this date, so the price and the FY2024 period-end share count
are already mutually consistent; no back-adjustment is performed or needed.
`semantic_evidence_bridge.load_verified_market_price` re-queries the live
table on every call and fails closed if the row is missing, the cited value
has drifted, the citation conflicts with another, or `adjustment_status` is
outside the one supported value -- there is no PDF/manifest hash here; the
database row itself is the evidence.

## Share identities (never aliased)

Reuses the two facts already qualified in `share_basis_qualification.md`
(Note 27 period-end 6,396,250,200; Note 40.1 weighted-average basic
6,396,250,200 -- numerically equal this year, kept as separate citations).
`relative_valuation.py`'s single, conflated `share_count` input is replaced
with two explicit keys:

- `share_count_weighted_average_basic` -- P/E only.
- `share_count_period_end` -- P/B, and historical market-cap reconstruction
  (reused for P/S and EV/Sales).

Supplying one never satisfies the other, even when their values are equal
(`tests/test_historical_relative_valuation_snapshot.py::test_pe_and_pb_share_identities_never_aliased`).

## Market cap and results

Historical market cap = qualified close x period-end shares, only when
`current_price.financial_period` matches the period-end share count's own
period exactly (`_resolve_market_cap`); a direct `market_cap` input (an
externally-supplied, already-qualified figure) still takes priority when
present, unchanged from before. P/B and P/S divide this one reconstructed
market cap by shareholders_equity/revenue; EV/Sales adds already-qualified
`total_debt`/`cash_and_equivalents`. P/E is computed separately, from price x
weighted-average shares, never from the reconstructed market cap.

At 2024-12-31: P/E 10.55, P/B 1.11, P/S 0.91, EV/Sales 1.46. EV/EBITDA stays
unavailable -- `ebitda` was never qualified and is not derived here.

## Wiring

`export_ai_bundle.py` adds `_historical_relative_valuation_price`,
`_relative_valuation_period_end_share_count`, and
`_relative_valuation_weighted_average_share_count`, and feeds them into the
single `evaluate_relative_valuation` call site (previously fed the live
`snapshot_rows` price and no share count at all). `_net_net_share_count` and
the `evaluate_intrinsic_valuation` call site are untouched -- Net-Net keeps
its own, separately-qualified live-price-actionability signal, out of scope
for this milestone.
