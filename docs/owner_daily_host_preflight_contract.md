# Owner Daily host preflight V1

`owner_daily_host_preflight/v1` is a read-only, point-in-time operator gate. Authority
effect is `NONE / OWNER_DAILY_HOST_PREFLIGHT_ONLY`. It does not acquire evidence,
contact providers, kill processes, clean disk, or write repository/runtime state.

Run `python -B tools/check_owner_daily_host_preflight.py` in the canonical main
checkout immediately before launch. Optional `--root` and `--retained-root` select
explicit observation roots; retained-root otherwise honors
`STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT`. Output is stdout JSON only. Exit codes are
0 READY, 2 AMBER (operator action required), and 3 BLOCKED. No diagnostic-file writer
is provided. Current machine readings are observations, not durable launch permits.

| Dimension | READY | AMBER | BLOCKED |
| --- | --- | --- | --- |
| Available system commit | >=12.0 GiB | 9.2–12.0 GiB | <9.2 GiB or unknown |
| Available physical | >=6 GiB | 2.5–6 GiB; recommended amber band starts at 3.5 GiB | <2.5 GiB or unknown |
| C: free | >=25 GiB | 17–25 GiB | <17 GiB or unknown |
| Writers | None observed | — | Runtime writer, Git index lock, or unobservable writer state |

These are evidence-backed Windows V1 operator bands, not universal requirements.
The unspecified 2.5–3.5 GiB physical band conservatively requires operator action.
Unknown pagefile state, missing IID model input, or unqualified current-main
provenance produces at least AMBER. Missing T0 is optional metadata and does not
affect host readiness or first capture-marker eligibility. No composite score exists.

Windows `GetPerformanceInfo` supplies physical RAM and system commit limit/current
commit/available commit. Local CIM supplies pagefile allocation/use and process
inventory. Only sanitized process names, PIDs, working-set sizes and writer roles
are emitted; command lines are private classification inputs. The invoking Owner
process and its launcher ancestors are excluded. Other relative Daily/Producer
entry commands and repository-bound runtime interpreters are possible writers.
Unknown runtime command lines fail closed. Git observations use local refs and
`--no-optional-locks`; no fetch, refresh write, or remote call occurs. Tracked dirty
worktrees are reported as observations, not falsely asserted to be running writers.
The existing repository cleanliness gate remains separate. This observation does
not reserve the host or eliminate the race with a writer starting afterward.

Only known IID and immutable T0 family paths are globbed at their defined depths.
Payloads are never loaded. The latest session/largest same-session IID file is used
conservatively. Its byte size is multiplied by **5.05**; `peak_basis` is
`MODELED_FROM_RETAINED_CURRENT_MAIN`. Provenance is the owner's 2026-10-04 forensic
directive on main `2c6c79224ae2a3a57b50dae7b96666bd2ec09715`. Baseline current-main
IID scaling estimate is not the Daily high end. The final real-scale retained
benchmark on main `bf881cd4cc9453d351389de87ed2312c4a9e0150`, supplied by the owner
on 2026-10-04, measured unchanged Producer `build_delivery` at approximately
**+2.88 GiB transient over ~1.98 GiB resident**; streaming T0 is no longer the peak.
It revises the Daily-child working band to **6.5–8.0 GiB**, with **8.0 GiB a floor
for the high end, not a hard ceiling**. This is retained-benchmark provenance,
not measured Monday telemetry. It tightens the baseline commit bands to 12.0/9.2 GiB.
The historical **9,853,145,088-byte** pre-streaming peak is **STALE** for this model,
retained as historical metadata, not deleted or relabeled in historical evidence.
The existing 7 GiB scaling reference is retained conservatively, not asserted as
an upper bound. Above an IID scaling estimate of 7 GiB, memory bands scale by
that estimate /7 GiB; smaller inputs
never lower the baseline bands. Disk bands stay fixed. Future code or input changes
may require renewed model qualification; the estimate is not a memory guarantee.

The normal Owner launcher rechecks immediately before spawning its canonical child.
BLOCKED refuses acquisition; AMBER refuses automatic launch and requires the
operator to close ordinary background browsers/IDEs/unrelated Python workloads,
rerun preflight and launch alone only when READY. There is no override flag. READY
continues through the existing Daily evidence/runtime gates; it does not bypass
them. Verified completed-session publication replay does not launch acquisition
and retains its existing gates. Launcher logging/journaling is separate from this
read-only tool.

Terminal implementation disposition: `OWNER_DAILY_HOST_PREFLIGHT_V1_COMPLETE`.
Monday launch requires a fresh READY result plus existing release/environment,
evidence, runtime, session/window and owner calendar gates. Calendar registration
and first-real capture acceptance remain pending. Capture marker semantics remain
`CAPTURE_COMPLETENESS_ONLY`; T0 availability is independently exposed by Monday
acceptance. No core memory refactor or analytical capability/authority change.
