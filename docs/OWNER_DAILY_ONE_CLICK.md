# Owner Daily One Click

## Daily use

At or after about 16:30 Asia/Ho_Chi_Minh, double-click `Stock Lookup Daily.cmd` on the Desktop.
It safely fast-forwards a clean Producer checkout, runs Canonical Daily, verifies retained
completion evidence, commits only the governed session registry when needed, and publishes the
compact private AI handoff.

## Green result

`FINAL STATUS: PASS` means the remote AI handoff is `READY_FOR_AI`.

## Red result

Send the displayed failure summary and log path to ChatGPT. Do not run two Daily writers at once,
and do not manually push generated files while the launcher is running.

## If the console was closed or the machine slept mid-run

A hard terminal close cannot run any cleanup code, so it can leave the run without a final
`result.json` -- `FINAL STATUS: INTERRUPTED` / `REASON: NO_RESULT_FILE_WRITTEN` on the next
launch (see the script's own handling of this above). Just double-click the launcher again.
Since `CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1` (2026-09-22), the
workflow keeps its own durable journal (`operations-review/owner-daily-journal-v1/journal.json`)
written at each stage as it happens; if Canonical Daily itself had already fully completed for
that session before the interruption, the next run resumes publication straight from there --
it does not reacquire market data or re-run Daily Producer. Nothing to do manually; this is
automatic and requires no flag.

## Keeping the Producer checkout Daily-ready

- Primary `main` should normally sit exactly at `origin/main`. Development happens in isolated
  worktrees (`worktrees/...`), never as loose commits on the primary checkout.
- Investigation or exploratory commits must not remain on primary `main` overnight. If Daily
  reports `UNSAFE_GIT_DIVERGENCE`, integrate or archive that work onto a branch and repoint `main`
  to `origin/main` before rerunning Daily -- never `git reset --hard` or `rebase` to force it.
- Retained runtime/evidence files that Daily itself generates (e.g. `data/dnse-foreign-flow/`,
  `data/market_raw_lake/`) are expected to sit untracked inside the checkout when no separate
  runtime root is configured. They do not make the checkout dirty and Daily will not block on them.
- Any *other* untracked file -- a stray script, a new module, a config override that hasn't been
  reviewed and committed -- still blocks Daily with `RELEASE_CHECKOUT_DIRTY` /
  `UNSAFE_UNTRACKED_CHECKOUT`. Commit it, remove it, or move it out of the checkout.
- A refusal now names exactly what is wrong: `TRACKED_DIRTY` (edited/staged tracked files),
  `UNSAFE_UNTRACKED` (unreviewed untracked files), or `APPROVED_RUNTIME_UNTRACKED` (informational --
  never the cause of a block). No log archaeology should be required to tell which one blocked.
- A provider/data blocker (e.g. a missing retained input or an exhausted rate budget) is reported
  separately from a checkout problem -- see the failure code's own prefix
  (`FAILED_PREFLIGHT_RETAINED_EVIDENCE`, `FAILED_PREFLIGHT_RUNTIME`, etc.) rather than
  `FAILED_PREFLIGHT_PRODUCER`.
