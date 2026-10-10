# Stock Lookup — System Map

> Navigation aid only. Milestone state is in ROADMAP_STATE.json; contracts/code govern semantics; STATE/ROADMAP/DECISIONS preserve history. Follow AGENTS.md's Authority by domain rule.
> Start with the compact active set: [ACTIVE_STATE](ACTIVE_STATE.md), [CAPABILITIES](CAPABILITIES.md), [AUTHORITY](AUTHORITY.md), [DAILY_PIPELINE](DAILY_PIPELINE.md), [ROADMAP_CURRENT](ROADMAP_CURRENT.md); history index: [HISTORICAL_INDEX](HISTORICAL_INDEX.md).

Outcome-feedback children (pre- and post-handoff) run bounded: `feedback_resource_guard.py` (admission, one total deadline, memory ceiling, reaping) around
`prospective_feedback_streaming.py` (streamed proof and output, atomic COMPLETE publication). Content and `artifact_identity` equal the original
`prospective_decision_outcome_feedback.build_feedback_artifact`; resource reasons are never feedback evidence. [Contract](owner_daily_feedback_resource_containment_contract.md).

Prospective market continuity: `prospective_market_snapshot_contract.py` owns price/volume
fitness and scoped official comparison; `prospective_market_evidence_retention.py` is its
immutable Daily I/O boundary, using the existing universe verifier/retainer and corporate
ledger/factor engine. `canonical_post_close_pipeline.acquire_and_materialize` retains
market receipts before optional work. [Contract](market_pit_foundation_contract.md).

`market_only_pit_eligibility.py` owns signal-specific input, contiguous-region and
D/W/M constituent gates. `vnm_shadow_backtest.py` reuses its existing signal/return
primitives for bound gross research. `tools/run_market_only_pit_acceptance.py` scans
exact R7 inputs offline. [Contract](market_only_pit_eligibility_contract.md).


## Repository navigation status — 2026-10-01

### Source package migration — 2026-10-10

The owner admitted [root structure simplification](repository_root_structure_simplification_v1_contract.md)
after semantic corrective PR105. Landing acquisition code is in `stocklookup_core/acquisition/`;
official document evidence and temporal receipts are in `stocklookup_core/evidence/`.
Financial panels, Financial V2 and fundamental research are in `stocklookup_core/financial/`.
Valuation calculations, peers and current-input scaleout are in `stocklookup_core/valuation/`.
Decision inputs, risk/thesis/opportunity contexts, packets, integrated brief and workspace
projection are in `stocklookup_core/decision/`; Daily orchestration/retention remain in place.
[Decision package contract and evidence limits](decision_research_package_v1_contract.md).
Tactical contexts, breakout/relative-volume projection and V2 dispatch are in
`stocklookup_core/tactical/`. Frozen V1 producers, primitive and relationship bridge
retain root paths; frozen V2 moves without changing bytes.
[Tactical package contract and frozen-source limits](tactical_research_package_v1_contract.md).
Thesis adapters, matrix, sidecars and runtime are in `stocklookup_core/research/`;
their existing child tools retain their paths and resolve the repository source root.
The existing offline `official_document_acquisition.py` CLI is a small compatibility launcher.
All library consumers import the packages; historical module names resolve through
`config/repository_layout.json`. Owner Daily and publishing launchers retain their paths.
Root placement is enforced by `tests/test_repository_layout.py`.

The runtime topology below is authoritative as a navigation aid, but the filesystem is still historically flat. The public root currently contains hundreds of implementation modules; this is recognized layout debt, not evidence that those modules are unused.

Repository cleanup follows the governed strangler plan in [REPOSITORY_LAYOUT_MIGRATION.md](REPOSITORY_LAYOUT_MIGRATION.md):

- do not perform a wholesale `src/` migration;
- do not classify a module as legacy by filename;
- move only coherent capability families with known call graphs and focused parity tests;
- keep production entry points truthful throughout migration;
- reduce the root gradually alongside product-critical roadmap work.

The October 1 Owner Daily live-acceptance gate is complete and PR #31 is merged. R2 and R4 are complete, R3 remains terminal for its current source set, and R5 is locally complete. R6 Prospective Learning & Calibration is locally COMPLETE; R7 Portfolio / PIT / Execution Authority is locally COMPLETE for capability implementation, with stronger authority still pending evidence/owner approval; the successor is owner roadmap review/rebaseline, with no automatic milestone; repository-layout work must not displace capability work.

## Evidence-continuity navigation — 2026-10-02

R5–R7 merged in PR #35. The [post-release system review](internal/POST_R1_R7_SYSTEM_REVIEW_20261002.md) selects prospective evidence continuity first. `prospective_decision_retention.build_corpus_health` owns the single v2 operational health verdict, including horizon-specific source-fitness diagnosis by genuine T0 session. `prospective_decision_outcome_feedback` embeds it; the existing offline retention/maturation runner copies that exact verdict. Neither consumer recomputes maturity, reconstructs T0 nor changes sample floors or policy. Retention, numerical outcomes and action authority remain unchanged.

## R7 authority-readiness navigation

See [contract](portfolio_pit_execution_authority_contract.md) and [acceptance](internal/R7_PORTFOLIO_PIT_EXECUTION_ACCEPTANCE.json).
`raw_pit_authority_matrix` owns the consumer matrix/dossier and final non-voting PORTFOLIO_FIT adapter.
`portfolio_aware_decision`, `current_portfolio_risk_envelope` and `current_portfolio_risk_research`
reuse the existing governed risk/minimum-cap, exposure and window engines. `vnm_shadow_backtest`
reuses the isolated VNM replay engine through explicit authority gates; no generic or live order path
is added. `tools/run_portfolio_pit_execution_acceptance.py` is an offline exact-manifest review tool,
not another production entrypoint. Source registries and promoted authority are unchanged.

## Canonical Pipeline Flow

```
stocklookup.ps1
  └─> stocklookup.py
        └─> Canonical Daily Operation (canonical_daily_operation.py / daily_analysis_pipeline.py)
              ├─> Market-Data Acquisition (canonical_post_close_pipeline.py)
              ├─> Canonical / Current Research (daily_producer_pipeline.py / daily_research_session_operations.py)
              ├─> Tactical Engine V2 (tactical_behavior_context.py / watchlist_tactical_entry_classifier.py)
              ├─> Financial Analysis V2 (financial_analysis_engine_v2.py / financial_analysis_product_projection.py)
              ├─> Valuation & Opportunity Integration (current_valuation_opportunity_integration.py)
              ├─> Investment Decision Workspace (investment_decision_workspace_projection.py)
              ├─> Screener Master Projection (screener_master_projection.py)
              ├─> AI Handoff Publication (ai_handoff_publication.py / next_session_decision_brief.py)
              └─> Dashboard Release (dashboard_release_publisher.py / publish_dashboard.py)
```

## Canonical prospective learning path (R6)

NEW Integrated products serialize the existing research-action policy version. Canonical Daily
seals `prospective_decision_retention/v1` full T0 decisions and exact prices, binds their product,
snapshot and operation identities in the handoff, then runs its unchanged non-blocking
`prospective_decision_outcome_feedback/v3` observer. Both genuine T0 families use one qualified
completed-session chain through `integrated_decision_prospective_feedback/v3`.
`empirical_setup_outcome_calibration/v2` reuses outcomes/serialized conditions for T5/T10/T20/T60
cohorts, calibration eligibility and deterministic human-review-only policy candidates.
The existing read-only CLI materializes derived research artifacts on demand. No second store,
Daily entrypoint, automatic policy writer or background loop is created.

Workspace admission/durable-store/learning-ledger and older shadow rollforward remain readable
under their own provenance/human-review contracts; they cannot be retroactively converted into
Integrated T0 authority. See the [current contract](empirical_setup_outcome_calibration_contract.md)
and [acceptance](internal/R6_PROSPECTIVE_LEARNING_ACCEPTANCE.json).

## Stage Map

### 1. Host Entrypoint
- **Responsibility:** Windows PowerShell entry wrapper; locates Python interpreter and invokes `stocklookup.py`.
- **Primary Entry Module:** [`stocklookup.ps1`](../stocklookup.ps1)
- **Key Output Contract:** Process exit code and standard console output.

### 2. Owner CLI Dispatcher
- **Responsibility:** Command dispatcher for `daily`, `roadmap`, `portfolio`, and `action-center`.
- **Primary Entry Module:** [`stocklookup.py`](../stocklookup.py)
- **Key Output Contract:** CLI execution status, terminal handoff summary, and process exit code.
- **`daily` production vs. diagnostic split (since 2026-09-22,
  `CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1` corrective pass):** the
  zero-flag invocation (`stocklookup.ps1 daily` with no extra arguments -- the owner's actual
  daily command) now delegates entirely to
  [`tools/run_owner_daily.py`](../tools/run_owner_daily.py)'s `run_workflow()`, the same
  production entrypoint the desktop one-click launcher (`tools/run_owner_daily.ps1`) already
  uses: durable crash-resume journal, auto-resume, presentation-binding attestation, governed
  Dashboard publication, AI handoff, Action Center. Any diagnostic/override flag (`--session`,
  `--runtime-root`, `--retained-evidence-root`, `--output-root`,
  `--no-new-provider-acquisition`, `--preflight`, `--replay-local`, `--replay-operation`,
  `--local-only`) still runs the original separate inline pipeline/decision-brief/handoff/
  dashboard sequence below it in `stocklookup.py` -- never a second production Daily.

### 3. Current Canonical Daily Operation
- **Responsibility:** Sequential post-close lifecycle: session qualification gates (Phase A/B), market-data acquisition, session input registration, daily producer execution, runtime materialization, trusted-subset release, and (since 2026-09-22, `CANONICAL_DAILY_POST_HANDOFF_AND_OWNER_WORKFLOW_RECONCILIATION_V1`) post-handoff observers -- Signal Velocity, current foreign-flow (since 2026-09-23 `CURRENT_FOREIGN_FLOW_DAILY_ACTIVATION_V1`, production Daily enables live exact-session acquisition; failure degrades and cannot invalidate Core Daily), Flow-Price Divergence, and a post-handoff prospective outcome-feedback rerun -- run via the shared `canonical_post_close_pipeline.run_post_handoff_observers()` / `run_post_handoff_prospective_outcome_feedback()` helpers strictly after `build_tiered_bundle` binds the same-session canonical handoff.
- **Primary Entry Module:** [`canonical_daily_operation.py`](../canonical_daily_operation.py) (invoked via [`daily_analysis_pipeline.py`](../daily_analysis_pipeline.py) `--canonical-post-close`)
- **Key Output Contract:** `canonical_daily_operation/v1` manifest (`operations-review/canonical-post-close-v1/<session>/post-close-attempt-<ts>/canonical_daily_operation_manifest.json`).
- **Diagnostic sibling:** [`canonical_post_close_pipeline.py`](../canonical_post_close_pipeline.py)'s own `run_canonical_post_close()` is a non-production diagnostic CLI (not reached by `stocklookup.ps1 daily`) that now shares the same post-handoff helpers rather than reimplementing them, so the two paths cannot silently diverge again.

### 4. Market-Data Acquisition
- **Responsibility:** Governed market-wide post-close EOD data capture (P3F9B route) and exact-session MVA snapshot materialization.
- **Primary Entry Module:** [`canonical_post_close_pipeline.py`](../canonical_post_close_pipeline.py) (`acquire_and_materialize`)
- **Key Output Contract:** `p3f9_exact_session_mva_snapshot/v2` (`market_wide_mva_p3f9_scaleout_artifact.json`).

### 5. Canonical / Current Research
- **Responsibility:** Deterministic multi-axis research computation across descriptive metrics, breadth, sector leadership, corporate intelligence, screening opportunities, and daily producer operations.
- **Primary Entry Module:** [`daily_producer_pipeline.py`](../daily_producer_pipeline.py) / [`daily_research_session_operations.py`](../daily_research_session_operations.py)
- **Key Output Contract:** `daily_research_session_operation/v1` (`daily_research_session_operations_artifact.json`, `ai_research_session_bundle.json`).
- **Decision-fitness diagnostic:** `current_research_decision_input.py` now exposes `current_research_coverage_decision_fitness/v1`, a read-only market-wide coverage/gap projection over the existing Integrated Decision input contract. CLI: `tools/build_current_research_decision_fitness.py`. It does not recompute analytical axes or alter posture/authority.

### 6. Tactical (Tactical and Behavioral Engine V2)
- **Responsibility:** Evaluates nine-state entry classification, close-only technical structure, multi-label setup tags, and confirmation/invalidation price boundaries.
- **Primary Entry Module:** [`tactical_behavior_context.py`](../stocklookup_core/tactical/tactical_behavior_context.py) (with [`watchlist_tactical_entry_classifier.py`](../stocklookup_core/tactical/watchlist_tactical_entry_classifier.py))
- **Key Output Contract:** `tactical_behavior_context/v1` (`tactical_behavior_context_artifact.json`).

### 7. Financial V2
- **Responsibility:** Structured financial fact extraction, period semantics resolution, layered issuer applicability classification, and working capital/liquidity ratios.
- **Primary Entry Module:** [`financial_analysis_engine_v2.py`](../stocklookup_core/financial/financial_analysis_engine_v2.py) / [`financial_analysis_product_projection.py`](../stocklookup_core/financial/financial_analysis_product_projection.py)
- **Key Output Contract:** `financial_analysis_product_projection/v1` (`financial_analysis_product_projection_artifact.json`).

### 8. Valuation / Opportunity Integration
- **Responsibility:** Multi-method valuation metrics, peer-relative percentiles, opportunity context join, and governed research candidate stance assignment.
- **Primary Entry Module:** [`current_valuation_opportunity_integration.py`](../stocklookup_core/valuation/current_valuation_opportunity_integration.py)
- **Key Output Contract:** `opportunity_context/v1` and `security_decision_context/v1` (`current_valuation_opportunity_integration_artifact.json`).

### 9. Investment Decision Workspace
- **Responsibility:** Multi-axis decision convergence joining Opportunity Context, Tactical V2, Financial V2, liquidity research proxy, and research stances into unified per-ticker decision records.
- **Primary Entry Module:** [`investment_decision_workspace_projection.py`](../stocklookup_core/decision/investment_decision_workspace_projection.py)
- **Key Output Contract:** `investment_decision_workspace_dashboard_projection/v1` (`investment_decision_workspace_dashboard_projection_artifact.json`, `decision_workspace_cards.json`).
- **Sealed pre-handoff, additively re-joined post-handoff:** this Workspace is materialized inside Daily Producer, before Signal Velocity/Flow-Price can exist for the same session (they are post-handoff observers -- see stage 3). `canonical_post_close_pipeline.run_post_handoff_presentation_projection()` (2026-09-22, `CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1`) additively re-runs the identical join once those observers exist, into a new directory, then `canonical_dashboard_runtime_release.restage_runtime_with_presentation_projection()` overlays only the already-promoted runtime-served copy (never the sealed Producer operation directory) so the Dashboard actually shows same-session Velocity/Flow-Price instead of "unavailable by construction."
- **`research_stance`/`entry_action` vs. `research_action_posture`:** this card's `research_stance`/`entry_action`/`entry_state` (from `security_decision_context.infer_research_stance`) are a distinct, tactical/research-candidate presentation layer -- a separate deterministic policy function from `integrated_investment_decision_product.decide_research_action_posture`'s `research_action_posture` (the integrated analytical decision posture surfaced in the AI handoff/Action Center). Both are legitimate, intentionally separate layers over overlapping evidence, not two competing BUY/SELL verdicts for the same question; see the card's own `authority_boundary.research_stance_is_not_execution_order`.

### 10. Screener Master Projection
- **Responsibility:** Presentation read-model joining the canonical screening snapshot with Decision Workspace cards, Financial V2 compact states, VCI sector labels, and tactical/liquidity fields.
- **Primary Entry Module:** [`screener_master_projection.py`](../screener_master_projection.py)
- **Key Output Contract:** `screener_master_projection/v1` (`screener_master_projection_artifact.json`, `screener_master_projection.json`).

### 11. AI Handoff
- **Responsibility:** Deterministic packaging and idempotent git publication of daily research session bundle and next-session decision brief to the private AI handoff repository.
- **Primary Entry Module:** [`ai_handoff_publication.py`](../ai_handoff_publication.py) / [`next_session_decision_brief.py`](../next_session_decision_brief.py)
- **Key Output Contract:** Git commit in private handoff repo (`LATEST.json`, `ai_research_session_bundle.json`, `next_session_decision_brief.json`).

### 12. Dashboard Release
- **Responsibility:** Atomic validation, staging, and publishing of canonical runtime artifacts and projection models to the web dashboard distribution repository.
- **Primary Entry Module:** [`dashboard_release_publisher.py`](../dashboard_release_publisher.py) / [`publish_dashboard.py`](../publish_dashboard.py)
- **Key Output Contract:** Published dashboard bundle (`decision_workspace_cards.json`, `screener_master_projection.json`, `bundle_manifest.json`).


### Corporate Intelligence forward-driver context (R4)

`current_corporate_intelligence_axis.build_forward_driver_context` projects the retained
classified event axis into `forward_driver_context/v1`. The Integrated Decision corporate
join attaches it to the corporate summary, evidence-axis context and Current Research
CORPORATE dimension; `forward_driver_coverage` aggregates over the decision denominator.
This is a non-voting research explanation. The source axis/identities and all action policy
remain unchanged. See [the contract](ANALYTICS_AND_DECISION_FEATURE_SPEC.md#forward-driver-explanatory-contract-r4-2026-10-01)
and [retained acceptance](internal/R4_FORWARD_DRIVER_ACCEPTANCE.json).


## Governed Current Research intrinsic/scenario valuation — R5

`canonical_post_close_pipeline.build_enrichment_components` supplies retained canonical semantic rows, governed entity applicability and the decision session to `canonical_daily_financial_v2_materialization.build_evaluated_valuation_artifact`. The existing `current_research_valuation_context` attaches `current_research_intrinsic_scenario/v1` after the unchanged peer-relative evaluation. `intrinsic_valuation.py` owns the single assumption/input readiness boundary, existing FCFF/Net-Net evaluation and the existing reverse FCFF solver. Governed production assumptions reside in `config/current_research_valuation_assumptions.json` (empty, with no generated defaults).

`integrated_investment_decision_product` binds R4 forward-driver explanations, adds the verified projection to its VALUATION evidence context and exposes it through `current_research_decision_input`. The existing opportunity re-evaluation preserves a verified projection. These fields do not vote in posture or replace relative valuation. Contract and ticker/session identity failures block only the intrinsic context. Product wrapper/content hashes bind the added fields; decision identities and posture policy remain unchanged.

`tools/replay_intrinsic_scenario_valuation.py` reads only explicit canonical October 1 paths plus the pinned Financial V2 semantic authority. It writes local scratch outputs, checks the 1,683-ticker denominator, deterministic models, additive-field allowlist, existing decision fitness/identities/postures and input byte hashes. [Portable acceptance](internal/R5_INTRINSIC_SCENARIO_ACCEPTANCE.json) is reviewable without private source copies. [Method contract](intrinsic_sector_valuation_contract.md) defines conditional calculations, native output units, missing-input/implementation/applicability states and reopen gates. No acquisition or ordinary Daily is required for this replay.
