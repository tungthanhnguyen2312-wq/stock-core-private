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
