# Current Research future freshness — resume checkpoint 2026-10-01

Repository: stock-core-private, canonical checkout. Branch:
`feature/current-research-future-freshness-20261001`, based on
`59580f6cda300dce8013af284d2ce11e026e3029` (origin/main at start).
This milestone is independent of the Windows RSS repair at `4116e0f` / PR #28.
The owner explicitly authorized autonomous independent work with an empty next queue.

`CURRENT_RESEARCH_FUTURE_DATED_FRESHNESS_GUARD_V1 = COMPLETE`.
Demonstrated defect: a macro observation dated 2026-10-02 evaluated at
2026-10-01T07:00:00+07:00 returned current/actionable. Corrected result is
unknown/non-actionable with `source_date_after_reference_anchor`. Shared calendar
cadences and completed-market-session anchors remain unchanged; source values/dates
are retained. Future inputs cannot become fresh merely because age is negative.

Regression coverage: every existing freshness domain, pre-close market observations,
and mixed valid/future macro input. Valid sibling macro series remains current while
the future series becomes unknown; aggregate context becomes PARTIAL.
77 focused/adjacent tests plus 16 domain subtests passed (freshness, macro presentation,
AI source matrix, Daily contract and Dashboard domains). File metadata adjacency
also passed (37 tests including overlapping freshness/macro suites, 16 subtests).
py_compile and git diff --check passed. Roadmap check is required at checkpoint.

Retained replay uses only the existing runtime macro snapshot at its own generation
timestamp, 2026-09-30T17:12:45+07:00. All 17 series and the complete context equal
base `59580f6` exactly: 12 current, 5 stale/expiring, 0 unknown/missing.
Identity: `macro_presentation_context:d0045da8120a7799efe12856c0ae341e4146c1ab547de1e08679c95aab1d5c11`.
Source SHA-256 is unchanged:
`f5110e7039c037dcb47a81f6f23b12736a28ccb2956c401f427a3f00892aeb2d`.
The external sibling run-logs directory `telemetry-replay-20260930-postmerge` retains
`freshness_acceptance.py` and `freshness-acceptance.json`; no runtime output is rewritten.
No new acquisition, Daily invocation, publication, DB write, private-data read or
authority promotion occurred. Owner untracked `data/` is preserved and must never be staged.

Resume: inspect this branch's PR/checks and exact Git state, then choose independent
Current Research work from current evidence under the existing owner autonomy override.
Do not merge either PR or repeat already-passed replay/bootstrap. 2026-10-01 live
telemetry acceptance remains a future completed-session gate, never synthesized or polled.
