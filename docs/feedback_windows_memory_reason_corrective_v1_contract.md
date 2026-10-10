# Windows feedback memory reason corrective V1

Scope FEEDBACK_WINDOWS_MEMORY_REASON_CORRECTIVE_V1; starting live main
`701d432cd6736dc93f005ab56321189ba031c137` (PR113). Owner approved exact PR113 HEAD
`c2ddc709f5c113193b5fae8c704ceeda7fc5e9f6`; four PR jobs 38049457444 and four post-merge
jobs 38050775088 SUCCESS. Standing PROGRAM_LEAD_CONTINUATION_AND_STANDING_DELEGATION
(2026-10-10) authorizes this bounded corrective, native admission, tests/commit/safe PR.
One writer, one ACTIVE scope, empty queue; separate exact-HEAD merge and production gates.

The PR113 affected-consumer regression exposed a real Windows guard failure. Isolated
64/256 MiB allocation chunks under a 512 MiB per-process Job ceiling fail with kernel
PROCESS_MEMORY_LIMIT messages, peaks 479,313,920 / 277,585,920 bytes, but are labeled
COMPUTATION_ERROR. An ordinary ValueError after successful 480 MiB allocation, peak
512,888,832 bytes, is wrongly labeled MEMORY_LIMIT. This same reason boundary is used
by both optional Daily feedback children. Correct both directions as one coherent scope;
no new analytical feature, root slice or speculative engine.

Preserve the completion-port memory notification while waiting for tree-zero, then dequeue
remaining messages nonblocking even when the job is already empty. Dequeue uses the
existing shared cleanup deadline, never a daemon, sampling loop or new grace budget.
Only the associated job completion key and PROCESS_MEMORY_LIMIT/JOB_MEMORY_LIMIT events
supply positive limit evidence. A notification can arrive after tree-zero; preserve it.
[Microsoft's Job completion-port contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_associate_completion_port)
warns that these notifications are not guaranteed. Missing notification is inconclusive.

Unknown nonzero failures use observed kernel events or existing known NT memory statuses,
not peak proximity or stderr text. Explicit sidecar/exit reasons keep precedence; caught
allocation failure followed by success remains success, and timeout still wins. Missing
positive limit evidence with no explicit reason retains the existing generic defect fallback;
do not claim every possible allocation failure can be conclusively attributed. Peak remains
reported as telemetry. Tree accounting remains mandatory and unknown reap status still
wins over any resource classification. Successful result schema/content is unchanged.

The existing 1,200 s / 2 GiB policy, admission floors, five-second shared cleanup, suspend/
assign/resume containment, degraded mode, POSIX behavior, reason vocabulary, stage order,
immutability/publication and all analytical/authority boundaries stay fixed. No production
Daily, runtime/store/database/retained artifact writes or host-threshold changes. Source
change is only the existing feedback_resource_guard.py; tests extend its existing suites.

Acceptance: reproduce both wrong classifications on released code; real Windows allocation
and high-peak exception tests; event delivery before/after tree-zero, wrong completion key,
missing notification, unknown tree and bounded drain; caught failure/success, explicit defect
and timeout precedence; parent UNAVAILABLE/non-evidence status with unchanged fixture bytes
and no feedback publication; related streaming/publication/call-shape and native controls;
installed core tiers and four hosted jobs. Preserve the original kernel near-ceiling lower/
upper assertions with smaller allocation chunks; add separate low-peak failures, no weakened
assertion or evidence skip. Hosted Linux exercises event-consumer seams but cannot qualify
Windows kernel enforcement; owner-host real Windows tests are separate evidence.

Root remains 519 files / 501 Python / 9 directories. Fiscal and exact historical research
replay reopening gates remain unchanged; no new evidence qualification or history rewrite.
[Acceptance and durable merge gate](internal/FEEDBACK_WINDOWS_MEMORY_REASON_ACCEPTANCE_20261010.md).
