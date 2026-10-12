# OWNER_DAILY_AI_HANDOFF_IMPORT_RECOVERY_20261012

Owner-directed P0 corrective on main `4755d94a977f468a4122e40fba77850281582f42`.
Authority effect: `NONE`.

## Incident

The 2026-10-12 Owner Daily completed phases 1–5 (Canonical Daily 13/13, retained
completion, Producer state, Dashboard) and failed at phase 6 with
`ModuleNotFoundError: No module named 'daily_integrated_decision_brief'`.

## Root cause

The owner process imported `tools/run_owner_daily.py` at `95216b77`, the checkout's last
pull, made on 2026-10-10. Its own phase-1 `preflight_repository` then ran
`git pull --ff-only` across 102 commits (PRs 101 and 105–131) to the V3 merge `d11b1016`,
and the process kept executing its pre-pull bytecode. At `95216b77`,
`resolve_m1_handoff_authority` contained the function-local
`import daily_integrated_decision_brief`. PR 110 (decision research package V1, `cdd8a766`,
merged `8142f4f8`) had relocated that module into `stocklookup_core.decision` and retargeted
this import. That was before the bulk V1–V3 consolidation, which did not touch it.
In phase 6 the stale statement resolved against the new tree and failed. The traceback shows
the new file's text at the old line number (587). Daily subprocesses had already run the
new code, so the parent ran mixed old and new code from phase 2 onward.

The relocation was the trigger. The defect is that the workflow updates its own
checkout and keeps running pre-update code. Hosted CI checks one tree at a time, so it
could not observe a process that spans two trees.

## Corrective

- After a Producer `FAST_FORWARDED` result, phase 1 raises `ProducerCodeAdvanced` before
  the Consumer/Dashboard preflights and any analytical, publication or Action Center step.
  It writes no journal failure.
- `main` relaunches the same entrypoint (`tools/run_owner_daily.py`) once, with the same
  arguments and the same telemetry run, under `STOCK_LOOKUP_OWNER_DAILY_CODE_HEAD`. The
  relaunched process owns the result file and does not present the owner view a second time.
- A relaunched process that sees a second fast-forward fails closed
  (`PRODUCER_CODE_ADVANCED_AFTER_RELAUNCH`). If the relaunch cannot start, the result is
  `PRODUCER_CODE_RELAUNCH_FAILED`. In both cases nothing analytical has run.
- Unchanged: Daily calculations, sealed artifacts, AI handoff content, evidence
  verification, publication idempotency, Action Center and Dashboard semantics, and the
  V1/V2 code digests.

## Governance

`tools/run_owner_daily.py` is re-pinned exactly in `tests/fixtures/e2e3_frozen_sources.json`
and in `config/daily_path_launchers.json` (caller AST, plus the declared self-relaunch). The
CI workflow digest is updated for the one added focused test. The E5/E6 historical-base
byte comparison for this one file is replaced by an owner-approved exact re-anchoring in
`tests/fixtures/frozen_source_reviewed_amendments.json`. The amendment verifies that the
base hashes to the old pin and the file hashes to the new pin.

## Acceptance

`tests/test_owner_daily_code_advance_relaunch.py` (hosted focused selection):

- a fast-forward stops before any later phase (pre-fix: the Consumer preflight ran on
  pre-pull code), shown with stubs and with real Git;
- exactly one relaunch, with the same argv and run, and the result left to the child;
- fail-closed second advance, and the relaunch-failure result;
- the relaunch does not present the owner view twice;
- a cold, fresh-interpreter execution of every function-local entry import from the
  script context, with providers and network blocked;
- a 2026-10-12-shaped resume after the Dashboard step: no Canonical Daily rerun, the
  verified Dashboard reused, and the AI handoff published exactly once across two replays.

No Owner Daily, production replay, AI handoff or Dashboard publication, provider call or merge
belongs to this milestone. The completed-session replay is a separate Owner-approved step.
