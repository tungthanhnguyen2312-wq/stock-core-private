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

## Slice 2 — independent thesis research

The evidence slice is checkpointed at `cc81a74`. Six thesis implementations move
to `stocklookup_core/research/`; 19 source/test/tool consumers use package imports.
No additional root wrapper is needed. All 22 moved modules have baseline-equal
non-import AST after normalizing only three reviewed path expressions: the
catalyst module's source root, the child tool path, and the child's working directory.
The repository ancestor replaces the old file parent; runtime/output roots are not
inferred or changed. The original Owner Python/PowerShell launchers are byte-identical.

| Source root | Baseline | Final candidate |
|---|---:|---:|
| Tracked root files | 613 | 592 |
| Root Python files | 595 | 574 |
| Tracked root directories | 8 | 9 |

The broader integration selection initially passed 372 cases with one deselected
and 13 setup errors from an old shadow-recommendation class whose August inputs
are absent in the clean worktree. Its exact eleven retained inputs are now declared
with the existing tier contract; assertion bodies and historical expectations remain
unchanged. The Monday source-inspection invariant now checks the final module name
inside package imports, preserving its ban on Stage-1 imports in the acceptance harness.

Final broader integration run: **372 passed, 14 deselected** in 131.85 seconds.
This includes actual fixture-only Thesis child execution, separate output roots,
source identity/seal contracts, offline Owner call shape and workflow regression.
The newly added legacy-runner source-root/explicit-output fixture test additionally
passed; package placement/resolution guards passed all four cases.
Shadow retained accounting: **13 skipped**, every exact missing input named.
The legacy catalyst runner has no argument parser: an attempted `--help` call
stopped at its absent event input, before any output directory or write. Its
fixture-only runner test now verifies source defaults and explicit temporary output.

Governance/active-document tests: **49 passed**; latest active-view budget/link check:
**12 passed**. Evidence-tier accounting for the six previously undeclared inputs:
**6 skipped, 31 deselected**, exact missing manifest/provenance paths reported.
CLI help resolves for the owner CLI, acquisition compatibility launcher, landing
operator and listing discovery tool. No acquisition or Daily command was executed.

## Remaining boundaries

PR106 CI run `38022003589` passed three jobs; the hermetic job recorded
3,754 passed, 132 skipped, 38 deselected and 49 subtests passed, with one failure:
the existing workflow tier contract requires four pytest commands, while the new
standalone layout guard added a fifth. The guard is now part of the existing
structural hermetic command, preserving all assertions and four-command tiering.
Focused dependency-tier and layout verification: **39 passed**. Replacement CI
must pass before release; the earlier exact-HEAD approval cannot authorize this
changed candidate.

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

## Next product priority, after source release

Semantic corrective PR105 is released; this layout candidate is pending review,
not deployed. Existing integrated product milestones remain complete. The known
fiscal-calendar/publication mapping gap is now explicit rather than disguised by
the lexical feature-label maximum. Recommend a separately bounded evidence gate
for issuer fiscal-calendar and publication metadata, using existing admitted source
routes and exact knowledge times. No dates, fiscal conversion, shares, normalized
earnings or valuation authority should be inferred to make that gate pass.
Broader root layout remains debt; high-fanout Daily/publishing/financial families
should move only after their own dependency closure and parity acceptance.
Neither recommendation starts a new analytical program or promotes authority.

## Optional independent Grok review prompt

You are an independent, read-only architecture reviewer for the PUBLIC GitHub
repository `tungthanhnguyen2312-wq/stock-core-private`. Review the branch
`refactor/repository-root-simplification-v1-20261010` against released main
`40c88c2a73bcf9cb0a92c3127ca2cf4c34243386`. Do not write to the repository,
merge, deploy, run production Daily, inspect private runtime/portfolio contents,
request credentials, or scan operations-review artifacts. Claude Code is unrelated.

The owner requested physical root simplification while preserving operational and
analytical contracts. The candidate relocates seven acquisition landing modules,
eight official document modules, one temporal receipt module, and six thesis modules
into ordinary `stocklookup_core/acquisition`, `evidence`, and `research` packages.
Root Python counts fall from 595 to 574, root files from 613 to 592. One existing
`official_document_acquisition.py` CLI wrapper remains; all library callers use package
imports. No packaging framework, installers, services or new production entrypoint.
Owner CLI/PowerShell/tool paths, schema identities, numerical policy and evidence
paths remain unchanged. Three source-root expressions are adjusted for package depth.

Challenge import/reflection/subprocess resolution, historical-name navigation,
API compatibility assumptions, preservation of deterministic identities, retained
test-tier declarations, package placement enforcement and residual layout debt.
Inspect `config/repository_layout.json`, `tests/test_repository_layout.py`, the
controlling contract and this acceptance report, plus only directly relevant source.
Distinguish a concrete regression from a hypothetical external consumer: cite exact
file/line and reproduction for findings. In particular check fixture-only real Thesis
child execution, separate output roots, the offline Owner production call shape and
the updated package-aware Stage-1 import prohibition. The PDF retrieval module requires
existing optional pypdf and is validated separately from pinned core CI. Missing retained
evidence is declared, never fabricated or used to weaken assertions. Return a concise
English verdict, blocking findings, non-blocking debt and any genuinely unverified assumption.
