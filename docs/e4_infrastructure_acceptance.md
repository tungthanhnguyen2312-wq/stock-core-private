# E4 infrastructure acceptance

Baseline `0061d5f8afe4275ef6cf1dd7ba44930f559d2278`; E2/E3 post-merge Producer
CI38181224017: four successful jobs. E4 is bounded side-by-side development;
the [contract](e4_versioned_identity_safe_infrastructure_extraction_contract.md)
keeps production feedback identity activation and merge outside this milestone.

## Execution parity and identities

205 E4 tests passed on the local interpreter. Original V1 executes beside candidate
functions on synthetic fixtures: 50 paths, 49 fixed; eight root/path flavours, five
normal/malformed/nested sessions, invalid inputs, exact event selection, legacy
discovery and `cpc.level2` monkeypatch; exact compact/pretty chunks, bytes, errors
and hashes with LF/CRLF, Unicode, mixed keys, nonfinite floats, map/list records,
65535/65536/65537 token boundaries; bounded parser, duplicate/trailing/invalid data,
record-sized memory behavior, repeated execution and import-order isolation.
Actual baseline Git libraries and candidates produce equal Brief joins and exact
T0/current Thesis view/card NDJSON, matrix digest and input identities. Performance
telemetry is deliberately not asserted byte-identical. Synthetic outputs confer
no historical evidence or authority.

All E2/E3 frozen-source hashes and relocation mappings remain unchanged. V1 feedback
code digest remains `fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46`;
verification receipts also retain their original source inputs. The read-only V2
qualifier computes `e4_infrastructure_source/v2` over its explicit closed source set.
Candidate digest: `07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567`.
Qualifier fixture compact: 81 bytes, SHA256
`e93064c59bc7b95bfed31ce8be3ab2be7899c8fa847f034fdb649f6e2f354140`;
Windows native pretty: 130 bytes, SHA256
`2ebae284cfb33b3fd413aaebbb772784fce82269e2add58cd0e75679789fa9b2`.
Pretty hashes vary by native LF/CRLF exactly as V1 does; both are independently tested.
V1 and V2 differ deterministically despite output-byte/content-hash parity; V1 reuse
with V2 is rejected. No historical manifests/identities are mutated, adopted or copied
into V2; no production feedback path consumes the candidate metadata.

## Validation and graph measurements

Initial affected integration: 234 PASS (frozen E2/E3, Brief, Thesis Stage2, feedback
streaming); final pinned affected/E4/Thesis: 233 PASS. Structural/layout/ratchet/
roadmap/production call-shape/compact control plane: 149 PASS. Clean-clone retained
accounting: 5 PASS, 44 explicit absent-evidence SKIP. Architecture and Daily launcher
guards, pip check, installed dependency tiers, launcher compilation and state JSON
validation PASS. Full pinned hermetic selection: 5835 PASS, 75 SKIP, two Windows
virtual-environment launcher failures, 49 retained deselections, 103 subtests PASS.
Both failures reproduce against an untouched Git archive of accepted V1: the Windows
venv redirector creates a separate interpreter PID and consumes an extra Job member.
The unchanged containment assertions both PASS with the real base executable and
the same pinned libraries (`python -S`, explicit venv site-packages, no global/user
site packages, provider blocking). Thus all 5837 selected executable cases pass
across the broad run plus the two qualified reruns; 75 explicit skips remain.
No test, Job limit, source pin or runtime containment code is relaxed or repaired.
Hosted Ubuntu independently runs its native CI selection; these Windows-only tests
are explicitly platform-skipped there. External
reports retain exact commands, JUnit output, source inventory, qualification metadata,
graph snapshots/SCC memberships and affected fan-in/out. No retained artifacts,
provider requests, Owner Daily, Consumer/Dashboard edits or production writes.

Same analyzer/policy/settings, baseline to final candidate:

| Measurement | Before | After |
|---|---:|---:|
| Internal import edges | 3306 | 3322 |
| Backward edges | 188 | 185 |
| core-to-root edges | 150 | 147 |
| Eager SCCs | 1 | 1 |
| Runtime SCCs | 8 | 10 |
| Largest runtime SCC | 60 | 26 |
| Modules in runtime SCCs | 86 | 65 |
| Source modules | 971 | 975 |

Three backward edges removed: Brief to Level-2, Integrated Decision to root bounded
streamer, Thesis production to root bounded streamer. Eager membership is identical;
the 60-module runtime component splits into 26/10/3, releasing 21 modules from cycles;
all other runtime components are unchanged. No new cyclic edges or backward dependency.
Extra edges/modules reflect explicit foundation ownership and the offline qualifier.
Legacy bounded streamer fan-in23→21; retained V1 Level-2 fan-in30 unchanged (one removed
Brief connection and one explicit offline V1 parity connection). Exact fan-in/out and
SCC memberships are in the external graph report. No baseline/policy/grandfathering
or relocation mapping changed; only reviewed CI workflow binding is updated.

## Native and release gates

Native E4 admission uses the owner directive and preserves the COMPLETE E2/E3 record.
Queue stays empty. Local closeout occurs only after the admitted parity/integration/
architecture conditions pass. Hosted Producer CI and exact-HEAD Owner merge review
are separate from local acceptance. A future production V2 feedback transition must
integrate versioned terminal manifests and verification receipts under new explicit
owner activation authority; this PR preserves the frozen V1 runtime implementation.

Native local closeout: implementation checkpoint
ddc1880579a38eedfd17d1111a46b6064dd6ea60, COMPLETE /
LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED. No automatic successor.
Feature PR and hosted CI remain separate release-candidate gates; E4 merge and
production V2 feedback activation require their own owner decisions.
