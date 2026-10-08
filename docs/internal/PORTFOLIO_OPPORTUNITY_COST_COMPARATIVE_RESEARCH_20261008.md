# Portfolio opportunity-cost comparative research — 2026-10-08

Milestone `PORTFOLIO_OPPORTUNITY_COST_COMPARATIVE_RESEARCH_V1`, owner directive
`OWNER_DIRECTIVE_2026_10_08_PORTFOLIO_OPPORTUNITY_COST_COMPARATIVE_RESEARCH_V1`.
Starting main `da5206716ade44a4b896de48ca5c66c330191991`. Authority effect: none. Offline, opt-in.
Contract: [portfolio_opportunity_cost_research_contract.md](../portfolio_opportunity_cost_research_contract.md).

## Reused

`portfolio_research_decision_workbench` (overlap, opportunity counts, correlation),
`portfolio_aware_decision` `portfolio_state/v1` (holdings, sector weights, NAV, cash, policy),
integrated decision `FUNDAMENTAL_STATES` / `TACTICAL_PHASES`, valuation `RELATIVE_METHODS` and the
workspace relative-label guard. No concentration, overlap or shortlist engine was recreated; the
shortlist and decision packet are unchanged.

## Gaps verified in code

| Gap | Finding | Change |
|---|---|---|
| A | `_counts(rows, "sector")` counted opportunities | basis label; owner exposure from `portfolio_state/v1` only |
| B | `_pearson` accepted equal-length undated lists | date-intersection alignment; undated marked unverified, not comparable |
| C | shortlist has `CORE_POSITION_REVIEW` only | research cases in the new contract |
| D | workbench had no fundamental/valuation axis | per-axis comparability |
| E | no cash lens existed | owner cash facts, `expected_return: null` |

## Six synthetic scenarios

1. Strong Core, tactical `BREAKDOWN` → hold review keeps `REPORTED_THESIS_INTACT_FUNDAMENTAL_STATE_CONSISTENT`; tactical is counter-evidence only.
2. Attractive candidate, owner sector 45% vs 40% limit, shared thesis → alternative review with limit and redundancy counter-evidence; held add review narrowed.
3. Sound Core, qualified expensive (P/E TTM, P/B) → valuation trim review, `fundamental_thesis_break: false`; no add review.
4. A→B with no common valuation method → `PARTIALLY_COMPARABLE`; with candidate fundamentals insufficient and no valuation → `INSUFFICIENT_COMPARABLE_EVIDENCE`.
5. Early reversal → `UNCONFIRMED` counter-evidence; structural lens unchanged.
6. Cash with incomplete alternatives → cash review citing them, cash-to-NAV fact, no return.

No Daily, T0, October 7 record, owner holding or Dashboard output was touched.

## Release corrective (PR #94)

- Valuation fitness: the consumer accepted a method by name. It now reads upstream peer methods
  through the workspace predicate `qualified_relative_methods` (status `READY_RESEARCH_ONLY`), and
  the label must agree with the percentiles. Missing, blocked, incompatible or strict-style status,
  caller lists and market cap stay `UNQUALIFIED_*`.
- Holding coverage: `portfolio_state/v1` has no coverage guarantee, so a ticker missing from it is
  `CURRENT_POSITION_UNRESOLVED`, not confirmed not-held.
- Thesis: `thesis_status` is a caller-reported assertion with `thesis_source`, not a qualified
  multi-year structural thesis.
- CI: `test_timeout_before_first_output_publishes_nothing_and_changes_no_evidence` failed identically
  on clean main (runs 37729085586, 37733426993). It is a pre-existing timing-sensitive test that
  imports nothing changed here, so feedback-resource code was left as it is.
