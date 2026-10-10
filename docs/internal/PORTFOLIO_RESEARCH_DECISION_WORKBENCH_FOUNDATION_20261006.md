# Portfolio research decision workbench

Milestone `PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_V1`.

Authority effect: none. This is not leverage, position sizing, or an order.

Contract: `portfolio_research_decision_workbench/v1`.

Given several supplied opportunities, the workbench reports:

- sector concentration
- style concentration
- liquidity and volatility labels when supplied, otherwise missing counts
- thesis-id and event-id overlap
- duplicate tickers, collapsed rather than double-counted
- current return correlation only for aligned series of at least three points,
  labelled `CURRENT_RESEARCH_ONLY_NOT_PIT`
- a ranking only when the caller names an objective measurement

A missing objective stays `OBJECTIVE_NOT_SUPPLIED`. A missing measurement drops
that member from the rank and lists it. The rank is not a capital allocation.

Weights, allocations, position size, leverage, orders, buy scores, target
prices, and probabilities are rejected. Nothing is persisted.

Measurement integrity corrective: [contract](../portfolio_research_measurement_integrity_v1_contract.md).
Returns must be finite nonboolean numbers; malformed points are not dropped to improve
alignment. Verified dates are unique canonical real ISO dates. Arithmetic overflow or
nonfinite intermediate Pearson results remain NOT_COMPARABLE, never a zero association.
Date alignment attests only shared dates, not source/method/price-basis compatibility,
causality, a completed session or PIT authority. Valid undated legacy values remain
caller-asserted/unverified. Conflicting duplicate tickers fail; exact duplicates collapse.
Explicit objectives preserve zero/negative measurements and reject boolean/nonfinite/
malformed values with measurement_rejected reasons; omitted values stay in
measurement_missing and present-null is additionally labelled PRESENT_NULL.
