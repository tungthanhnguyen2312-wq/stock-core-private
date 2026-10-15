# Root dependency breakout and real consolidation V5

Owner milestone: `PRODUCER_ROOT_DEPENDENCY_BREAKOUT_AND_REAL_CONSOLIDATION_V5`.
Exact released base: `1471d448a514ae54728696945abe56f914287664` (V4 PR153).
Authority effect: NONE; source ownership and imports only. Local implementation,
validation and commits are authorized. Push, merge, production operations and
automatic successors require separate Owner decisions.

## Evidence and choice

Reuse the complete V4 classification of the original 286 modules, SHA-256
`4ace3f91bc636ef9c5fb51fd8748dbe54fe143ed4bc9c296658708425ccd69cc`.
Its 4/173/90/17/2 dispositions and V1–V4 fixtures are preserved, not regenerated.
Only the selected dependencies, imported symbols, bodies and consumers are refreshed.

Two viable approaches were compared:

| Approach | Coupling and ownership | File effect and risk | Decision |
|---|---|---|---|
| Artifact I/O and event owner, followed by dependent stores | Decouples current consumers of the 66-importer atomic hub and its event dependency; closes five dependent root modules | One new implementation owner, two proven necessary historical interfaces, two existing owners absorb stores; requires filesystem failure, event, serialization and Daily parity | Selected: broadest independently testable seam with no frozen-source edit |
| Entity classification model extraction and classifier/reconciler consolidation | Could unlock two root engines under financial applicability; root authority loading/resolution remains | A separate neutral model owner is needed to avoid a new resolver cycle; enum/dataclass pickle names, precedence, config defaults and module patch slots need their own proof | Viable alternative, lower leverage for this wave; not implemented |

The important hubs remain individually constrained:

| Hub | Actual boundary and disposition |
|---|---|
| `atomic_io` | Atomic replace, validation, fsync, immutable hard-link publication, exceptions and event emission move together; this is not the landing writer's different newline/error contract |
| `semantic_evidence_bridge` | Its evidence loaders perform qualification and depend on financial observations/correction; no unqualified substitute or second admission path |
| `field_temporal_contract` | Genuine temporal types/evaluation still use freshness rules; eligible identity-only consumers were already separated in V3 |
| `financial_observations` | Provider normalization still depends on the pinned execution guard and frozen exporter name; not the raw observation store consolidated here |
| `entity_classification_contract` | Config authority precedence and historical typed interfaces remain intact; do not turn schema/template evidence into positive issuer authority |
| `official_source_registry` | Approval instant, exact host/type/rate policy and default registry location form a governance boundary; its qualification is not replaced by a parsing helper |
| `vn_time` | Exact E2/E3/provider-bundle pin; no second clock authority |
| `runtime_paths` | Exact E2/E3/provider-bundle pin and frozen operational callers; runtime-root policy unchanged |

These are implementation constraints, not permission to reopen their analytical work.
Unselected V4 dynamic, historical, source-pin and SCC constraints remain in force.

## Canonical ownership

`stocklookup_core/acquisition/artifact_io.py` owns the original atomic writer and
structured event bodies. It imports only stdlib modules. Acquisition is the lowest
existing domain that can own this file boundary under the unchanged E0 policy;
evidence and all downstream domains may consume it. No new package is introduced.
The existing `acquisition_landing_atomic_io` retains its different serializer,
newline, exception and cleanup contracts; apparent similarity is not equivalence.

`atomic_io.py` and `observability_events.py` retain only explicit re-exports of
these same objects. Immutable executed E4/E6 sources and reviewed Daily/export/
publication sources still import those exact root names. This demonstrates the
compatibility need; their frozen consumers are not rewritten. There is no module
proxy, service locator, dynamic fallback registry or duplicate implementation.
Exceptions, event enums and public callables retain their historical `__module__`
and pickle bindings. Both import orders and the existing `atomic_io.os.fsync`
patch slot are tested. New consumers intentionally bind the canonical owner's
globals; arbitrary reflective rebinding of unused legacy private slots is not
claimed as a supported plugin API.
The historical `atomic_io` import still initializes `observability_events` before
exporting its bindings; this observable import-order detail is tested explicitly.
Only serialization metadata retains the original callable/type import names;
neither module object's name nor the code filename is disguised.

Eleven additional Daily orchestration/publication sources keep their baseline
bytes as well, including canonical product/dashboard release, companions,
publication completion, scheduler and the Daily liquidity/materialization/brief
runners. They continue through the proven root API. The exact local preservation
inventory accompanies the 81 existing protected paths.

Five root implementations leave the root, with no compatibility copies:

| Removed root | Implementation owner |
|---|---|
| `raw_financial_store.py` | Existing `stocklookup_core/financial/raw_financial_observations.py` |
| `current_official_universe_evidence_retention.py` | Existing `stocklookup_core/evidence/current_official_market_universe.py` |
| `dnse_market_risk_evidence_store.py` | `stocklookup_core/evidence/dnse_market_risk_evidence_store.py` |
| `dnse_trades_canonical_shadow.py` | `stocklookup_core/evidence/dnse_trades_canonical_shadow.py` |
| `market_wide_coverage_report.py` | `stocklookup_core/acquisition/market_wide_coverage_report.py` |

Raw observation extraction and its deterministic gzip store share one financial
owner. Two private JSON/hash helper pairs were AST-identical and are deduplicated;
observation schema and store schema remain separately named/versioned. The store's
`OBSERVATION_SCHEMA_VERSION` patch binding remains independent. Gzip mtime, raw
rows, paths, failures, source fingerprints and qualified-field semantics stay fixed.
Financial observations are not newly admitted or promoted by moving their store.

Qualified universe retention now lives beside its existing verifier. It still
requires an explicit source, verifies the same artifact identity, refuses conflicts
and never discovers or acquires evidence. `RETENTION_CONTRACT_VERSION` preserves
the separate retention contract without replacing the verifier's version.
The Trades module retains its `_source_row` patch binding and selection/refusal
semantics. Existing consumer aliases and lazy import placement are preserved.

The optional `root_dependency_breakout_v5` section of the existing layout map binds
the exact base, original LF hashes, five relocations and two retained interfaces.
It is source-layout metadata, not a new authority registry. V1/V2/V3/V4 maps,
architecture baseline/policy, launcher paths/ASTs and package initializers do not change.

## Validation and measurements

Baseline and candidate run separately against synthetic fixtures, with provider
clients blocked and an owned temporary runtime for broad tests. Golden replay
covers observation rows, deterministic gzip bytes, risk OHLC, coverage, exact
universe identity and retention refusals, atomic writes/immutable reuse/conflicts,
fixed-time event bytes and failed Trades selection. Only temporary absolute roots
and random validator tempfile names are normalized; artifact bytes are not.

Required checks include E0 and all existing relocation/pin/historical guards,
Daily launch and call shape, import order/object/pickle identity, filesystem
failure cleanup, affected tests and the existing broad hermetic CI selection.
Compile and whitespace checks cover changed Python files. Exact test counts,
graph edges/SCCs, hub fan-in, cold-import samples, protected-source hashes and
October 14/VRE hashes are retained in the local acceptance report.

Expected structural accounting: root Python 282 to 277; five root removals,
three new relocated modules and one canonical I/O module. Two store boundaries
are absorbed into existing owners, two identical helper pairs disappear, and two
root implementations become required compatibility interfaces. Python files net
minus one; this new contract adds one file, so total tracked files remain 2,637.
No test or evidence deletion contributes to the result. No speedup is assumed.

Measured graph: raw edge rows 3,929 to 4,016 and module pairs 3,730 to 3,810.
The increase is package-initializer reachability from explicit package imports;
excluding initializer targets, edge rows are 2,615 to 2,612 and pairs 2,571 to
2,568. Backward rows/pairs fall 147/143 to 144/140, and core-to-root pairs 109 to
106. Atomic root fan-in falls 66 to 20; event root fan-in remains 5, including the
historical atomic import binding. The retained
Daily interfaces are counted rather than hidden. Eager/runtime SCCs remain 1/11
with identical membership, and unresolved/unsupported sites remain 9/15.
Implementation modules with own top-level functions/classes fall 572 to 569.
Five fresh-process affected-closure samples give median imports 0.778s to 0.772s
and working sets 104,386,560 to 104,206,336 bytes. Concurrent host activity and
normal timing variation preclude a meaningful speed or memory improvement claim.

Focused replay before edits: 103 passed, 4 skipped, one existing failure. Candidate:
106 passed, 4 skipped, the identical failure; three added object/import/pickle/fsync
boundary tests pass. Final structural/frozen/Daily selection: 811 passed.
Normalized exact golden: 25,566 bytes, SHA-256
`3cf78d8c983bd13740c612d14f33d9843bc76458119c95f73a3fc9661b5024bf`.
The local acceptance report records the separate broad and retained comparisons;
these focused counts do not claim that unavailable retained tests passed.

Final broad hermetic baseline and candidate each pass 5,687 tests, skip 95 and
deselect 49, with 134 passing subtests. All primary test IDs/outcomes match;
there are no removed cases or new regressions. Final structural selection passes
811, and the final import/Daily supplement passes 29. Retained baseline and final
candidate each have 8 passes, 14 skips and the same 27 failures, with exact
failure/skip identities. Four CLI help outputs match byte-for-byte. A read-only
import of the released Dashboard publisher verifies the same legacy helper
objects, signatures and fixed-time event bytes; no publish function is called and
bytecode writes are disabled. Consumer tracked source has no direct reference to
the seven affected root names. Neither sibling repository is modified.

The baseline focused selection has one existing archetype assertion failure:
`ArchetypeTests::test_corporate_template_never_grants_a_corporate_archetype` uses
`AAA`, whose retained classification now resolves corporate. This source refactor
does not change the authority manifests or that assertion. Baseline/candidate
failure identities are compared explicitly. V4's 27 retained-tier failures remain
reported as limitations, never relabelled passing or hidden by weaker tests.

## Native and Owner release workflow

The released succession operation transfers Claude Opus 5.5 to Codex at revision
151, preserving all 26 prior lane records and history. The first uncheckpointed
admission used an unsupported package-root placement; E0 rejected it. Its exact
diff is retained externally, its lane is ABANDONED, and normal native admission
registers the complete corrected scope as
`PRODUCER_ROOT_DEPENDENCY_BREAKOUT_AND_REAL_CONSOLIDATION_V5_SOURCE` (ACTIVE 156).
No allowed-path rewrite or policy exception is used. The VRE COMPLETE_LOCAL lanes
and `ACTIVE_STATE.md` lease remain unchanged. That navigation file is deliberately
excluded; the bound native state supplies this milestone's execution disposition.

The retained V4 handoff identifies two separate controls. The host classifier
refused the author/integrator writing its own `reviewed_by` receipt as
"Self-Approval". Separately, the PR author's GitHub account could not approve its
own PR. The Owner personally supplied the receipt and ran the release/closeout;
an extra JSON `owner_review` field was not itself authentication. Neither control
is disabled here. A technical report does not grant merge authority or constitute
an independently executed native review receipt.

A future single Owner-executable PowerShell action could accept one reviewed bundle
(repository, PR, exact candidate/main/plan hashes, technical receipt and CI locators),
display those bindings, require the human's own authenticated authorization, and
perform the already-approved exact-head normal merge only after all native/GitHub
gates pass. It must refuse self-review or stale identities. Its output would be an
immutable merge/CI evidence bundle; bound Codex would independently verify and record
native MERGED_RELEASED. It must not manufacture an Owner signature or use `--agent`
as proof of human approval. There is no authenticated human-approval contract in the
current local receipt schema, so an executable approval/merge wrapper is not added
under this source-layout wave. Reuse and parameterize the existing Owner-only V4
PowerShell closeout rather than build another coordinator. Its current hardcoded
V4 plan/head/agent values must never be replayed for V5. The candidate implementation
can supply an unsigned evidence bundle; the Owner-controlled execution boundary
must supply genuine review and authorization. No boolean or agent-generated
approval string can replace that boundary. This is the narrow future design,
not an implemented governance extension or a new Owner approval assertion.

Local source completion is not release. No V5 push, merge, Daily, database write,
Dashboard publication, provider call, sealed-session change or VRE admission occurs.
