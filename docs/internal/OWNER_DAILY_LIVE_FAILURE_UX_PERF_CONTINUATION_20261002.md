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

## P2B — RELEASED: tactical index and observation read deduplication

Milestone: `OWNER_DAILY_P2B_TACTICAL_SHADOW_IO_DEDUP_V1`. Starting main/origin/main:
`d956057e8706ec04e29dd392073820abe8ce3f9d`. No signal rule, threshold, observation or outcome
identity/content, shadow authority, posture or evidence-mode change; no outcome-contract change.

- **Run-scoped index.** `TacticalArtifactIndex` (frozen, read-only `session -> exact artifact path`) is built once
  by `build_tactical_artifact_index` and passed explicitly through `collect_session`, `mature_all`, `main` and the
  historical-mapping runner. Exact declared-session lookup only; no latest/mtime fallback; ambiguity still raises
  at construction; unparseable artifacts are still skipped at discovery and still raise on load. No global or
  persistent cache. Calling without an index keeps the previous behavior.
- **Single observation read.** `ProspectiveShadowObservationStore.iter_validated_observations` streams one file at
  a time, identity-verified exactly as `load_observation` (misfiled ids still validate via their canonical path;
  repeated ids yield once). `list_observation_ids` uses it (2 reads/file -> 1). `mature_all` streams, persists
  with `persist_outcome_update(..., validated_observation=)` (no reload; mismatched object falls back to the
  fail-closed reload) and keeps only the status fields `build_collection_status` reads instead of all
  observations and outcomes. Matured ids remain sorted.
- **Known behavioral nuance:** a malformed/tampered observation file now raises when reached in the stream, so
  outcome updates for earlier valid observations may already be appended (valid, content-addressed, idempotent);
  previously the validation pass raised before any write. Error codes are unchanged.
- **Counters:** `build_tactical_artifact_index(metrics=)`, `load_tactical_artifact(metrics=)` and per-store
  `read_metrics`; the tests also count `Path.read_text` directly.

Measured (synthetic hermetic corpus: 24 sessions x 300 tickers, 7,200 observations, 6,900 outcome updates; the
real retained 24 artifacts / ~25k observations are not in the cloud checkout, so no real-corpus timing is claimed).
One final `main` run, old vs new: classifier JSON parses 722 -> 50 (24 index + 26 loads; mature_all alone 648 ->
48); observation file reads 28,800 -> 7,500 (the remainder is `persist_observation` read-back during collection);
outcome reads 6,900 -> 6,900 (P2E); wall 4.06s -> 2.76s; peak RSS 196 -> 130 MB. Store trees (observations +
outcome_updates) and stdout JSON are byte-identical (same tree SHA-256).

Tests: 63 collection/operationalization tests pass (incl. a verbatim legacy-procedure oracle asserting identical
outcome bytes, status and CLI output, idempotent rerun, tamper/malformed/misfiled cases, parse/read counts).
`test_canonical_daily_operation.py` has two retained-fixture errors that reproduce on the unmodified baseline.

## P2D — single IID serialization + atomic byte copy

Milestone: `OWNER_DAILY_P2D_SINGLE_IID_SERIALIZATION_V1`.
Release PR: https://github.com/tungthanhnguyen2312-wq/stock-core-private/pull/49
Starting main: `d956057e8706ec04e29dd392073820abe8ce3f9d`.
Release branch: `perf/single-iid-serialization-20261002`.
Validated code HEAD: `25f56f77e7cb3ae9d74a9df1034b5382ab66ed39`.
Release gate: all four PR CI jobs green, exact-head merge, main verification and synchronization.
Concurrent main advanced to `3b01325f6ea47a3db39a15429440242b791d6a5f` with P2B released.
Only this continuation conflicted; its P2B release record and implementation were preserved.
Final merge/head are recorded by PR #49. This record enters main with that gated release.

Removed only the second IID `_write_json` call in enrichment `_attempt`. The Integrated
Decision builder still produces its standing content identity, then the canonical retained
artifact serializes once with exactly the existing UTF-8 / sorted / indent-2 / trailing-LF
bytes. A private, current-build write receipt captures raw-byte SHA-256 and byte count
from the chunks being written, plus exact path/session/contract/declared content identity.
No receipt is reused across builds, no giant JSON is reparsed to authorize copy, and no
extra full serialization computes the receipt. Existing downstream content-identity checks
remain unchanged; the builder's contract, session and identity/digest declaration are checked.

The enrichment working view receives actual JSON bytes from that exact successful write.
Copy streams at most 1 MiB per read into a unique destination-directory temporary file,
checks source metadata before/after, byte count and raw SHA-256 against the write receipt,
flushes/fsyncs, closes handles and atomically replaces the view. Source stays untouched.
Missing/empty/changed/other-session/unbound source, partial copy, fsync or replace failure
leaves a valid previous view intact and removes the temporary file. The standing optional
component failure result retains its explicit reason/PRIOR_AS_OF_CONTEXT or UNAVAILABLE
status; it never reports BUILT after failed promotion. There is no latest substitution,
symlink/hardlink or pointer-only working view.

Both source and destination P2A summaries still emit from the in-memory artifact, with
independent correct path/stat metadata and the same raw-byte digest. P2A is not redesigned.
Operation/manifest declarations, coverage, postures, identity, T0, Brief, AI handoff and
Current Research authority are unchanged.

Validation: 513 affected hermetic tests passed; 6 retained/provider cases deselected.
Includes 25 new focused cases covering the actual enrichment path, single serialization,
copy byte/JSON/content-identity equivalence, preserved declarations and both summaries,
bounded reads, canonical write failures, bad source/receipt/session/identity/contract,
partial copy/atomic replacement/fsync failures and temp cleanup. Existing P0 zero-byte,
truncation/atomic-write and AI handoff resolver/publication regressions passed. The existing
CI selection adds only the new directly relevant test file.
CI's write-quarantine guard required explicit artifact/output roots on the new synthetic
enrichment call; both are the same isolated temporary root. The fixture was corrected.

Cheap bounded synthetic fixture: 2,161,128 bytes. Old logical path: 2 file serializations;
new: 1 file serialization + streaming byte copy. All four old/new canonical/view SHA-256:
`7fce011beef18b5d978ab887b69e7ac754d032c9367175e07ca9d2fba6661747`.
Old 0.039588 s; new 0.046718 s on this tiny fixture, including receipt hashing/fsync.
This proves invocation/byte equivalence, not a production wall-time speedup or RSS claim.
No 1.33 GB test artifact, ordinary Daily, acquisition or whole-corpus benchmark was run.
Helper/fixture bytes remain ignored scratch. Unrelated untracked `data/` preserved.

## Checkpoint disposition and exact remaining slices

`P2D_RELEASED_COMPLETE` upon the gated PR #49 merge/main sync. D is COMPLETE in this
release. P0/P1/P2A stay RELEASED COMPLETE; P2B was concurrently released by its own work.
This is the final pre-reset job; stop here. Do not start another milestone or repeat
Claude's profile. Original B/C/E/F ordering is preserved: B is already COMPLETE;
remaining, in order:

C. settled feedback contribution cache
E. tactical outcome persistence redesign (outcome identity includes `evaluation_as_of_session` /
   `retained_future_session_count`; the persist read-back is also E's)
F. telemetry sizing cleanup

The only durable continuation is this file. Preserve distinct pre/post temporal admission,
unchanged policy/authority and clean-full-rebuild equivalence for later owner-approved slices.


## Owner-authorized C/E/F/R continuation — 2026-10-03 (ACTIVE)

The previous stop-after-P2D instruction is superseded by the owner's explicit full
technical/release authorization for `OWNER_DAILY_PERFORMANCE_AND_PROSPECTIVE_RETENTION_CLOSEOUT_V1`.
Starting main/origin/main: `238edce670ea02da42e81e8ad3062dad23a4f151`.
One branch: `perf/owner-daily-performance-retention-20261003`.
One dedicated workspace-relative worktree: `../worktrees/owner-daily-performance-retention-20261003`.
Implementation checkpoint: `a4ee8b0f197946a2a62d2d37de090659b1361227` (before this operational record).

C uses `settled_prospective_feedback_contribution/v1` within the ignored derived
`settled_prospective_feedback_cache/v1` container. Bounds: 8,192 contributions / 64 MiB.
Complete bounded 20-session price/diagnostic window plus terminal condition proof;
never age alone or an arbitrary open-condition cutoff. `NOT_SATISFIED_YET` and unresolved
future first-event order remain uncached. Conditions may settle at a proven first event,
structural non-evaluability, immutable T0 price failure or immutable structural T0 mismatch.
Current projected decision/content, container headers, conditions, versions/policies and
exact dependency sequence/snapshot identities/content digests bind reuse. A terminal
chain extension can reuse; dependency mutation cannot. `use_settled_cache=False` remains
the exact full-rebuild oracle. Cache failure/pruning never changes output authority.

E uses `tactical_prospective_shadow_outcome_store/v2`: canonical NDJSON plus a sealed
session manifest, streamed/fsynced in temporary bytes and promoted after the complete
validated pass. Outcome objects and outcome_update_id semantics are unchanged. Failed
or malformed late observations publish nothing. Same-session identical runs reuse;
conflicts fail closed. V1 loose files are never deleted/rewritten. V1/V2/mixed readers
retain the V1 filename tie-break, deduplicate exact identities and expose an explicit
bounded run index (300,000 rows, 50,000 latest observations, 128 MiB encoded latest rows,
8 MiB per outcome row). Derived legacy compaction is disposable and content-validated;
corruption/unwritable derived state falls back to originals. Legacy source bytes are
validated once per index construction; warm reuse suppresses loose JSON decoding.
Normal maturation does not load historical outcome files at all. Historical queries
reuse exact indexed offsets. The benchmark's explicit source/output separation keeps
all derived writes in scratch.

F keeps periodic disk-free/process-memory JSONL sampling, but output-tree recursion
only occurs at configurable phase boundaries or explicit diagnostic sizing. Existing
Vietnamese/redirected UI and detailed telemetry remain unchanged.

R replaces whole-snapshot compact hashing with deterministic JSONEncoder.iterencode
batches, pretty serialization with a same-directory temporary streaming writer plus
fsync/atomic promotion, and existing-destination read_text comparison with bounded
raw byte hashing/size. Native pretty newline behavior is preserved. Full T0 content
remains retained. The engineering memory failure is the additional giant canonical,
pretty and comparison strings alongside the large Integrated Decision object graph;
the exact allocation site of the original MemoryError is not claimed. No October 2
T0 was fabricated or registered. Acceptance is structural/exact, not an arbitrary RSS cap.

Validation so far: 187 integrated directly affected tests passed; Producer's local
CI-equivalent selection passed 1,956 tests / 30 subtests, 16 Windows platform skips,
14 deselected before final focused follow-up cases. Seven offline production smoke
checks passed. Host pip check passed; the existing global installation has ten version
pin drifts and two importable retired provider packages. It was not mutated. Clean
remote CI remains the release dependency check.

Benchmarks and PR/main release control are still in progress. Full completed-price
feedback inventory was stopped at measured helper RSS 6,275,387,392 bytes / available
system memory 511,578,112 bytes, before any T0 write or publication. Use a bounded
100-decision / three real immutable-price-session feedback sample instead; do not
claim a whole-feedback real-corpus wall time. Retention validation uses one complete
real September 9 snapshot (91,663,871 source bytes). All benchmark output is explicitly
NON_AUTHORITATIVE_RETAINED_REPLAY_DIAGNOSTIC under ignored scratch.
