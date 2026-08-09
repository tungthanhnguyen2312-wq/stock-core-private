# Qualified market observations contract

**Status:** active · **Established:** 2026-08-09 · **Provider scope:** KBS, VCI
**Modules:** `market_basis_capability_registry.py`, `qualified_market_observations.py`
**Producer flag:** `--include-qualified-market-observations` (`export_ai_bundle.py`,
forwarded by `tools/operate_stocklookup.py`) · **Consumer:**
`apply_bundle_qualified_market_observations_contract` in
`ai-core-private/builders/build_ticker_context.py`

---

## The one-sentence version

Two provider-scoped market bases (`kbs.`, `vci.`) were already qualified and mostly
disconnected from the research product; this contract is the bounded, additive,
non-actionable section that wires the capabilities each matrix already proved safe into the
bundle, without touching the generic `price_basis_verified`/`volume_basis_verified` gate
anywhere.

---

## Layer correction this contract encodes

The generic price and volume basis are **not** the whole picture. Two layers, kept
separate everywhere in this codebase and in this section's own output:

```text
Provider-scoped basis        QUALIFIED / CAPABILITY-LIMITED
  kbs.price_basis             = empirically_event_adjusted (empirically_deduced)
  vci.price_basis              = empirically_event_adjusted (empirically_deduced)
  kbs.volume_unit               = shares
  vci.volume_unit                = shares
  kbs.volume_market_scope         = unknown
  vci.volume_market_scope          = partially_observed_but_not_qualified

Generic actionable basis     BLOCKED / SOURCE-AUTHORITY + MARKET-SCOPE + LINEAGE
  price_basis_verified   = false   (bundle root, market-wide, unchanged by this contract)
  volume_basis_verified  = false   (bundle root, market-wide, unchanged by this contract)
```

Neither provider verdict inherits the other's, and neither promotes to the generic root
fields. `market_basis_capability_registry.assert_no_cross_provider_inheritance()` and each
underlying matrix's own `assert_no_generic_field_upgrade()` enforce this structurally.

---

## The capability ladder (six rungs, annotation only)

`market_basis_capability_registry.ladder_level()` tags every capability record from every
underlying matrix with which rung its *class* occupies. It is read-only: the level explains
what a capability would need in order to be the next one safely reachable, it does not
grant anything, and every Level 4/5 capability in this repository today is
`unavailable_by_contract` regardless of its level.

| level | name | what it means |
| --- | --- | --- |
| 0 | `generic_basis_unknown_no_market_derived_capability` | no capability contract exists |
| 1 | `provider_scoped_descriptive_basis` | provider identity + basis qualified; descriptive statements about that series |
| 2 | `provider_scoped_adjusted_price_analytics` | analytics valid for the qualified adjusted series (technical indicators, provider-series returns) |
| 3 | `qualified_volume_unit_descriptive_analytics` | volume unit known (shares); basic descriptive volume computations |
| 4 | `market_scope_qualified_liquidity` | requires knowing what volume includes/excludes -- not reached by either provider today |
| 5 | `generic_raw_as_traded_authoritative_market_basis` | raw/as-traded, valuation, ranking, sizing, backtesting -- requires Pillar B |

---

## `qualified_market_observations` -- the new bundle section

One record per ticker, attached only when `--include-qualified-market-observations` is
passed. Two shapes:

```text
status = "unavailable"
  reason: ohlcv_provider_provenance_absent | ohlcv_window_mixes_more_than_one_provider |
          provider_not_in_capability_registry:<X> | ohlcv_recent_absent |
          insufficient_session_history
  provider: the provider if known, else null
  is_actionable: false · liquidity_actionable: false

status = "available"
  provider: "KBS" | "VCI"
  namespace: "provider_scoped" · descriptive_only: true
  price_basis: {price_basis, price_basis_qualification, raw_as_traded_eligible,
                historical_mutability, volume_market_scope (KBS only)}
  descriptive_price: {session_count, as_of_date, latest_close, period_high/low, mean_close,
                       capability: {...ladder-tagged registry record...}}
  descriptive_volume: {session_count, latest_volume, mean_volume, relative_volume, capability: {...}}
  return_descriptors: {window_return, realized_volatility, maximum_drawdown, sessions_used,
                        required_label: "provider_series_return", capability: {...}} | null
  is_actionable: false · liquidity_actionable: false · market_dependent: false
  prohibited_claims: [current_valuation, target_price, buy_hold_sell, ranking,
                       current_market_liquidity, position_sizing, market_impact,
                       days_to_liquidate, official_exchange_price, total_shareholder_return,
                       raw_as_traded_price, expected_return, portfolio_allocation]
```

`return_descriptors` is `null` whenever the return/technical-continuity capability itself is
unavailable for that provider (never for KBS or VCI today, since both carry a qualified
`provider_series_return`-eligible verdict) -- the field exists so a future unqualified
provider degrades to `null` rather than a fabricated number.

### Provenance and the 20-session floor

`export_ai_bundle.load_ohlcv_provider_purity()` answers "did this exact retained window
(the same one `ohlcv_recent` already returns) come from exactly one provider" by reading
`ohlcv.source` over the identical `ORDER BY date DESC LIMIT n` window -- a separate,
additive, always-present sibling field (`ohlcv_provider_provenance`), never merged into
`ohlcv_recent` itself. **Verified 2026-08-09: all 11 production tickers are 100%
VCI-sourced** in `dashboard-runtime/vn_stock.db`. A window mixing providers, or with fewer
than `qualified_market_observations.MIN_SESSIONS` (20) usable sessions, refuses rather than
computing a number from noise or blending two unqualified-relative-to-each-other bases.

### Not restricted to the fundamental-evidence pilot set

Unlike `historical_decision_analysis`/`portfolio_risk_analysis`/`qualified_research_brief`
(which only ever cover `PILOT_TICKERS` -- HPG, VNM, VCB), this section is attached for
**every** ticker in the bundle. Its only precondition is OHLCV provider purity, which is a
market-data property, not a fundamental-evidence one.

---

## Consumer pass-through

`apply_bundle_qualified_market_observations_contract` copies the Producer record verbatim.
An `unavailable` Producer verdict is a valid pass-through, not a fallback trigger. A record
is refused to `{"status": "malformed", ...}` if it fails ticker match, `is_actionable is
False`, `liquidity_actionable is False`, or (when `status == "available"`)
`descriptive_only is True` and `namespace == "provider_scoped"`. The Consumer performs no
recomputation, narrowing, or widening of anything the Producer already decided.

---

## What this contract did not change

The generic `price_basis_verified`/`volume_basis_verified` gate, `risk_liquidity.py`'s
existing `market_risk`/`liquidity_risk` output shape, the KBS and VCI matrices' own
capability records (delegated to, never re-derived), and every liquidity/execution/
point-in-time-truth capability's `unavailable_by_contract` status. No production database,
Dashboard rendering, ranking, recommendation, sizing, or backtest output.

See `docs/kbs_empirical_basis_qualification.md`, `docs/market_volume_capability_contract.md`
and `provider_price_basis_registry.py` for the underlying evidence this contract composes
and cites, never re-derives.
