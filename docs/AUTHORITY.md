# Stock Lookup — Authority Map

Who may speak for what. This file **summarizes** authority; it promotes nothing. The controlling
contract named in each row decides disputes. Written 2026-10-04 on main `920d579`. Current-state
facts live in [ACTIVE_STATE.md](ACTIVE_STATE.md); capabilities in [CAPABILITIES.md](CAPABILITIES.md).

**Status vocabulary:** `AUTHORITATIVE` (may speak for its stated scope) · `SCOPED` (valid only for
the named use/window/source) · `NON_VOTING` (descriptive; never a decision input, action, rank or
verdict) · `BLOCKED` (not available; fail closed for dependent use) · `DEFERRED` (not started).

Governing rules that apply to every row: `UNKNOWN` is not rejection — keep raw data and provenance,
mark the semantic unknown, fail closed only where required; a fallback is a separately named
`DERIVED_PROXY`; consumers pass Producer verdicts through and may narrow but never widen them;
`is_actionable=false` everywhere; qualification is field/feature/use-case level, never a global
ticker verdict ([AI_RULES.md](AI_RULES.md) rules 5–10, [DATA_FIRST_DOCTRINE.md](DATA_FIRST_DOCTRINE.md)).

## 1. Fact, number and AI boundaries

| Area | Status | Meaning | Controlling source |
|---|---|---|---|
| Factual authority | `AUTHORITATIVE` | Only retained first-party raw evidence with provenance and knowledge time speaks as fact; AI-generated text never does. A source speaks only at its `documented_verified` tier; `empirically_deduced` is provider/field/ticker/window-scoped. | [DATA_FIRST_DOCTRINE.md](DATA_FIRST_DOCTRINE.md), [AI_RULES.md](AI_RULES.md) |
| Numerical authority | `AUTHORITATIVE` | Deterministic Python engines own every formalizable calculation and eligibility rule; strategy owns thresholds. A ratio constrains only the ratio; no absolute scale without an independent anchor. | AI_RULES rule 7; [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md) (scale tiers) |
| AI authority boundary | `SCOPED` | AI may research semantics, extract candidate evidence, explain deterministic outputs, surface counter-theses and anomalies. AI may not invent facts, turn `UNKNOWN` into `QUALIFIED`, fabricate values/targets/probabilities, infer semantics from labels, or override risk gates. Normal Daily publication adds no generated verdict. | [AI_RULES.md](AI_RULES.md) "AI boundary"; [thesis_evidence_stage_2_production_contract.md](thesis_evidence_stage_2_production_contract.md) |
| Current session vs historical / PIT | `SCOPED` | Current Research / Product Mode (provider and research proxies allowed with explicit method, provenance, fitness) is separate from Audit / PIT / Exact Mode. Missing audit-grade authority blocks only the dependent exact use. Historical artifacts are never recomputed or reinterpreted as PIT. | [AGENTS.md](../AGENTS.md), [market_pit_foundation_contract.md](market_pit_foundation_contract.md) |

## 2. Prospective evidence chain

| Area | Status | Meaning | Controlling source |
|---|---|---|---|
| Capture completeness | `SCOPED` | `CAPTURE_COMPLETENESS_ONLY`. A complete-session record and the write-once `first_complete_capture_session` marker attest that exact immutable market/listing/binding batches existed inside the 15:00 → 09:00 window under a Phase-B `READY` gate. Grants no signal evaluation, backtest, execution, source promotion or PIT. T0 is **not** a precondition. | [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md) |
| T0 snapshot | `AUTHORITATIVE` | The immutable content-addressed snapshot is the sole authority for what the Integrated Decision knew at T0 for that session. One-shot per session; never rebuilt, backfilled or reinterpreted. Its absence (`UNAVAILABLE`) is a legal state and says nothing about capture or the decision. The seal index is a derived `SCOPED` pointer. | `prospective_decision_retention.py`; [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md) |
| Listing | `SCOPED` | Official HNX equity / HOSE stock-master same-session presence (`LISTED_PRESENT_AT_SESSION`) with source-row identity and knowledge time. `ACTIVE_UNIVERSE` / effective ACTIVE intervals remain `UNKNOWN`. | capture contract "Positive listing presence"; `ROADMAP_STATE.json` blocked_capabilities |
| Calendar | `SCOPED` | Forward DNSE working-date identity known at the cutoff; no exchange-specific proof, no session-completion proof, no weekday inference, no stitching across the 2026-09-05 → 2026-10-01 gap. | Monday contract (`governed_calendar_evidence_at_cutoff/v1`) |
| RAW as traded | `SCOPED` | Prospective raw-as-traded only for bars equal to the official HOSE series; historical raw is `PARTIAL` (HOSE, research grade). RAW dimensions stay independent (capture fitness, representation tier, basis claim, official match, empirical unadjusted finding, CA comparability). Stable native scale never establishes global RAW or VND economics. | [prospective_raw_pit_authority.md](prospective_raw_pit_authority.md), capture contract |
| Corporate actions (CA) | `BLOCKED` | 0 qualified executed factor events; no factor chain, no PIT-adjusted history. Source-record identity alone never establishes event identity, terms, lifecycle or knowledge time. | [portfolio_pit_execution_authority_contract.md](portfolio_pit_execution_authority_contract.md), [corporate_currency_daily_rollforward_contract.md](corporate_currency_daily_rollforward_contract.md) |

## 3. Analytical context

The [annual context contract](audited_annual_exact_field_context_contract.md) admits ten later-known FY2025 exact fields across HPG/PNJ/PVD/FPT. Auditor opinion continuation is source-bound; historical context does not replace annual valuation inputs or rewrite completed sessions.

The [HPG share contract](hpg_common_share_evidence_contract.md) qualifies one audited
historical common-outstanding observation. Listed quantity is separate. Complete
subsequent continuity and knowledge eligibility remain mandatory for current valuation.


The local October-7 projection checkpoint distinguishes current official exact-field facts
from annual research admissibility. Reviewed H1 income retains `RESEARCH_PERIOD_NOT_ANNUAL`;
it cannot replace annual inputs, create TTM or upgrade other fields. Session event projection
preserves source qualification, explicit dates and knowledge time; it grants no factor,
governance, ownership, share, PIT or execution authority.
The [currency context contract](currency_preserving_interim_context_contract.md) admits
source-qualified USD income fields for context only. No FX conversion or VND valuation
input/citation use follows.
The [earnings component contract](reported_earnings_component_context_contract.md) admits
explicit reported disposal results as descriptive context. Recurrence stays UNKNOWN; no
normalized EPS, annual valuation input, action or score change follows.

| Area | Status | Meaning | Controlling source |
|---|---|---|---|
| Technical (contextual V1/V2) | `NON_VOTING` | Deterministic descriptive context; tactical owner (BOS/CHoCH, pivots, breakouts, posture, triggers, invalidations) unchanged. V1 frozen; V2 production from 2026-10-03; Oct-2 V2 is replay-diagnostic. Retrospective-adjusted evidence stays POST. | [contextual_technical_features_v2_contract.md](contextual_technical_features_v2_contract.md) |
| Volume / Flow | `NON_VOTING` | Facts-only research reference; every item POST unless an exact V2 seal binds T0 native volume. Native volume unit is source-undocumented; foreign flow is FACTS_ONLY and never directional. | [volume_and_flow_context_v2_contract.md](volume_and_flow_context_v2_contract.md) |
| Thesis (Stage 1/2) | `NON_VOTING` | Independent LONG/SHORT lens states with conflicts and blockers; no action, ranking, overall verdict, second posture or decision input. `origin=SEAL_TIME` is the only potentially learning-eligible origin. | [thesis_evidence_stage_2_production_contract.md](thesis_evidence_stage_2_production_contract.md), [thesis_evidence_matrix_stage_1_contract.md](thesis_evidence_matrix_stage_1_contract.md) |
| Posture / action | `SCOPED` | `research_action_posture` is a research label from the deterministic Integrated Decision (nine evidence axes); it is not an order, target, probability, stop or size. Tactical entry labels (e.g. `BUY_ON_CONFIRMATION`) are research states. | `integrated_investment_decision_product/v1`; [watchlist_tactical_entry_decision_contract.md](watchlist_tactical_entry_decision_contract.md) |
| Valuation | `SCOPED` | Current-state relative valuation as research context (market cap is size, not valuation). Intrinsic / reverse-valuation outputs are `BLOCKED` until a governed evaluator output and FCFF inputs are retained. | [current_state_relative_valuation_contract.md](current_state_relative_valuation_contract.md), [intrinsic_sector_valuation_contract.md](intrinsic_sector_valuation_contract.md) |
| Outcomes / learning | `NON_VOTING` | Outcomes matured from genuine T0 over the governed completed-session chain; resource/defect statuses are never feedback evidence; calibration candidates are human-review-only and sample-limited. Neither a missing outcome nor an unavailable T0 is negative or neutral evidence. | [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md), [empirical_setup_outcome_calibration_contract.md](empirical_setup_outcome_calibration_contract.md) |

## 4. Execution, portfolio and promotion

| Area | Status | Meaning | Controlling source |
|---|---|---|---|
| Portfolio / risk | `SCOPED` | Strict research sizing, exposure aggregation and risk-window readiness only; private portfolio inputs are explicit and never committed. | [portfolio_aware_decision_and_risk_contract.md](portfolio_aware_decision_and_risk_contract.md), [private_portfolio_context_contract.md](private_portfolio_context_contract.md) |
| Execution / liquidity / sizing | `BLOCKED` | No execution-grade liquidity, canonical participation/horizon policy, capital binding, theoretical or execution size. | [portfolio_pit_execution_authority_contract.md](portfolio_pit_execution_authority_contract.md), [liquidity_execution_capacity_and_sizing.md](liquidity_execution_capacity_and_sizing.md) |
| PIT backtest / replay / live eligibility | `BLOCKED` | Needs qualified CA chain, volume documentation and effective-time membership, or an explicit recorded owner approval. | same, [market_only_pit_eligibility_contract.md](market_only_pit_eligibility_contract.md) |
| Authority promotion (any) | `DEFERRED` | Never by side effect: not by registry presence, canonical representation, software release, marker publication, a READY host, or a completed milestone. Requires exact evidence per contract or explicit owner decision. | [AI_RULES.md](AI_RULES.md) rules 4, 10, 11; STATE Invariant 6 |
| Operator host gate | `SCOPED` | `NONE / OWNER_DAILY_HOST_PREFLIGHT_ONLY`: a point-in-time observation that gates launch; no analytical authority. | [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md) |


Retained reviewed H1 requalification (`PNJ_VRE_REVIEWED_H1_PROVISION_COMPONENT_AND_TOTAL_ASSET_IDENTITY_V1`): indirect cash-flow line 03
is an earnings-quality component only (`NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE`,
recurrence UNKNOWN, no normalization). Total assets require a literal total label; 2026
templates number `Tài sản dài hạn khác` 270. Facts first qualified now are known now.

NVL's newly retained H1 filing proves reviewed consolidated assurance after explicit
zero-candidate native fallback. Every exact financial value remains blocked; no current
field, valuation input or quality score is added. Source receipt and exact blockers:
[October8 campaign](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).
