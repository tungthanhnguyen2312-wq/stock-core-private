# E5 runtime cycle acceptance

Accepted baseline main `e9ee2fe135e9e529b60f11ab97f30fc6441e6e24`, E4 PR126;
post-merge Producer CI38186488312 SUCCESS. Exact scope and compatibility limits:
[contract](e5_runtime_dependency_cycle_reduction_contract.md).

## Independent execution and compatibility

Accepted E4 Git source was archived outside the checkout without runtime evidence.
The same fixed synthetic fixture code executes in separate processes with that
source and the E5 source, using the same isolated pinned libraries. Event projection,
financial currency, its packet context, Human/AI packet, assurance proof, TemporalField
record, field JSON/SHA, Daily product identity and portfolio identity are exactly equal.
Combined compact UTF-8 output: 14,703 bytes, SHA256
`be69a64373b485f9563b560af68555c4d7a10dfd8e300dbbe415bdaf6422c5cb`.
The fixture and accepted source reference are retained as regression evidence;
individual outputs, commands and source hashes remain in the external report.

152 final E5 tests PASS: original/candidate cutoff and normalization functions,
malformed/missing/future/naive inputs, default-str/NaN/nonfinite/mixed-key/Unicode
field JSON, actual consumer hashes, nested capital-field rejection, shared exports,
mutable policy and monkeypatch/import-order tests, lightweight import isolation,
restored-cycle negative controls and exact frozen-source checks, including the existing
TemporalField stable-ID slot and lower-owner helper patching.

Eleven V1 feedback inputs, E4 V2 source set, E2/E3 pinned sources, provider bundle,
frozen Technical/Volume V1 and tactical owner are byte-preserved (LF normalization
only where the standing source contract already uses it). V1 digest:
`fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46`;
E4 V2 candidate digest:
`07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567`.
Changed unbound source hashes are recorded as changed, without historical digest
rewriting or V2 production activation. Field JSON is not E4 strict artifact JSON.

## Identical graph measurement

| Measurement | Accepted E4 | E5 |
|---|---:|---:|
| Source modules | 975 | 979 |
| Internal import edges | 3322 | 3350 |
| Backward dependency edges | 185 | 176 |
| core-to-root edges | 147 | 140 |
| Eager SCCs | 1 | 1 |
| Runtime SCCs | 10 | 11 |
| Largest runtime SCC | 26 | 10 |
| Total modules in runtime SCCs | 65 | 47 |

Four new leaf owners add explicit imports/package edges. Nine inversions are
eliminated: seven stable-ID-only core→root edges and Financial Currency→decision
package/module forms. No forbidden edge, unsupported/unresolved loader, cycle edge,
policy/baseline/relocation change or new root module is admitted. Eager SCC membership
is identical. The largest component splits and releases fourteen modules; heading
folding releases assurance/period recognition from the financial SCC, and the schema
tuple releases both Financial Currency and the Human/AI packet from their cycle.
Restoring the four return dependencies restores SCC maximum26/participation65.

Removed return dependencies: official event context→rollforward; financial assurance
and period identity→OCR engine; Financial Currency→Human/AI packet. Remaining largest
components are the ten-module Daily orchestration component and ten-module financial
extraction/admission component. The seven-module calendar/capture component includes
frozen V1 inputs; Technical dispatch/view/V2 and frozen serializer pairs remain.
Exact memberships, reachable dependency graph and changed-module fan-in/out are
preserved in the external before/after graph report.

## Validation, baseline limits and release

Initial expanded affected selection: 228 PASS, five missing-retained-fixture failures.
All five reproduce on untouched accepted E4 source, each because the isolated source
checkout lacks the same governed official manifest. They are optional OCR retained
tests outside the normal hermetic CI selection. No source/evidence fixture is fabricated,
regenerated or loosened. Synthetic normalizer and full assurance/period consumers
are independently tested. Final affected selection: 680 PASS, 13 explicit skips,
three missing-retained-file failures in portfolio/learning tests outside standard
CI selection. Those three also reproduce on unchanged accepted E4 source. Their
synthetic identity consumers are covered by the independent execution fixture.

Structural selection: 148 PASS and one compact-doc wording failure after a size-budget
trim; corrected in docs, with all 12 compact-control-plane tests then PASS. The other
137 structural/layout/roadmap/production-call-shape cases passed unchanged. The size
and mandated live-remote verification wording are preserved; no test was weakened.
Retained-accounting selection: 5 PASS, 44 explicit absent-evidence skips, 6064 deselected.
Architecture ratchet, Daily launcher guard, dependency tiers (0 violations), pinned
package consistency, five launcher compilation checks, roadmap JSON and diff checks PASS.
Full CI-equivalent focused hermetic selection: 5989 tests and 103 subtests PASS,
75 explicit skips, 49 deselected, zero failures/errors (1027.44s pytest elapsed).
JUnit counts subtests as separate cases (6167 total, including skips).
Native closeout follows the clean implementation checkpoint.

Pinned CI packages run with the real Windows Python executable and explicit libraries
(`python -S` parent excludes global/user site; children inherit pinned PYTHONPATH and
provider import blocking), avoiding
the accepted E4 diagnostic limitation of the Windows venv redirector PID/Job member.
The original assertions and containment policies remain intact.

Native admission preserves E4 completion/history and keeps the queue empty. Local
closeout requires the complete admitted scope's validation and a clean implementation
checkpoint. Feature publication/hosted CI and separate Owner exact-HEAD merge approval
are release gates. No Daily, provider request, production write, Consumer/Dashboard
edit, evidence promotion or production V2 activation is performed.
