# Repository root structure simplification acceptance — 2026-10-10

[Contract](../repository_root_structure_simplification_v1_contract.md).
Branch: `refactor/repository-root-simplification-v1-20261010`.
One writer, dedicated `repository-root-simplification-v1` worktree. Existing canonical
checkout and its untracked data remain untouched; semantic corrective checkpoint
`01b372ea9ad89383f2349d9aba4a6fe5a65aa331` is preserved.

## Corrective release closure

PR105 merged exact approved head `01b372e` at `40c88c2a73bcf9cb0a92c3127ca2cf4c34243386`
after all four PR CI jobs succeeded (38020691437). Owner specifically approved merge
conditional on that success. All four post-merge jobs succeeded (38021005739).
Original 403-pass acceptance is reused, not rerun. Native roadmap admission closes
that corrective and records the owner's exact bounded structure scope; queue empty.

## Dependency investigation

AST graph of 1,694 tracked Python files identified 595 root modules and 340
dynamic-import/subprocess call sites. Tracked-code search additionally checked
literal mock/reflection targets, file launchers, source-root expressions, scheduling
entrypoints and workflow references. No recursive retained-evidence search was used.
Consumer and Dashboard source have no imports of these relocated families; serialized
field/identity references remain intact. The graph is a local investigation artifact,
not a second runtime registry. `config/repository_layout.json` contains only source
placement and historical-name navigation.

## Slice 1 — acquisition and official document evidence

16 implementations move into ordinary `stocklookup_core/acquisition/` and `evidence/`
packages. 47 source/test/tool consumers receive bounded import or mock-target updates.
All 16 non-import ASTs equal the released baseline. No calculations, strings naming
artifact identities, schemas, admission policy, storage paths or receipt fields change.
Only the existing `official_document_acquisition.py` filename CLI remains as a
six-line compatibility launcher; no root library shim collection is introduced.

| Source root | Baseline | Slice 1 |
|---|---:|---:|
| Tracked root files | 613 | 598 |
| Root Python files | 595 | 580 |
| Tracked root directories | 8 | 9 |

Pinned core dependencies audited PASS (zero violations); retired providers blocked.
Evidence/acquisition plus offline production call-shape and placement tests:
**242 passed, 31 skipped, 6 deselected, 12 subtests passed**.
Optional PDF retrieval: **2 passed** on the existing PDF-capable interpreter.
The baseline collection revealed `pypdf` is outside pinned core requirements;
no dependency or packaging system was changed merely for this migration.

Before relocation the same core selection had 238 passed, 31 skipped and six
missing-retained-input failures. Two VNM provenance tests and four onboarding tests
now declare their existing retained inputs under the existing tier contract.
Their assertion bodies are unchanged; no evidence was copied or invented. Core
deselects these tests, while retained accounting must name their missing inputs.
Other 31 historical skips retain their existing reasons. These are not full retained
acceptance or production qualification.

## Remaining boundaries

Historical prose is preserved; original module names navigate through the relocation
map. Active navigation and the landing framework's physical-layout convention are
updated. New root Python names are rejected in CI; compatibility exceptions require
an explicit manifest reason. Package initializers do no runtime work.

Root debt remains substantial. Daily, publishing and high-fanout financial/provider
families remain in place for independently admitted/tested later slices. Library
clients outside the inspected repositories must adopt package import paths; no
unverified external alias guarantee is claimed. Fiscal-calendar/publication mapping
remains unresolved. No analytical successor is started by this maintenance work.

No production Daily, deployment, evidence deletion, database/runtime/portfolio write,
source authority promotion or immutable-session modification was performed.
