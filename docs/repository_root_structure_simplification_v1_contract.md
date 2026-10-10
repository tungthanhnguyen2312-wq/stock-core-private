# Repository root structure simplification V1

Milestone: `REPOSITORY_ROOT_STRUCTURE_SIMPLIFICATION_V1`.
Starting release: semantic corrective PR105, merge `40c88c2a73bcf9cb0a92c3127ca2cf4c34243386`.
Authority effect: `NONE / SOURCE_LAYOUT_ONLY`.

## Released checkpoint

COMPLETE: owner-approved PR106 HEAD `306da44f92b4e974addddbaaef98114095d9509b`
merged at `04dca9b360e064b0538a797c780895e6a4c43fc7` on 2026-10-10.
All four PR CI jobs succeeded (run `38022405076`). Root files 613 → 592,
root Python 595 → 574; 22 implementations moved, one required CLI launcher retained.
No production activation or analytical successor. Exact validation and residual
boundaries: [acceptance](internal/REPOSITORY_ROOT_STRUCTURE_SIMPLIFICATION_ACCEPTANCE_20261010.md).

## Owner admission and boundaries

The owner's explicit `STOCK_LOOKUP_CONTINUATION_AND_REPOSITORY_STRUCTURE_SIMPLIFICATION`
directive admits sequential, independently tested source-family relocations after the
semantic corrective's release gate. The native roadmap admission records that exact
scope override; broad lead delegation alone does not admit a successor.
One repository writer, one dedicated worktree. Source edits, offline tests, local
commits and public-safe feature PRs are authorized. Structure PR merge remains a
separate owner decision. No production Daily, runtime writes, deployment, authority
promotion, evidence deletion, repository visibility changes or unrelated features.

## Package boundaries

Use ordinary source-checkout packages under `stocklookup_core/`, alongside the
existing `stocklookup.py` CLI. No installer, path-hook framework, `src/` conversion
or new service architecture. Package initializers must not activate runtime work.

1. `acquisition/`: the seven acquisition landing contract/identity/atomic I/O,
   isolation, quarantine, retention and checkpoint modules.
2. `evidence/`: official document acquisition/discovery/store, qualification,
   canonical activation, OCR handoff, retrieval and downstream shadow, plus the
   existing temporal receipt contract.
3. `research/`: the six independent thesis adapter/contract/matrix/production,
   runtime and catalyst/downside modules, only after evidence acceptance.

`config/repository_layout.json` maps every original source filename to its sole
implementation path and records grandfathered root modules. Historical prose and
artifact identities retain their original names. Source-family membership is based
on imports, call shapes and responsibility, never filename age or presumed obsolescence.

## Compatibility

Preserve `stocklookup.ps1 daily`, `stocklookup.py`, all `tools/` launch paths and
governed publishing interfaces. Preserve the existing filename CLI
`official_document_acquisition.py` with one explicit launcher forwarding `main`.
All repository library consumers use the new package paths; root library aliases
are not invented for hypothetical external clients. Consumer/Dashboard source has
no imports of the moved modules. Schemas, deterministic identity strings, numerical
values, immutable retained paths and admission policy remain unchanged.
Thesis resolves its source root and child tool from the repository ancestor, not
the deeper package directory. Its caller-supplied runtime/output roots stay explicit.

## Acceptance

Run affected synthetic unit/integration tests in pinned core Python with retired
providers blocked; run optional PDF retrieval tests separately on the existing
PDF-capable interpreter. Record absent retained evidence explicitly using the
existing test-tier contract; never manufacture or copy historical evidence.
Require unchanged non-import AST for evidence modules, exact schema/identity tests,
offline production call-shape smoke, real fixture-only Thesis child execution,
CLI help/dispatch, package resolution, no stale imports, root counts and clean Git
checkpoints. No production Daily is an acceptance command.

New implementation modules belong in the appropriate package; reusable tools in
`tools/`; temporary helpers outside source Git or `.stocklookup/scratch/`.
The structural guard rejects new root Python names and stale relocated imports.
An exception requires an explicit compatibility reason, manifest update and review.

This slice does not close all flat-layout debt or start an analytical successor.
Fiscal-calendar/publication mapping remains unresolved from the semantic corrective.
