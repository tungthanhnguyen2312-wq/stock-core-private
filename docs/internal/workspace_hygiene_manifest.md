# Workspace hygiene manifest — 2026-08-11

Safe inventory only. No ambiguous artifact was deleted, moved, staged, or archived.

Repository: `stock-core-private`; HEAD `025313b50f9df4eac5649f71c3fae197ebf939bd`; upstream `origin/main` (ahead 0, behind 0 at inspection). Before this milestone's files were added, `git status --porcelain` reported 113 untracked entries and no tracked modifications in the inspected checkout.

| Category | Observed category | Disposition |
|---|---|---|
| Governed evidence | 104 `operations-review/**` entries, including retained documents, manifests, closeouts and market pilots | Preserve; active operational evidence. Consolidate only under a separate archival authority. |
| Runtime/cache/temp | `tmp/`, `.pytest_cache` access-protected, generated JSON bundles | Preserve; do not infer deletion safety. Candidate for owner-approved retention policy. |
| Shadow experiments | `dev/`, `dnse_prospective_pit_shadow.py`, shadow JSON bundles | Preserve and classify in a later bounded review. |
| Active source candidates | `tests/`, `tools/` untracked paths | Preserve; inspect before any promotion. |
| Unknown/malformed paths | `StockLookupstock-core-private'`, `h = (Get-FileHash …)` | Preserve; exact origin and ownership are unknown. |

Known cleanup remaining: classify each `operations-review` subtree against the workspace archival policy; determine whether `tmp/` is an active runtime root; identify the two malformed filenames; then request exact move/delete authority if needed. `git clean`, reset, mass deletion, and blind cleanup are prohibited.
