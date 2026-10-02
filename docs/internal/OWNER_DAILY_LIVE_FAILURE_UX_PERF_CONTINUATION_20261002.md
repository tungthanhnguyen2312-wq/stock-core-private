# Owner Daily live failure, UX and performance continuation — 2026-10-02

Milestone: `OWNER_DAILY_LIVE_FAILURE_UX_AND_PERFORMANCE_CORRECTIVE_V1`.
Owner authorizes release and governed completed-session resume; no further approval required.
Preserve unrelated untracked `data/`. Do not re-audit, reacquire, rebuild T0 or recreate Claude's patch.

## P0 checkpoint

Base main: `bc76cd9e5cda32559b1c23f9261383ba6cb93fce`.
Branch: `fix/owner-daily-live-failure-ux-perf-20261002`.
Claude commit: `0315ed48e8d69fc255f586a04fcda7873883195d`.
Exact-session resolver and atomic streaming writer retained. Invalid UTF-8 now counts as a damaged
candidate. Existing recomputed identity, session, contract, coverage and Brief checks remain mandatory.
Required CI includes resolver/resume tests. Initial resolver/workflow tests: 257 passed.
Release and live restoration/resume are pending.

## Exact recovery authority

Only phase 6 failed: `M1_CANONICAL_INTEGRATED_DECISION_UNAVAILABLE`.
Daily LOCAL_COMPLETE, Producer COMPLETED, runtime/trusted subset READY, Dashboard published.
Zero-byte view: `operations-review/canonical-post-close-v1/2026-10-02/enrichment/integrated_investment_decision_product.json`.
Retained source: `operations-review/integrated-investment-decision-product-v1-20261002/integrated_investment_decision_product_artifact.json`.
Source size 1,333,531,241 bytes; session 2026-10-02; 1,683 records; contract `integrated_investment_decision_product/v1`.
Identity: `integrated_investment_decision_product/v1:964774b2282cc9af8ade4bf1a2ece35e207b740a8cbdd8d10da83b59e5622b77`.
Canonical operation: `canonical_daily_operation:eb00f5c8dedc9e6b023471b8f0157338d9a9ded1ed2b6f6a13a27b72f3cdfc80`.
Producer operation: `daily_research_session_operation:8ffe280acf28cd191a849af90611ab1c3986a14c539b18252d5898d1978bd054`.
Sealed manifest: `run_manifest.json` in that exact producer operation directory.

After merge and clean main sync: verify source contract/session/count/recomputed identity against
sealed manifest; restore exact bytes atomically. Never overwrite a valid conflicting view.
Run `tools/run_owner_daily.py --replay-completed-session 2026-10-02` with distinct external result/progress
paths in existing workspace run-logs. Preserve original `stock_lookup_daily_20261002_154250.*`.
Acceptance: final PASS, exact AI remote identity, dashboard reuse, no acquisition or T0/posture mutation.

## Remaining in strict order

1. P0: release, restore, downstream-only live resume to PASS.
2. P1 after P0 PASS: Vietnamese nine phases, explicit UTF-8 PowerShell/native/log, recent successful
   history median ETA, measured acquisition counters, in-place interactive rendering, sparse redirected
   output, Vietnamese final PASS/FAILED. Preserve existing .cmd → PowerShell → Python owner entrypoint.
3. P2 after P1 secure: profile feedback (pre ~11m36/post ~10m01), tactical shadow (~13m13), huge
   serialization/copy and resource sampling. Deterministic deltas must equal clean full rebuild with
   no temporal leakage/policy changes. Prefer byte copy for required views; avoid frequent recursive sizing.

Update this one file with release/live evidence and exact next action at each checkpoint.
