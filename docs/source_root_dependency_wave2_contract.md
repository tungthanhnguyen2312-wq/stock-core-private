# Source/root/dependency simplification Wave 2

Owner source-only closeout `STOCKLOOKUP_ARCHITECTURE_SIMPLIFICATION_AND_CORRECTNESS_CLOSEOUT_20261014`.
The native coordinator owns admission; this document grants no runtime, release or evidence authority.

Five closed, reviewed implementations move: `market_feature_store_v1`, `strategy_framework`,
`momentum_screening_v1` and `candlestick_patterns` to `stocklookup_core/tactical/`;
`source_schema_guards` to `stocklookup_core/evidence/`. Root Python count is 291 → 286.
The existing layout manifest and [exact fixture](../tests/fixtures/source_root_dependency_wave2_relocations.json)
name each sole implementation. No root shim, dependency-policy exception or baseline refresh is added.

Consumers change imports. Standalone news uses the canonical guard with a temporary checkout
import path that is removed immediately; the separate file-loaded guard instance is eliminated.
Strategy's registry default resolves the checkout ancestor after relocation. Registry labels,
feature identifiers, formulas, schemas, numerical results and contract lineage remain unchanged.
`candle_scan.py` and the Phase 3/4B tool paths remain the same entrypoints.
SSI's ownership, frozen/historical imports, pinned consumers and cyclic families stay deferred.

Acceptance: affected tests, old/new synthetic numerical and lineage parity, unchanged CLI help/dispatch,
standalone news load without checkout on `sys.path`, foreign-CWD registry load, existing layout/import
ratchets, historical root-name exclusions and unchanged frozen/launcher/registry bytes.
The original CI corrective remains an ancestor; PNJ/FPT admission and October 13 seals are unchanged.
