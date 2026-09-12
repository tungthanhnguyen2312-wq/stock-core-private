# Canonical recurring thesis and portfolio context — retained 2026-09-11 replay

This is a local-only replay of
`canonical_current_product_projections.materialize_and_write_current_product_projections()`.
It reads the already retained 2026-09-11 registry inputs and dashboard screen snapshot, writes
only to a temporary local operation directory, and makes no network, provider, database, or
private-portfolio read.

## Source map

### Thesis

- `current_evidence_bound_scenario/v1` is a retained Daily research overlay with Bear/Base/Bull
  conditional cases. It is not the `thesis_cases` contract consumed by `opportunity_context`.
- `current_research_scenario_context/v1` is a separately run, retained
  CONSERVATIVE/BASE/SPECULATIVE research-condition/presentation artifact. It is not generated in
  canonical Daily and is not a decision-chain input.
- Neither contract supplies the required catalyst/invalidation/counter-thesis record structure or
  authority. Both explicitly prohibit probability, target, expected-return, recommendation, and
  sizing output.
- Result: `THESIS_RECURRING = NO`,
  `CURRENT_THESIS_DECISION_INPUT_NOT_ESTABLISHED`. No source identity is represented as current
  decision input because doing so would be a false lineage claim.

### Portfolio

- `portfolio_aware_decision/v1` consumes an explicit private `portfolio_snapshot/v1` after a
  finished Integrated Investment Decision. Its state is local-only; its optional helper is not
  wired into canonical Daily.
- Canonical Daily has no safe private opt-in. No private root or workbook was read.
- Result: `PORTFOLIO_RECURRING = NO` for canonical Daily. Each public Workspace card remains
  `evaluated=false`, `status=NOT_EVALUATED`,
  `reason=NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED`.
- A portfolio risk ceiling, where the separate private capability can calculate one, is a
  portfolio-policy research ceiling. It is not an executable quantity:
  `execution_qualified_quantity` remains `NOT_EVALUATED` without exact liquidity authority.

## Replay result

| Metric | Result |
| --- | ---: |
| Workspace denominator | 1,683 |
| Workspace zero silent drops | true |
| Portfolio evaluated / unevaluated | 0 / 1,683 |
| Research stance | WAIT_FOR_CONFIRMATION 1,473; INSUFFICIENT_EVIDENCE 210 |
| Entry state | NONE 1,683 |
| Screener denominator / duplicates | 1,683 / 0 |
| Price coverage | 952 |
| Sector coverage | 1,678 |
| Financial V2 coverage | 1,476 |
| Tactical coverage | 951 |

The retained primary root used for this replay did not have the post-close supplemental tactical
artifacts generated in the prior full-source replay. The resulting existing optional-axis
degradation is reported above; it is not a new policy or authority effect. The required base's
full-source baseline remains the documented 1,683 denominator with
`WAIT_FOR_CONFIRMATION: 824`, `AVOID_NEW_ENTRY: 422`,
`ACCUMULATE_RESEARCH_CANDIDATE: 163`, `INSUFFICIENT_EVIDENCE: 190`,
`INITIATE_RESEARCH_CANDIDATE: 54`, and `HIGH_RISK_SPECULATION_ONLY: 30`.

## Privacy and disposition

No positions, quantities, costs, cash, NAV, margin, or other private values were read, copied,
or emitted. The explicit unavailable-state materialization is deterministic and does not alter a
security stance, portfolio action, policy threshold, source authority, or execution authority.

`CANONICAL_RECURRING_THESIS_AND_PORTFOLIO_CONTEXT_MATERIALIZATION_V1 =
PARTIAL_BY_CURRENT_SOURCE_AVAILABILITY`.
