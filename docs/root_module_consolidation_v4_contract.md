# Root module consolidation and net file reduction V4

Owner milestone: `PRODUCER_ROOT_MODULE_CONSOLIDATION_AND_NET_FILE_REDUCTION_V4`.
Base: `416c3083a7547039386c330f550ed2dbf7eed324`. Source layout only; authority
effect NONE. One Codex writer, isolated worktree, no production operations or
source push/merge. The [V1](accelerated_root_package_consolidation_v1_contract.md),
[V2](accelerated_root_package_consolidation_v2_contract.md),
[V3](root_hub_dependency_reduction_v3_contract.md) and
[E0 ratchet](stocklookup_architecture_dependency_ratchet_and_daily_launch_guard_v1_contract.md)
constraints remain unchanged. This is a new bounded source cohort; prior completions
and the VRE independent-review packet are not reopened.

## Discovery and selected boundary

All 286 baseline root modules are recorded in the local operator classification
manifest, with original blob/file hashes, functionality and exported symbols,
static import sites and aliases, root/package edges, SCCs, loader/CLI references,
source/path/serialization sensitivity, historical execution and frozen consumers,
proposed destinations, dispositions and exact reasons. The unchanged E0 analyzer,
layout, launcher inventory, E2/E3/E4/E5/E6 protection and V1/V2/V3 historical-source
fixtures supply the evidence. Static analysis does not prove arbitrary runtime
reflection; unresolved sites are not waived. The manifest is a review artifact,
not a new runtime registry or migration framework.

The complete local manifest is `classification-all-286.json`, SHA-256
`4ace3f91bc636ef9c5fb51fd8748dbe54fe143ed4bc9c296658708425ccd69cc`.
It also annotates 728 conservative imported-alias/literal monkeypatch sites; the
four selected originals have no such existing targets. Unselected semantic
destinations are explicitly proposals, with their existing root owner retained.

Disposition totals: MOVE_SAFE 4; KEEP_PINNED 173; KEEP_ROOT 90; KEEP_DYNAMIC 17;
KEEP_CYCLE 2. No duplicate/dead implementation is declared proven. Many root
modules have no intrinsic byte pin but a pinned importer still requires their
root name. KEEP_ROOT names the unclosed dependency paths; its proposed destination
is not permission to add package-to-root debt.

The selected boundary is four acyclic retained-only pilot implementations. They
have no pinned importer, executed historical import-name dependency, code-digest
consumer, unresolved loader or module-name serialization consumer. Actual imports,
synthetic CLI flags and object bindings were reviewed, not inferred from filenames.

| Original root implementation | Canonical owner | Change |
|---|---|---|
| `opportunity_snapshot.py` | `stocklookup_core/decision/opportunity_snapshot.py` | Move the decision/ranking snapshot contract |
| `opportunity_snapshot_retention.py` | Same snapshot owner | Consolidate its append-only validation/retention with the snapshot and serializer it already imported |
| `ssi_securities_pilot.py` | Existing `stocklookup_core/evidence/official_document_downstream_shadow.py` | Consolidate the pure input-identity/scope qualifier with its sole runtime caller; retain `evaluate_ssi` binding |
| `vnm_execution_contract.py` | `stocklookup_core/portfolio/vnm_execution_contract.py` | Move exact implementation bytes; no execution activation |

The SSI qualifier maps same-filing identities, scope, units and applicability; it
performs no ratio or financial calculation. Evidence ownership avoids forcing an
evidence-to-financial dependency. Its `SSI_VERSION` remains 1.1.0 while the existing
shadow `VERSION` remains 1.0.0. `evaluate_ssi` retains the original function name
`evaluate`; no forwarding function is introduced. Snapshot and retention share the
existing version/serializer values; retention error class, conflict handling,
append bytes and order remain unchanged. The reconstruction caller and backtest
bind the canonical objects directly. No old root shim survives.

Existing pilot CLIs are opt-in synthetic checks. Their reviewed replacement paths:

```text
python -m stocklookup_core.decision.opportunity_snapshot --frozen-pilot
python -m stocklookup_core.decision.opportunity_snapshot --historical-pilot
python -m stocklookup_core.portfolio.vnm_execution_contract --frozen-pilot
```

No reviewed Daily launcher used the removed filenames. Historical filename labels,
capability keys, R7 source-hash records and artifact identities retain their original
strings. Consumer's dynamic loader still requires `news_ticker_mapping.py` at root;
its standalone import test and root implementation remain untouched. VNM shadow
backtest stays at root because its other dependencies are not legally movable.

## Actual simplification

| Measure | Before | After |
|---|---:|---:|
| Root Python modules | 286 | 282 |
| Tracked files, including this document | 2,638 | 2,637 |
| E0 unique edge rows | 3,932 | 3,929 |
| E0 unique module pairs | 3,735 | 3,730 |
| Backward edge rows / pairs | 148 / 144 | 147 / 143 |
| Core-to-root pairs | 110 | 109 |
| Eager / runtime SCCs | 1 / 11 | 1 / 11 |
| Runtime SCC participants | 41 | 41 |
| Unresolved / unsupported dynamic sites | 9 / 15 | 9 / 15 |

Four old root files are removed, two package files are added, and one existing
owner absorbs a qualifier. Two standalone module boundaries are consolidated;
zero needed implementations or tests are deleted. Adding this contract leaves
one fewer tracked file overall. There are zero new wrappers, shims, packages,
dependency registries or framework layers. Eleven import sites change (including
the removed SSI import), with existing tests retargeted rather than discarded.

Mapping old nodes to their final owners, removing package initializer and newly
internal self edges, produces the identical 2,614 dependency rows in both trees.
This explicit many-to-one projection is not a claim that the raw graph is identical.
SCC membership is exactly unchanged. E0's sealed baseline, dependency policy and
five E1 carry rows are unchanged; no new debt allowance is added.

Five fresh interpreters per side measured the actual affected pilot/shadow import
closure: medians about 19.5 ms before and 19.9 ms after. This small host measurement
does not establish a meaningful startup speedup. No runtime optimization follows.

## Significant remaining root hubs

| Hub | Why it stays |
|---|---|
| `atomic_io` | Immutable executed E4/E6 sources import its root name; fsync, replacement, exception and observability semantics cannot be replaced by a convenient domain helper |
| `runtime_paths` | E2/E3 exact source pin and provider bundle; frozen operational callers consume it |
| `field_temporal_contract` | Historical sources and genuine temporal types still need the hub; V3 already retargeted eligible identity-only imports to their package owner |
| `vn_time` | Exact E2/E3 and provider-bundle source identity; a second clock authority is not introduced |
| `daily_session_level2_package` | Frozen receipt/code-digest input and reviewed Daily paths; operational behavior and identity remain fixed |
| `dnse_access` | Reviewed frozen callers need the credential/request boundary at its existing import name |
| `entity_classification_contract` | Executed historical sources and frozen decision consumers need its root types/constants |
| `official_source_registry` | Native financial replay and immutable historical imports bind the root authority interface |
| `semantic_evidence_bridge` | Executed E6 admission/qualification sources depend on the exact root interface and its financial-observation dependency |
| `technical_structure_context` | Frozen technical measurement owner and historical source; neither new measurement semantics nor a compatibility copy is authorized |
| `dnse_secrets_env` | Reviewed frozen callers and its root `dnse_access` dependency preserve the credential boundary; moving just the leaf adds backward debt |
| `prospective_market_snapshot_contract` | Frozen technical, prospective capture and decision sources import its root contract |
| `bounded_artifact_stream` | E2/E3 byte pin and E4 V1 code-digest input; its optional E4 package successor is not implicitly activated |
| `market_wide_current_fundamental_research` | Historical and frozen financial callers require its root API; canonical store, semantic bridge and related root dependencies remain unclosed |
| `financial_evidence_currency_contract` | Immutable historical imports and frozen PDF/financial consumers bind the exact contract |
| `provider_execution_guard` | E2/E3 pin and worker bundle; no provider policy/runtime change or second guard is authorized |
| `prospective_decision_retention` | E2/E3 pin and E4 V1 source identity; original T0 and streaming semantics remain immutable |
| `owner_research_focus` | Historical executed source and frozen decision brief import it; config path and presentation-only semantics are retained |
| `daily_research_session_operations` | Reviewed launcher and immutable source identity; session orchestration is outside V4 |
| `dnse_bulk_market_data` | Depends on root credential/request owners; its bulk budget differs from the ordinary request boundary, so apparent duplication is not a deletion proof |
| `prospective_pit_capture_retention` | E2/E3 byte pin and E4 V1 digest; capture/receipt and knowledge-time semantics remain unchanged |

This table covers every root hub with at least 15 distinct E0 source importers at
the base (not repeated symbol imports). The full manifest covers all smaller hubs.

The minimum broader seam is a separately reviewed compatibility/pin policy for
these exact frozen import names or a genuine approved owner extraction that
preserves their identities. V4 does not manufacture a second implementation,
relocation shim, new carried edge or changed historical receipt to unlock volume.

## Validation and release boundary

The original base was executed before edits. The seven pilot suites pass before
and after; 41,219 canonical output bytes match exactly (snapshot IDs, retention
bytes/errors/replay, execution pilot, SSI acceptance/refusals and official shadow
lineage). Existing structural tests now cover the V4 many-to-one map separately
from the exact V1/V2/V3 fixtures. New CLI goldens pin outputs captured from the base,
and object-identity tests cover the real reconstruction/backtest bindings and the
two independently versioned SSI/shadow contracts.

Native structural/frozen-source, cold import, launcher/call-shape, affected financial,
valuation, PIT, tactical/research and hermetic selections are recorded in the local
acceptance handoff, including unavailable retained evidence and exact failures.
No production Daily is a validation command. Existing 81 protected source paths,
prior fixture maps, launchers, 51 protected session/publication files and the entire
VRE review packet must retain their hashes. Compile and whitespace checks apply to
every changed Python file. Exact test results and source HEAD govern readiness;
this document does not substitute for a passing native check or release review.

Retained-tier limitation: with the existing marker root pointing at the primary
checkout, eight retained tests pass and fourteen report absent inputs. Twenty-seven
legacy tests/builders still resolve worktree-local or hardcoded sibling-runtime
paths and fail in this isolated layout. Running those exact test IDs on an untouched
`416c3083` fixture reproduces all 27 failures, with no new failure ID. They remain
unverified here, not passing tests. No retained evidence is copied, linked or
rewritten and no assertion or marker is weakened to make them green.

The native coordinator admitted only the 18 disjoint paths. An attempted exact
lease for `docs/ACTIVE_STATE.md` was refused with `LANE_OWNERSHIP_OVERLAP` against
`VRE_IMAGE_BOUND_METADATA_INDEPENDENT_REPLAY_V1` at COMPLETE_LOCAL. That file is
excluded and unmodified; no manual state rewrite or alternate writer is used.
The VRE lease is preserved: V4 adds no `ACTIVE_STATE.md` line, and its native lane
record is the release authority. That navigation line waits for VRE's own normal
release; V4 does not qualify VRE evidence or admit assets.

The Owner later transferred V4 integration from Codex to Claude Opus 5.5. The
transfer used the native `--transfer-integration-owner` succession, which was released
separately. Codex's working tree was recovered unchanged, and the V4 source release
follows the normal exact-head review, hosted CI and ancestry-preserving merge. No
production operation, authority promotion or successor is authorized here.
