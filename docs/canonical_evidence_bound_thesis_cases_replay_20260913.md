# CANONICAL_EVIDENCE_BOUND_THESIS_CASES_DECISION_INPUT_V1 — Replay (2026-09-13)

Local checkpoint only. No push, merge, deploy, publish, or production DB write. No source
authority, `RAW_AS_TRADED`, PIT, valuation, or recommendation-policy change.

## 1. Existing consumer contract (traced before writing code)

`current_valuation_opportunity_integration.build_artifacts(..., thesis_cases: Mapping | None)`
already:

- reads `thesis_cases["as_of_session"]`/`["session"]` and asserts it is not future relative to
  the Daily decision session (`opportunity_axis_freshness.assert_artifact_session_not_future`);
- reads `thesis_cases["records"][ticker]` per ticker (map form, not a list) and passes it as
  `thesis=` into `opportunity_context.build_ticker_opportunity`.

`opportunity_context.py` reads exactly five fields off that per-ticker `thesis` mapping:

| field | consumed by | effect |
|---|---|---|
| `catalysts` | `_catalyst_axis` | fallback catalyst list when `events` alone don't confirm one |
| `retained_event_context` | `_catalyst_axis` | fallback `WATCH_FOR_EXECUTION` signal |
| `technical_invalidation` | `_downside_axis` | fallback when `tactical.invalidation` unusable |
| `fundamental_invalidation` | `_downside_axis` | **only source** for `downside.fundamental` |
| `counter_thesis_evidence` | `_downside_axis` | **only source** for `downside.thesis_conflict` |

`downside.fundamental`/`downside.thesis_conflict` flow straight into
`security_decision_context.build_ticker_decision`'s `fundamental_invalidation` and
`key_counter_thesis` (merged with FA V2's own separate counter-thesis contribution). At base
`1a924786…`, `thesis_cases=None` everywhere, so `fundamental_invalidation` was `UNAVAILABLE` for
100% of tickers and `downside.thesis_conflict` never had a thesis-sourced entry — the gap this
milestone closes.

## 2. Dependency DAG

```
financial_analysis_product_context (financial_analysis_engine_v2 -> financial_analysis_product_projection)
    \
     +--> current_thesis_case_context.build_artifact --> thesis_cases
    /
current_official_event_context / current_corporate_event_context (registry event_context)
```

`current_thesis_case_context.py` imports only `collections`, `hashlib`, `json`, `typing` — it
does not import `opportunity_context`, `security_decision_context`,
`investment_decision_workspace_projection`, `screener_master_projection`,
`current_research_scenario_context`, `current_evidence_bound_scenario`,
`shadow_security_recommendation`, or `portfolio_aware_decision` (verified structurally in
`tests/test_current_thesis_case_context.py::test_module_imports_nothing_downstream_of_the_
security_decision`). Both its two real inputs are already-upstream artifacts
`opportunity_context.build_ticker_opportunity` independently accepts as separate arguments today
— feeding them into this new module cannot create a new upstream dependency on any downstream
product.

**`THESIS_INPUT_DAG_ACYCLIC = YES`.**

| candidate source | classification | used? |
|---|---|---|
| `financial_analysis_product_context` (`financial_analysis_context/v2`) | `UPSTREAM_SAFE` | yes (SUPPORT/COUNTER/INVALIDATION) |
| `current_official_event_context` / `current_corporate_event_context` | `UPSTREAM_SAFE` | yes (RISK; catalysts deliberately not re-derived) |
| `tactical_confirmation_invalidation_boundaries/v1` (via `tactical_behavior_context`) | `UPSTREAM_SAFE`, already wired for `technical_invalidation` | not duplicated |
| `current_research_scenario_context/v1` | `PRESENTATION_ONLY` | no (prior milestone finding, reconfirmed) |
| `current_evidence_bound_scenario/v1` | `PRESENTATION_ONLY` | no (prior milestone finding, reconfirmed) |
| `thesis_catalyst_downside_research_cases.py` | `TEMPORALLY_INCOMPATIBLE` (frozen 13-issuer 2026-08-28 snapshot of a *different*, superseded `fundamental-plus-market-opportunity-ranking-v1` contract) | no |
| `fundamental_thesis_invalidation_precision.py` | `TEMPORALLY_INCOMPATIBLE` (depends on the module above) | no |
| `security_decision_context` / Workspace / Screener / portfolio | `DOWNSTREAM_OF_SECURITY_DECISION` | never read |
| AI narrative products | `AI_NARRATIVE_ONLY` | never read |

## 3. Basis of the two shadow modules being unsuitable

`thesis_catalyst_downside_research_cases.py`'s own `execute()` reads three fixed
`operations-review/*-20260828/artifact.json` paths, one of which
(`fundamental-plus-market-opportunity-ranking-v1-20260828`) is a *different*,
already-superseded per-ticker schema (`research_classifications`, `market_technical_strength`,
`tactical_setup`, `opportunity_research_priority`) — not the current `opportunity_context/v1`
axes (`fundamental`, `valuation`, `tactical`, `market_sector`, `catalyst`,
`downside_invalidation`, `liquidity`). It cannot advance to a new session without code changes and
is scoped to a frozen 13-issuer cohort, not the market-wide Daily denominator. Its evidence
*shape* (dual technical/fundamental invalidation, catalyst/counter/gap taxonomy) informed this
module's design; its data path was not reused.

## 4. Case taxonomy actually implemented

Per ticker: `case_classes_present` (subset of `SUPPORT`, `COUNTER`, `RISK`, `INVALIDATION` — never
forced, a ticker may have zero). `CATALYST` is not a case class this module populates (see §5).

- **SUPPORT** (`supporting_evidence`, structured, lineage-only — not read by any existing
  consumer today): a `financial_analysis_context/v2` categorical state in its positive value
  (`profitability_state=PROFITABLE`, `margin_state=MARGIN_EXPANDING`,
  `balance_sheet_state=STRENGTHENING`, `cash_conversion_state=HEALTHY`).
- **COUNTER**: two representations.
  - `counter_thesis_evidence_detail` — full structured evidence for *every* negative dimension
    (including ones `security_decision_context._financial_analysis_annotation` also tags),
    lineage/taxonomy only.
  - `counter_thesis_evidence` — the consumer-read field: short string tags
    (`FA_V2_<DIMENSION>_<STATE>`), **excluding** `PROFITABILITY`/`MARGIN`/`BALANCE_SHEET`/
    `CASH_CONVERSION` (already tagged elsewhere from the same record via the separate
    `financial_analysis` argument) — only `GROWTH_CONTRACTING` and adverse-event tags are
    genuinely additive.
- **RISK** (`risk_evidence`, structured, lineage-only): a corporate event with a genuinely
  adverse `event_status`/`event_state` (`CANCELLED`, `CONFLICTING_EVIDENCE`). **Never** a merely
  non-empty `warnings` list — see §6.
- **INVALIDATION** (`fundamental_invalidation`, the consumer-read field): one deterministic
  boundary, `FA_V2_POSITIVE_STATE_REVERSAL_BOUNDARY/v1` — the first positive dimension in a fixed
  priority order (profitability > margin > balance_sheet > cash_conversion) becomes a
  `READY`/`CONDITIONAL` watch for its paired negative value; `UNAVAILABLE` with
  `NO_POSITIVE_FA_V2_STATE_TO_INVALIDATE` when no dimension is currently positive (an invalidation
  is not manufactured from nothing).
- **CATALYST**: `catalysts`/`retained_event_context` stay explicitly `[]` with
  `catalyst_axis_reason` set — `current_corporate_event_context`/`current_official_event_context`
  already feed `_catalyst_axis` directly; re-deriving here would be noise, not new evidence.
- `technical_invalidation`: explicitly `{"status": "UNAVAILABLE", "reason": "..."}` — already
  sourced live from `tactical_confirmation_invalidation_boundaries/v1` via `tactical_behavior_
  context`'s own `invalidation` field whenever tactical is usable.

## 5. Fact vs. inference / no presentation prose

Every SUPPORT/COUNTER/INVALIDATION item is built from `financial_analysis_context/v2`'s
categorical `*_state` fields only. `positive_evidence`/`negative_evidence`/`conflicting_evidence`
(human-readable prose, e.g. `"AAA: profitable retained net income"`) are never read —
`presentation_only_sourced_cases` is `0` in every real replay
(`coverage.presentation_only_sourced_cases`), verified by
`tests/test_current_thesis_case_context.py::test_presentation_only_sourced_cases_is_always_zero`
and the prose-rejection assertions in `test_supporting_and_counter_evidence_map_from_fa_v2_
categorical_states_only`.

## 6. Two self-caught defects, fixed before the checkpoint

1. **RISK overclassification.** First draft treated any event with a non-empty `warnings` list
   as adverse. Running the real 2026-09-11 `current_official_event_context/v1` corpus through it
   showed every single retained event — routine `CASH_DIVIDEND`/`AGM` events included — carries
   one of three fixed, templated authority-boundary disclaimers in `warnings` (e.g. *"No event
   impact, probability, score, target, or recommendation is derived."*), 4,444 occurrences across
   the corpus, zero of them adverse. That draft fabricated RISK on **1,101 of 1,683 tickers**
   (65%) from pure boilerplate. Fixed: `_risk_evidence` now requires a genuinely adverse
   `event_status`/`event_state` (`CANCELLED`/`CONFLICTING_EVIDENCE`); the real corpus has none
   today, so RISK is honestly `0` market-wide (see §8) rather than a suppressed or invented
   signal. Regression test:
   `test_routine_boilerplate_warning_is_never_treated_as_risk_evidence`.
2. **Counter-thesis type/duplication defect.** First draft put full structured evidence dicts for
   all four FA V2 paired dimensions directly into `counter_thesis_evidence`. That field flows
   verbatim into `security_decision_context`'s `key_counter_thesis`/`counter_thesis` — a list
   every other contributor populates with short string tags, never objects — and
   `security_decision_context._financial_analysis_annotation` already independently tags
   `PROFITABILITY`/`MARGIN`/`BALANCE_SHEET`/`CASH_CONVERSION` negative states from the *same*
   record via its own separate `financial_analysis` argument, so re-emitting them here would
   double-count one observed fact as two list entries and mix types in one list. Fixed: the
   consumer field is now a tag list restricted to non-duplicate dimensions
   (`GROWTH_CONTRACTING`, adverse events); full detail moved to `counter_thesis_evidence_detail`.
   Regression test: `test_counter_thesis_tags_never_duplicate_what_the_fa_v2_decision_annotation_
   already_tags`.

## 7. Zero silent drops

`current_thesis_case_context.build_artifact` is built over exactly the caller-supplied
`daily_tickers` (watchlist ∪ valuation — the same formula
`materialize_current_investment_decision_workspace` already uses to project `feature_store`),
never the wider `financial_analysis_product_context`/event-context universe, and never narrower:
`set(records) != set(daily_tickers)` raises `THESIS_CASE_SILENT_TICKER_DROP`. A ticker with
neither source available still gets a full record (`case_classes_present: []`,
`fundamental_invalidation: UNAVAILABLE`, explicit `evidence_gaps`) — never dropped, never a
fabricated neutral case.

## 8. Real 2026-09-11 retained replay

No network, provider, database, or publish. Root: the primary checkout's retained
`operations-review/` evidence for 2026-09-11 (this feature worktree's own `operations-review/` is
gitignored/worktree-local and empty, per established convention — code ran from this worktree,
data resolved from the primary checkout, same pattern prior milestones used).

```
ticker_denominator:              1,683
zero_silent_ticker_drops:        true
tickers_with_>=1_eligible_case:  1,361
tickers_with_zero_eligible_cases:  322
case_class_ticker_counts:        SUPPORT 1,164 | COUNTER 830 | RISK 0 | INVALIDATION 1,164
fundamental_invalidation_status: READY 1,164 | UNAVAILABLE 519
presentation_only_sourced_cases: 0
source_artifacts.financial_analysis_product_context: financial_analysis_product_integration/v1:33ae5571...
source_artifacts.corporate_event_context:            current_official_event_context:98c83c3c...
artifact_identity: current_thesis_case_context/v1:eba14f71fc6dc000a2db677bb9315c37c7b4ef380a39cd6407c82330282ad311
```

`supplementary` availability this run: `liquidity` AVAILABLE, `leadership` AVAILABLE,
`financial_analysis_product_v2` AVAILABLE, `tactical_boundaries` AVAILABLE,
`technical_structure`/`tactical_setup_tags` **UNAVAILABLE** — the retained corpus is missing
`operations-review/integrated-investment-decision-product-v1-20260911/{technical_structure_
context,tactical_setup_tags}_artifact.json`, so `tactical_behavior` is `UNAVAILABLE`
(`TACTICAL_BEHAVIOR_MANDATORY_INPUT_MISSING`) for this specific replay. This is a **pre-existing
source-availability gap unrelated to this milestone** (confirmed absent everywhere searched: this
worktree, three sibling worktrees, and the primary checkout) — it does not block `thesis_cases`,
which depends only on `financial_analysis_product_context`/`event_context`.

## 9. Workspace/decision before vs. after (same resolved 2026-09-11 inputs, thesis_cases=None vs. wired)

| metric | before | after |
|---|---|---|
| `security_decision_context` denominator | 1,683 | 1,683 |
| `research_stance_distribution` | `{WAIT_FOR_CONFIRMATION: 1473, INSUFFICIENT_EVIDENCE: 210, rest 0}` | **identical** |
| `fundamental_invalidation` status distribution | `{UNAVAILABLE: 1683}` | `{READY: 1164, UNAVAILABLE: 519}` |
| tickers with non-empty `key_counter_thesis` | 815 | 841 (+26, all `FA_V2_GROWTH_CONTRACTING`) |
| `entry_state` distribution | `{None: 1683}` (tactical_behavior unavailable this replay) | identical |
| Financial V2 coverage (`financial_analysis` status available) | 1,683 | identical |

`research_stance_distribution` is intentionally unchanged: the current decision policy treats
thesis cases as supporting evidence (`key_counter_thesis`, `fundamental_invalidation` display
fields), never a posture override, and this replay's `tactical_behavior` gap independently caps
every stance at `WAIT_FOR_CONFIRMATION`/`INSUFFICIENT_EVIDENCE` regardless of thesis input — this
is the milestone's own explicitly acceptable outcome (step 20), not a defect.

## 10. Sample traces (real 2026-09-11 retained evidence, contract trace only)

| ticker | case classes | `counter_thesis_evidence` tags | `fundamental_invalidation` | `security_decision_context.research_stance` |
|---|---|---|---|---|
| AAA | SUPPORT, COUNTER, INVALIDATION | `[]` (only duplicate-covered `BALANCE_SHEET` observed) | `READY` (`PROFITABILITY` → watch `LOSS_MAKING`, as_of `2026-Q1`) | `WAIT_FOR_CONFIRMATION` |
| AAN | SUPPORT, COUNTER, INVALIDATION | `["FA_V2_GROWTH_CONTRACTING"]` | `READY` (`PROFITABILITY` → watch `LOSS_MAKING`, as_of `2026-Q1`) | `WAIT_FOR_CONFIRMATION` |
| A32 | *(none — zero eligible cases)* | `[]` | `UNAVAILABLE` (`FA_V2_CONTEXT_ABSENT`) | `INSUFFICIENT_EVIDENCE` |

No ticker in the real 2026-09-11 corpus carries `RISK` evidence (§6/§8) — no risk-evidence sample
row exists to report; this is the honest result, not an omission.

## 11. Temporal / lineage semantics

Each evidence item's `as_of` is the FA V2 record's own `as_of_financial_period` (a financial
period identity, e.g. `2026-Q1`) — **not** the Daily `as_of_session` — preserving financial
evidence's periodic knowledge-availability exactly as `canonical_current_product_projections.py`
already treats `feature_store`. The per-ticker record's own `as_of_session` field is the Daily
session, kept as a separate, correctly-labeled field. `lineage.financial_analysis_source_identity`
= the FA V2 record's `lineage_ref`; `lineage.corporate_event_source_session` = the event record's
own `research_session`. No file mtime, machine path, worktree path, or wall-clock timestamp enters
`artifact_identity` (`requested_at` is excluded before hashing; verified deterministic across two
builds with different `requested_at` in
`test_deterministic_identity_same_inputs_same_identity`).

## 12. Screener non-regression

Screener Master Projection is unaffected by this milestone (it is not wired to `thesis_cases`);
the real 2026-09-11 replay's Screener-relevant coverage fields (denominator 1,683, zero
duplicates, price/sector/Financial V2/tactical coverage) are unchanged from the immediately
preceding milestone's documented baseline (`docs/canonical_recurring_thesis_portfolio_context_
replay_20260913.md`), confirmed by the unmodified `materialize_current_screener_master_
projection` call path and `tests/test_canonical_current_product_projections.py`'s existing
Screener tests passing unmodified.

## 13. Tests

New: `tests/test_current_thesis_case_context.py` (20 tests) — deterministic identity, same-input
same-output, per-case-class evidence mapping (SUPPORT/COUNTER/RISK/INVALIDATION), the two
self-caught-defect regressions (§6), no-fabrication on missing evidence, zero ticker drop, no
probability/target/expected-return/action/sizing fields anywhere, no `presentation_only_sourced_
cases`, temporal/lineage preservation, DAG/import-boundary structural checks, `build_artifact`
signature shape, and an end-to-end smoke test feeding a real thesis artifact into
`current_valuation_opportunity_integration.build_artifacts` and confirming
`fundamental_invalidation` reaches the decision record.

Updated: `tests/test_canonical_current_product_projections.py` — `unavailable_recurring_context_
axes()` now only declares `portfolio`; new test confirms `thesis_cases` materializes over the
Daily denominator with legitimately-zero cases when no FA V2/events are supplied; top-level test
confirms the artifact is written to disk and `thesis_cases` no longer appears in
`unavailable_optional_axes` on success.

Targeted regression run (not the full W1–W4 matrix — no changed module in this milestone belongs
to that suite):

```
tests/test_current_thesis_case_context.py            20 passed
tests/test_canonical_current_product_projections.py  18 passed, 1 skipped (pre-existing, unrelated)
tests/test_current_valuation_opportunity_integration.py  passed
tests/test_security_decision_context.py                  passed
tests/test_investment_decision_workspace_projection.py   passed
tests/test_production_call_shape_smoke.py + tests/test_canonical_daily_operation.py:
  48 passed, 1 pre-existing failure (test_isolated_2026_08_26_full_replay_reaches_published_
  without_dispatch) -- confirmed caused by this worktree's gitignored/worktree-local
  operations-review evidence being absent (a known, documented pattern -- see
  feedback_stocklookup_runtime_path_split / prior worktree cross-checkout mismatches), not by
  this milestone's change. Not modified, not in scope.
```

## 14. Authority effect

`NONE / DETERMINISTIC_THESIS_CONTEXT_MATERIALIZATION_AND_INTEGRATION_ONLY`. No provider/source
authority added or changed. No `RAW_AS_TRADED` or PIT promotion. No probability, target price,
expected return, action, or sizing ever emitted (`blocked_outputs`, verified by
`test_no_probability_target_price_expected_return_action_or_sizing_fields`). Portfolio remains
out of scope, unchanged, private-local, post-security-decision.

## 15. Remaining open gates (not addressed here, out of scope)

- `tactical_behavior` is `UNAVAILABLE` for 2026-09-11 in the retained corpus
  (`technical_structure_context`/`tactical_setup_tags` files absent) — a pre-existing
  source-availability gap, unrelated to `thesis_cases`, caps this replay's `research_stance_
  distribution` regardless of thesis input.
- `opportunity_context._catalyst_status`/`_map_event_status` match against an `event_status`
  vocabulary (`CONFIRMED_UPCOMING`/`CONFIRMED_RECENT`/`PLANNED_NOT_EXECUTED`) that the real
  production `current_official_event_context/v1` records do not carry (they use `event_state`:
  `PAST`/`RECENT`/`UPCOMING`/`DATE_INCOMPLETE`) — a pre-existing field-name mismatch discovered
  while building `_risk_evidence`, in code this milestone does not own or modify. Flagged, not
  fixed.
