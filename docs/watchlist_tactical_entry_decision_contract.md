# Watchlist tactical entry-state classifier contract

> **2026-08-23 closeout correction.** Four corrections were applied to the original same-day
> build, before this classifier's first use against the actual configured watchlist ahead of the
> 2026-08-24 market open: (1) `entry_action` was added as the PRIMARY should-I-enter field,
> separate from the pre-existing `action`, which is now documented as secondary and
> position-management-conditional (see "Action, horizon, and full-position gating" below); (2)
> `is_full_position_ready` is now unconditionally `False` (and `position_sizing_status`
> unconditionally `"NOT_EVALUATED"`) for every record, since position sizing is not implemented,
> replacing the old BREAKOUT_READY-conditional gate; (3) `EARLY_REVERSAL_CANDIDATE` (rule `R6`) now
> requires an independent confirming signal beyond the bare momentum-sign flip; (4) `BASE_BUILDING`
> (rule `R7`) now additionally requires no bottom-quartile relative momentum and no confirmed-down
> session today, so low volatility alone no longer qualifies a persistent weak/downtrend. See
> `docs/DECISIONS.md`'s 2026-08-23 "Watchlist Tactical Decision Closeout" entry for the full
> rationale and real-data before/after counts.

Schema/contract version: `1.0.0` / `watchlist_tactical_entry_classifier/v1`. Deterministic per-ticker
tactical entry classification for watchlist review before the next trading session, built only from
already-computed current market-wide research: `market_wide_current_descriptive_research.py`
(technical features, `trend_state`, breadth/regime descriptors, descriptive liquidity),
`current_market_screening_opportunity_comparison_foundation.py` (market-relative and sector-relative
momentum/volume percentile context), and `market_wide_current_fundamental_research.py`
(official/provider fundamental tier). No new technical indicator, ranking, feature store, or
evidence is computed anywhere in `watchlist_tactical_entry_classifier.py`.

## Inputs and identity

`build_artifact(descriptive_source, screening_source, fundamental_source, requested_at)` verifies
each input's own recorded `artifact_sha256` independently (via each sibling module's own
`content_identity()`), then verifies `screening_source` was built from exactly `descriptive_source`
(`input_lineage.current_descriptive_artifact_identity` and `session` must match). `fundamental_source`
is **not** cross-verified against the other two: its 523-member P3-F10/P3-F13 cohort is a
structurally distinct universe (different acquisition lineage, no session concept comparable to
the descriptive/screening lane's 1,510-denominator cohort). A ticker present in the
descriptive/screening universe but absent from the fundamental one reports
`fundamental_context.status = "NOT_IN_FUNDAMENTAL_COHORT"` — a data-coverage boundary, never a
session/denominator mismatch and never coerced toward `BLOCKED`.

## Two output layers

`ticker_structure_state` (5 values: `ABOVE_MA20_MOMENTUM_POSITIVE`, `ABOVE_MA20_MOMENTUM_NEGATIVE`,
`BELOW_MA20_MOMENTUM_POSITIVE`, `BELOW_MA20_MOMENTUM_NEGATIVE`, `NEAR_MA20_NEUTRAL`, plus
`NOT_AVAILABLE` when technical features are unavailable) is the ticker's own raw posture: `close` vs
`ma_20` and `momentum_20d`'s sign, with a close-vs-MA20 proximity test reusing
`price_structure_breakout_context.NEAR` (2%) — not a new threshold.

`entry_state` (the required 9-state taxonomy: `DOWNTREND`, `SELLING_PRESSURE_EASING`,
`EARLY_REVERSAL_CANDIDATE`, `BASE_BUILDING`, `SIDEWAYS_NEUTRAL`, `BREAKOUT_READY`,
`UPTREND_CONFIRMED`, `DISTRIBUTION_RISK`, `BREAKDOWN_RISK`) additionally folds in: market-relative
momentum quartile (screening's `momentum_bucket`), sector-relative momentum quartile
(`sector_relative_comparison.momentum_bucket`), today's session return sign, provider-relative-
volume confirmation (the `RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN` screen flag), and a cross-sectional
volatility regime (a ticker's `volatility_20d` compared only to the market's own contemporaneous
median from `market_breadth.volatility.median` — never a historical-compression claim). One
ordered, first-match-wins decision table (`_entry_state_rule()`, documented per-rule in
`RULE_DEFINITIONS`) produces exactly one state for every technical-eligible ticker.

`EARLY_REVERSAL_CANDIDATE` (rule `R6`) requires price at/below MA20 with positive 20-day momentum
**and** at least one independent confirming signal: market-relative momentum in the upper half of
the cohort, sector-relative momentum in the upper half of its own sector cohort, or today's return
positive together with elevated relative volume. Without a confirming signal the ticker falls to
rule `R6B` and is reported `SIDEWAYS_NEUTRAL` instead — an unconfirmed momentum tick is neutral,
not a reversal candidate. `BASE_BUILDING` (rule `R7`) requires low cross-sectional volatility with
no elevated volume **and** no bottom-quartile relative momentum **and** no confirmed-down session
today — low volatility alone no longer qualifies a persistent weak/downtrend as a base (2026-08-23
closeout correction; see `RULE_DEFINITIONS` for the exact predicates).

## Two action fields: entry_action (primary) and action (secondary)

Two separate, deliberately not conflated action fields travel with every record (2026-08-23
closeout correction). Earlier same-day code exposed only `action`, a 9→7 lookup that included
`HOLD_DO_NOT_ADD`/`REDUCE_EXIT` — position-management verbs that presuppose an existing position.
Because this pipeline has no holdings/portfolio input anywhere, those two values are meaningless as
an answer to "should I enter this ticker," so a second, primary field was added rather than
reinterpreting the first:

`entry_action` is a fixed 9→5 lookup (`ENTRY_ACTION_BY_ENTRY_STATE`) — the PRIMARY field for
"should I enter," never `HOLD_DO_NOT_ADD` or `REDUCE_EXIT`:

| entry_state | entry_action |
|---|---|
| `BREAKOUT_READY` | `BUY_ON_CONFIRMATION` |
| `EARLY_REVERSAL_CANDIDATE` | `EARLY_ENTRY` |
| `BASE_BUILDING` | `ACCUMULATE_IN_BASE` |
| `UPTREND_CONFIRMED`, `DISTRIBUTION_RISK`, `SELLING_PRESSURE_EASING`, `SIDEWAYS_NEUTRAL` | `WAIT` |
| `BREAKDOWN_RISK`, `DOWNTREND` | `AVOID` |

`action` (`ACTION_BY_ENTRY_STATE`, unchanged from the original build) remains a fixed 9→7 lookup,
now documented as SECONDARY and position-management-conditional — only meaningful if the reader
already holds the ticker, never a basis for the entry decision:

| entry_state | action |
|---|---|
| `BREAKOUT_READY` | `BUY_ON_CONFIRMATION` |
| `UPTREND_CONFIRMED` | `HOLD_DO_NOT_ADD` |
| `EARLY_REVERSAL_CANDIDATE` | `EARLY_ENTRY` |
| `BASE_BUILDING` | `ACCUMULATE_IN_BASE` |
| `SELLING_PRESSURE_EASING`, `SIDEWAYS_NEUTRAL` | `WAIT` |
| `DISTRIBUTION_RISK` | `HOLD_DO_NOT_ADD` |
| `BREAKDOWN_RISK` | `REDUCE_EXIT` |
| `DOWNTREND` | `AVOID` |

`EARLY_ENTRY` maps only from `EARLY_REVERSAL_CANDIDATE` in both lookups — deliberately not gated
behind `UPTREND_CONFIRMED`/`BREAKOUT_READY`, per this milestone's own instruction that a confirmed
uptrend must never be a prerequisite for it, preserved unchanged by the closeout correction.

## Horizon and full-position gating

`horizon` (`NEXT_SESSION_WATCH` / `SHORT_TERM_FEW_SESSIONS` / `MULTI_WEEK_SWING`) has a fixed base
value per `entry_state` (`HORIZON_BY_ENTRY_STATE`), downgraded one tier toward `NEXT_SESSION_WATCH`
when `fundamental_context.authority_tier` is `None` (not in cohort) or `BLOCKED` — missing
fundamental authority *narrows* horizon, it never forces `WAIT` by itself. `entry_state`/
`entry_action` never require `OFFICIAL_QUALIFIED` fundamentals: fundamental tier only ever modifies
`horizon` and `data_quality.confidence`, never the tactical classification itself.

`is_full_position_ready` is unconditionally `False`, and `position_sizing_status` is unconditionally
`"NOT_EVALUATED"`, for **every** record regardless of `entry_state` (2026-08-23 closeout
correction, replacing the original BREAKOUT_READY-conditional gate): position sizing is not
implemented anywhere in this pipeline, so no ticker may ever be reported ready for a full-size
position. This is enforced twice, independently: the Producer never computes anything but `False`/
`"NOT_EVALUATED"`, and Consumer's `watchlist_tactical_entry_classifier_contract()` fails a record
closed to `status="malformed"` if `is_full_position_ready` is ever anything but `False`, or
`position_sizing_status` anything but `"NOT_EVALUATED"`, regardless of what the bundle claims.

## Market state

`market_state` (`RISK_ON_BROAD_PARTICIPATION` / `RISK_OFF_BROAD_WEAKNESS` /
`MIXED_NO_CLEAR_MARKET_REGIME`) is derived once per build from
`market_wide_current_descriptive_research.market_breadth`'s own `breadth_descriptor`/
`momentum_descriptor` (both reused verbatim from `market_regime_breadth_context._descriptor()`,
never recomputed) and shared by every ticker in the same build. It is contemporaneous breadth
context only — it never gates or overrides a ticker's own `entry_state`, and is never a forecast or
timing call (`authority_boundary.market_state_is_context_not_a_forecast_or_gate_on_ticker_entry_state`).

## Evidence, confirmation, invalidation

`evidence_for`/`evidence_against` are deterministic string templates over already-computed values
only (trend, momentum sign/value/bucket, today's return, relative volume, volatility regime, sector
standing when available, liquidity, fundamental tier, market state) — never free-form generation.
`confirmation_trigger`/`invalidation` are fixed per-`entry_state` templates
(`_CONFIRMATION_TRIGGER_BY_STATE`/`_INVALIDATION_BY_STATE`); `EARLY_REVERSAL_CANDIDATE` and
`BASE_BUILDING` carry a deliberately stricter, faster `invalidation` than a confirmed-trend state's,
and neither state — nor any other — is ever described as a confirmed bottom or top
(`blocked_outputs.confirmed_bottom_or_top_claims`).

## No sizing, no forecast

`blocked_outputs` includes `portfolio_weights_or_position_sizes: "SIZING_FORMULA_NOT_YET_IMPLEMENTED"`
(reserved for a future milestone, not implemented here), `probabilities_or_target_prices:
"FORECAST_PROHIBITED"`, and `historical_raw_as_traded_or_pit: "RAW_AS_TRADED_NOT_PROMOTED"`. Every
record also carries its own `position_sizing_status: "NOT_EVALUATED"` (unconditional, see
"Horizon and full-position gating" above) so a per-ticker reader sees the boundary without needing
the artifact-level `blocked_outputs` block. No target price, probability, expected-return figure,
or position-size/share-count field exists anywhere in the artifact (verified by an explicit
key-absence test over both the synthetic test fixtures and the complete real 1,683-record output).

## Wiring

Producer flag: `export_ai_bundle.py --include-watchlist-tactical-entry-classifier`
`--watchlist-tactical-entry-classifier-path PATH` (opt-in, disabled by default; artifact's own hash
reverified before any attach; a mismatch fails the whole step closed). Runner:
`tools/run_watchlist_tactical_entry_classifier.py`. Bundle key:
`tickers[ticker].watchlist_tactical_entry_classifier`. Consumer:
`watchlist_tactical_entry_classifier_contract` / `apply_bundle_watchlist_tactical_entry_classifier_contract`
in `ai-core-private/builders/build_ticker_context.py`, byte-identical pass-through with independent
revalidation that `is_full_position_ready` is unconditionally `False` and `position_sizing_status`
unconditionally `"NOT_EVALUATED"` for every record, and that `entry_action` never carries
`HOLD_DO_NOT_ADD`/`REDUCE_EXIT`. `is_actionable=false` and `requires_human_review=true`
unconditionally at every level (artifact, per-ticker record, Consumer context) — this lane is
descriptive tactical classification for human review, never an execution instruction.
