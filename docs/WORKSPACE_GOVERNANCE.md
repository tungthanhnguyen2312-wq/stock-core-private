# Workspace governance pointer

**This file is a pointer, not a mirror.** It does not duplicate any governance content — it
records where the real, canonical governance documents live and how to recover if this pointer
is all that survives. Update it only if the canonical location or file set changes; never copy
`PROJECT_STATE.md`'s actual content into this file.

## Scope

This applies only when `stock-core-private` is checked out as a sibling inside the full
StockLookup workspace (alongside `ai-core-private`, `dashboard-runtime`, `operations-review`,
`archive`) — the layout this repository is normally developed in. A standalone clone of just this
repository (e.g. in CI, or a fresh isolated checkout) will not have the paths below; that is
expected, not an error, and is exactly why this pointer's content lives here rather than being
assumed.

## Canonical governance location

```
<workspace root>/operations-review/
    AGENT_WORKING_CONTRACT.md   -- stable rules every coding agent must follow
    PROJECT_STATE.md             -- current verified state (mutable, rewritten each milestone)
    OPERATIONS_INDEX.md          -- navigation entry point for operations-review/
    MILESTONE_LEDGER.md          -- compact milestone history
<workspace root>/archive/operations-review/
    README.md                    -- archive policy + manifest of everything moved there
```

`<workspace root>` is `C:\Projects\StockLookup` on the machine this was authored on — do not
hard-code that path in code; it is recorded here only as an operator convenience.

## Why this isn't tracked directly

`operations-review/` and `archive/` are deliberately **not** Git repositories (confirmed
2026-08-08) and are **not** owned by any single component repo — they span Producer, Consumer,
and Dashboard concerns equally, so putting the canonical files inside any one of those three repos
would misrepresent their scope. This pointer file is the accepted, documented compromise: the
governance content stays outside Git (persistent on the workstation, not version-controlled), but
its *existence and required paths* are recoverable from a fresh clone of this repository.

This is a known, accepted limitation, not an oversight. Revisiting it (e.g. git-initializing
`operations-review/` itself) is an architectural decision for the project owner, not something to
change opportunistically from an unrelated task.

## Recovery procedure if `operations-review/` is lost

1. Check for a filesystem-level backup or sync (e.g. OneDrive) of `C:\Projects\StockLookup`
   before assuming the content is gone — these directories are not Git-backed, so a filesystem
   backup is the only backup they have.
2. If genuinely lost, `archive/operations-review/README.md`'s manifest plus this repository's own
   `docs/DECISIONS.md` / `docs/STATE.md` / `docs/ROADMAP.md` are the next-best reconstruction
   sources for project history, but they will **not** reproduce `PROJECT_STATE.md`'s exact
   verified-state snapshot — that must be re-derived from current Git/runtime state, per
   `AGENT_WORKING_CONTRACT.md`'s own authority precedence (current evidence outranks any
   historical document, including this one).
3. Do not recreate `PROJECT_STATE.md`/`AGENT_WORKING_CONTRACT.md` from memory or assumption —
   re-verify against current repository and runtime state the same way the governance baseline
   milestone did (see `operations-review/MILESTONE_LEDGER.md`'s 2026-08-08 entries for what that
   involved, once recovered, or `archive/operations-review/README.md` if the ledger itself needs
   reconstructing).

## Precedence if this pointer and the live files disagree

The live files under `operations-review/` always win — this pointer only records *where* they
are, never *what* they currently say. If this file's recorded path or file set is stale, trust
what actually exists on disk and update this file to match, not the other way around.
