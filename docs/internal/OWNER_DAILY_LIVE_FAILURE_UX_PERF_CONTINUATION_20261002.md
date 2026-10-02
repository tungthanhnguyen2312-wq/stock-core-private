# Owner Daily live failure, UX and performance continuation — 2026-10-02

Milestone: `OWNER_DAILY_LIVE_FAILURE_UX_AND_PERFORMANCE_CORRECTIVE_V1`.
Owner authorizes release and governed completed-session resume. Preserve unrelated untracked `data/`.
Do not re-audit, reacquire, rebuild T0, alter postures, or recreate Claude's patch.

## P0 — RELEASED AND LIVE PASS

Base Daily main: `bc76cd9e5cda32559b1c23f9261383ba6cb93fce`.
Claude's existing `0315ed48e8d69fc255f586a04fcda7873883195d` retained.
PR #43: https://github.com/tungthanhnguyen2312-wq/stock-core-private/pull/43
P0 main merge: `c08b6783ad2102a15e78313de650470374c56365`; local main synced.
All four PR and main CI jobs green. Required focused tier: 1,793 passed, 41 skipped,
14 deselected, 30 subtests passed. Local resolver/workflow 257 passed; expanded guards 153 passed;
portable Git fixture correction 40 passed. Invalid UTF-8 fallback also covered.
The exact-session resolver retains session/contract/recomputed content identity/coverage/Brief checks.
The atomic streaming writer preserves valid destinations on failed serialization/write.

Verified source: `operations-review/integrated-investment-decision-product-v1-20261002/integrated_investment_decision_product_artifact.json`.
Restored exact bytes atomically to `operations-review/canonical-post-close-v1/2026-10-02/enrichment/integrated_investment_decision_product.json`.
Source session 2026-10-02, 1,683 records, 1,333,531,241 bytes, contract `integrated_investment_decision_product/v1`.
Content identity recomputed and equals sealed manifest:
`integrated_investment_decision_product/v1:964774b2282cc9af8ade4bf1a2ece35e207b740a8cbdd8d10da83b59e5622b77`.
Raw byte SHA256: `c569b80f752dfda9a8a63ae682d1596d716de56ff319964e21140f6cce53ea74`.
Original retained source size/mtime unchanged. No decision regeneration or reserialization during repair.
Verification plus atomic copy took 79.806 seconds.

Canonical operation: `canonical_daily_operation:eb00f5c8dedc9e6b023471b8f0157338d9a9ded1ed2b6f6a13a27b72f3cdfc80`.
Producer operation: `daily_research_session_operation:8ffe280acf28cd191a849af90611ab1c3986a14c539b18252d5898d1978bd054`.
Sealed `run_manifest.json` in that exact producer operation directory.
Governed `tools.run_owner_daily.main --replay-completed-session 2026-10-02` reached PASS in 180.848 seconds.
Assertion-guarded ordinary analytical Daily execution calls: ZERO.
Producer state NO_CHANGE; Daily ALREADY_COMPLETED / REUSED; Dashboard REUSED_EXISTING_PUBLICATION,
PUBLISHED/public byte identity PASS at `6e8feabaa27404f372187be809f4491a8a91336f`.
AI authority exact `964774b2...`; parity 1,683 full-universe / 79 scoped / 10 owner-focus;
remote READY_FOR_AI, SHA `0f3380e22c50ab9eac9261d78df3f2a5a7258cff`.
Action Center READY at identity `personal_investment_decision_action_center/v1:59ed46fdea0da2756125cb0ce52e3e5a121a3c474969dcabbafb6632fc04f728`; owner view opened.
Canonical operation record, sealed manifest and completed-session registry hashes match before/after.
Pre-existing T0 status remains UNAVAILABLE (`PROSPECTIVE_SNAPSHOT_RETENTION_FAILED:MemoryError:`);
no T0 was invented, rebuilt or mutated. Peak resume memory 6,733,393,920 bytes (~6.27 GiB).
AI verification/publication phase took ~101 seconds; this is fresh measured P2 profiling evidence.

Local evidence under the existing workspace `run-logs/` (one level above Producer):
- `stock_lookup_daily_20261002_recovery.proof.json`
- `stock_lookup_daily_20261002_retention.before.json` and `.after.json`
- `stock_lookup_daily_20261002_resume.result.json`, `.progress.jsonl`, `.log`, `.execution.proof.json`
Preserve original `stock_lookup_daily_20261002_154250.*`.

## P1 — RELEASED AND LIVE PASS

PR #44: https://github.com/tungthanhnguyen2312-wq/stock-core-private/pull/44
P1 code merge/main: `1fe92ca64c49a87ac1ceef10295035ac1faddb9d`; local main synced.
All four PR and main CI jobs green. Source branch `fix/owner-daily-vietnamese-terminal-20261002` retained.
`stocklookup.ps1 daily` shares the existing Desktop PowerShell launcher; Python orchestration is unchanged.
Nine Vietnamese rows; UTF-8 console/native/Python/log encoding; BOM on PowerShell source for PS 5.1,
normal UTF-8 log bytes. Native stderr text and exit codes preserved.
Interactive cursor updates with safe redirected fallback; no ANSI in redirected output.
Default console hides child commands/helpers/hashes/paths/resource clutter and heartbeat spam;
detailed raw log/JSONL telemetry retained. Diagnostic mode explicitly shows raw output.
Phase boundaries, five-percent acquisition thresholds, changed retry/failure counters and real
low-disk warning are visible. Real DNSE request/coverage counters only; reuse is not acquisition.
Initial phase ETA: P50 of at least three successful ordinary Daily runs from at most 30 recent
result names, each result <=2 MiB and same-name sidecar <=16 MiB; session/run binding checked.
Replay/failed/corrupt/nonfinite timing evidence excluded. No history means `đang ước tính`.
Denominator ETA uses real measured work; a heartbeat cannot invent ETA. Completed phases show elapsed.
Vietnamese PASS/FAILED views include total/session/components or phase/explanation/code/resumability/log.
Tests: 33 progress/real Windows launcher passed; 136 workflow passed; 15 entry-route/smoke checks passed.
The real production PowerShell launcher (no replacement entry script) ran with explicit
`-ReplayCompletedSession 2026-10-02 -NoPause` and returned PASS in 15.181 seconds.
All nine phase rows and Vietnamese final screen validated; UTF-8 console/log decode cleanly;
no replacement characters, ANSI, raw helper commands or resource clutter in redirected output.
Daily reused; Producer NO_CHANGE; Dashboard/AI publication and Action Center reused; owner view opened.
Retained operation/manifest/registry hashes still match the pre-P0 proof. T0 remains unchanged/unavailable.
Separate harmless Windows PTY fixture exercised cursor-based in-place updates successfully (exit 0).
Live result/log: workspace `run-logs/stock_lookup_daily_20261002_191840.result.json` and `.log`;
sidecar `.progress.jsonl`; capture `stock_lookup_daily_20261002_p1_console.txt`;
acceptance `stock_lookup_daily_20261002_p1_acceptance.proof.json`;
retention comparison `stock_lookup_daily_20261002_retention.p1.after.json`.
The acceptance helper initially assumed a `remote.status` field in the reused AI shape;
the actual launcher had already returned PASS. Saved-result verification was corrected to
the existing `ALREADY_PUBLISHED_VERIFIED` contract plus exact remote session/SHA; no new run needed.

## P2A — RELEASED: feedback IID classification-summary cache

Milestone: `OWNER_DAILY_P2A_FEEDBACK_IID_SUMMARY_CACHE_V1`.
Release PR: https://github.com/tungthanhnguyen2312-wq/stock-core-private/pull/46
Starting synchronized main/origin/main: `9914d4f80fafdd1c41e07470b259d39a933927bc`.
Release branch: `perf/feedback-iid-summary-cache-20261002`.
Validated code HEAD: `f8af02017252a52debeb4c1eff5902b6d1034c67` (before this continuation-only update).
Released branch HEAD: `b58db05263450419ffb6ee5bf9f572a80f8b3c37`.
Merged code/main checkpoint: `9c9ec3123ab71c5347727ad433c0da0a734b72cf`.
PR #46 merged on 2026-10-02; all four PR CI jobs and all four main CI jobs passed.
Main CI run: https://github.com/tungthanhnguyen2312-wq/stock-core-private/actions/runs/37013903555
Local main/origin/main verified equal at the merged code checkpoint; only unrelated
untracked `data/` remained. This final release-record update changes documentation only.

Contract: `integrated_decision_classification_summary/v1`, in the versioned
`integrated_decision_classification_summary_cache/v1` container at ignored derived path
`operations-review/prospective-decision-outcome-feedback-v1/_artifact_summary_cache.json`.
Entries contain source relative path, size, mtime_ns, current raw-byte SHA-256, four IID
header fields, record count and deterministic summary identity. Maximum 2,048 entries /
8 MiB; sorted deterministic serialization, fsync and same-directory atomic replacement.
Cache failures preserve analytical behavior and previous cache bytes; corrupt entries
fall back to the existing loader. Historical IID evidence is never rewritten.

The cache is non-authoritative. Size/mtime/path alone cannot validate a source: warm
reuse streams and hashes its current bytes with bounded memory and checks metadata
stability. Same-size/same-mtime malformed replacement therefore cannot survive on an
old summary. Exact handoff identity/session and operation identity/session/output IID
identity, where declared, remain binding; conflicts force the original full parse and
qualification. Existing qualification policy is unchanged. There is no latest fallback,
other-session substitution, T0 promotion or policy/authority change.

Cold encounters perform exactly one original IID JSON parse, derive the small summary,
and reuse that parsed artifact for the same call. Warm classification-only encounters
perform zero IID JSON parses. Legacy GENUINE cases still load the real record payload.
Both existing IID write locations emit summaries from their in-memory artifacts without
another IID serialization or parse. Source-byte hashing adds streaming I/O; this release
avoids decoding and the large object graph, not all reads. Modern immutable-snapshot
handoffs retain their existing early skip. Pre/post feedback builders remain separate.
`use_summary_cache=False` and external `cache_metrics` provide the full-parse oracle and
parse/byte counters without changing feedback output fields or identity.

Validation: 155 hermetic feedback/retention/measurement/bridge/canonical-pipeline tests
passed, 6 retained/provider cases deselected. The feedback file contains 27 passing
cases including the required 20-case acceptance matrix: exact cold/warm/full canonical
output bytes and artifact identity; linked classification-only read suppression; genuine
payload reads; missing/empty/malformed/current source and size/mtime invalidation;
same-stat corruption; resealed wrong identity/session; handoff/operation conflicts;
atomic-write failure; corrupt/oversized cache; in-memory emission; pre/post equivalence;
and later-session preservation of earlier temporal inventory. Unrelated untracked `data/`
was preserved. CI uses the existing selected feedback file; no workflow expansion.

Bounded real retained validation used only the September 30 mutable copy at
`operations-review/canonical-post-close-v1/2026-09-30/enrichment/integrated_investment_decision_product.json`.
Its source is 171,551,405 bytes, classified CURRENT_VIEW_OF_OLD_SESSION.
An initial probe selected the immutable-linked original, which correctly retained its
existing early skip and yielded no inventory; that probe is not a performance claim.
Fresh-process measurements on the classification-only mutable copy:

| Mode | Wall seconds | Peak RSS bytes | Full IID parses | IID bytes parsed |
| --- | ---: | ---: | ---: | ---: |
| Cold | 4.453715 | 966,352,896 | 1 | 171,551,405 |
| Warm | 0.405221 | 118,857,728 | 0 | 0 |

Avoided: 1 full IID parse / 171,551,405 decoded bytes. Both corpus canonical SHA-256:
`e1e281292631d4b6a3fe576af664c2de4201f3272a7ed8129f2e5629d8e87ef7`.
These are bounded discovery measurements, not whole-feedback or ordinary Daily timings.
No acquisition, Daily, publication, P0/P1 replay or historical T0 rebuild was run.
Benchmark helper/cache remain ignored scratch, not another strategic document.

## Checkpoint disposition and exact remaining slices

`P2A_RELEASED_COMPLETE`: implementation, validation, PR #46 merge, green PR/main CI
and main synchronization complete. Stop here. P0/P1 stay complete. Do not repeat Claude's read-only profile or
start another P2 slice without owner authorization. The exact remaining order is:

B. tactical index/read deduplication
C. settled feedback contribution cache
D. single IID serialization + atomic byte copy
E. tactical outcome persistence redesign
F. telemetry sizing cleanup

The only durable continuation is this file. Keep distinct pre/post temporal admission,
unchanged policy/authority and clean-full-rebuild equivalence for later approved slices.
