# Windows feedback memory resource/defect acceptance — 2026-10-10

## Released baseline and scope

Owner approved PR113 at exact HEAD c2ddc709f5c113193b5fae8c704ceeda7fc5e9f6. It is merged
at verified live main 701d432cd6736dc93f005ab56321189ba031c137; four PR CI jobs 38049457444
and four post-merge jobs 38050775088 SUCCESS. One native ACTIVE scope is
FEEDBACK_WINDOWS_MEMORY_REASON_CORRECTIVE_V1, predecessor case lifecycle COMPLETE,
empty queue, explicit standing program delegation, no production activation.
[Contract](../feedback_windows_memory_reason_corrective_v1_contract.md).
Branch: fix/feedback-windows-memory-reason-v1-20261010, sole writer dedicated checkout.

This is a direct correctness follow-up to the reproduced PR113 Windows baseline defect.
The already-associated completion port contains PROCESS_MEMORY_LIMIT, but wait_empty
returns immediately when accounting is zero and discards the notification on port close.
Peak proximity then misclassifies both actual allocation failure and ordinary high-peak error.
No evidence-blocked fiscal/historical retry or automatic root-cleanup slice was selected.

## Before/after evidence and implementation

Read-only temporary diagnostics on released source, 512 MiB per-process ceiling:

| Fixture child | Kernel observation / peak | Before reason | Corrected reason |
|---|---|---|---|
| Repeated 64 MiB allocations | PROCESS_MEMORY_LIMIT; 479,313,920 bytes | COMPUTATION_ERROR | MEMORY_LIMIT |
| Repeated 256 MiB allocations | PROCESS_MEMORY_LIMIT; 277,585,920 bytes | COMPUTATION_ERROR | MEMORY_LIMIT |
| Successful 480 MiB allocation, then ValueError | 512,888,832 bytes; ordinary defect | MEMORY_LIMIT | COMPUTATION_ERROR |

Four new real Windows regressions (128/256/512 MiB denied allocations and high-peak ordinary
exception) fail on released code: 4 failed in 24.43s. The existing baseline kernel test also
failed during PR113's regression. The fixed guard suite initially passed 20 cases in 15.98s.
Seven platform-neutral event-accounting cases and two real parent integration cases extend
coverage. The two parent cases pass after checking interpretation at its actual status-file
boundary, preserving the existing parent response schema.

Only feedback_resource_guard.py changes in production source. Capture memory-limit events
from the associated completion key while waiting for tree-zero; drain queued messages without
waiting even if already empty, within the existing shared cleanup deadline. Unknown nonzero
failure uses positive memory event or existing NT memory statuses, not peak or stderr guesses.
Explicit sidecar/exit reason, caught failure then success, and timeout precedence stay fixed.
Memory-event receipt never proves tree death; unknown accounting remains unsafe/unavailable.

The kernel enforcement test retains its original near-ceiling lower/upper assertions. Change
its allocation chunk from 64 to 8 MiB so it actually reaches that near-ceiling range; separately
assert low-peak large denied allocations. No weakened assertion or evidence skip is added.
New Windows-only tests declare their OS requirement; platform-neutral event cases run in Linux
CI. Microsoft does not guarantee these notification deliveries, so missing event is inconclusive.
See the controlling scope's official API reference. No universal memory-attribution claim.

Default policy/ceilings/floors, five-second cleanup grace, suspend/assign/resume, degraded mode,
result schema/reason vocabulary, fail-soft ordering, numerical/learning outcomes and immutable
publication contracts are unchanged. Parent failure tests fingerprint every fixture evidence
file and confirm no feedback artifact is published; resource/defect statuses stay non-evidence.

## Final validation

Final complete CI selection plus native/layout/active/call-shape controls on Windows:
4,936 PASS, 74 existing/platform skips, 49 deselected, 103 subtests PASS; two unrelated
provider Windows fixture failures (888.33s). All memory guard/event/parent cases pass.
The exact two failed nodes reproduce in the unchanged prior checkout (2 failed in 0.88s):
- test_provider_windows_os_containment::test_suspended_spawn_assign_verify_resume_and_kill_the_whole_job
- test_provider_windows_os_containment::test_named_pipe_gateway_serves_a_job_member_and_refuses_everyone_else
The first observes the child interpreter PID rather than the venv launcher PID; the second
receives empty worker output under its active-process cap. Provider backend/gateway/worker
containment and test source match released text. No new skip or assertion hides either.
Reopen through a separately bounded Windows SameIdentitySpawner/venv redirector process-chain
qualification preserving process caps and named-pipe membership checks. Retired provider
runtime is not reopened or authorized by this corrective.

Installed core dependency tiers PASS (zero violations); policy/reason constants, unaffected
functions and result-schema keys match released source. Native clean checkpoint is verified
before push. Active set 102,243 bytes (100 KiB budget).
The retained/full production corpus is not replayed, and no production Daily/store/runtime,
market/model/provider call or source-authority promotion is performed. Root layout stays
519 files / 501 Python / 9 directories. No existing entrypoint/fitness/session registry or
protected producer is modified. Fiscal and exact historical research replay gates remain.

## Durable next action and owner gate

Resolve PR by exact branch, check final HEAD and all four hosted jobs, then obtain separate
owner approval for merge at that HEAD. Use --match-head-commit and verify four post-merge jobs
and live main before native COMPLETE. Linux CI cannot itself qualify the Windows kernel;
real owner-host fixture results supply that qualification. Missing-notification attribution
remains limited by the OS contract; changes to thresholds or analytical policy need separate
scope. Production Daily/deploy/runtime writes and trust promotion remain owner-only.
Standing program continuation requires explicit native admission selected by demonstrated
product value. No watcher, child workload or autonomous loop survives the agent session.

## Optional independent review prompt

Review PUBLIC repository tungthanhnguyen2312-wq/stock-core-private read-only. Compare
fix/feedback-windows-memory-reason-v1-20261010 against main
701d432cd6736dc93f005ab56321189ba031c137. Read the controlling scope, guard and two changed
test suites. Challenge both resource/defect directions, completion key/event ordering,
already-empty tree handling, bounded nonblocking dequeue, unknown tree override and explicit
reason/timeout precedence. Verify policy/schema/analytical output preservation and absence
of production writes or hidden evidence substitution. Account separately for Windows real
kernel tests and Linux event-seam tests, including nondelivery limitations. Return concise
English blockers with reproducible file/line evidence. No writes, runtime launch, merge,
deploy, threshold changes or authority promotion.

## Verified release

Owner approved exact HEAD 5a7c22b13a6c46972eceec02ff1633e3456bf75d when four PR CI jobs succeeded. PR114 merged at 04211888251473f7872af88e959cf49ca9089dd5; all four PR jobs (38052737565) and all four post-merge jobs (38053161990) SUCCESS, independently verified. No Daily/deploy/runtime or authority activation. Next standing-authorized native admission: PORTFOLIO_RESEARCH_PACKAGE_V1.
