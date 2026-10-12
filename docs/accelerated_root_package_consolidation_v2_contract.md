# Accelerated root package consolidation V2

Owner directive 2026-10-12: native scope `ACCELERATED_ROOT_PACKAGE_CONSOLIDATION_V2`,
admitted at the exact starting HEAD before any source edit. Baseline: V1 PR129 merge
`9174d2b8b8e13fa3a2a4c696b9e2fb28a39a81ea` (source `c1c21ee` is an ancestor);
post-merge Producer CI `38210255068`, four jobs SUCCESS. `authority_effect` NONE:
source layout only. No merge, Daily, deploy, production write, evidence rewrite,
identity activation or successor. [V1 contract](accelerated_root_package_consolidation_v1_contract.md)
and its classification rules remain in force.

## AMBER resolution

V1's scanner was rerun unchanged on the released tree (its dependency reasons predated the
95 moves). Each AMBER reason was then resolved by evidence, not waived:

- Filename references were classified by AST context. Strings inside data/message
  structures (registry rows, provenance `source_modules`, report text, Daily stage names)
  are identity text and stay byte-identical. Pin-list holders (E4/E5/E6 tests, the E4
  qualifier) keep their modules at root. Non-test path/launch uses keep modules at root.
  Test reads of a module's source by checkout path follow the move through exact,
  line-scoped literal rewrites.
- All 28 `__name__` flags were `type(x).__name__`/`func.__name__` (no module identity);
  all 19 hashing flags were `source_sha256` data fields, not code hashing.
- The usual V1 gates still apply: no byte/AST-pinned importer, no `__main__` CLI, no root
  name imported by an executed historical source, closed root dependencies, and
  dependency-policy-legal placement for every package importer.

The binding constraint is closure. Hub modules such as `field_temporal_contract`
(imported by accepted replay sources), `atomic_io` (E4/E6 sources),
`semantic_evidence_bridge` (E6 source) and the provider-bundle `vn_time` must stay at
root, so their dependents cannot move without new package-to-root debt. That debt is not
allowed, and the E1 carry allowance is not extended.

## Relocation

Three cohorts move 45 implementations: 23 market-data/provider-basis evidence modules,
then 8 temporal/official/share evidence modules and 4 source adapters (EODHD boundary,
SJC and VCB macro) to `acquisition/`, then 6 financial, 1 valuation, 1 research and
2 decision modules. Totals: 31 to `evidence/`, 4 to `acquisition/`, 6 to `financial/`,
1 to `valuation/`, 1 to `research/` and 2 to `decision/`. Bodies change only in
import lines and the `parents[2]` checkout-root idiom. Consumers change only the import
statements naming a moved module. No shim, compatibility entrypoint or proxy is added.
`macro_sync` keeps its root launch path and its lazy call-time imports, so module-object
patches still propagate.

Reviewed test edits:
- KBS import-set expectations collapse into the existing `stocklookup_core` entry.
- Line-scoped source-path reads in the KBS overclaim scan, the VCB ticker-branch scan and
  the representation token test; the KBS scan previously skipped missing paths silently.
- One EODHD patch target.

## Pins and fixtures

The E0 sealed baseline, grandfathering, E1 carry policy, E2/E3 pins, V1's 95 mappings,
E4 V1/V2 identities, provider bundle, launcher paths/ASTs and workflow are unchanged.
`tests/fixtures/bulk_root_package_consolidation_v2_relocations.json` pins the 45 additions.
Structural tests require the layout to equal the disjoint union of the E2/E3, V1 and V2 maps.
They apply the V1 no-shim, carry, historical-name and import-probe checks to V1 ∪ V2.

[Acceptance](accelerated_root_package_consolidation_v2_acceptance.md).
