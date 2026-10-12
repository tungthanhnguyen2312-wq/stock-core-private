# E6 financial extraction/admission boundary

Owner directive: attachment `3ead8b4b-ef62-4137-add2-c6e02170d704`, 2026-10-12.
Native scope: `E6_FINANCIAL_EXTRACTION_ADMISSION_BOUNDARY`; accepted E5 merge
`70fbba96d02369e0f02a5a15dd264bad780fe6ce`, source `ad66c6e964845b0b972a29383ae844213107bd98`.
[E5 contract](e5_runtime_dependency_cycle_reduction_contract.md) and
[acceptance](e5_runtime_cycle_acceptance.md) remain preserved. Local edit/test/commit,
closeout and one feature PR/CI repairs are authorized; publication requires successful
E5 post-merge CI. No merge, Daily, acquisition/provider request, deploy, production
write, evidence/authority promotion, V2 activation or E7 admission.

## Narrow ownership seams

1. `stocklookup_core/evidence/financial_row_identity.py` owns the existing mutable
   `ROW_LABEL_CONTRACT`, NFD-only `_identity_fold`, literal row predicate and two
   crossed total/parent income line-code identities. Filing admission, interim
   ingress and historical correction consume it without importing OCR execution.
   Interim ingress exports the exact conflict frozenset; OCR exports the exact
   dictionary and fold callable. The OCR row predicate retains its original public
   signature as a compatibility wrapper, forwarding its live `_normalize` slot to
   the lower predicate. This wrapper is intentionally a distinct callable, required
   to preserve the existing E5 normalizer monkeypatch surface; migrated consumers
   share the lower callable. No duplicate policy table or domain algorithm remains.
   Optional `normalizer` supplies only this explicit pure text transformation, not
   an execution service, module locator or hidden dependency. Unknown metric behavior,
   literal loan/total/parent labels, compact spacing and superscript ambiguity stay exact.
2. `stocklookup_core/evidence/financial_metadata_envelope.py` owns the pure existing
   envelope constants, strict JSON/SHA helpers, frozen `EvidenceSpan`, `_span` and
   `qualify_document_metadata`. Filing exports the same objects explicitly. Refresh,
   precedence and document registration bind the lower envelope owner; actual source
   admission and replay remain in their original owners. Metadata is only document
   proof, never value-level or numerical authority. The schema does not infer required
   values, assurance, periods, currency, units or scope from discovery hints.
3. `stocklookup_core/financial/qualification_states.py` owns only the five original
   qualification result labels. Policy explicitly exports those same objects, while
   precedence imports `QUALIFIED` without loading policy, evidence bridge or historical
   correction. Evaluation rules, evidence replay and thresholds remain policy-owned.

All three owners import only stdlib or the unchanged E5 heading normalizer. They load
without extraction, acquisition, admission or policy execution. Root imports keep their
existing eager/lazy timing apart from loading these pure leaves. Existing mutable row
policy and ordinary from-import bindings remain shared; rebinding one module's export
does not broadcast assignments. Pure helper globals belong to the lower owner.
`EvidenceSpan` has its honest new module location; legacy imports/unpickle class lookup
resolve to that exact class. New pickle bytes are not claimed equal; no pickle consumer
or historical financial artifact uses them. JSON, citation/envelope identity and frozen
dataclass semantics are preserved; no module-name spoofing is used.

## Financial and source preservation

Period/currency/unit recognition, source-domain/issuer binding, assurance, physical
document integrity, immutable registration, OCR geometry/execution and native parsing,
knowledge/cutoff gates, append-only publication, overlay conflicts, valuation/citation
eligibility and current-versus-historical semantics remain unchanged. NFD literal labels
are distinct from E5 NFKD headings. No OCR numeric repair, missing label inference,
consolidated/standalone mixing, inferred annual winner, Q3 opening or invented values.

Frozen V1 feedback sources, offline-only E4 V2 input set, E2/E3 source pins, provider
bundle, Technical/Volume V1, E5 foundations and financial registry/legacy row pins remain
byte-preserved. Changed unbound library hashes are recorded honestly. No old digest is
returned for changed bytes; no historical records or identities are recomputed.

## Graph qualification and remaining component

Use the identical E0 analyzer/settings. Preserve before/after sources and graph;
record exact eager/runtime membership, backward/core-to-root edges, fan-in/out and
dynamic/unresolved sites. No analyzer, sealed baseline, policy, relocation or
grandfathering relaxation. Removed return dependencies:

- Filing admission → OCR row predicate; filing → interim ingress conflict tuple.
- Interim ingress → OCR row predicate; historical correction → OCR row predicate.
- Precedence → qualification policy status; precedence → filing metadata status.

Restoring those exact accepted-source dependencies must recreate the ten-module
financial SCC and original cyclic participation. The Daily ten-module component and
eager SCC must be identical. E5's historical 26/65 restored-cut proof is preserved
against immutable E5 source, while the live negative control still requires the
event-cycle restoration to worsen coupling. Legitimate E6 financial reductions must
not be forced to recreate unrelated old cycles merely to satisfy a historical number.

The remaining four-module component joins refresh, native PDF evidence, precedence
and document registration. Its edges include actual source replay/admission and
refresh's cohort-bound metadata/fact adapters. Extracting those adapters now would
require moving period/unit recognition and entity-family policy too, or introducing
new lower-to-root dependencies. Keep those contracts intact rather than add policy
exceptions or an artificial injected service bundle. No frozen seam is crossed.

## Validation and release

Freeze accepted E5 source and execute identical owned synthetic fixtures in separate
processes before/after edits. Verify metadata envelopes, literal rows, period/scope/
currency/unit conflicts, assurance, extracted facts, retained registration, malformed/
missing source and PIT/use gates, serialized bytes and hashes. A separate isolated,
pinned optional native-parser tier must include physical hash/parser/registration
positive and failure cases; the ordinary hermetic tier retains explicit parser-absence
failure checks. Synthetic documents are clearly test-owned, never official evidence.

Test shared exports/class/mutable identity, legacy and lower patch points, both import
orders, import isolation, original-library result/error parity and restored-cycle
negative controls. Run affected, E1 layout, E4/E5, launcher/call-shape, CI-equivalent
hermetic, retained-accounting and native checks. Missing retained fixtures must be
reported separately; never regenerate evidence or weaken containment/tests.
Validated clean implementation checkpoint precedes native local closeout and its
documentation commit. Hosted CI and separate Owner exact-HEAD merge review remain
release gates. [Acceptance](e6_financial_boundary_acceptance.md).
