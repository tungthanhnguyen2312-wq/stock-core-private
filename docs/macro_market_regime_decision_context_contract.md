# Macro / market regime decision context

Contract `macro_market_regime_decision_context/v1`.

The context binds explicit identities from `current_macro_regime/v1`,
`market_regime_breadth_context/v1`, and
`current_market_sector_leadership_context/v1`. It does not look up a latest file
and it does not recompute axis rules.

Each dimension carries state, evidence, freshness, authority, and limitations.
A missing axis is `UNKNOWN`. Presentation series from `macro_sync` stay
presentation availability. Yahoo Finance, Vietcombank quotes, and SJC quotes do
not become official regime observations.

Macro and market disagreements stay as conflicts with no winner. Sector
alignment is `RELATIONSHIP_NOT_FORMALIZED`. Company economics and tactical
posture are separate fields.

The human/AI packet receives the context in `market`, missing dimensions in
`uncertainty`, and evidence fields in `counter_thesis`. Python does not emit a
probability, forecast, target, recommendation, position size, or regime score.

FRED latest-vintage rows stay current research. The completed 2026-10-07
session is not rewritten. Domestic SBV USD/VND, policy rate, and credit growth
remain unknown: no retained first-party metric and no governed machine-readable
locator, so this milestone made no HTTP request.

Disposition `PARTIAL_MACRO_MARKET_REGIME_DECISION_CONTEXT_READY`. No successor.
