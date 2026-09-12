# Canonical current-product projections — retained 2026-09-11 replay qualification

Local, no-network, no-provider-acquisition replay of `canonical_current_product_projections.py`
against the retained `2026-09-11` `daily_research_session_input_registry.json` selection and
`dashboard-runtime/screen_snapshot.csv`. Confirms `CANONICAL_CURRENT_PRODUCT_PROJECTIONS_AND_
DASHBOARD_BINDING_V1`'s core claim: both products materialize genuinely current for the session
they claim, using only already-retained, already-governed evidence.

## Result

```
RETAINED_2026_09_11_WORKSPACE = CURRENT (as_of_session=2026-09-11)
RETAINED_2026_09_11_SCREENER_MASTER = CURRENT (as_of_session=2026-09-11)
```

## Investment Decision Workspace

- `as_of_session`: `2026-09-11`
- `artifact_identity`: `investment_decision_workspace_projection/v1:208a45c47e3ac26e0e3b3f4a4661f3012d0133b895662357b306432d1b0a885c`
- `ticker_denominator`: 1,683, `zero_silent_ticker_drops`: true
- `financial_analysis_available_count`: 1,476 / 1,683
- `valuation_relative_state_distribution`: `{ABSOLUTE_RESEARCH_ONLY: 6, UNAVAILABLE: 1677}`
- `research_stance_distribution` / `entry_state_distribution` (top-level decision fields):
  100% `INSUFFICIENT_EVIDENCE` / `NONE` -- see "Known, disclosed limitation" below. This is an
  honest reflection of current axis availability, not a code defect: the same denominator, zero
  silent drops, and correct session identity as the original 2026-08-28 run are all present.
- `stale_axis_present_count`: 1,683 (every ticker; expected -- `events` is the retained
  `current_corporate_event_context/v1` snapshot, genuinely last refreshed 2026-08-21, the same
  "STALE_BUT_RESEARCH_USABLE, not a bug" finding the original 2026-08-31 milestone entry in
  `docs/DECISIONS.md` already documented for its own catalyst axis).
- Lineage (`source_artifacts`): `opportunity_context/v1:a0215bf7...`,
  `security_decision_context/v1:434488b9...`,
  `market_sector_leadership: current_market_sector_leadership_context:49607ef6...` (exact-session,
  `operations-review/current-market-sector-leadership-context-v1-20260911/`),
  `portfolio_research_context: null`, `prospective_thesis_lifecycle: null` (both genuinely
  unavailable, honestly reported, exactly like the original run's own
  `prospective_cases_available_count: 0` finding).

## Screener Master Projection

- `as_of_session`: `2026-09-11`
- `artifact_identity`: `screener_master_projection/v1:20a7f7bec6c46316f8f4f885d2fadeeedcaa366dd680e1b800a42b0c804b7f01`
- `ticker_denominator`: 1,683, `zero_duplicates`: true, `workspace_only_extras_excluded`: 0
- `price_available_count`: 952 / 1,683 (731 explicit `PRICE_UNAVAILABLE`, never silently zero)
- `sector_available_count`: 1,678 / 1,683 (5 `UNKNOWN`), `hnx_listed_display_hnx_count`: 299
- `financial_v2_available_count`: 1,476 / 1,683 (207 explicit `ABSENT`)
- `tactical_available_count`: 951 / 1,683; `tactical_entry_state_distribution`:
  `DOWNTREND 309, SELLING_PRESSURE_EASING 198, UPTREND_CONFIRMED 186, BREAKDOWN_RISK 95,
  EARLY_REVERSAL_CANDIDATE 64, SIDEWAYS_NEUTRAL 54, DISTRIBUTION_RISK 18, BASE_BUILDING 16,
  BREAKOUT_READY 11, NONE 732` -- reads from the exact-session `watchlist_tactical_entry_
  classifier` artifact via the Workspace card's nested tactical view, independent of the
  top-level decision `entry_state` limitation above.
- `research_liquidity_proxy_count`: 937, `execution_capacity_exact_blocked_count`: 1,683
  (unchanged authority: no exact execution/sizing anywhere in this product, by design)
- Lineage (`source_artifacts`): `screen_snapshot: canonical_screen_snapshot:screen_snapshot.csv`
  (exact-session, `dashboard-runtime/`), `investment_decision_workspace:
  investment_decision_workspace_projection/v1:208a45c47e...` (this run's own Workspace output),
  `financial_analysis_product_integration: financial_analysis_product_integration/v1:33ae5571...`
  (exact-session, `operations-review/financial-analysis-product-v2-20260911/`),
  `official_market_universe: current_official_market_universe:d77e16f8...` (stale-but-usable,
  `operations-review/current-official-market-universe-integration-v1-20260824/`, the same input
  the already-correct `current_decision_cockpit.json` accepts for this same axis today).

## Known, disclosed limitation: `feature_store` and `tactical_behavior_context`

`opportunity_context.py`'s stance-determination logic (`security_decision_context.py`) requires
at least one of the `fundamental` or `tactical` MAJOR_AXES to be `usable`, and `usable` for
each is gated strictly on `bool(feature_record)` / `bool(behavior)` being present --
independent of whether `watchlist`/`financial_analysis_product_context` (both genuinely
exact-session today) already populate the *display* fields for those axes. Neither
`market_wide_fundamental_feature_store` nor `tactical_behavior_context` has any recurring,
canonical-runtime materialization today: each exists only as a single one-off snapshot
(2026-08-31), retained solely inside a now-detached feature worktree
(`worktrees/stock-core-tactical-behavioral-engine-v2-20260831`,
`worktrees/stock-core-market-wide-fundamental-feature-store-v1-20260831`), never regenerated
since and never wired into any recurring pipeline step.

This module deliberately does **not** reach into those worktree-local one-off snapshots for the
canonical path -- doing so would (a) reintroduce exactly the "frozen historical snapshot
silently reused as if current" defect this milestone exists to remove, just relocated to two
different axes, and (b) create a fragile, non-portable dependency on a specific sibling
worktree's continued existence on this machine, which is not a sound foundation for a
recurring canonical materializer. Both axes are passed as `None` (a genuinely unavailable
optional axis, not a fabricated stale value), which is why the top-level `research_stance`/
`entry_state` decision fields currently resolve to `INSUFFICIENT_EVIDENCE`/`NONE` for
(honestly) every ticker, even though every other axis this milestone wires up is either
exact-session or a disclosed, genuinely-retained stale-but-usable snapshot.

**This is a real, disclosed capability gap, not a defect introduced by this milestone**: the
two axes were exactly as absent from any recurring path before this work as they are after it.
What this milestone fixes is the session-identity binding defect (the product now genuinely
claims, and is, `as_of_session=2026-09-11`, using every currently-available exact-session
input) and the Dashboard-visible symptom (a frozen 2026-08-28 artifact silently presented as
current). Recommended follow-up (a separate, later milestone, not opened here): build a
recurring, session-parametric materializer for `market_wide_fundamental_feature_store` and
`tactical_behavior_context`, matching the pattern this milestone already established for
`market_wide_current_liquidity_research` / `current_market_sector_leadership_context` /
`financial_analysis_product_v2`.
