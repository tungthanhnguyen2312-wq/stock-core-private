# E6 financial boundary acceptance

Baseline: accepted E5 merge `70fbba96d02369e0f02a5a15dd264bad780fe6ce`;
[contract](e6_financial_extraction_admission_boundary_contract.md).
E5 post-merge CI38190156979 was initially 3/4 SUCCESS, focused regressions pending.
Final baseline verification: all four jobs SUCCESS on exact accepted merge HEAD.
The required baseline publication gate is satisfied.

## Independent semantic and byte parity

Accepted E5 Git archive and E6 execute the same owned synthetic fixture in separate
processes, with pinned core libraries and no global/user site in the `python -S`
parent. Children inherit pinned libraries and provider import blocking. The optional
PDF tier adds only isolated pinned `pypdf==6.14.2`, not a production dependency change.

Core output: 141,591 identical compact UTF-8 bytes, SHA256
`62862f936b6e6659303536b95d6c18b739bf41d03eecdf672860b00cf0a5826b`.
Optional native PDF/registration output: 165,531 identical bytes, SHA256
`6d1fd5ee414c6d874a5a03e93f9826eca788d32ca9b7878469ed99cb49cc17ff`.
Cases include metadata missing/conflicting spans, headings/periods, scope/currency/units,
literal/superscript row labels, source assurance, direct admission/use/cutoff guards,
extracted facts, owned OCR panel/ingress, precedence/policy, native PDF extraction,
and actual registration/persistence of intact/tampered/missing owned sources.

V1 and E4 V2 are recomputed, not shimmed:
`fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46` and
`07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567`.
All source inputs, E2/E3 pins, provider bundle and E5 foundations remain unchanged.
Financial registry/legacy row pins, assurance/period/unit owners and native PDF
implementation are also unchanged. Changed unbound hashes are recorded separately.

## Identical analyzer measurement

| Measurement | Accepted E5 | E6 |
|---|---:|---:|
| Modules | 979 | 982 |
| Internal import edges | 3350 | 3374 |
| Backward edges | 176 | 176 |
| core-to-root edges | 140 | 140 |
| Eager SCCs | 1 | 1 |
| Runtime SCCs | 11 | 11 |
| Largest financial SCC | 10 | 4 |
| Largest runtime SCC | 10 | 10 |
| Cyclic participation | 47 | 41 |

The eager and Daily components are unchanged. No new backward/cyclic dependency,
unsupported loader, exemption or source placement exception. Six return dependencies
are removed; restoring them recreates financial10/participation47. The four remaining
financial members and exact rationale are recorded in the contract. Full memberships,
fan-in/out, dynamic sites and normalized changed-source hashes remain in the external report.

## Validation and native state

Final E6 targeted: 166 PASS, three explicit optional-parser skips. Isolated optional
native-parser tier: all 169 PASS. Structural/layout/E1 relocation/roadmap/production
call-shape/compact contracts: all 149 PASS. Qualified affected integration: 847 PASS,
four explicit optional-dependency skips, five deselected absent-evidence tests.

The initial expanded affected run had 846 PASS, four skips and six failures: one
fixture assertion compared in-memory tuples to their JSON list representation, fixed
to compare serialized bytes/JSON; five native-PDF tests lacked the same retained AAA
binary. All five reproduce on unchanged E5 source (five FileNotFound failures, 0.83s).
No test annotation, evidence requirement or source predicate was loosened; the final
affected selection lists those exact five absent-evidence test IDs explicitly. Owned
native-parser fixtures independently exercise intact/tampered/missing sources.
The initial compact docs exceeded the budget by 21 bytes; only the new roadmap scope
text was trimmed. Final structural contracts passed without changing their checks.

Retained accounting: 5 PASS, 44 explicit missing-evidence skips, 6233 deselected.
Architecture ratchet, Daily launcher guard, pinned dependency tiers (0 violations),
package consistency, five launcher compilation checks, roadmap JSON and diff checks
PASS. Native ACTIVE consistency is ON_TRACK / VERIFIED; queue empty. Full CI-equivalent hermetic selection: 6155 tests plus 103 subtests PASS, 78 explicit skips, 49 deselected, zero failures/errors (1046.23s pytest elapsed). JUnit includes subtests in its 6336 total cases. Clean-checkpoint native closeout follows qualified implementation. No local
completion is claimed until required checks pass. No production evidence was generated
or promoted. Implicit fixture source replay resolves only an owned temporary root,
and the caller environment is restored afterward; both independent output hashes
remain identical under this containment.

Final API parity includes literal-fold deferred annotations. The broad run preceded
that compatibility-only flag, filing ownership docstring and fixture-root containment
update; final targeted/native/contained-fixture checks qualify those changes. Financial
algorithms are unchanged; no expensive broad rerun for these bounded updates.

Native local closeout: implementation checkpoint
`3d731a81cabf9537289f08138d921615b899fa34`, COMPLETE /
LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED, ON_TRACK / VERIFIED; queue empty.
Feature publication and hosted CI remain separate release-candidate gates. Owner
exact-HEAD merge approval is required; no E6 merge or E7 admission is performed.
