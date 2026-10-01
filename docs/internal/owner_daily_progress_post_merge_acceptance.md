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
