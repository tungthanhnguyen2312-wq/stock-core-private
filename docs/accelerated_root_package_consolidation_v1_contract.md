# Accelerated root package consolidation V1

Owner directive 2026-10-12 (replacing the stopped E6-gate job): native scope
`ACCELERATED_ROOT_PACKAGE_CONSOLIDATION_V1`, a bounded continuation of the
[root simplification program](repository_root_structure_simplification_v1_contract.md).
Baseline: E6 PR128 merge `3f1be104386a218899b7dcb4bdeaa154be17ce06` (source
`3d865da` is an ancestor); E6 post-merge Producer CI `38194697661`, four jobs SUCCESS.
`authority_effect` is NONE: source layout only. Local edits/tests/checkpoints,
native closeout, one feature PR and in-scope CI repairs are authorized. No merge,
Daily, deploy, production write, evidence rewrite, identity activation or successor.

## Classification

Every root Python module was classified from the unchanged E0 AST graph, AST string
constants (not comments/docstrings), tracked non-Markdown filename references and the
protected source sets. RED: front door, the 31 reviewed path-launch targets and the 12
AST-pinned callers, E2/E3 byte pins, frozen V1 `code_digest`/receipt inputs, E4 V2
sources, provider worker bundle, E5/E6 pinned foundations, eager/runtime SCC members
(cycle rows are name-keyed), root-to-tools debt and unresolved/unsupported loaders.
AMBER: consumer-code filename references, documented `python file.py` use, non-standard
`__file__`, `__name__`/`__module__`/pickle identity, source/code hashing, `sys.path`,
`__main__` CLIs, or dependence on a non-movable root module. GREEN requires none of
these, a closed set of root dependencies, no byte/AST-pinned importer and policy-legal
placement for every package importer. Filename age or fan-in never decides.

Three otherwise-GREEN modules stay at root because an immutable accepted source executed
by a parity harness or replay imports them by name: `official_acquisition_budget`
(E5 baseline), `official_financial_value_evidence` (E6 baseline) and
`sector_relative_research_context` (accepted peer replay). Seven are deferred for
ambiguous ownership (no governed publishing/utility package, or financial semantics that
direction rules would force into `evidence`).

## Relocation

Four cohorts move 95 implementations: 45 to `evidence/`, 3 to `tactical/`, 19 to
`financial/`, 20 to `research/`, 2 to `portfolio/`, 6 to `decision/`. Placement satisfies
`config/architecture_dependency_policy.json` for every dependency and package importer.
A moved body changes only import lines naming moved modules and, where present, the
established `Path(__file__).resolve().parents[2]` checkout-root idiom. Consumers change
only those import statements (`import X as Y` keeps its alias). No root shim or
compatibility entrypoint is added; old names do not resolve.

Serialized artifact keys, provenance citations and registry labels that spell a module
name are identity text and stay byte-identical. The feature-fitness pointer test resolves
a relocated label through `config/repository_layout.json`. Reviewed test literals: KBS
import-set expectations, two `__import__` calls given `fromlist`, a leaf-name forbidden
import guard, and the zero-active-Vnstock audit entrypoints.

## Ratchet and pins

The sealed E0 baseline, grandfathering and E1 carry policy are unchanged; no moved module
gains `relocated_debt_edges`. The 120 E2/E3 relocation mappings stay exact;
`tests/fixtures/bulk_root_package_consolidation_relocations.json` pins the 95 additions.
Layout tests reject root copies, carried-debt expansion and relocation of any root name
imported by the listed executed historical sources. No byte/AST-pinned file, provider
bundle, launcher path, workflow or dependency file changes.

[Acceptance](accelerated_root_package_consolidation_v1_acceptance.md).
