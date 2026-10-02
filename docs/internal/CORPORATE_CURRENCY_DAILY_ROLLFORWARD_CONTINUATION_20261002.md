# Daily corporate currency rollforward continuation checkpoint

Status: CHECKPOINT_READY_FOR_CONTINUATION. Inspection and dedicated worktree creation only; implementation, acceptance, and release remain outstanding. This is not milestone completion.

## Repository truth

- Verified local main and origin/main: c96c95ca4826709663b4788aab6edc1481e36229.
- Main Producer CI run 36937410044: completed SUCCESS.
- Primary checkout: C:/Projects/StockLookup/stock-core-private; tracked clean, unrelated untracked data/ preserved.
- Dedicated worktree: C:/Projects/StockLookup/worktrees/corporate-currency-daily-rollforward-20261002.
- Branch: feature/corporate-currency-daily-rollforward-20261002, based on verified main.
- No production Daily, official HTTP acquisition, runtime publication, registry mutation, raw-evidence mutation, or background job performed for this milestone.
- No PR opened for this milestone. No implementation tests run yet. Roadmap status is unchanged: current-currency COMPLETE, Daily rollforward NEXT.
- Standing owner autonomy includes implementation, release, merge, main sync, and subsequent useful milestones. No routine approval is needed. One writer; no agents.
- Full current owner request: C:/Users/tungt/.codex/attachments/75d74622-4878-4b00-b662-ad03d55b9dde/Pasted text.txt.

## Inspected production call graph and next implementation boundary

stocklookup.ps1 -> stocklookup.py daily -> canonical_daily_operation.run_canonical_daily_operation -> canonical_post_close_pipeline.acquire_and_materialize -> exact-session snapshot validation -> daily_session_level2_package.materialize_independent_components -> dependent components. Canonical operation then registers inputs, validates/freezes completed session, builds enrichment components, builds Integrated Decision/product, publishes and collects prospective evidence.

The earliest suitable refresh seam is after valid exact-session market snapshot and before independent Level-2/corporate consumers. Refresh belongs in session orchestration, not per ticker, Integrated Decision record, or publication. Propagate one immutable selection/receipt downstream; consumers verify selected bytes instead of rediscovering latest.

Relevant canonical functions:

- canonical_daily_operation.run_canonical_daily_operation: injected acquisition seam receives now and mode; DIAGNOSTIC plus no_new_provider_acquisition is historical compatibility. Normal orchestration enables existing official liquidity rollforward. Registry/freeze precede enrichment.
- canonical_post_close_pipeline.acquire_and_materialize: carries now, retained_evidence_root, output_root, no_new_provider_acquisition, historical_compatibility, optional rollforward flags. Snapshot coverage failure precedes independent components.
- canonical_post_close_pipeline.build_enrichment_components: obtains session_artifact_paths twice, including a separately resolved retained-root latest official context; corporate context and corporate axis repeat lookup. Integrated Decision consumes corporate axis and enforces market-session forward-driver cutoff.
- canonical_post_close_pipeline.run_canonical_post_close: diagnostic route has its own register/freeze/enrichment calls; propagate selection consistently without enabling unintended live acquisition.
- daily_session_level2_package.session_artifact_paths currently calls _latest_official_event_context_dir without a historical knowledge cutoff. Narrow-fix historical callers to date/known-time appropriate evidence and frozen registry selection.

## Critical findings; design still to finalize before editing

The same invocation may target October 1 market session while acquiring October 2 CURRENT RESEARCH evidence. Acquisition date must use actual VN civil/knowledge time, never target_session. October 2 current context must not rewrite October 1 frozen registry, packet, prospective T0, historical replay, or previously frozen corporate identity.

Keep explicit current research selection and historical market/T0 selection separate. A current research overlay may require a civil-date output namespace/sidecar with receipt; using a market-date IID path for fresh October 2 observations risks overwriting October 1. Finalize how Dashboard/brief actually receives fresh non-voting research without changing the frozen packet. Do not claim architecture complete until this is implemented and tested.

Registry already has optional event_context and official_universe fields. Reuse those fields for eligible new session lineage; do not create a competing registry. Completed entries must remain byte/identity immutable.

Important loophole: canonical_post_close_pipeline.NOT_SESSION_LOCKED_REGISTRY_KEYS excludes event_context and official_universe during completed-session comparison. register_session_inputs can report ALREADY_FROZEN_IDENTICAL with a newly discovered optional identity while actual registry stays old; enrichment then independently consumes latest. Narrow correction should reuse and verify the completed entry's actual frozen optional selection, not ignore it and not reject a harmless new current overlay merely because latest has advanced. Existing test around tests/test_canonical_post_close_pipeline.py lines 720-745 explicitly expects optional advance; update this expectation to immutable completed selection with independent current research currency.

Current enrichment writes corporate axis to a shared artifact path. Avoid overwriting a historical frozen corporate identity with the current overlay.

## Existing acquisition capabilities to reuse

- official_corporate_event_incremental_acquisition.acquire: current VN date/acquired_at; same-date SUCCESS prohibits duplicate acquisition. Prior FAILURE permits a consciously invoked explicit new attempt; previous failed manifest archived by canonical SHA. No hidden retry.
- Shared official_acquisition_budget.AcquisitionBudget: default 64 requests, 32 MiB total, 8 MiB response, 180 sec wall budget, 30 sec HTTP, 16 pages per surface. All HNX/HOSE requests use it. Preserve these bounds, response bounded reads, source page reconciliation, raw immutability, and failure kinds.
- acquire accepts hnx_rights_window; existing source pFromDate/pToDate filter was verified by PR37. HNX wrapper disclosures default False; HOSE uses 11 public routes. Do not regress routes or manufacture authority.
- materialize_current_official_event_context accepts explicit acquisition_session. It currently reads source artifacts but does not itself replay raw-hash verification; add integrity verification for successful reuse/recovery. It currently unconditionally writes derived output; prefer verified matching materialization reuse and fail closed on unexpected immutable selection conflicts.
- Acquisition sessions under operations-review/official-corporate-event-acquisition-sessions; raw store under operations-review/official-corporate-event-raw-store; manifest acquisition_attempt.json.
- Existing replay functions in HNX and HOSE modules verify raw hashes and artifact identity. Reuse rather than duplicate parsing.
- Current lifecycle code already preserves plans, requires explicit execution, never substitutes record date for ex-date. R4 blocks future-information as of a historical market cutoff. Preserve these safeguards.

## Required rollforward contract

One session decision; successful current civil-date reuse with zero HTTP, otherwise at most one bounded attempt per ordinary invocation. Missing materialization after retained SUCCESS recovers offline. Failure falls back only to verified permitted descriptive prior context, explicitly stale; no partial SUCCESS and no unrelated-lane global failure. Corrupt/missing receipt references fail closed.

Receipt fields: contract version, target market session, acquisition civil date, observed_at, action (REUSED_CURRENT_SUCCESS / ACQUIRED_CURRENT_SUCCESS / REFRESH_FAILED_REUSED_PRIOR / REFRESH_FAILED_NO_USABLE_CONTEXT), selected acquisition session/attempt identity/path, context identity/path, acquired_at, source age/freshness, budget policy identity, request/byte/page counts, exact failure reason, prior success identity, historical-use prohibition, authority NONE / CURRENT_RESEARCH_EVIDENCE_ONLY. Portable paths, no sensitive URLs. Freeze selected identity and bytes; no second latest lookup.

## Retained offline acceptance; no new HTTP required

Prior release worktree: C:/Projects/StockLookup/worktrees/roadmap-r5-r7-release-20261002.
Prior branch feature/current-corporate-currency-budget-20261002 head e0746598b46b61ea49c33d689aa7d70fd6b5c5a4; merged PR37 at c96c95c.

Retained root there: .stocklookup/scratch/corporate-currency-window-20261002.
Successful acquisition 2026-10-02T05:38:59+07:00, September 2-October 16 rights window; 31 requests/capture hashes, 3,216,925 bytes, 24.542608 seconds. Context 186 events/174 names in retained official 1,507-name denominator. R4 retained acceptance: 160 explanatory drivers / 153 names, 26 blocked, 184 ANNOUNCED / 2 UNKNOWN, zero inferred executions. These are fixture regression facts, not product requirements.

Other retained roots: .stocklookup/scratch/corporate-currency-20261002 (initial page-budget failure), .stocklookup/scratch/corporate-currency-upcom-window-probe (source window verification).
Committed reports: docs/internal/CURRENT_CORPORATE_CURRENCY_ACCEPTANCE.json, CURRENT_CORPORATE_CURRENCY_WINDOW_ACCEPTANCE.json, CURRENT_CORPORATE_CURRENCY_VALIDATION_20261002.md. Prior local handoff: .stocklookup/scratch/CORPORATE_CONTINUATION_LOCAL.md. Do not redo PR37 audit; verify only changed boundary and retained hash stability.

## Exact next actions

1. Re-read owner request and this checkpoint; confirm main/worktree state without restarting R1-R7 audits.
2. Finalize minimal dual knowledge-time/current-research versus frozen-market selection propagation and product consumption. Inspect level2.materialize_independent_components, market-wide corporate tool inputs, publication/brief projection to resolve remaining product seam.
3. Implement rollforward helper, source integrity/idempotent materialization, canonical orchestration propagation, explicit current selection, narrow historical lookup/registry fixes, receipt telemetry and failure containment.
4. Add >=20 owner-listed offline cases, including independent substages, exact selection stability, prior FAILURE explicit retry, budget kinds, missing materialization resume/raw unchanged, corruption fail closed, current research versus Oct1 T0, completed registry immutable, unrelated lanes survive.
5. Run layered focused tests, retained acceptance (31 hashes /160 drivers/153 names), Producer CI-equivalent, py_compile, roadmap --check, diff --check. Offline smoke guard forbids requests/urllib/socket; mock new orchestration seam appropriately. Retained-root-dependent tests may need STOCKLOOKUP_RETAINED_EVIDENCE_ROOT pointing to primary retained evidence; classify genuine environment dependencies explicitly.
6. Update required docs/contracts/roadmap truthfully only once implementation and validation justify state; checkpoint, push, PR, inspect CI, fix regressions, green merge, sync main under standing authorization.
7. After actual merge, answer all ten owner bottleneck questions; choose next milestone by product usefulness. Do not assume valuation inputs; no default assumptions. Natural production Daily is not required or manufactured.

## Outstanding proof and authority

All new milestone proofs and release remain outstanding. No new Corporate Intelligence coverage or posture change claimed. Existing authority remains NONE / CURRENT_RESEARCH_EVIDENCE_ONLY; no PIT, execution, sizing, financial-fact or valuation-assumption promotion. No external blocker identified. Stop here is a context checkpoint, not a request for approval.
