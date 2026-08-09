# Market Basis Capability Activation and Generic Unlock Gap Closure

**Milestone:** `MARKET_BASIS_CAPABILITY_ACTIVATION_AND_GENERIC_UNLOCK_GAP_CLOSURE`
**Date:** 2026-08-09. **Scope:** Price/Volume Basis track, continuing from
`M1_QUALIFIED_RESEARCH_LIVE_DELIVERY: PASS`.

## What this milestone found, in one paragraph

Nothing about price or volume basis was re-qualified. The repository already had two
mature, independently-earned provider-scoped basis findings (KBS's full price+volume
capability matrix, VCI's volume-composition matrix) and a canonical cross-provider price
verdict registry (`provider_price_basis_registry.py`) -- but only one live consumer
(`risk_liquidity.py`) actually called into any of them at runtime, and even that consumer
gated its own return/volatility/drawdown computation on the *generic* `price_adjustment`
flag rather than the provider-scoped verdict it had available. The KBS/VCI
`CONSUMER_CLASSIFICATION` registers were aspirational documentation: zero of the ~20 named
consumer call-sites (`candlestick_patterns.*`, `vn_indicators.*`, `stock_analyzer.*`) import
either matrix. No bundle section surfaced any of this to the research product, the Consumer,
or the Dashboard.

## What was built

1. **`market_basis_capability_registry.py`** -- one queryable registry across both
   providers. Delegates unchanged to `kbs_capability_matrix.py` (KBS, price+volume) and
   `market_volume_capability_matrix.py` (VCI volume). Fills the one real gap -- VCI never
   had a *price* capability matrix shaped like KBS's, only a flat eligibility list in
   `vci_direct_basis_pilot.py` -- with 8 new capability records built from already-recorded
   facts in `provider_price_basis_registry.py`, in the same shape KBS already uses. Adds
   the brief's Level 0-5 capability ladder as a read-only annotation, and the generic-unlock
   gap table (`generic_unlock_gap_table()`, 7 rows, see `generic_unlock_gap_table.json`).
2. **`qualified_market_observations.py`** -- the new, bounded, provider-scoped descriptive/
   technical section. Computes latest/mean/range price stats, mean/relative volume, and
   (gated behind the `provider_series_return` label both matrices already require) window
   return, realized volatility and maximum drawdown, from a single-provider retained OHLCV
   window. Fails closed on missing provenance, mixed-provider windows, unsupported
   providers, and fewer than 20 sessions. `is_actionable` and `liquidity_actionable` are
   hardcoded `False`; nothing computed here can turn them on.
3. **Producer wiring** (`export_ai_bundle.py`): `load_ohlcv_provider_purity()` -- a new,
   separate, read-only query answering "did this ticker's retained window come from exactly
   one provider" (verified: **all 11 production tickers are 100% VCI-sourced**, confirmed
   directly against `dashboard-runtime/vn_stock.db`). `ohlcv_recent`'s own shape is
   untouched; the provenance is a new, additive, always-present sibling field. New opt-in
   `--include-qualified-market-observations` flag attaches `qualified_market_observations`
   for every ticker with enough history -- **not** restricted to the `PILOT_TICKERS` set the
   historical-decision/portfolio-risk lane uses, since this depends only on OHLCV provider
   purity, which every production ticker already has.
4. **Operator wiring** (`tools/operate_stocklookup.py`): the new flag is forwarded through
   the one supported operating command, at all six of the same touch-points the four
   existing research-lane flags use -- learned directly from the 2026-08-09 DECISIONS.md
   entry recording that those four flags previously reached only `export_ai_bundle.py`
   directly, bypassing this command's verify/rollback/Consumer-validate gates.
5. **Consumer wiring** (`ai-core-private/builders/build_ticker_context.py`):
   `apply_bundle_qualified_market_observations_contract` -- verbatim pass-through, refuses
   (falls to `status: malformed`) any Producer record that isn't ticker-matched,
   `is_actionable: False`, `liquidity_actionable: False`, and (when `status == "available"`)
   correctly `descriptive_only`/`provider_scoped`. An `unavailable` Producer verdict passes
   through as-is -- it is not something the Consumer falls back from.

## Real defect found and fixed during implementation

`apply_bundle_qualified_market_observations_contract`'s own shape-validity check called
`.get()` on the raw Producer payload before confirming it was a mapping, which crashed
(`AttributeError`) instead of failing closed to `malformed` when a Producer payload was
ever malformed in a structurally surprising way (e.g. a list instead of a dict). Fixed by
short-circuiting on the already-computed `structurally_valid` (which does check
`isinstance(raw, Mapping)`) before evaluating the second condition. Covered by
`test_non_mapping_raw_is_refused`.

## What was deliberately not done

- **No Dashboard UI rendering.** `company-panel.js` reads OHLCV/RSI/volume figures from
  `screen_snapshot.csv`/`ta_signals.csv` via a completely different path
  (`load_technical_slice`), not `analysis_bundle.json`; building a rendered section for this
  new data is a distinct, UI-risk-bearing scope this milestone does not take on. The data
  reaches the bundle and the Consumer context; it is not yet rendered anywhere.
- **`risk_liquidity.py` was not modified.** Its `realized_volatility`/`downside_volatility`/
  `maximum_drawdown` stay gated on the generic `price_adjustment` flag exactly as before --
  changing that gate would touch a load-bearing, already-shipped section's output shape for
  a mechanism (branch restructuring) with real regression risk, for no gain this milestone's
  new, separately-namespaced section doesn't already provide additively and more safely.
- **No new live network acquisition.** See "Generic-unlock route selected" below.

## Generic-unlock route selected: Pillar B (unchanged from the existing roadmap)

Sections 16/19 of the handoff asked for one route to be chosen and, if boundable within
this milestone, implemented. The volume-trade-scope investigation (section 19) required no
new work: it was already closed by `docs/DECISIONS.md`'s 2026-08-04 entry "Ninety-six
fields, and none of them says put-through" (VCI) and `kbs_empirical_basis.market_scope_
contract()`'s unconditional `unknown` (KBS, no admissible evidence route exists). Both are
now cited by name in `generic_unlock_gap_table()['average_daily_volume_and_tradability']`
rather than re-probed.

For the market-cap/valuation-unlock route: **Pillar B (official corporate-action lineage
expansion)** is selected, unchanged from `docs/ROADMAP.md`'s existing "Next highest-value
milestone." It is already owner-approved and active (B1), with a concrete next bounded
input already named there: an official VSDC ex-date notice for SSI (the retained `ISS`
event has no ex-date; VCB was acquired the same way on 2026-08-08). This milestone does
**not** execute that acquisition -- a live external network request is a materially
different class of action from the source/test/doc work here, and the brief's own section
16 explicitly permits stopping at a decision package rather than executing. The decision
package is: **route = Pillar B, next input = SSI VSDC ex-date notice, mechanism = the
established B2/B3 pattern (bounded, hash-verified, rate-limited, already governed).**

## Test counts

63 new tests added (36 `test_market_basis_capability_registry.py`, 27
`test_qualified_market_observations.py`, 10 `test_ohlcv_provider_purity.py` in
`stock-core-private`; 12 `test_qualified_market_observations_contract.py` in
`ai-core-private` -- 85 total including the Consumer side). Targeted regression:
**524/526 passing** in `stock-core-private` (2 pre-existing, unrelated failures -- a
date-relative fixture drift in `test_export_ai_bundle.py::ScreenSnapshotLiveTests` and a
stale string assertion in `test_vci_contract_reconciliation.py` -- confirmed via
`git diff --stat` to be untouched by this milestone's two modified files; flagged
separately, not fixed here). **418/428 passing** in `ai-core-private` (10 pre-existing
failures, all missing-generated-artifact errors in unrelated batch/catalog/registry-shadow
tests, none touching `build_ticker_context.py`'s apply-chain).

## Production/publish status

Source and tests only. See `docs/STATE.md` for whether this shipped to the live serving
universe at the time this document is read.
