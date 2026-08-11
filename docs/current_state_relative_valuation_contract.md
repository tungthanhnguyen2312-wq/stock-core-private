# Current-state relative valuation contract

Schema/method version: `1.0.0` / `current_state_relative_valuation_v1_current_price_x_official_current_shares`.
`market_cap`, `pe`, `pb`, `ps`, `enterprise_value`, `ev_sales`, `ev_ebitda` from the qualified
DNSE current-state price (`dnse_current_state_price_analytics.py`, reused verbatim) times official
current common shares outstanding (`share_transition_bridge.resolve_share_transition`, fed only
by `data/official-evidence/share_basis_citations.jsonl`), against already-qualified historical
canonical financial denominators (`relative_valuation._qualified`, reused verbatim). Evidence-
bounded to the same ticker gate as DNSE current-state price analytics (currently HPG, VCB).

Every available method carries `as_of_semantics = "current_market_price_on_qualified_historical_fundamentals"`
— never "TTM", "forward", or "current earnings" — because it deliberately relates a *current*
price to an *older* qualified financial period. One current share count feeds every metric (not
relative_valuation.py's period-end/weighted-average split, which values a *completed* reporting
period against its own contemporaneous price; there is no "weighted-average during the still-open
current period" to compute). `is_actionable` is always `false`, at both the lane and method level.

Current shares are qualified for a session only when `resolve_share_transition`'s own
`coverage_through` reaches that exact session — never inferred forward from a stale corroboration
(deliberately not `market_wide_current_shares_resolver.py`'s more permissive lane). A blocked
current-shares leg blocks every method; a metric is never partially computed from a mix of
qualified and unqualified inputs.

`historical_comparison` reads the ticker's own `relative_valuation` bundle section read-only and
never recomputes it. A method is `comparable` only when both sides are `state="available"`, share
`denominator_identity` and `statement_scope`, and the historical side is `historical_only=true`;
otherwise `incomparable` with reasons. A comparable result exposes `multiple_change_pct` as a
plain descriptive delta only — never a cheap/expensive, buy/sell, or target-price conclusion.

Producer flag: `export_ai_bundle.py --include-current-state-relative-valuation` (opt-in, disabled
by default). Bundle key: `tickers[ticker].current_state_relative_valuation` — distinct from the
pre-existing `relative_valuation` (historical, untouched) and from
`ticker_capability_matrix.market_actionable.current_valuation` (an unrelated, market-wide generic
capability-status slot from `market_basis_capability_registry.py`, also untouched). Consumer:
`apply_bundle_current_state_relative_valuation_contract` in
`ai-core-private/builders/build_ticker_context.py`, byte-identical pass-through.

See `current_state_relative_valuation.py`'s module docstring for the full rationale, including the
three independent evidence-loader gaps (a `manifest.json` registration gap for HPG's period-end/
EBITDA-component evidence document, and a separate flat-path bug in
`official_evidence.load_cited_financial_records`) this milestone discovered while wiring this
contract but did not fix (shared, pre-existing infrastructure, out of scope).
