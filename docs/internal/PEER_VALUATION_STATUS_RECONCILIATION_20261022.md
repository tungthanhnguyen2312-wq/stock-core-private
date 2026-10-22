# Peer-valuation status reconciliation (2026-10-22)

Milestone `PEER_VALUATION_STATUS_RECONCILIATION_V1_20261022`, Owner-admitted 2026-10-22. Producer only.

## Defect
`sector_aware_relative_research` never evaluates valuation; its fixed `VALUATION_PEER_CONTEXT_UNAVAILABLE`
(locked by `tests/test_sector_aware_relative_research.py`) was copied into each Product V2 card as a
record-level gap (status, `peer_context.limitations`, expectations counter-evidence, a DATA_GAP
counter-thesis). AI delivery and the cockpit then attached `integrated_decision_v1`, whose
`valuation_context_summary.peer_relative_state` can hold a governed research verdict, without reconciling.
On 2026-10-22, 36/72 handoff contexts, 7/10 owner-focus contexts and 36 cockpit cards stated both.

## Change
- `current_daily_decision_research_product.reconcile_card_peer_valuation`: when the Integrated Decision
  record has CHEAP/MID_RANGE/EXPENSIVE_VS_PEERS, the delivered card sets `peer_valuation_status` to
  `PEER_RELATIVE_RESEARCH_IN_INTEGRATED_DECISION`, adds `peer_valuation_reconciliation` (reference and
  cohort basis `same_method_same_basis_peer_cohort/v1`, not industry-restricted), and drops only the
  layer gap token. Without a verdict the card keeps its gap statements.
- Card `peer_valuation_status_scope` names the sector-aware layer; the authority warning is scoped to the
  shadow proxy; `what_to_verify_next` keeps strict valuation unavailable.
- `ai_research_session_delivery`: applied to primary contexts, owner-focus contexts and cockpit
  `ticker_cards`; cockpit `risk_data_gaps.valuation_peer_context_unavailable` subtracts verdict records.

## Unchanged
Strict valuation, shadow-proxy fail-closed rules, the sector-aware artifact and its ai-core pass-through
contract, Integrated Decision records and identities, the Product V2 artifact itself, the full-universe
companion (raw layer records). No new verdict or authority.

## Evidence
Read-only replay over the retained 2026-10-22 handoff and cockpit: contradictions 36→0 (handoff),
7→0 (owner focus), 36→0 (cockpit); records without a verdict keep their gap (SSI, EVF, PNJ); strict
valuation changed on 0 records.
