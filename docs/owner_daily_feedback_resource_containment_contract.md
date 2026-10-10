# Owner Daily outcome-feedback resource containment — contract

`OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1` · authority effect **`NONE / OWNER_DAILY_RESOURCE_CONTAINMENT_ONLY`**.

A resource corrective, not a learning-policy change. No cohort, horizon, maturity, outcome, reason-code, ordering or
identity rule moved; no posture, tactical-owner, threshold, source, PIT, RAW or corporate-action authority changed.
Feedback stays fail-soft and downstream; first-capture evidence (capture, marker, T0, seal index, Technical, Thesis) is
never revised or blocked by it.

## 1. Measured root causes (pre-corrective)

| # | Cause | Evidence |
|---|---|---|
| A | The **parent** Daily process loaded the finished feedback artifact (`_load(feedback_output)`) and kept it inside the `prospective` result for the rest of the run; the post-handoff call loaded it again just to read `artifact_identity`. | 2026-10-02 Daily progress log: parent whole-report readback costs about 2.1 GiB per artifact; the 9.18 GiB high-water mark already occurred in enrichment/T0 before feedback. |
| B | The child decoded **every** retained input whole: each exact-session P3F9B snapshot (≈300 MB file → ≈0.9 GiB of objects, one per chain session, all resident), each T0 snapshot twice (parse + `validate_snapshot` re-canonicalisation), and the 1.33 GB 2026-10-02 decision artifact via `read_text` + `json.loads`. | Legacy builder on the real corpus under a 4 GiB Job ceiling: `MemoryError` at 2.9 GiB while reading the 1.33 GB artifact (54 s); one 87 MB T0 snapshot costs 469 MB to load and 11.6 s to validate vs 34 MB / 1.5 s streamed. |
| C | The whole output was one in-memory object graph (`records` list + `required` + `trigger_invalidation_outcomes` copies), then serialised twice (canonical identity string, then `indent=2` text). | 31,977 rows → 685–743 MB artifacts. |
| D | `run_observed_subprocess` waited in a `while True: communicate(timeout=30)` loop: **no total deadline**. | `canonical_post_close_pipeline` pre- and post-handoff call sites. |
| E | Both calls sat on the critical path with no admission check, so an optional computation could consume the RAM the first capture needs. | 2026-10-02: pre-handoff 696 s, post-handoff 601 s of a 4,655 s Daily. |

IPC (E in the milestone brief) was never the problem: the old child already exchanged only paths; the cost was the parent
re-loading the result. Python-object retention after the child (F) is therefore removed at the source — the parent now
holds a ≤ 20 kB compact status.

## 2. Design

* **Streaming verification.** `prospective_feedback_streaming.load_snapshot_handle` proves a T0 snapshot with
  `bounded_artifact_stream.stream_artifact` (sorted-unique object stream, one record resident): the snapshot identity is the
  SHA-256 of the same canonical bytes `retention._hash` produces (verified byte-for-byte by test), every record identity is
  recomputed, `contract_version`/ticker binding are checked, duplicate or unsorted keys fail closed. Equivalent to
  `validate_snapshot`; an unproven snapshot is excluded exactly as before. The original immutable file stays the only authority.
* **Receipts, not a second representation.** A verified header + record count + sealed T0 closes are cached under
  `operations-review/prospective-decision-outcome-feedback-v1/_stream/` keyed by the **SHA-256 of the exact source bytes** and a code
  digest. A corrupt, swapped or stale receipt is ignored and rebuilt. Receipts never replace the file.
* **Source-byte binding between proof and use.** Phase 2 re-streams records through a hashing reader; the bytes the parser consumed must
  hash to the proven value (`FEEDBACK_SOURCE_CHANGED_DURING_RUN`, fail closed).
* **Compact price index.** The forward bridge only reads the observation whose `session` equals the snapshot's own expected session
  (all matches are kept, so the `len(matches) != 1` rule is preserved). Sessions with a sealed T0 use its sealed closes exactly as before;
  the rest use a streamed per-session index (≈1 MB each) instead of the full 300 MB snapshot.
* **Streaming projection and output.** Rows are produced one record at a time in the original `(session, ticker, decision_identity)` order
  (k-way merge across the sources of one session), appended to two spools, and aggregated through the **original** summary / health /
  false-negative functions fed with reduced rows. The artifact is assembled once: `artifact_identity` is hashed over the canonical members as
  they are written, the identity placeholder is patched, the file is re-read and re-hashed, then published atomically with a completion
  manifest. Peak memory is O(one record + reduced rows), independent of artifact size.
* **Format.** Same JSON content and the **same `artifact_identity`** as `build_feedback_artifact`; on disk the canonical compact layout
  replaces `indent=2` (≈ 27 % smaller). Both layouts are accepted as equal when their content identity is equal
  (`stream_artifact_identity`).
* **Process boundary.** Parent ↔ child exchange paths, identities, hashes and a ≤ 256 kB status sidecar only. The artifact is never
  received, pickled or parsed by the parent.

## 3. FEEDBACK_CALL_RELATION = **INCREMENTAL**

Pre-handoff (`prospective-decision-outcome-feedback-v1/<S>`) runs before session `S`'s handoff exists; post-handoff
(`…-post-handoff-v1/<S>`) runs after the handoff binds `S`'s T0 snapshot. Their effective analytical inputs are **not** identical: post adds
the session-`S` completed chain member, `S`'s T0 snapshot and the handoff-snapshot inventory row. It is a strict superset
(`relate()` returns `INCREMENTAL`, `IDENTICAL`, `DISTINCT`, from deterministic input identities — never timing). The incremental delta cannot be
reduced to "new rows only": growing the chain by one session moves the maturity window of every non-terminal decision, so about half of the existing
rows legitimately change (measured on a real-scale rehearsal: 15,767 of 28,611 shared decisions changed, 12,844 byte-identical, 1,683 new). Neither call is deleted. Reuse applies where it
is exact: a retry, resume or replay with identical inputs and code returns `ALREADY_COMPLETE` without recomputing or rewriting.

## 4. Terminal reuse

* `*.complete.json` (completion manifest) = artifact identity, raw SHA-256, size, record count, **input digest** (data only), **code digest**.
* COMPLETE ⇔ manifest present **and** the artifact's current raw hash equals it. Reuse requires equal input digest *and* code digest.
* A feedback-only kernel lease covers the complete build, manifest and shared status transaction. Windows uses a global target-named mutex with abandoned-owner recovery; POSIX uses blocking `flock` on stable `/tmp` lease files that are never unlinked. TEMP/TMPDIR and Windows session differences cannot split the coordination identity. Kernel ownership releases on crash/death; no polling or sleep loop is used. The parent total deadline includes lock waiting. Targets and any shared status pointer are locked in deterministic path order.
* Exactly one same-input contender returns `BUILT`; later contenders verify COMPLETE and return `ALREADY_COMPLETE`. An atomic hard-link creates the artifact without replacing an existing destination; the manifest is written last. A crash after artifact creation is recovered only by proving equal content, then adopting it. Corrupt/conflicting bytes are never replaced.
* Parent IPC is a UUID attempt-local file; the shared status is published under the same leases as artifact/manifest. A conflicting or failed attempt cannot replace a successful pointer. Parent failure bookkeeping takes only a nonblocking lease and never waits outside the child deadline.
* Changed input at the same path ⇒ `IMMUTABLE_ARTIFACT_CONFLICT` (as before); at a new path ⇒ a new artifact with a distinct identity.
* An equal-identity artifact written by the original builder (indent layout, no manifest) is adopted after a streamed identity proof.
* The existing terminal-only `SettledFeedbackCache` is reused unchanged (its snapshot content proof is read from the file instead of a resident
  object). It is empty until a decision's T+20 matures (no T20 outcome exists yet).

## 5. Resource policy (`feedback_resource_guard.py`)

Defaults (`default_feedback_policy`, overridable by `STOCKLOOKUP_FEEDBACK_*` for operators/tests), calibrated on the real retained 31,977-row corpus
(31,977 rows = 19 sessions x 1,683; host 16 GiB RAM, 3-4 GiB available during the run):

| Quantity | Measured | Default | Margin / rationale |
|---|---|---|---|
| COLD (no receipts, empty derived state) | 263 s (earlier 340 s) | deadline **1,200 s** | 4.6x; one total deadline per child; production's first run also benefits from the existing summary cache |
| CHANGED INPUT (INCREMENTAL, +1 session of 505 MB T0) | 100 s | same | receipts/price index reused for all earlier sessions |
| WARM, new output path (identical inputs) | 134 s (primary), 79 s (reduced) | same | still recomputes rows (output path differs) |
| TERMINAL REUSE (`ALREADY_COMPLETE`) | 23 s, writes nothing | same | hashing + proof of inputs only |
| RETRY after mid-stream kill | 47 s (killed) + 96 s rebuild | same | temporaries of the dead writer removed automatically |
| Child committed peak (Job accounting) | 0.50-0.53 GiB; sampled RSS 0.30-0.33 GiB | ceiling **2 GiB** | 3.8x; growth about +5 MB per session |
| Parent RSS growth around a call | 20-330 KB | n/a | the artifact is never loaded by the parent |
| Admission floors | host available 2.8-4.0 GiB during runs | physical 768 MiB, commit 1 GiB, disk 4 GiB + 2x last output | 1.5x / 2x the child peak; output needs spool + final |
| Legacy builder for comparison | reduced corpus (8,415 rows): 79-122 s, 3.4-3.6 GiB; full corpus: `MemoryError` at 2.9 GiB (54 s) | - | exact identity equal on the reduced corpus |
| Output | 520 MiB (compact) vs 709 MiB (legacy layout, same rows) | - | 26.6 % smaller |

Pre-corrective Daily of 2026-10-02 (progress telemetry): parent RSS 4.1 GiB at the first feedback and 5.2 GiB at the second (the parent peak of 9.2 GiB
is reached earlier, in enrichment/T0, and is not caused by feedback); feedback cost 696 s + 601 s of a 4,655 s Daily.
Estimated Monday: 4,655 - 1,297 + (about 260 + 130) + 2 Thesis children (about 490 s each, measured elsewhere) = about 4,730 s (79 min).

Admission (`admit`) runs before each child: available physical memory, available commit, and free disk (≈ 2 × the last artifact size
for spool + output). Refusal returns `FEEDBACK_RESOURCE_UNAVAILABLE` (or `FEEDBACK_RESOURCE_DISK_UNAVAILABLE`) and **launches nothing**.
Unknown probes do not refuse. There is no daemon and no polling loop: the deadline is `Popen.wait(timeout=…)`, the ceiling is kernel-enforced.

* Windows: the child is created suspended, assigned to a Job Object (`KILL_ON_JOB_CLOSE` + `PROCESS_MEMORY` ceiling), then resumed — it
  never allocates uncontained. Peak accounting survives a kill. If the job cannot be created the child runs with the deadline only
  (`containment = DEADLINE_ONLY`, `containment_degraded = true`, reported). This has no hard memory ceiling or whole-tree guarantee: only immediate-child reaping is known. A timeout or memory termination in this mode returns `CHILD_REAP_UNCONFIRMED`, never a safely concluded analytical result.
* POSIX: `RLIMIT_AS` (max of 4× the ceiling or ceiling + 3 GiB, address-space based) + a new session for whole-group kill; Linux process-group accounting excludes non-running zombies.
* Timeout/cancellation request termination and allow at most five seconds of shared cleanup grace. Windows Job completion-port events confirm the tree is empty without polling. Results expose immediate-child reaping, tree confirmation and degraded containment; unknown/failed reaping returns `UNAVAILABLE / CHILD_REAP_UNCONFIRMED`. Parent success requires confirmed safe reaping. Cancellation records operational status before propagating the cancellation.

## 6. Reason vocabulary (disjoint)

| Class | Codes |
|---|---|
| Resource (never feedback evidence) | `FEEDBACK_RESOURCE_TIMEOUT`, `FEEDBACK_RESOURCE_MEMORY_LIMIT`, `FEEDBACK_RESOURCE_UNAVAILABLE`, `FEEDBACK_RESOURCE_DISK_UNAVAILABLE` |
| Operational containment | `CHILD_REAP_UNCONFIRMED`, `FEEDBACK_PARENT_CANCELLED` (never analytical evidence) |
| Defect / integrity | `FEEDBACK_COMPUTATION_ERROR`, `FEEDBACK_SOURCE_INTEGRITY_FAILED`, `FEEDBACK_SOURCE_CHANGED_DURING_RUN`, `FEEDBACK_IMMUTABLE_OUTPUT_CONFLICT` |
| Analytical (inside the artifact, unchanged) | `NOT_MATURE` / `PENDING`, `INSUFFICIENT_FUTURE_DEPTH`, `PRICE_SERIES_UNQUALIFIED`, `TEMPORAL_PROVENANCE_UNQUALIFIED`, `FIELD_NOT_RETAINED_AT_T0`, … |

A non-`COLLECTED` result is `UNAVAILABLE` with a resource/defect reason and `interpretation = RESOURCE_OR_DEFECT_STATUS_NOT_FEEDBACK_EVIDENCE`.
The handoff bundle, the AI-handoff attestation and the Owner Daily console state it truthfully (`reason_code` is added only when present, so
successful days are byte-identical to before). Missing feedback is never negative or neutral evidence.

## 7. Ordering and publication

Unchanged: Thesis T0 child → pre-handoff feedback child → handoff → observers → Thesis current child → post-handoff feedback child →
presentation → publication. Every heavy child is a blocking call that returns only after the process is reaped, so no two heavy children
overlap (rehearsal records `reaped` for every call). Feedback remains fail-soft: publication proceeds after a resource-unavailable feedback
result; the handoff and attestation carry the reason. Stages were not moved.

## 8. Disk effect

New artifacts are ≈ 27 % smaller (canonical compact layout); spools are removed on completion, failure, timeout (dead-writer temporaries are
swept at the next run) and never become authoritative; a retry/resume with identical inputs writes nothing. No historical artifact is touched.
Deeper reduction (a single rolling feedback artifact, pointer-based rows) is a product-contract change and is intentionally out of scope.

## 9. Known limits / reopen gates

* Memory is O(rows × ~3 kB) for reduced aggregation rows (≈ +5 MB per session today) and O(largest single record) otherwise.
* Cold cost is dominated by the one-time proof of ≈ 2.3 GB of T0 snapshots and ≈ 3–8 GB of hashing; later calls reuse receipts.
* The artifact is still a whole-corpus daily product (≈ 550 MB); its growth is linear in sessions.
* The 2026-10-02 Daily also spent ≈ 793 s in `Tactical reversal prospective shadow collection`; it is not part of this corrective.
* Reopen if a measured cold run exceeds half the deadline, child peak exceeds half the ceiling, or the corpus exceeds ≈ 150k rows.

## 10. Acceptance

`docs/internal/OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_ACCEPTANCE.json` (single acceptance artifact) and
`tools/run_owner_daily_feedback_rehearsal.py` (offline, read-only against retained evidence). The first-real-session harness reports
`feedback_pre_handoff`, `feedback_post_handoff`, `feedback_resource_admission`, `feedback_terminal_cache_reuse`,
`feedback_resource_reason` rows with `gates_capture = false`.

## Final release corrective (2026-10-04)

Claude Code implemented the streaming/resource corrective. Codex independently found and repaired the check-then-replace publication race, took over the same worktree as sole writer, and qualified real concurrent/crashing writers. `FEEDBACK_RESOURCE_CONTAINMENT_READY` is separate from `MONDAY_HOST_PREFLIGHT_PENDING`: the historical 9,853,145,088-byte (~9.18 GiB) enrichment/T0 peak remains untouched. Feedback admission floors are not a host launch gate. Live memory-headroom preflight is required before Monday launch; calendar registration remains unexecuted. Authority effect is `NONE / OWNER_DAILY_RESOURCE_CONTAINMENT_ONLY`.

The final retained rehearsal records fresh timing separately from the earlier calibration. Its required timing gate is completion within the configured 1,200-second total budget; the historical half-budget margin is reported as a comparison, not asserted afresh. The same source byte counts and row identity were reproduced. A slower fully measured cold run is a timing-headroom caveat and does not justify resetting the deadline or claiming whole-host Monday readiness.

Final isolated revalidation: cold 249.53 s; warm 112.16 s; serialized concurrent reuse 21.58/41.90 s; controlled 256-row timeout 120.02 s and exact retry 107.30 s. Maximum Job commit 560,644,096 bytes, parent growth 315,392 bytes; all 101 protected files (4,951,154,026 bytes) unchanged. The first timing-derived injection completed early and was replaced by a controlled mid-stream wait. Its cold build under concurrent hermetic validation was 793.88 s; the final isolated run reproduces the prior half-deadline margin. No deadline reset or threshold increase was made. Final real-process concurrency/reap qualification: 26 pass; hermetic CI-selected regression: 2,603 pass/16 platform skip/37 subtests. The existing acceptance artifact retains its original 15 gates and seals the supplemental final release validation.

## Windows reason correction (2026-10-10)

A denied large allocation can leave peak commit well below the ceiling, while an ordinary
exception can occur after successful high-peak allocation. Peak proximity is not causal proof.
The [bounded corrective](feedback_windows_memory_reason_corrective_v1_contract.md) retains
queued kernel memory-limit notifications before Job/port close, including already-empty trees.
Unknown nonzero failure classification uses positive kernel notification or the existing NT
memory statuses; explicit sidecar/exit reasons and timeout precedence remain. Missing event
is inconclusive, so an otherwise unknown failure keeps the generic defect fallback. Tree
accounting and the existing shared cleanup deadline still govern safe reaping. No schema,
reason vocabulary, resource threshold, analytical evidence or production-stage change.
