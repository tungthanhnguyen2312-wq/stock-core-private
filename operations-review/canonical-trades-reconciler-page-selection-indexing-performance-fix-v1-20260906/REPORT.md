# Canonical Trades Reconciler Page-Selection Indexing Performance Fix V1

Status: `COMPLETE` (local-only; push = `NO`)

Implementation commit: `c4409e55b1560419956c8bf2cace369809da83a6`.

## Result

`_select_pages` no longer re-enumerates and parses a whole raw-run directory for
each non-empty logical unit. `_PageSelectionIndex` enumerates each resolved raw
directory once, groups its immutable raw-lake filenames by exact normalized
instrument, and provides a sorted candidate tuple to the existing selection
logic. Filename data is used only for candidate discovery. Every candidate is
still opened and verified against the existing instrument, session, provenance,
payload, page-identity, and record-accounting rules.

The retained full baseline completed normally: 66,400 logical units across 40
sessions, 37,828 non-empty successes, 28,545 confirmed-empty units, and 27
remaining failures. Its coverage (66,400 units) and ordered selected-page list
(209,193 pages) have zero semantic mismatches against the accepted Task160
corpus. The existing reconciliation output identity remains
`82a11515a8a5f075fe999ed8c7d3ce461415f7296f39c0d4e60e79a8fc798ed2`.

## Performance evidence

Anti-Gravity observed the old full run for 132 minutes with zero output before
cancellation. The defect was a per-nonempty-unit directory glob plus full
parquet loads: `37,828 × 1,660 = 62,794,480` unrelated examinations in the
reported baseline shape.

The one retained foreground post-fix baseline finalized artifacts in `56m24s`
and exited `0`. It recorded 57 directory enumerations, 37,828 exact candidate
lookups, and 209,193 candidate validations. The generated validation artifacts
total 921,998,136 bytes under `full-baseline-reconciliation/`; no accepted
Task160 artifact was overwritten.

## Compatibility and boundaries

A bounded materializer smoke selected one original and one repair page from the
optimized manifest. It produced 104 canonical rows with zero duplicates,
missing rows, or quarantine rows; the output has the current 16-column schema
and its repeat run was idempotent. All 27 remaining failures have zero selected
page references.

No real DNSE acquisition, provider call, secret access, production canonical
materialization, database/Dashboard write, policy change, authority promotion,
push, merge, rebase, or amend occurred. The protected
`config/daily_research_session_input_registry.json` diff was preserved.

The `2026-09-04` fixture proves the index has no dependency on the old
40-session range. Reconciler/materializer CLI root parameters were checked.
Phase A remains unexecuted and requires owner review before Anti-Gravity resumes
real acquisition.

## Evidence index

- `reconciliation_page_selection_root_cause.json`
- `page_discovery_contract.json`
- `index_design.json`
- `operation_count_validation.json`
- `real_sample_semantic_comparison.json`
- `full_baseline_reconciliation_validation.json`
- `materializer_compatibility_validation.json`
- `phase_a_readiness.json`
- `antigravity_resume_handoff.json`
