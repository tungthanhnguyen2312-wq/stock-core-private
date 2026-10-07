# Owner Daily telemetry post-merge acceptance — 2026-10-01

Repository: stock-core-private; base main / origin/main
`59580f6cda300dce8013af284d2ce11e026e3029` (merged PR #27).
Required telemetry head `3d272a0a3c2c379bd38904c1691d44dd622c2a62` is an ancestor.
Checkpoint branch: `fix/owner-daily-telemetry-windows-rss-20261001`.

One actual Owner replay of governed completed session 2026-09-30 returned PASS,
`ALREADY_COMPLETED / REUSED`, Producer state `NO_CHANGE`, Dashboard
`REUSED_EXISTING_PUBLICATION`, and AI handoff `ALREADY_PUBLISHED_VERIFIED`.
No provider acquisition, duplicate publication, commit/push from the replay, or deployment.
The ordinary Owner journal advanced and the existing local owner view opened as designed.

Command (external logs beneath the workspace sibling run-logs directory):

```powershell
python tools/run_owner_daily.py --replay-completed-session 2026-09-30 --result-path ../run-logs/telemetry-replay-20260930-postmerge/replay.result.json --progress-path ../run-logs/telemetry-replay-20260930-postmerge/replay.progress.jsonl
```

External evidence in that directory: `before.json`, `preservation.json`,
`replay.result.json`, `replay.progress.jsonl`, `rss-repair.result.json`,
`rss-repair.progress.jsonl`, and the bounded `preservation.py` helper.
The original replay evidence is preserved, including its null RSS observations.

18 events: BEGIN/END for each phase 1 through 9, ordered, one run identity,
monotonic elapsed; total elapsed 8.006 seconds. Acquisition was skipped, so
request/coverage denominators, rate and ETA are unknown rather than fabricated.
The retained acquisition separately reports 853/1,683 exact-session observations.
Output observation: 26,876 bytes in the registered canonical operation directory;
final free disk: 70,665,957,376 bytes. Process-tree RSS and payload bytes stay unknown.

Real defect: untyped ctypes Windows HANDLE arguments/results silently yielded unknown
RSS on this 64-bit host. Explicit pointer-sized signatures for GetCurrentProcess,
OpenProcess, CloseHandle and GetProcessMemoryInfo repair the sampler. An independent
native telemetry-boundary check after repair reports READY, no warnings, positive RSS,
peak 50,466,816 bytes, and the same 26,876-byte output. This check is not another Owner
replay or a live-session acceptance. The new regression calls both native handle paths.

605 before/after SHA-256 checks matched with zero additions in the explicitly checked
session operation/source and owner data roots. Scope also includes the tracked Daily
registry, selected session inputs, top-level runtime JSON/CSV and existing private
Action Center artifacts. No recursive global operations-review audit was performed.
Canonical operation, Daily run/operation, decision packet, acquisition, prospective
cohort and T0 identities remain unchanged. Integrated Decision identity remains
`integrated_investment_decision_product/v1:cd0c92321fbef001be15477b876f46f3f1ab82961ce28b091daeb43a168d620f`.
The historical handoff still declares official liquidity `UNAVAILABLE_SOURCE`, with
no same-session official artifact. Corrected future planning remains separately tested:
403 HOSE requests, cap 400, retry 40, HNX/UPCoM 0, HTTP 0, preserved budget status.
Authority changes: NONE.

Validation: 23 telemetry/launcher tests and 29 official-liquidity tests passed;
py_compile and git diff --check passed. Roadmap drift check PASS with existing stale
HEAD-sentinel warnings and expected dirty-worktree warnings before checkpointing.
Existing telemetry tests verify write/resource failures, malformed sidecars, unsafe
paths, request versus coverage denominators, ETA semantics and callback identity equality.

Disposition: `REPLAY_ACCEPTANCE_PASS / NEW_SESSION_LIVE_ACCEPTANCE_PENDING`, with
the RSS defect corrected and validated locally. No successor started in this atomic step.
The 2026-10-01 live acceptance remains an external completed-session gate.

Next: review this local checkpoint; integrate through the normal protected-main workflow.
After integration, use the same replay command with fresh external result/sidecar paths
to retain an Owner-route RSS observation. Before selecting independent roadmap work,
finish the owner-requested full bootstrap and deliberate roadmap re-evaluation; this
acceptance step did not complete that expanded bootstrap or select a successor.
Owner untracked data must remain preserved; stage only named source/test/handoff files.


## Phase 2 V2 corrective — 2026-10-07

Owner explicitly authorized `OWNER_DAILY_PHASE2_TRUTHFUL_PROGRESS_AND_TERMINAL_CLEANUP_V2`
from main `4e580f34a14e1d69d2a39c1be766c31c92f1260c`, including checkpoint, push, PR, CI,
merge and canonical fast-forward. `--can-start` reports UNKNOWN_MILESTONE, including with
`--owner-override`; this records the owner's explicit bounded override under AI_RULES rule 11.
The analytical roadmap and its empty successor queue are unchanged. Authority effect
`NONE / OWNER_DAILY_OPERATIONAL_OBSERVABILITY_ONLY`. No production Daily or new T0 is authorized
or run for this corrective. No retained October 5/6/7 evidence is modified.

### Real October 7 forensic (read-only)

Only the latest bounded `stock_lookup_daily_20261007_163237` log/result/progress triplet was
selected. Phase 2 started 16:32:46.604646 and ended 17:23:52.987696 Asia/Ho_Chi_Minh:
3,066.382 seconds (51:06). Whole Owner run: 3,407.352 seconds (56:47). Phase 2 has 1,785 events:
1,685 REQUESTS events, 74 subprocess events, and coarse acquisition/parent boundaries.
The original progress SHA-256 is
`0936812c4a5fd9e83574fecfea62cc2da12699940baa43e269adc409de549aa7`.

| Largest event gaps | Seconds | Source execution between observed endpoints |
|---|---:|---|
| Acquisition END → prospective collection BEGIN | 952.010 | Phase B, registration/freeze, enrichment/IID, macro, Producer, runtime/trusted, T0/seal/capture, Thesis T0, decision packet |
| Tactical collector END → post-handoff feedback BEGIN | 528.141 | Tier/handoff build; signal velocity T0 verification, foreign flow, divergence, volume/flow, Thesis current |
| Initial feedback BEGIN → END | 269.475 | Existing contained feedback child |
| Post-handoff feedback BEGIN → END | 146.944 | Existing contained incremental feedback child |
| DNSE futures COMPLETED → retained snapshot REUSED | 81.400 | Existing exact-session materialization/reuse path |

Top five safely bracketed elapsed internal spans are the 952.010-second heavy aggregate,
826.746-second market-acquisition aggregate, 528.141-second handoff/observer aggregate,
269.475-second initial feedback, and 266.694-second tactical collector. These are **observed
spans**, not isolated timings for individual IID, Producer or T0 functions. Nested spans must
not be added together. New callbacks split those aggregates at their real execution boundaries;
there is no CPU-based inference or invented attribution of old elapsed time.

Eight existing 30-second RUNNING observations during the tactical collector provided useful
liveness evidence (30.003–30.026-second gaps), but `_should_write_human` suppressed their owner
presentation. Most acquisition helpers were shorter than 30 seconds. Contained feedback
provided BEGIN/END only. Request futures ran 0→1,683 before the reused event at run elapsed
291.515; the run did contain request-shaped work before reuse, so reuse must not be interpreted
as proof of zero requests for the whole run. Pipeline work continued for most of Phase 2.
Electron noise reported by the owner was outside the captured log triplet; source showed
`os.startfile` invoked directly from the console-owning parent. The corrective removes that
inheritance route rather than reclassifying noise as a Daily failure.

### Stable progress contract

`PIPELINE_CHECKPOINT_PROGRESS` is additive operational metadata on the existing v1 event
surface. Denominator **13**, fixed before the first checkpoint is published:

| Index | Stable ID | Completion boundary |
|---:|---|---|
| 1 | SESSION_RESOLVED | Phase A eligible, exact intended session resolved |
| 2 | MARKET_EVIDENCE_READY | Acquisition/reuse returned; exact-session assertions and Phase B READY |
| 3 | INPUTS_FROZEN | Input registration and freeze returned |
| 4 | DECISION_SURFACE_READY | Enrichment returned; required integrated delivery verified |
| 5 | PRODUCER_SEALED | Producer returned; session and shadow lineage verified |
| 6 | RUNTIME_TRUSTED_READY | Runtime and trusted materialization/session/readiness checks passed |
| 7 | T0_CAPTURE_HANDLED | T0/seal and capture boundary attempted; their soft outcomes retained |
| 8 | DECISION_PACKET_READY | Thesis T0 handled and decision packet built |
| 9 | PROSPECTIVE_COLLECTION_HANDLED | Initial collection/feedback and tactical collector handled |
| 10 | HANDOFF_READY | Tier/handoff bundle built |
| 11 | OBSERVERS_HANDLED | Approved post-handoff observers handled |
| 12 | FEEDBACK_HANDLED | Post-handoff feedback handled |
| 13 | CANONICAL_RECORD_VERIFIED | Presentation/restage, optional publication and immutable record write or replay comparison completed |

`checkpoint_completed / checkpoint_total * 100` is monotonically non-decreasing. BEGIN
identifies the current checkpoint; END identifies the checkpoint just finished. Fields include
stable ID, index, completed count, total, percent, current checkpoint, Vietnamese label, status
and observed phase elapsed. No checkpoint metadata enters returned/persisted analytical data.
100% is emitted only after successful final persistence or verified immutable replay, before
Owner phase 3 performs its separate completion verification. A raised boundary emits FAILED at
the last completed count, preserving the original exception. No checkpoint-derived rate/ETA.

Optional/not-applicable/fail-soft components are **handled within fixed checkpoints**, never
removed midway and never promoted to analytically available by counting finished work. Their
existing UNAVAILABLE/NOT_APPLICABLE results remain unchanged. Reuse completes a transition after
its ordinary checks; it does not fabricate fresh request progression. Four natural enrichment
boundaries and five observer task labels expose internal work without displaying function names.
T0 construction emits at 64-record intervals using existing mapping lengths. Signal velocity
reports verified/handled retained sessions using its existing sorted registry session list,
including excluded sessions; no extra T0 read, list materialization, hash pass or provider call.

### Acceptance, performance and remaining visibility limits

`tools/validate_owner_daily_progress_telemetry.py --phase2 --sidecar <exact original JSONL>
--output <external diagnostic JSON>` writes a complete per-event timeline (component, subtask,
kind, counts, status, elapsed and gaps), observed spans, and a deterministic **synthetic**
51:06 presentation. The synthetic allocation inside old silent aggregates is explicitly not
historical reconstruction. External evidence: run-logs subdirectory
`owner-daily-phase2-progress-v2-acceptance`, `acceptance.json`. It does not execute any Daily,
provider request, output builder or retention writer. In-memory 26-checkpoint-event + reused-detail
simulation took 0.001152 seconds on this host; this is fixture overhead, not a production benchmark.

Representative display (synthetic):

```text
[2/9] Chạy Daily chuẩn | ĐANG CHẠY | Tiến độ 6/13 (46%) | Đang làm: Lưu T0 & ghi nhận bằng chứng phiên
      Đã chạy: 00:22:55
      ETA: chưa đủ dữ liệu
      DNSE: dùng lại dữ liệu phiên đã hoàn tất
```

Work reaches 0→acquisition→enrichment/decision→retention→observers→100. Runtime/trusted
materialization occurs **before T0** in the actual code, and the display preserves that order.
Narrow consoles preserve the measured count before truncating labels. The same pure structured
PowerShell render plan serves interactive cursor updates and noninteractive output. Malformed
wire events are ignored while their original text stays in the log.

No new polling/background process, thread, sleep, scan, network request or full hashing pass is
introduced for telemetry. Existing foreground subprocess waits still emit real RUNNING observations.
IID build/write/copy, Producer construction and T0 bulk hash/write/seal remain indivisible between
natural boundaries. If one of these takes 15+ minutes in a future run, the task and last observed
elapsed stay visible, but there is no continuous liveness guarantee. The October 7 sidecar cannot
prove which individual call exceeded 15 minutes; only the 15:52 aggregate is known. Record counters
cover T0 construction, not its later full-file emission/hash. This limitation is deliberate.

The GUI helper is `sys.executable -c "import os,sys; os.startfile(sys.argv[1])" <path>`, with
`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, `close_fds=True`, stdin/stdout/stderr DEVNULL,
check=True and a 15-second foreground helper deadline. ShellExecute keeps the current default
Markdown association; no VS Code path is embedded. Exception/timeout is READY_VIEW_OPEN_FAILED
and remains an Owner warning. Real Windows fixture tests launch the same detached path with
node-compile-cache/DEP0169/AgentHost-shaped noise from the helper and a nested process: none enters
the launcher stdout, stderr or log. No real GUI is opened by that fixture. Successful default-handler
forwarding is tested separately; a live owner GUI run awaits the next separately authorized Daily.

Fixture parity verifies exact canonical operation bytes/identity/call counts with callback on/off
and failing callbacks, ordinary/reused paths and soft unavailable/skipped branches. T0 and streamed
signal velocity callback on/off artifacts are identical; full-native-byte immutability tests remain.
No Daily analytical output, session resolution, provider behavior, request budget, threshold, source
or stage semantics changes. No T0/capture/operation/Producer/publication/handoff/Action Center identity
contains telemetry. Existing production files were never written by the acceptance.


Validation before release: 407 passed / 8 retained-evidence deselected across Owner workflow,
telemetry, launcher, canonical operation/post-close, T0, signal velocity, journal, delegation
and active control-plane tests. Final telemetry/real-enrichment check: 42 passed; final Windows
PowerShell launcher check: 19 passed. The latter includes four narrow/wide interactive render
plans, redirected real events, malformed wire data, real detached nested-process noise isolation,
default-association forwarding and fail-soft launch errors. Python compilation and `git diff
--check` passed. Roadmap `--check`: ON_TRACK / DRIFT PASS, unchanged completed analytical
milestone and no successor; candidate tracked edits produced expected pre-checkpoint warnings.
CI additionally includes the signal-velocity tests so the new natural counter's parity is checked.
