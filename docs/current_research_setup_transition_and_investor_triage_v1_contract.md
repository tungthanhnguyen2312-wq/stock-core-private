# Qualified-session research-state evolution in the Action Center

Milestone `CURRENT_RESEARCH_SETUP_TRANSITION_AND_INVESTOR_TRIAGE_V1`.
Base: released main `21da278f2d18c22bc0d8bf7c0b3e49e36138a87c`.
Authority effect NONE. One opt-in explanation. No new posture, priority,
sizing, score, or execution authority.

## Gap and selected fix

`docs/current_research_conditional_opportunity_and_early_reversal_v1_contract.md`
already restates the current session's setup, posture, priority reconciliation,
confirmation and invalidation conditions, counter-thesis, and missing evidence.
`next_session_decision_brief/v2` already names market, sector, opportunity, and
per-ticker posture transitions for a qualified previous session. The Action
Center's previous-session market block is only the lexicographic descriptive
breadth comparison. It does not present those governed per-ticker rows beside
the conditional research view.

Two fixes were compared:

1. The Action Center consumes a verified `next_session_decision_brief/v2`
   artifact and rechecks each posture label with the brief's existing
   classifier. Selected.
2. A second adapter recomputes transitions inside the Action Center. Rejected.
   It would be a competing computation.

The descriptive `_previous_session` directory scan stays breadth-only. It is
not the qualified previous session. `evaluate_from_retained_artifacts` does not
infer a latest session for this path and does not load a brief.

## Interface

`personal_investment_decision_action_center.build_artifact` gains two optional
arguments, both defaulting to None:

- `next_session_artifact`
- `previous_integrated_decision_artifact`

Passing a brief with `include_conditional_research=False` raises
`SETUP_TRANSITION_REQUIRES_CONDITIONAL_RESEARCH`. Omitting the brief leaves
JSON, Markdown, content hash, and the disabled identity unchanged.

When both the conditional view and a brief are supplied, each already-selected
row gains `evidence.conditional_research.setup_transition`, and
`conditional_research_presentation.setup_transition` records the brief identity,
the two sessions, and `explanation_only: true`. Markdown adds that block only
when the key is present.

The view copies the brief's posture label, tactical confirmation membership,
market `advance_ratio_direction` or string transition, and the sector pair's
existing transition string. It compares retained setup fields by equality.
It copies `priority_posture_reconciliation` only when `integrated_posture`
matches the current canonical posture. It does not copy advance-ratio deltas
or price levels.

## Fail closed

The brief contract, content identity, authority boundary
(`is_actionable` false and `derived_evidence_not_new_factual_authority` true),
current session, and both integrated-decision artifact identities must match.
The previous session must be the brief's `previous_qualified_session` and must
be strictly before the current session. Each displayed ticker row must match
the classifier label and both decision identities. A ticker in more than one
confirmation list, or a confirmation membership that contradicts
`WAIT_TO_INITIATE`, `EARLY_WATCH_TO_INITIATE`, or `BREAKOUT_FAILED`, is
rejected. When both records carry a price unit, the units must be equal or the
ticker is rejected. A research-label change with the same unit does not
invent a distance. The limitation is
`PRICE_BASIS_LABEL_CHANGED_NO_CROSS_SESSION_NUMERIC_COMPARISON`.
Current-session numeric display stays under the existing withhold rule.
A policy-epoch mismatch keeps the governed label
`NOT_COMPARABLE_POLICY_CHANGE` and does not interpret confirmation.

No previous qualified session produces status `UNAVAILABLE`, no invented label,
and the limitation `NO_PREVIOUS_QUALIFIED_SESSION_NO_TRANSITION_INVENTED`.

## Meaning

A transition label is not an investment outcome. A future trigger condition is
not a triggered event. `PRIORITY_NOW` is research attention, not BUY NOW.
`EARLY_WATCH` is not capital authorization. Market weakness stays context in
this view. `FUNDAMENTAL_INSUFFICIENT` does not remove the retained technical
state. This presentation does not rewrite either session's original decision.
