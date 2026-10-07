# Stock Lookup — Capability Registry

Current capability state, one block per capability. No scores. Written 2026-10-04 on main `920d579`;
[ACTIVE_STATE.md](ACTIVE_STATE.md) holds the date-sensitive facts, [AUTHORITY.md](AUTHORITY.md) the
authority rules, [DAILY_PIPELINE.md](DAILY_PIPELINE.md) the run order.

**Runtime status vocabulary:** `ACTIVE` (runs in production, failure blocks that stage) ·
`ACTIVE_FAILSOFT` (runs in production, failure is component-local `UNAVAILABLE`, never revises sealed
results) · `FROZEN_HISTORICAL` (code/artifacts preserved, not the production path) ·
`BLOCKED_EVIDENCE` (cannot advance until named evidence exists) · `DEFERRED` · `EXPERIMENTAL`.
**Authority vocabulary:** `AUTHORITATIVE` · `SCOPED` · `NON_VOTING` · `BLOCKED` · `DEFERRED`.
**Production vocabulary:** `IN_DAILY_BLOCKING` · `IN_DAILY_FAILSOFT` · `OWNER_LAUNCHER` · `OFFLINE_ONLY` · `NOT_RUN`.
Each block: **Contract** · **Runtime** · **Authority** · **Production** · **Input** · **Predecessor**
(frozen) · **Blocker** · **Next trigger** (the evidence that would change the status).

Decision-intelligence closure (2026-10-07) is research coverage and calibration context
only. Contract `decision_intelligence_coverage_calibration/v1`. It does not vote, size,
or recommend. The optional read-only CLI is deferred.
[Closure evidence](internal/DECISION_INTELLIGENCE_COVERAGE_AND_CALIBRATION_CLOSURE_20261007.md).

## A. Market evidence and calendar

Phase C resource architecture (released 2026-10-06) retains record-wise IID hashing, borrowed
analytical binding leaves and bounded delivery encoding. Production signal velocity verifies
full T0/root/per-record hashes while retaining only seven axes; T0 and observer hashing/emission
are record-bounded, with exact immutable publication/reuse. Held-live heavy-path private
peak 4.03 GiB; separate actual Owner completion/handoff 5.51 GiB, under unchanged 7-GiB
containment. Disposition `RESIDUAL_PEAK_CORRECTIVE_READY`; no capability or authority promotion
and no production Daily launch. Disk admission remains independently mandatory.
[Whole-pipeline review evidence](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md).

### 1. Market acquisition (DNSE exact-session)
- Contract: [exact_session_bundle_contract.md](exact_session_bundle_contract.md); Phase A/B gates in `completed_market_session_gate.py`
- Runtime: `ACTIVE` · Authority: `SCOPED` (current-session exact evidence; no RAW/PIT claim) · Production: `IN_DAILY_BLOCKING`
- Input: DNSE/Livespeed credentials via the existing local source; DNSE working-dates probe
- Predecessor: Vnstock/KBS/VCI supplemental routes (retired 2026-09-29, `FROZEN_HISTORICAL`)
- Blocker: exact-session coverage is partial by nature (2026-10-02: 908 of 1,683 candidates); basis is `DNSE_PRIMARY_UNCORROBORATED`
- Next trigger: Monday 2026-10-05 first real Daily

### 2. Listing evidence
- Contract: [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md) ("Positive listing presence")
- Runtime: `ACTIVE` · Authority: `SCOPED` (official HNX equity / HOSE stock-master same-session presence only) · Production: `IN_DAILY_BLOCKING` (as part of capture batches)
- Input: exact selected official observations known at the cutoff
- Predecessor: default ACTIVE-interval gate (unchanged)
- Blocker: `ACTIVE_UNIVERSE` stays `UNKNOWN`; missing listing = `UNKNOWN`, never inferred
- Next trigger: first complete real capture; official effective-time evidence

### 3. Governed calendar
- Contract: [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md) (`governed_calendar_evidence_at_cutoff/v1`)
- Runtime: `ACTIVE` · Authority: `SCOPED` (forward working-date identity; no exchange-specific or session-completion proof) · Production: `IN_DAILY_BLOCKING` (receipt retained by the Daily's existing probe)
- Input: DNSE `working_dates` receipts known by the consumer cutoff; static ledger to 2026-09-04
- Predecessor: static ledger; weekday inference is prohibited
- Blocker: 2026-09-05 → 2026-10-01 unsupported gap; Oct-2 receipt registered host-locally (see ACTIVE_STATE §4)
- Next trigger: Monday's retained probe; any receipt overlapping the gap

### 4. Prospective capture (companions, complete session, first marker, readiness)
- Contract: [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md)
- Runtime: `ACTIVE` · Authority: `SCOPED` (`CAPTURE_COMPLETENESS_ONLY`) · Production: `IN_DAILY_FAILSOFT` (capture failure is `UNAVAILABLE`/incomplete; never invented)
- Input: Phase-B `READY` gate, exact market/listing/binding batches, supported calendar
- Predecessor: legacy sparse retained-session mode (`LEGACY_RETAINED_SESSION_MODE`, before the marker)
- Blocker: first marker null, complete count 0; no PIT/RAW/signal authority follows from the marker
- Next trigger: `FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE`

## B. T0 and technical/flow context

### 5. T0 decision snapshot
- Contract: `prospective_decision_retention.py` (`prospective_decision_snapshot/v1`); [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md)
- Runtime: `ACTIVE_FAILSOFT` · Authority: `AUTHORITATIVE` for its own immutable T0 content only · Production: `IN_DAILY_FAILSOFT`
- Input: sealed Integrated Decision artifact + operation identity (+ exact price snapshot)
- Predecessor: handoff-qualified legacy T0 artifacts (readable, frozen); 19 T0 families preserved
- Blocker: one-shot per session; 2026-10-02 T0 permanently `UNAVAILABLE` (0-byte file kept); streaming write validated at real scale (scratch benchmark only)
- Next trigger: first real session T0

### 6. T0 seal index
- Contract: [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md) (`prospective_t0_seal_index/v1`)
- Runtime: `ACTIVE_FAILSOFT` · Authority: `SCOPED` (derived pointers; the snapshot stays authority) · Production: `IN_DAILY_FAILSOFT`
- Input: the just-written T0 snapshot and its write hash
- Predecessor: none (new for sessions ≥ 2026-10-03); `tools/recover_t0_seal_index.py` is explicit-recovery only
- Blocker: missing index demotes V2 lookup to POST (`T0_SEAL_INDEX_UNAVAILABLE`)
- Next trigger: first real T0

### 7a. Technical V1 (contextual)
- Contract: [contextual_technical_features_contract.md](contextual_technical_features_contract.md)
- Runtime: `FROZEN_HISTORICAL` · Authority: `NON_VOTING` · Production: `NOT_RUN` for sessions ≥ 2026-10-03
- Input: n/a · Predecessor: n/a · Blocker: none (frozen) · Next trigger: none

### 7b. Technical V2 (contextual)
- Contract: [contextual_technical_features_v2_contract.md](contextual_technical_features_v2_contract.md)
- Runtime: `ACTIVE` · Authority: `NON_VOTING` (descriptive; tactical owner BOS/CHoCH/posture unchanged) · Production: `IN_DAILY_BLOCKING` (built inside the Integrated Decision enrichment; contexts that fail are explicit)
- Input: canonical D/W/M market bars, Tactical V3 structure, exact snapshot
- Predecessor: Technical V1; Oct-2 V2 is `REPLAY_DIAGNOSTIC`
- Blocker: retrospective-adjusted evidence stays POST; first production V2 session is 2026-10-05
- Next trigger: Monday acceptance rows `technical_v2_production_routing`, `exact_t0_v2_seal_index`

### 8. Technical–participation relationship view
- Contract: [technical_relationship_view_contract.md](technical_relationship_view_contract.md)
- Runtime: `ACTIVE` (library consumed by Technical V2, Volume/Flow V2, Thesis adapters) · Authority: `NON_VOTING` · Production: `IN_DAILY_FAILSOFT`
- Input: verified technical contexts · Predecessor: V1/V2 bridge only · Blocker: none · Next trigger: none

### 9a. Volume & Flow V1
- Contract: [volume_and_flow_context_contract.md](volume_and_flow_context_contract.md)
- Runtime: `FROZEN_HISTORICAL` · Authority: `NON_VOTING` · Production: `NOT_RUN` for sessions ≥ 2026-10-03
- Input/Predecessor/Blocker/Next trigger: n/a (frozen)

### 9b. Volume & Flow V2
- Contract: [volume_and_flow_context_v2_contract.md](volume_and_flow_context_v2_contract.md)
- Runtime: `ACTIVE_FAILSOFT` (post-handoff observer) · Authority: `NON_VOTING` (facts; POST unless an exact V2 seal binds T0 native volume) · Production: `IN_DAILY_FAILSOFT`
- Input: Technical V2 contexts, T0 seal index, foreign flow, signal velocity
- Predecessor: Volume & Flow V1 · Blocker: native volume unit source-undocumented; stale prior-20 trajectories
- Next trigger: Monday `t0_native_volume`, `post_to_t0_leakage` (only evaluable when T0 exists)

### 10. Foreign flow
- Contract: `current_foreign_flow_enrichment_operation.py`; Volume/Flow V2 contract (qualified foreign VALUE primitives)
- Runtime: `ACTIVE_FAILSOFT` (live collector enabled in normal Daily) · Authority: `NON_VOTING` (FACTS_ONLY in Thesis) · Production: `IN_DAILY_FAILSOFT`
- Input: DNSE foreign value history; governed calendar for continuity
- Predecessor: frozen V1 sources · Blocker: 11-name qualified cohort; 5/10/20-session maturity 11/0/0 at last measure; continuity UNKNOWN beyond receipts
- Next trigger: accumulating real sessions

## C. Fundamental, valuation, decision

### 11. Corporate Intelligence
- Local projection checkpoint: exact selected session event context joins the three retained
  historical chains. Prior contexts require deterministic session projection with immutable
  parent identity; missing selection is explicit UNAVAILABLE. Governance/ownership remain
  unavailable without their own evidence. [Measured integration](internal/CURRENT_OFFICIAL_EVIDENCE_PROJECTION_INTEGRATION_20261007.md).
- Contract: [corporate_currency_daily_rollforward_contract.md](corporate_currency_daily_rollforward_contract.md); `current_corporate_intelligence_axis.py`
- Runtime: `ACTIVE_FAILSOFT` (bounded HNX/HOSE rollforward; failure leaves the axis `NOT_PROVIDED`) · Authority: `SCOPED` (additive IID axis; official events only) · Production: `IN_DAILY_FAILSOFT`
- Input: official HNX/HOSE corporate events within one shared budget · Predecessor: frozen 2026-08-21 event context
- Blocker: three real corporate-action factors unqualified; lifecycle/term identities incomplete
- Next trigger: qualified executed official factor with explicit ex-date and knowledge time

### 12. Current financial evidence
- Local projection checkpoint: the frozen August-23 baseline remains immutable. Session
  projections add qualified PNJ/VRE 2026-H1 revenue/profit and three PVD USD income fields
  as exact-field official facts. USD remains context only, excluded from the VND citation
  lane under [currency context contract](currency_preserving_interim_context_contract.md); nonannual
  research-use restrictions remain. PNJ parent profit and VRE reported disposal context
  follow the [earnings contract](reported_earnings_component_context_contract.md); recurrence UNKNOWN.
  Annual metrics/share gates unchanged; remaining issuers retain extraction/route blockers.
- Contract: [financial_statement_canonical_contract.md](financial_statement_canonical_contract.md); `financial_analysis_engine_v2.py`
- Runtime: `ACTIVE` · Authority: `SCOPED` (provider-reported research evidence with explicit method/provenance; no official promotion) · Production: `IN_DAILY_BLOCKING` (inside enrichment; absent inputs yield explicit ABSENT records)
- Input: pinned Financial V2 current-input authority chain · Predecessor: legacy 523-record fundamental shape (frozen)
- Blocker: official statement refresh and OCR cohorts `PARTIAL`
- Next trigger: official statement currency refresh

HPG's audited capital note now supplies one dated common-outstanding observation,
context only until complete continuity qualifies. Listed quantities and provider
agreement cannot establish common semantics or continuity. Completed sessions remain
immutable. [Share contract](hpg_common_share_evidence_contract.md).

### 13a. Relative valuation (current state)
- Contract: [current_state_relative_valuation_contract.md](current_state_relative_valuation_contract.md)
- Runtime: `ACTIVE` · Authority: `SCOPED` (research context; no target price/probability) · Production: `IN_DAILY_BLOCKING` (inside enrichment)
- Input: Financial V2 engine artifact, valuation inputs, entity applicability · Predecessor: raw valuation lane (frozen shape)
- Blocker: market cap is size, not valuation; EV/EBITDA only where qualified · Next trigger: input qualification changes

### 13b. Intrinsic / reverse valuation
- Contract: [intrinsic_sector_valuation_contract.md](intrinsic_sector_valuation_contract.md), [scenario_analysis_contract.md](scenario_analysis_contract.md)
- Runtime: `BLOCKED_EVIDENCE` for qualified outputs · Authority: `BLOCKED` · Production: `OFFLINE_ONLY` outputs; scenario context rides in the Integrated Decision as research
- Input: governed intrinsic evaluator output and FCFF inputs · Predecessor: n/a
- Blocker: zero qualified intrinsic outputs (`ROADMAP_STATE.json` blocked_capabilities) · Next trigger: governed FCFF/WACC/terminal inputs

### 14. Integrated Decision + Daily Producer (research posture)
- Contract: `integrated_investment_decision_product/v1` (`integrated_investment_decision_product.py`); Producer `daily_producer_pipeline.py`
- Runtime: `ACTIVE` · Authority: `SCOPED` (research posture only; `is_actionable=false`; no target/probability/size) · Production: `IN_DAILY_BLOCKING`
- Input: nine evidence axes, Tactical V3 structure, financial/valuation/corporate/market-sector context · Predecessor: legacy opportunity decision
- Blocker: none for operation; memory-heavy (see ACTIVE_STATE launch conditions) · Next trigger: none

## D. Thesis, feedback, learning

### 15a. Thesis Stage 1
- Contract: [thesis_evidence_matrix_stage_1_contract.md](thesis_evidence_matrix_stage_1_contract.md)
- Runtime: `FROZEN_HISTORICAL` (adapters/reducers/policies frozen; called by Stage 2) · Authority: `NON_VOTING` · Production: `OFFLINE_ONLY` directly
- Input/Predecessor/Blocker/Next trigger: frozen; retained acceptance is `REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE`

### 15b. Thesis Stage 2 (production sidecar)
- Contract: [thesis_evidence_stage_2_production_contract.md](thesis_evidence_stage_2_production_contract.md)
- Runtime: `ACTIVE_FAILSOFT` (hook enabled; retained-only child; failure is component-local) · Authority: `NON_VOTING` (no action, rank, or second posture) · Production: `IN_DAILY_FAILSOFT` (T0 stage after the marker; current stage after observers)
- Input: T0 seal index, sealed/current Integrated Decision, Technical V2, Flow
- Predecessor: Thesis Stage 1 · Blocker: T0 stage needs a verified seal index; `origin=SEAL_TIME` only can enter future learning
- Next trigger: Monday `thesis_*` acceptance rows

### 16. Outcomes / outcome feedback
- Contract: [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md); `prospective_decision_outcome_feedback.py`, `prospective_feedback_streaming.py`, `feedback_resource_guard.py`
- Runtime: `ACTIVE_FAILSOFT` (two child calls per Daily, `INCREMENTAL`, 1,200 s total deadline, Job-Object contained) · Authority: `NON_VOTING` (resource/defect status is never feedback evidence) · Production: `IN_DAILY_FAILSOFT`
- Input: T0 snapshots, exact-session price snapshots, governed session chain · Predecessor: legacy whole-load builder (identity-equal; superseded)
- Blocker: T20/T60 not yet mature; growth linear in sessions; reopen if cold run > half the deadline
- Next trigger: depth accumulation

### 17. Prospective learning / calibration
- Contract: [empirical_setup_outcome_calibration_contract.md](empirical_setup_outcome_calibration_contract.md); `prospective_daily_rollforward.py`
- Runtime: `ACTIVE_FAILSOFT` · Authority: `NON_VOTING` (human-review-only candidates) · Production: `IN_DAILY_FAILSOFT` / `OFFLINE_ONLY` calibration
- Input: genuine T0 cohorts + feedback · Predecessor: handoff-qualified legacy T0 lineage
- Blocker: `EMPIRICAL_SAMPLE_INSUFFICIENT`; zero calibration-eligible candidates · Next trigger: contiguous governed capture depth (20/21/50/60/120/250)

## E. Portfolio, execution, PIT

### 18. Portfolio / risk context
- Contract: [portfolio_aware_decision_and_risk_contract.md](portfolio_aware_decision_and_risk_contract.md), [private_portfolio_context_contract.md](private_portfolio_context_contract.md), [portfolio_risk_liquidity_contract.md](portfolio_risk_liquidity_contract.md)
- Runtime: `ACTIVE_FAILSOFT` · Authority: `SCOPED` (strict research sizing/exposure; no execution) · Production: `IN_DAILY_FAILSOFT`
- Input: explicit private portfolio context (never committed) · Predecessor: demonstration input
- Blocker: no canonical capital/risk-budget binding; execution size/liquidity zero · Next trigger: owner-supplied bindings

### 19. Execution / PIT / RAW gates
- Contract: [portfolio_pit_execution_authority_contract.md](portfolio_pit_execution_authority_contract.md), [prospective_raw_pit_authority.md](prospective_raw_pit_authority.md), [market_only_pit_eligibility_contract.md](market_only_pit_eligibility_contract.md)
- Runtime: `BLOCKED_EVIDENCE` · Authority: `BLOCKED` (RAW partially promoted, use-scoped) · Production: `OFFLINE_ONLY`
- Input: qualified CA factor chain, volume unit documentation, effective-time membership
- Predecessor: n/a · Blocker: 0 qualified CA factors; PIT backtest/execution replay blocked
- Next trigger: exact evidence per contract, or explicit owner approval (never inferred)

## F. Delivery and operator gates

### 20. Dashboard / AI handoff publication
- Contract: [dashboard_release_session_contract.md](dashboard_release_session_contract.md), [release_publication_contract.md](release_publication_contract.md); `release_orchestrator.py`, `ai_handoff_publication.py`
- Runtime: `ACTIVE` · Authority: `SCOPED` (presentation of Producer verdicts; consumers may narrow, never widen) · Production: `OWNER_LAUNCHER` (phases 3–9)
- Input: sealed Producer operation, retained Brief, Integrated Decision overlay · Predecessor: pre-M1 publication path
- Blocker: none recorded · Next trigger: Monday `FINAL STATUS: PASS` = `READY_FOR_AI`

### 21. Host preflight (operator gate)
- Contract: [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md)
- Runtime: `ACTIVE` · Authority: `SCOPED` (`NONE / OWNER_DAILY_HOST_PREFLIGHT_ONLY`; observation, not a lease) · Production: `OWNER_LAUNCHER`
- Input: Windows commit/physical/pagefile, C: disk, writers, latest IID size × 5.05 · Predecessor: none
- Blocker: last observed `BLOCKED` on commit headroom (host-local) · Next trigger: READY immediately before launch; measured Monday peak

### 22. Market bars and liquidity context
- Contract: [market_bar_basis_multitimeframe_contract.md](market_bar_basis_multitimeframe_contract.md), [liquidity_authority_contract.md](liquidity_authority_contract.md)
- Runtime: `ACTIVE` (bars) / `ACTIVE_FAILSOFT` (official liquidity rollforward, status `PARTIAL`) · Authority: `SCOPED` (current-session descriptive; no execution-grade liquidity) · Production: `IN_DAILY_BLOCKING` / `IN_DAILY_FAILSOFT`
- Input: DNSE bars with basis/CA/native-volume restrictions; official HOSE/HNX liquidity series · Predecessor: legacy descriptive liquidity
- Blocker: canonical participation policy unbound · Next trigger: owner policy binding

### 23. Supplemental provider runtime (Vnstock/VNAI/KBS/VCI)
- Contract: `ROADMAP_STATE.json` blocked_capabilities `SUPPLEMENTAL_PROVIDER_RUNTIME_OPERATION`
- Runtime: `FROZEN_HISTORICAL` (retired 2026-09-29; worker removed; retained research evidence preserved, never officially promoted) · Authority: `BLOCKED` · Production: `NOT_RUN`
- Input/Predecessor/Blocker/Next trigger: new owner decision required to revive anything
