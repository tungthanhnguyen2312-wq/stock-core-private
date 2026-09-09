# Empirical Setup Outcome Calibration V1 — Contract

`EMPIRICAL_SETUP_OUTCOME_CALIBRATION_V1`. Implemented in `empirical_setup_outcome_calibration.py`
(`CONTRACT_VERSION = "empirical_setup_outcome_calibration/v1"`). Turns the existing, deliberately
non-calibrated prospective outcome corpus into deterministic empirical setup distributions:

```
immutable T0 decision snapshot -> later observed completed sessions -> matured outcome
    -> comparable cohort -> empirical calibration
```

## Why this module, not another engine

Three existing modules already implement every stage below `empirical calibration`, and each of
them explicitly says so in its own authority boundary (`"no_probability_or_calibration": True`,
`"no_calibration_insufficient_sample": True`, `"INSUFFICIENT_SAMPLE_FOR_CALIBRATION": True`) — this
module is exactly the successor those boundaries point to, not a replacement for what they already
do correctly:

* **`prospective_decision_outcome_feedback.build_feedback_artifact()`** — corpus discovery across
  both genuine T0 sources (immutable `prospective_decision_retention/v1` snapshots and
  canonical-handoff-qualified legacy `integrated_investment_decision_product` artifacts), temporal
  qualification, and a per-(ticker, T0 session) `feedback_record` carrying the full T0 decision
  content plus forward-outcome/trigger-invalidation results. Called as-is, read-only.
* **`integrated_decision_prospective_feedback`** — the session-counted (never calendar-day)
  forward-close-return and close-only excursion calculator, reused directly. Its own
  `FORWARD_HORIZONS` contract (`{1,3,5,10,20}`) is never mutated — this milestone's own required
  horizon set (`{5,10,20,60}`) reuses `_forward_horizon`/`_close_excursion` directly for the one
  horizon (`T60`) the shared, Daily-brief-facing bridge doesn't compute, and reuses `T5`/`T10`/`T20`
  verbatim from the existing `feedback_record`.
* **`prospective_decision_retention.evaluate_serialized_close_condition`** — reused verbatim for
  invalidation-hit (and, only when a genuine T0 target exists, target-hit) event detection over the
  governed session chain.

No T0 decision is ever reconstructed retroactively: every observation traces to a genuinely
retained, content-identified decision record this module only reads.

## Prospective-only temporal contract

Horizons are `T5`/`T10`/`T20`/`T60` — completed **trading sessions** from the governed chain
(`resolve_combined_chain_and_snapshots`, the union of the two genuine T0 sources' own chains; at
least as complete as, never a subset of, either branch's chain, so T60 introduces no additional
look-ahead risk). Per horizon: `forward_return`, `mfe_close_proxy`/`mae_close_proxy` (explicitly
labelled `CLOSE_ONLY_NOT_INTRADAY_MFE_MAE`, never silently rebranded to true intraday MFE/MAE), and
`r_multiple` (forward return expressed in units of the T0 decision's own already-retained
`(entry - invalidation_level) / entry` downside fraction — never a stop-loss or execution
boundary). `invalidation.hit`/`sessions_to_invalidation` and, only when an explicit
caller-supplied deterministic target/reward boundary genuinely existed at T0,
`target.hit`/`sessions_to_target`/`target_invalidation_ordering` are computed once per observation
(event-based, not per-horizon). A missing input is always an explicit `PENDING` /
`INSUFFICIENT_FUTURE_DEPTH` / `UNAVAILABLE_*` state, never a fabricated value — `retention.
maturity_state()` is reused verbatim for T60's own maturation-state classification.

## Cohort semantics

`cohort_key()` prioritizes, in order: the feature/decision contract versions
(`integrated_investment_decision_product` + `prospective_decision_outcome_feedback` versions —
pulled from those modules' own `CONTRACT_VERSION` constants, never hand-copied strings, so a future
contract bump automatically creates a new cohort rather than silently pooling incompatible data),
`research_action_posture_at_t0` (action/posture family), `tactical_structure_state_at_t0`
(tactical/setup family), `invalidation_method_at_t0`, and `horizon`. Market regime
(`market_regime_at_t0`) is an **optional** stratification: `aggregate_cohorts()` emits a
regime-stratified variant of a cohort *alongside* (never instead of) its base cohort, and only when
every member actually retains a real regime value and the stratified split itself would still
clear the `DESCRIPTIVE_ONLY` sample floor. Cohorts are never fragmented by ticker or sector by
default.

## Sample adequacy V1 (research policy, not factual authority)

| condition | state |
|---|---|
| `< 20` matured observations, or `< 5` distinct T0 sessions | `INSUFFICIENT_SAMPLE` |
| `20-49` observations **and** `>= 5` distinct T0 sessions | `DESCRIPTIVE_ONLY` |
| `>= 50` observations **and** `>= 10` distinct T0 sessions | `CALIBRATED_RESEARCH` |

`DESCRIPTIVE_ONLY` emits sample counts and robust quantile/median distributions (forward return,
close-proxy MFE/MAE, R-multiple) but **never** a probability claim
(`empirical_positive_return_rate` stays `None`). `CALIBRATED_RESEARCH` additionally emits Wilson
score confidence intervals (`wilson_interval()`, 95% by default) for empirical frequencies
(positive-return rate, invalidation rate, target-hit rate when applicable) — always labelled
`EMPIRICAL_RESEARCH_ESTIMATE_NOT_UNIVERSAL_PROBABILITY`. No fitted parametric distribution is used
anywhere in V1; every statistic is a deterministic median/quantile/hit-rate/Wilson interval over
the actual retained observations.

## Portfolio V2 integration (bounded, optional, never automatic)

`portfolio_aware_decision.build_ticker_portfolio_aware_decision()`/`build_artifact()` gained one
new optional parameter, `calibration_artifact` (default `None`). When supplied and the ticker is a
genuine tactical decision sleeve (`sizing_mode` is `FULL_RISK_BUDGET` or `PROBE_RISK_BUDGET`),
`empirical_reward_context_for_cohort()` looks up the matching cohort by
(posture, `market_structure_state`, `invalidation_method`, horizon — default `T5`) and, **only**
when that exact cohort reached `CALIBRATED_RESEARCH`, attaches its empirical R-multiple/return
distribution as `empirical_reward_context`. Absent a calibration artifact (every real call site
today) or below `CALIBRATED_RESEARCH`, the field is uniformly `NOT_AVAILABLE`/`NOT_APPLICABLE`.

This context is **never** fed into `margin_economics` automatically: that engine's own
`reward_boundary` parameter is untouched by this milestone and stays exactly as
explicit/caller-supplied as before — `portfolio_aware_decision.py` never forces a margin value into
existence just to improve coverage, and MFE is never silently converted into an executable target.
`execution_qualified_quantity`, `portfolio_risk_quantity_ceiling`, and every other execution/sizing
field are byte-identical whether or not this hook fires (see `test_21b_...` in
`tests/test_portfolio_aware_decision.py`).

## Existing heuristic policy: unchanged

The 2.0 / 3.0 net-reward/risk margin thresholds added in
`PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1` are untouched and remain the V2 policy defaults.
This milestone measures outcomes; it does not retune those thresholds, and does not implement
Kelly sizing, CVaR optimization, or probability-based position sizing (all explicitly out of
scope for V1).

## Real retained corpus (2026-09-09)

`prospective_decision_outcome_feedback.discover_prospective_corpus()` finds exactly two genuine
T0-qualified Integrated Decision sessions today (`2026-09-03`, `2026-09-08`; a third,
`2026-09-09`, is genuine only via the separate immutable-snapshot lineage), 1,683 tickers each,
5,049 total observations across the union. Every cohort (100 across the 4 horizons) is
`INSUFFICIENT_SAMPLE` — correctly, since maturation requires at least 5 distinct T0 sessions even
for `DESCRIPTIVE_ONLY` and only 2-3 exist yet. This is not a defect: future Daily sessions will
naturally mature the retained observations and grow the distinct-session count.

## Tool

`tools/run_empirical_setup_outcome_calibration.py --root <repo>` — read-only, no Daily run, no
provider call. Prints identity/count summary by default; `--output`/`--evidence-dir` write the
full immutable artifact.
