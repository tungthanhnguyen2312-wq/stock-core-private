# Current Event Catalyst Decision Semantics Corrective V1 — Replay (2026-09-13)

Local checkpoint only. No network, provider, database, publish, deployment, or authority
promotion occurred.

## Production event contract and root cause

The canonical Daily path is `daily_research_session_operations.resolve_inputs()` → registry
`event_context` → `canonical_current_product_projections.materialize_current_investment_decision_workspace()`
→ `current_thesis_case_context.build_artifact()` and
`current_valuation_opportunity_integration.build_artifacts()`. For the retained 2026-09-11
session, the registry resolves `current_official_event_context/v1`, identity
`current_official_event_context:98c83c3c180fe28c98719b4b83a214570629ea5f491fd05feb3d6d28f5261391`,
produced by `current_official_event_context.build_artifact()` and retained from the source's
`research_session=2026-09-05` artifact.

Its ticker key is `ticker`; event identity is `event_id` (with `source_record_identity` and
`source_identity` retained alongside it). Its field is `event_state`, with exactly `UPCOMING`,
`EX_DATE_TODAY`, `RECENT`, `PAST`, `DATE_INCOMPLETE`, or `UNKNOWN`; it does not publish
`event_status`. Event-date semantics are explicit `ex_date`, `record_date`, and `execution_date`,
never inferred. `published_at` and `official_observed_at` carry their own availability state;
`qualification`, `materiality_status`, `publication_availability`, `pit_suitability`, `warnings`,
and per-event reason/identity fields remain source evidence. There is no amendment/supersession
field. The old opportunity path read `event_status` directly, so it did not interpret the actual
canonical contract correctly.

`current_corporate_event_context/v1` remains a separate legacy normalized contract. Its
`event_status` vocabulary is interpreted only when that exact version is declared; neither
vocabulary is silently mapped into the other.

## Classification contract

`current_event_catalyst_classification/v1` is now the single version-aware boundary used by
both thesis and opportunity/security integration. It preserves source dates and source temporal
state; it does not infer an event date, execution, probability, impact, target, action, or sizing.

| Source condition | Classification | Decision treatment |
|---|---|---|
| Official current/recent qualified price/share event | `POSITIVE_CATALYST` | Eligible catalyst with source lineage |
| Official AGM/informational governance event | `NEUTRAL_INFORMATION` | Retained context, not a catalyst |
| Official `PAST` | `INELIGIBLE` | Not a current catalyst |
| Official incomplete/unknown date state | `UNRESOLVED` | No fabricated temporal conclusion |
| Legacy cancelled/conflicting event | `NEGATIVE_CATALYST` | Adverse/superseded context, never active positive catalyst |
| Unknown state or contract | `UNRESOLVED` | Explicit reason code, no fallback |

Official positive classification additionally requires `CASH_DIVIDEND`, `STOCK_DIVIDEND`,
`BONUS`, or `RIGHTS`, `PRICE_SHARE_AFFECTING`, and `EX_DATE_OFFICIAL_QUALIFIED`. The retained
official contract has no separate amendment/supersession field. Its declared state is therefore
preserved; legacy `CANCELLED` and `CONFLICTING_EVIDENCE` are treated as adverse/superseded, never
retained as active catalysts. Fixed boilerplate warnings are ignored as non-signal.

## Retained 2026-09-11 replay

The bounded replay used the production materialization path and the registry-resolved local input.
Daily denominator: 1,683; event tickers: 1,101; retained events: 4,444; duplicate source-event
identities after boundary deduplication: 0; legacy-field usage: 0; unrecognized source states: 0.

| Source `event_state` | Count |
|---|---:|
| `PAST` | 4,258 |
| `RECENT` | 139 |
| `UPCOMING` | 41 |
| `DATE_INCOMPLETE` | 6 |

| Classification | Events | Reason |
|---|---:|---|
| `POSITIVE_CATALYST` | 112 | `CURRENT_QUALIFIED_PRICE_SHARE_EVENT` |
| `NEUTRAL_INFORMATION` | 44 | `INFORMATIONAL_GOVERNANCE_EVENT` |
| `INELIGIBLE` | 4,282 | 4,258 past; 24 currently unqualified price/share events |
| `UNRESOLVED` | 6 | `TEMPORAL_OR_EVENT_STATE_UNRESOLVED` |
| `NEGATIVE_CATALYST` | 0 | No retained adverse legacy event |

There are 108 tickers with eligible catalysts. Examples, with source identities retained in the
artifact: `ACE` cash dividend / `RECENT` → positive; `ACE` AGM / `RECENT` → neutral; `A32` cash
dividend / `PAST` → ineligible; `DSG` cash dividend / `DATE_INCOMPLETE` → unresolved. The first
three also demonstrate why the ubiquitous warning text cannot be treated as adverse evidence.
No retained negative/adverse or amended/superseded official-event sample exists; focused synthetic
tests cover those legacy and unknown-state paths.

## Thesis and security effects

| Measure | Before corrective | After corrective |
|---|---:|---:|
| Tickers with at least one eligible thesis case | 1,361 | 1,385 |
| Tickers with zero eligible thesis cases | 322 | 298 |
| Total thesis cases | 3,158 | 3,266 |
| `CATALYST` cases | 0 | 108 |
| `SUPPORT` / `COUNTER` / `RISK` / `INVALIDATION` ticker counts | 1,164 / 830 / 0 / 1,164 | unchanged |

Catalysts now reach thesis records and `opportunity_context._catalyst_axis` through one
classification result, with event lineage and method identity retained. Opportunity catalyst
status is `CONFIRMED` for 108 tickers, `WATCH_FOR_EXECUTION` for 993, and `UNAVAILABLE` for 582.
Security has 830 non-empty `key_counter_thesis` records and fundamental invalidation `READY` for
1,164 / `UNAVAILABLE` for 519. The security policy itself is unchanged: in this
primary-retained-root replay all 1,683 security records are `INSUFFICIENT_EVIDENCE`, because its
post-close supplementary tactical artifacts are unavailable; that independent source-availability
condition is not a catalyst-policy result. No stance, recommendation, valuation, RAW_AS_TRADED,
PIT, liquidity, sizing, or execution authority changed.

## Sample event traces

| Ticker | Event identity | Type/state | Classification / reason | Source identity | Thesis case / security stance |
|---|---|---|---|---|---|
| ACE | `current_official_event:997161…b5626c9` | CASH_DIVIDEND / RECENT | `POSITIVE_CATALYST` / `CURRENT_QUALIFIED_PRICE_SHARE_EVENT` | `a2a087…58bfe` | `CATALYST`; `INSUFFICIENT_EVIDENCE` |
| ACE | `current_official_event:f6d38d…a41ad9` | AGM / RECENT | `NEUTRAL_INFORMATION` / `INFORMATIONAL_GOVERNANCE_EVENT` | `a2a087…58bfe` | none; `INSUFFICIENT_EVIDENCE` |
| A32 | `current_official_event:8751c2…97c44c` | CASH_DIVIDEND / PAST | `INELIGIBLE` / `PAST_EVENT_NOT_CURRENT_CATALYST` | `90724b…51c5` | none; `INSUFFICIENT_EVIDENCE` |
| DSG | `current_official_event:a1b2f6…cc1e17` | CASH_DIVIDEND / DATE_INCOMPLETE | `UNRESOLVED` / `TEMPORAL_OR_EVENT_STATE_UNRESOLVED` | `4f467e…2a417` | none; `INSUFFICIENT_EVIDENCE` |

The ACE dividend and AGM rows both carry the boilerplate no-impact/no-recommendation warning but
remain positive and neutral respectively, proving warnings do not become catalyst or risk signal.
No retained adverse or amended/superseded sample exists; the deterministic legacy tests exercise
cancelled/conflicting state so it cannot remain an active positive catalyst.

## Verification and remaining limits

Focused tests cover official-state semantics, legacy version isolation, cancelled/conflicting
handling, boilerplate warning rejection, date preservation, identity deduplication, thesis
lineage, no ticker drop, and opportunity/security consumption. The focused suite passed:
`127 passed, 1 skipped`.

The input's own `research_session` is 2026-09-05 for a 2026-09-11 decision session, and many
official publication/observation times remain unavailable. Those facts remain source-declared
fitness limits; the classifier neither hides nor cures them.
