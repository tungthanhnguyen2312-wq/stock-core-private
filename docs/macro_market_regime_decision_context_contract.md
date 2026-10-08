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

## Canonical Daily consumer and temporal corrective

`MACRO_REGIME_CANONICAL_DAILY_CONSUMER_AND_TEMPORAL_CORRECTIVE_V1` is explicitly
owner-authorized after Claude's PR #94 merge and Producer-writer handoff, starting
from `e472a3dbaa2af5bc914e9f5a2f0acbec24acc77d`. Authority effect is NONE.

For a new same-day session after the October-7 release boundary, Canonical Daily
calls `prepare_macro_delivery` once after presentation refresh. It acquires
`current_macro_regime/v1`, retains its raw FRED payloads and the full NSO evidence
artifact in the sealed operation, and captures the actual research-delivery
cutoff after acquisition. This cutoff is separate from the frozen equity and
financial input-lock cutoff. A later replay cannot bind newly acquired macro to
an earlier session. Completed-session Owner publication replay remains retained-only.

The Producer passes the explicit artifact, cutoff and exact attempt-selected
market/enrichment inputs into `build_operation`. Before sealing, the operation
builds this context and, when its governed opportunity exists, the existing
`current_research_decision_packet/v1` with an additive shared
`macro_market_regime_context`. No second packet architecture is introduced.
Absent opportunity stays absent; the independently available macro context and
explicit absence of a canonical packet identity still reach the Daily product.
The later packet stage verifies and retains the same packet instead of rebuilding it.

`session_context` requires timezone-bearing retrieval/knowledge times and an
explicit cutoff on the receiving session date. Both retrieval and knowledge time,
and a supported intraday release time, must be no later than the cutoff. Date-only
publication is labelled DATE_ONLY and supplies no intraday historical-PIT claim.
Late/stale observations retain provenance but narrow their dependent axes to UNKNOWN.
FRED uses the existing `freshness_history` daily/monthly domains; NSO uses its
retained next-release calendar rule. Latest-vintage FRED remains current research.
The production knowledge timestamp is the captured cutoff, never the scratch constant.
Context session and content identity are verified at packet and human-packet binding.

AI session delivery and cockpit carry the same shared context and canonical packet
identity, including observation/source identities, release precision, retrieval and
knowledge time, raw payload hash, freshness, authority, UNKNOWN dimensions and conflicts.
Presentation quotes cannot supply analytical axes. Macro acquisition failure is local
UNAVAILABLE; no Integrated Decision posture, probability, target, score or size is added.

Offline acceptance: `tests/test_macro_canonical_daily_consumer.py` uses the default
Canonical Daily Producer route, real Producer/session/packet/materializer/AI/cockpit
and private handoff packager, with synthetic security engines and acquisition/gates.
It runs without network, production publication or T0 retention. October-7 human
packet bytes/identity are identical with the excluded overlay; its acquisition is skipped.
No genuine October-7 artifact or registry lock is rewritten. One local retained regression
(`test_retained_pre_workspace_session_fails_closed_before_publication`) fails on both
base and candidate because its DNSE evidence companion is absent; it is outside hermetic CI.

Owner acceptance remains pending: after release CI and a fresh READY host/writer gate,
an ordinary new-session Owner Daily must retain the exact macro/context/packet identities
and cutoff in its sealed operation, then show identical context in the published private
AI bundle and cockpit bytes. Missing official SBV axes remain UNKNOWN. No Daily or
Dashboard publication is part of this corrective, and no successor is authorized.
