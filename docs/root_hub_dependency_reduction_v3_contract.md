# Root hub dependency reduction V3

Owner directive 2026-10-12: native scope `ROOT_HUB_DEPENDENCY_REDUCTION_V3`, admitted at the
exact starting HEAD before any source edit. Baseline: V2 PR130 merge
`d53999ba07a080b7fae2104185c56cc9a55ce210` (source `fdc974b` is an ancestor); post-merge
Producer CI `38222535046` SUCCESS. `authority_effect` NONE: source layout and import
ownership only. No merge, Daily, deploy, production write, provider call, evidence rewrite,
identity activation or successor. The [V1](accelerated_root_package_consolidation_v1_contract.md)
and [V2](accelerated_root_package_consolidation_v2_contract.md) rules remain in force.

## Hub analysis

V2 left 205 AMBER modules; 50 cited closure on four root hubs that must keep their root
names. Usage was measured per imported symbol, not per module:

| Hub | Importers | Symbols actually used | Disposition |
|---|---:|---|---|
| `field_temporal_contract` | 81 | `stable_id` 77, `canonical_json` 9, temporal types 6 | **Seam**: 75 importers use only identity primitives the hub re-imports from `stocklookup_core.evidence.field_identity` (the E5 owner) |
| `atomic_io` | 66 | write/replace/validate helpers | Deferred: no lower-level owner with identical fsync/replace semantics; extraction would edit the historically imported root implementation, which also imports root `observability_events` |
| `vn_time` | 36 | `vn_now`, `VN_TZ`, `vn_now_iso` | Frozen (E2/E3 pin, provider bundle); no sanctioned package owner; a second zone/clock authority is not created |
| `semantic_evidence_bridge` | 15 | verified-evidence loaders | Deferred: the loaders *are* the qualification; the bridge depends on root `financial_observations`; no second implementation |

## Seam

`field_temporal_contract` re-exports `stable_id`, `canonical_json` and `_sanitize_for_json`
from `stocklookup_core.evidence.field_identity`; it does not implement them. 43 root modules that
imported only those names now import them from the owner. Only the module token of each
import changes; aliases, function-local placement and all other bytes are kept. The bound
objects are identical (`is`) in both import orders. Monkeypatching is unchanged:
`from`-imports already bound the owner's objects at import time.

Not edited: the hub; its five genuine temporal consumers (`TemporalField`,
`wrap_temporal_fields`, `FreshnessState`, `PitStatus`, `extract_field_values`); E2/E3 pinned and
protected sources; Daily launcher targets; `tools/`; tests. Seven root modules keep the hub path
for identity names and are listed in the fixture.

## Relocation

With that edge gone, 13 AMBER modules had no remaining root dependency (fixpoint over V2's
exclusions). 11 move with V2's `migrate.py`: 6 to `evidence/`, 1 to `financial/`, 1 to
`valuation/` and 3 to `research/`. None is imported by an executed historical source or a
dynamic loader, uses `__file__`/`ROOT`, or is pinned. `artifact_identity` label strings are
unchanged. `adtv20_exact_reconciled_trailing_window_recovery` and
`historical_matched_trading_value_authority` stay at root. Their owner is evidence, but they
import valuation's `official_research_universe_tickers`, and a valuation placement would be
forced rather than owned.

## Pins and fixtures

The E0 sealed baseline, grandfathering, E1 carry policy, E2/E3 pins, V1/V2 mappings, E4
identities, provider bundle, launcher paths/ASTs and workflow are unchanged.
`tests/fixtures/root_hub_dependency_reduction_v3_relocations.json` pins the 11 additions and the
identity seam. Structural tests require the layout to equal the disjoint union of the E2/E3, V1,
V2 and V3 maps. They also require that the hub's primitives are the owner's objects, that only
the listed root modules keep the hub path for them, and that no V3 module imports the hub.

[Acceptance](root_hub_dependency_reduction_v3_acceptance.md).
