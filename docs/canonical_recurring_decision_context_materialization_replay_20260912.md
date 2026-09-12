# Canonical recurring decision context materialization — retained 2026-09-11 replay

Local, no-network, no-provider-acquisition replay proving `market_wide_fundamental_feature_
store` and `tactical_behavior_context` are now genuinely recurring, non-historical-source
inputs to `canonical_current_product_projections.py`, and that the Investment Decision Workspace
and Screener Master Projection consume them correctly with zero denominator regression.

## Baseline

- `origin/main`: `03012a42b30bbe41001d9a0991d02be6430cf602`
- Preceding local checkpoint: `fda11ad025433700068a297be4e4edd736031e3a`
  (`CANONICAL_CURRENT_PRODUCT_PROJECTIONS_AND_DASHBOARD_BINDING_V1`)
- New worktree: `worktrees/stock-core-canonical-recurring-decision-context-v1-20260912`
- New branch: `feature/canonical-recurring-decision-context-materialization-v1-20260912`
- Requested replay session: `2026-09-11`
- Documented pre-milestone baseline: `docs/canonical_current_product_projections_replay_20260912.md`

## Source map

### Fundamental (`market_wide_fundamental_feature_store/v1`)

- Builder: `market_wide_fundamental_feature_store.build_artifact(semantic_rows, period_semantics_identity, requested_at)` — unmodified.
- Semantics source: `financial_v2_current_input_authority.resolve(root)` (pinned, versioned, force-tracked; `AUTHORITY_VERSION = "2026-09-05.1"`) + `canonical_daily_financial_v2_materialization.load_semantic_rows(authority)` — the same evidence Financial V2's own engine already reads and identity-verifies every session.
- Period/freshness semantics: periodic, not session-bound. Identity changes only when the authority itself is advanced to a newer pinned snapshot.
- Never used: `market_wide_fundamental_feature_store.DEFAULT_SEMANTICS` (module's own frozen 2026-08-31 constant); the frozen 2026-08-31 Feature Store artifact the same authority separately pins for Financial V2's own internal entity-type join (`feature_store_dir`/`expected_feature_store_identity`).
- Old historical dependency eliminated: the detached `worktrees/stock-core-market-wide-fundamental-feature-store-v1-20260831` sibling worktree is never read.
- Identity (real replay): `market_wide_fundamental_feature_store/v1:517953fff339efdb35051ffb4d9972fa08331fe4565b62a8e8f9ee7431e0b744` — distinct from the frozen snapshot's pinned identity (`...3a2c6273...`), proving a genuine fresh rebuild.

### Tactical (`tactical_behavior_context/v1`)

- Builder: `tactical_behavior_context.build_artifact(...)` — unmodified.
- Mandatory sources: `watchlist_tactical_entry_classifier` (registry-resolved, `registry_inputs["tactical"]`, already exact-session), `technical_structure_context`, `tactical_setup_tags`.
- `technical_structure_context` was already rebuilt fresh every Daily run inside `canonical_post_close_pipeline.py::_integrated_investment_decision_product()` but never persisted anywhere — fixed by persisting the already-computed artifact (zero new computation) to a new per-session path.
- `tactical_setup_tags` was never built by any canonical-runtime code path — fixed by building it best-effort, inline, from already-in-scope same-session inputs (`technical_structure`, `current_descriptive`, `current_screening`, `current_leadership`, `tactical`), mirroring the existing `tactical_confirmation_invalidation_boundaries` best-effort pattern exactly.
- Optional sources: `tactical_confirmation_invalidation_boundaries` (already retained per-session), `current_market_sector_leadership_context` (already resolved via `SUPPLEMENTARY_INPUT_TEMPLATES["leadership"]`). Absence degrades per-ticker (`BOUNDARY_ARTIFACT_NOT_SUPPLIED`, `leadership_context_available=False`), never fails the whole artifact.
- Session semantics: exact-session. `materialize_current_tactical_behavior_context` validates `registry_inputs["tactical"]["session"] == session` before calling the builder; the builder itself fails closed (`*_SESSION_MISMATCH`, `TICKER_SET_MISMATCH_ACROSS_SOURCES`) on any internal inconsistency.
- Old historical dependency eliminated: the detached `worktrees/stock-core-tactical-behavioral-engine-v2-20260831` sibling worktree is never read.
- Identity (real replay): `tactical_behavior_context:0f2ce35f441f798fd52fe0dc1cdb7366664939bf2b0e006b55e517f5b2469b9e`.

## Current materialization

New functions in `canonical_current_product_projections.py`:
`materialize_current_fundamental_feature_store_context`, `materialize_current_tactical_behavior_context`,
`_project_to_daily_tickers` (see "Architectural interaction" below). New per-session retained
artifact locations added to `SUPPLEMENTARY_INPUT_TEMPLATES` and (for the two newly-persisted
tactical inputs) to `daily_session_level2_package.session_artifact_paths()`:
`technical_structure_context_artifact.json`, `tactical_setup_tags_artifact.json` (both under
`operations-review/integrated-investment-decision-product-v1-{session}/`, alongside the existing
`tactical_confirmation_invalidation_boundaries_artifact.json`).

Retained outputs written into the Daily Research Session Operation directory (same directory as
Workspace/Screener):

- `market_wide_fundamental_feature_store_artifact.json` (summary; `records` popped out, replaced by `records_payload`, matching `tools/run_market_wide_fundamental_feature_store_v1.py`'s own scalable representation)
- `market_wide_fundamental_feature_store_records.jsonl.gz`
- `tactical_behavior_context_artifact.json`

No Dashboard binding was added for either file — both are internal supporting artifacts feeding
decision fields already exposed via Workspace/Screener, not separate public products.

## Real replay — Feature Store coverage

```
status: MATERIALIZED
artifact_identity: market_wide_fundamental_feature_store/v1:517953fff339efdb35051ffb4d9972fa08331fe4565b62a8e8f9ee7431e0b744
source_semantics_identity: market_wide_structured_financial_period_semantics/v1:ca7c2a28a9dd9e00774dcd10c2b9aa993a0fc4664e551236408287c830ad4457
ticker_denominator: 1492 / 1492   zero_silent_ticker_drops: true
tickers_with_ready_feature: 1489
tickers_with_product_ready_health_context: 1489
feature_status_distribution: {BLOCKED: 16792, PARTIAL_RESEARCH: 16, READY_RESEARCH_PROXY: 11540}
compatibility_class_distribution: {BLOCKED_INCOMPATIBLE: 16792, POINT_IN_TIME_TRAJECTORY_COMPATIBLE: 3952, SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE: 7604}
provider_source_coverage: {KBS: 1407, VCI: 1382}
generic_corporate_applicability_exclusions: 83
CURRENT_SOURCE = YES
2026_08_31_FROZEN_RUNTIME_DEPENDENCY = NO
```

## Real replay — Tactical Behavior coverage

```
status: MATERIALIZED
artifact_identity: tactical_behavior_context:0f2ce35f441f798fd52fe0dc1cdb7366664939bf2b0e006b55e517f5b2469b9e
session: 2026-09-11
candidate_count: 1683
technical_eligible_count: 951
leadership_context_available_count: 1507
boundary_available_count: 1683
entry_state_counts: {DOWNTREND: 309, SELLING_PRESSURE_EASING: 198, UPTREND_CONFIRMED: 186, BREAKDOWN_RISK: 95, EARLY_REVERSAL_CANDIDATE: 64, SIDEWAYS_NEUTRAL: 54, DISTRIBUTION_RISK: 18, BASE_BUILDING: 16, BREAKOUT_READY: 11}
entry_state_missing_count: 732
confirmation_boundary_ready_count: 386
technical_invalidation_boundary_ready_count: 699
source_artifacts: {tactical, technical_structure_context, tactical_setup_tags, confirmation_invalidation_boundaries, current_leadership} — all real identities, see raw script output
EXACT_SESSION_CURRENT_SOURCE = YES
2026_08_31_FROZEN_RUNTIME_DEPENDENCY = NO
```

`entry_state_counts` is **exactly identical** to the Screener Master's own independently-sourced
`tactical_entry_state_distribution` (below) — a strong cross-check that the new join reproduces
the classifier's real `entry_state`, not a fabricated or default value.

## Workspace before/after (2026-09-11)

| Field | Before (documented baseline) | After (this replay) |
|---|---|---|
| denominator | 1,683 | 1,683 |
| zero_silent_ticker_drops | true | true |
| Financial V2 available | 1,476 / 1,683 | 1,476 / 1,683 |
| research_stance_distribution | `{INSUFFICIENT_EVIDENCE: 1683}` | `{WAIT_FOR_CONFIRMATION: 824, AVOID_NEW_ENTRY: 422, ACCUMULATE_RESEARCH_CANDIDATE: 163, INSUFFICIENT_EVIDENCE: 190, INITIATE_RESEARCH_CANDIDATE: 54, HIGH_RISK_SPECULATION_ONLY: 30}` |
| research_stance_readiness_distribution | `{RESEARCH_NOT_READY: 1683}` | `{RESEARCH_NOT_READY: 190, RESEARCH_CONDITIONAL: 824, RESEARCH_READY_CONDITIONAL: 669}` |
| entry_state_distribution | `{None: 1683}` | `{None: 732, DOWNTREND: 309, SELLING_PRESSURE_EASING: 198, UPTREND_CONFIRMED: 186, BREAKDOWN_RISK: 95, EARLY_REVERSAL_CANDIDATE: 64, SIDEWAYS_NEUTRAL: 54, DISTRIBUTION_RISK: 18, BASE_BUILDING: 16, BREAKOUT_READY: 11}` |
| entry_action_distribution | (not separately tracked in the baseline doc) | `{None: 732, WAIT: 456, AVOID: 404, EARLY_ENTRY: 64, ACCUMULATE_IN_BASE: 16, BUY_ON_CONFIRMATION: 11}` |
| stale_axis_present_count | 1,683 (corporate event context, unrelated to this milestone) | 1,683 (unchanged; same disclosed reason) |

`DEGENERACY_REMOVED_BY_CURRENT_CONTEXT = YES`. Both axes materialized successfully; the
distributions above are real, deterministic evidence from the actual builders (not loosened
rules) — 190 tickers remain `INSUFFICIENT_EVIDENCE` because they genuinely lack both fundamental
feature coverage (outside the 1,492-ticker Feature Store universe) and tactical coverage (outside
the 951 technical-eligible / 951+ classified tickers), a real, disclosed remaining boundary, not
a defect.

## Screener non-regression (2026-09-11)

| Field | Before (documented baseline) | After (this replay) |
|---|---|---|
| denominator | 1,683 | 1,683 |
| duplicate_count | 0 | 0 |
| price_available_count | 952 | 952 |
| sector_available_count | 1,678 (5 UNKNOWN) | 1,678 (5 UNKNOWN) |
| financial_v2_available_count | 1,476 (207 ABSENT) | 1,476 (207 ABSENT) |
| tactical_available_count | 951 | 951 |
| tactical_entry_state_distribution | DOWNTREND 309, SELLING_PRESSURE_EASING 198, UPTREND_CONFIRMED 186, BREAKDOWN_RISK 95, EARLY_REVERSAL_CANDIDATE 64, SIDEWAYS_NEUTRAL 54, DISTRIBUTION_RISK 18, BASE_BUILDING 16, BREAKOUT_READY 11, NONE 732 | identical |
| research_liquidity_proxy_count | 937 | 937 |
| execution_capacity_exact_blocked_count | 1,683 | 1,683 |

Every field is bit-for-bit identical to the documented pre-milestone baseline.
`research_stance_distribution` is the only new, additive field on the Screener card (pass-through
from Workspace) — no coverage regression anywhere.

## Architectural interaction found and fixed pre-commit

`market_wide_fundamental_feature_store`'s own ticker universe (1,492, drawn from the structured
financial-semantics corpus) is not a strict subset of the Daily Product's own denominator (1,683,
drawn from watchlist/valuation). Before the fix, passing the real Feature Store artifact into
`current_valuation_opportunity_integration.build_artifacts` widened its internal `_tickers()`
union past what `financial_analysis_product_context` (itself already Daily-denominator-complete)
covers, raising `FINANCIAL_ANALYSIS_PRODUCT_SILENT_TICKER_DROP` for every extra ticker. Fixed
with `_project_to_daily_tickers()`: a transient, join-time-only view that restricts the Feature
Store's `records` to the Daily watchlist/valuation ticker set before the join — it fabricates
nothing, and never alters the retained on-disk Feature Store artifact's own full records or
identity. This mirrors `canonical_daily_financial_v2_materialization.py`'s own established
pattern of projecting Financial V2's narrower engine cohort onto "the Daily Product's OWN ticker
denominator, never the engine's own narrower cohort."

## Safety

- No historical/glob/mtime discovery anywhere in the new code (`glob(`, `rglob(`, `getmtime`, "latest" selection all absent — verified by direct source inspection and by test static guards in `tests/test_canonical_recurring_decision_context_materialization.py`).
- No network, no provider call: the replay used only already-retained local evidence, read via a bounded scratch script (`run_recurring_decision_context_replay_full.py`) that reads from the primary checkout (`C:\Projects\StockLookup\stock-core-private`, which retains real 2026-09-11 evidence gitignored out of every worktree) and writes only into a scratch operation directory outside both checkouts.
- No production DB write; no mutation of either the primary checkout or this worktree by the replay script (all `_write_json`/artifact writes in the exercised code go to the caller-supplied `operation_dir`/scratch mirror, never to the evidence-read root).
- No stale fallback: a mandatory-input gap or session mismatch for either axis is always an explicit `UNAVAILABLE` status with a reason code, never a historical or cross-session substitute.
- No authority change: Feature Store and Financial V2 remain distinct products under their own authority boundaries (`OPERATIONAL_PROVIDER_RESEARCH_ONLY`, non-actionable, non-PIT); Financial V2's own semantics/engine are untouched (only read via already-existing functions).

## Validation

- New tests: 14 (`tests/test_canonical_recurring_decision_context_materialization.py`).
- Existing fixture updated: `tests/test_canonical_current_product_projections.py::test_resolve_supplementary_inputs_missing_axis_is_none_not_an_error` (asserts against the now-larger `SUPPLEMENTARY_INPUT_TEMPLATES` dict rather than a hardcoded 3-key literal).
- Directly-relevant suites (`canonical_post_close_pipeline`, `daily_session_level2_package`, `market_wide_fundamental_feature_store`, `tactical_behavior_context`, `tactical_setup_tags`, `technical_structure_context`, `current_valuation_opportunity_integration`, `investment_decision_workspace_projection`, `screener_master_projection`, `daily_producer_pipeline`, `dashboard_release_publisher`, `canonical_daily_financial_v2_materialization`, `structured_financial_period_semantics`, `watchlist_tactical_entry_classifier`, `tactical_confirmation_invalidation_boundaries`, `current_market_sector_leadership_context`): 265 passed, 54 subtests passed, only pre-existing gitignored-evidence-gap failures remain (confirmed byte-identical set/count against the untouched `fda11ad` baseline worktree).
- Full updated W1-W4 focused-regression command: **407 passed, 1 skipped, 1 deselected** (393 baseline + 14 new), 113.65s.
- `python -m py_compile` on all modified files: clean.
- YAML parse of `.github/workflows/producer-ci.yml`: clean.
- JSON parse of `docs/ROADMAP_STATE.json`: clean.
- `git diff --check`: clean.
- `tools/stocklookup_roadmap.py --check`: drift `PASS`.

## Disposition

`CANONICAL_RECURRING_DECISION_CONTEXT_MATERIALIZATION_V1 = COMPLETE_LOCAL`.
`FUNDAMENTAL_RECURRING = YES`. `TACTICAL_BEHAVIOR_RECURRING = YES`.
`PRODUCTION_ANALYTICAL_AUTHORITY = UNCHANGED`. `RELEASE_NOT_YET_AUTHORIZED`.
Not pushed, not merged, not deployed. No successor milestone opened.
