# AGENT_BOOTSTRAP_FOOTGUN_REMOVAL_V1

Execution state is `docs/ROADMAP_STATE.json`, queried with `python tools/stocklookup_roadmap.py`.
This contract does not add a second roadmap, agent memory, or CI controller.

## Ordinary path

- `python tools/handoff.py` reports repo, branch, HEAD, tracked cleanliness, the native milestone, the next note, and local-fast tests.
- It does not open `docs/STATE.md`, `docs/DECISIONS.md`, or `docs/ROADMAP.md`.
- `python tools/handoff.py --historical` is the explicit request to read the preserved narrative files.
- `python tools/stocklookup_roadmap.py --check` exits 0 only when native state is `ON_TRACK` and `git_verification` is `VERIFIED`.
- A missing repository is `SKIPPED`. A directory that is not a Git repository is `UNAVAILABLE`. Either result is `GIT_NOT_CHECKED`, not `ON_TRACK`.
- A recorded checkpoint that does not match live Git is `MISMATCH`.
- `--worktrees` prints class, HEAD, branch, tracked-dirty count, and path. It deletes nothing.

## Unchecked facts

Hosted CI, consumer HEAD, dashboard HEAD, disk free space, and untracked files outside the bounded worktree probe stay `UNKNOWN` until a command checks them.

## Non-goals

No Daily change. No production write. No worktree deletion. No source, valuation, or evidence authority change. No Q3 activation. Historical files stay in place.
