# Portfolio opportunity-cost comparative research — contract

Contract: `portfolio_opportunity_cost_research/v1` · Module: `portfolio_opportunity_cost_research.py`
· Milestone: `PORTFOLIO_OPPORTUNITY_COST_COMPARATIVE_RESEARCH_V1` · Authority effect: **none**.
Mode: **offline, opt-in**. Not called by Owner Daily, not sealed, not published to the Dashboard,
nothing persisted.

## Purpose

Research for a human, never an allocation. For each supplied comparison unit it states whether a
case exists to hold or add to a Core position, to review a valuation-based trim without a thesis
break, to consider another investment, or to keep cash, and whether an apparent alternative is
redundant exposure.

Comparison unit: `ticker × thesis_id × horizon × portfolio_role × market_state`.
Horizons `STRUCTURAL | STRATEGIC | TACTICAL`; roles `CORE | STRATEGIC | TACTICAL` (research framing,
not a holding fact).

## Independent lenses

| Lens | Reads | Never |
|---|---|---|
| `core_structural` | `fundamental_state` (integrated `FUNDAMENTAL_STATES`); `thesis_status` `INTACT/UNDER_REVIEW/BROKEN/UNKNOWN` kept as a caller-reported research assertion with `thesis_source` | changed by tactical input; treated as proof of a qualified multi-year structural thesis |
| `strategic` | upstream `peer_relative_context.methods` through the workspace predicate `qualified_relative_methods` (true relative method, status `READY_RESEARCH_ONLY`), and the label must match those percentiles (≤0.25 attractive, ≥0.75 expensive); event ids | treats a method name, a label, a caller list, market cap, or another status as qualification; claims strict valuation authority (`SCOPED_RELATIVE_RESEARCH_NOT_STRICT_VALUATION`) |
| `tactical` | `tactical_phase` (integrated `TACTICAL_PHASES`) → `CONFIRMED / UNCONFIRMED / ADVERSE / EXTENDED / UNKNOWN` | relabels the structural state |
| `cash_optionality` | owner `cash_available`, `effective_nav`, `minimum_cash_reserve_to_nav` | carries a return (`expected_return: null`, `NONE_NOT_INVENTED`) |

Every lens carries `source_identity`, `session` and `fitness`.

## Research cases (not instructions)

`HOLD_CORE_REVIEW`, `ADD_CORE_REVIEW`, `VALUATION_TRIM_REVIEW`, `ALTERNATIVE_INVESTMENT_REVIEW`,
`CASH_OPTIONALITY_REVIEW`, `INSUFFICIENT_COMPARABLE_EVIDENCE`. Each exposes supporting evidence,
counter-evidence, evidence gaps, thesis and horizon, portfolio role, concentration/overlap,
decision changers (rule-based plus source invalidation), and source identities with fitness.

- Hold/add/trim are emitted only for `HELD_CONFIRMED` positions in an explicit `portfolio_state/v1`.
  `portfolio_state/v1` carries no coverage guarantee, so a ticker absent from `positions` is
  `CURRENT_POSITION_UNRESOLVED` (`TICKER_NOT_LISTED_IN_OWNER_PORTFOLIO_STATE`); it may get an alternative
  review with that gap. Only a listed zero-quantity or `CLOSED` row is `NOT_HELD_CONFIRMED`.
- Structural status labels are prefixed `REPORTED_` (for example
  `REPORTED_THESIS_INTACT_FUNDAMENTAL_STATE_CONSISTENT`).
- Trim requires a **qualified** expensive label and no thesis break (`DETERIORATING` or `BROKEN`);
  a thesis break is never relabelled as a valuation trim.
- Add is withheld (listed under `narrowed_by_owner_constraints_or_evidence`) when an explicit owner
  sector or single-position limit is reached. Owner limits only narrow.
- Unresolved or owner-excluded positions receive no hold/add/trim/alternative case.
- A candidate with neither comparable structural nor qualified valuation evidence is
  `INSUFFICIENT_COMPARABLE_EVIDENCE`.

## Comparability and redundancy

Per held × candidate pair: axes `COMPARABLE / NOT_COMPARABLE`; strategic needs a **common** qualified
method. Overall `COMPARABLE` (all three), `NOT_COMPARABLE` (neither structural nor strategic),
else `PARTIALLY_COMPARABLE`. Side-by-side values only; `superiority` and `winner` are always null.
Redundancy: `LIKELY_REDUNDANT_EXPOSURE` (same sector plus shared thesis or event),
`PARTIAL_OVERLAP`, `OVERLAP_UNKNOWN` (sector missing), `NO_OVERLAP_OBSERVED`.

## Workbench corrections (gaps confirmed in code)

- **A.** Workbench sector/style concentration counts opportunities; it now says so
  (`basis: OPPORTUNITY_COUNT_NOT_OWNER_EXPOSURE`). Owner exposure comes only from `portfolio_state/v1`
  sector weights; unweighted or unsectored holdings make it `PARTIAL_UNCERTAIN` and limit checks
  `…_LOWER_BOUND_ONLY`.
- **B.** Correlation is `comparable` only when both series carry dates and are aligned on shared,
  unique dates. Undated equal-length series keep their value for backward compatibility but are
  `CALLER_ASSERTED_UNVERIFIED`, `comparable: false`. Always `CURRENT_RESEARCH_ONLY_NOT_PIT`.
- **C.** The shortlist vocabulary has no trim or opportunity-cost bucket; this contract adds research
  cases without changing the shortlist.
- **D.** Unknown fundamental/valuation axes yield `PARTIALLY_COMPARABLE` / `NOT_COMPARABLE`.
- **E.** Cash carries owner facts only.

## Fail-closed

Raises `OpportunityCostResearchError` on: candidate, lens or market-context session mismatch;
missing lens source identity; unknown vocabulary; differing integrated-decision identities across
candidates; wrong owner-state contract; duplicate ticker; any forbidden key (weights, allocation,
sizing, leverage, order, buy score, target price, probability, expected return, score,
recommendation, winner, rotate, buy, sell, capital decision).

## Not authorized

Automatic buy/sell/rotate, target weights, sizing, orders, leverage, expected returns, unsupported
valuation, normalized earnings, generic optimisation score. Macro context is optional descriptive
input (`market_state`, session-checked); no dependency on a new Macro integration.
