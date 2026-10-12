# E5 runtime dependency cycle reduction

Owner directive: attachment `52159840-ddf2-4d3c-bc6e-7e29d14338ff`, 2026-10-12.
Native admission: `E5_RUNTIME_DEPENDENCY_CYCLE_REDUCTION`, accepted main
`e9ee2fe135e9e529b60f11ab97f30fc6441e6e24` (E4 PR126). E4 post-merge Producer
CI38186488312 succeeded. Local design/implementation/test/checkpoint/closeout and
one feature PR/CI corrections are authorized. No E5 merge, Daily, provider calls,
deployment, production writes, evidence/authority promotion or V2 activation.
No successor starts automatically. Existing native governance remains authoritative.

## Selected ownership corrections

1. `evidence/corporate_event_temporality.py` owns `context_known_by`: exact existing
   observation and optional publication timestamp checks against an explicit aware
   cutoff. Empty/missing/malformed inputs and error semantics remain unchanged.
   Rollforward re-exports the same callable; current official event projection binds
   the lower owner lazily. Acquisition, date-directory selection, reuse/freshness and
   current-versus-frozen presentation remain in rollforward. Frozen Canonical callers
   retain their original source and legacy import surface.
2. `evidence/financial_document_text.py` owns the exact historical heading/assurance
   `_normalize`. OCR exports that same callable; assurance and period-negation checks
   import the lower owner lazily. The OCR engine and image/table evidence are never
   needed just to fold a heading. NFKD/apostrophe/accent/punctuation behavior is
   unchanged; this normalizer never receives values. The distinct NFD literal
   `_identity_fold` and mutable `ROW_LABEL_CONTRACT` stay in the original OCR module.
   No superscript numeric repair, assurance inference or row-label widening occurs.
3. `evidence/research_output_fields.py` owns only the existing Human/AI packet
   `FORBIDDEN` tuple. The packet exports that exact object, and Financial Currency's
   nested-field guard binds it without importing a decision producer. Other contracts'
   different prohibition sets are untouched. Capital/numerical decisions remain human.
4. `evidence/field_identity.py` owns the existing field JSON sanitizer, canonical JSON
   and stable SHA-256 helpers. `field_temporal_contract` retains exact compatibility
   exports and all temporal classes, mutable freshness RULES, gates and domain policy.
   Seven stable-ID-only core consumers bind the lower owner: official document
   qualification, current valuation inputs, P3F valuation, fundamental cohort scaleout,
   current portfolio risk envelope, prospective learning and current Daily research
   product. The multi-period panel still imports actual temporal types/policy and
   retains that architectural dependency honestly.

Field JSON converts float NaN to null and tuples to lists, permits other unsupported
values through `default=str`, and rejects float infinities. Mixed-key/error/Unicode/
negative-zero behavior and exact UTF-8 hashes stay unchanged. This schema is distinct
from E4 strict artifact JSON; E5 does not substitute one for the other, globally
consolidate JSON variants or materialize streamed artifacts as whole documents.

## Compatibility and identity boundaries

Exports are explicit; no star export, module-name spoofing, service locator, reflected
loader, fallback or lazy-import trick hides a dependency. The lower owners are stdlib
only and load without orchestration, freshness or domain builders. Existing consumer
lazy imports remain lazy; module-load imports acquire only pure leaf owners.
Functions/tuples are shared objects through their legacy exports. Existing rollforward
acquisition seams, OCR `_normalize` slot/row policy, field TemporalField stable-ID slot
and `cpc.level2` remain patchable. Ordinary `from` imports retain binding semantics;
rebinding one legacy alias does not broadcast assignments to independent consumers.
Helper globals now belong to their declared lower owner. Mutable policy objects and
exception classes are not copied or redefined.

The eleven V1 feedback input files, all E4 V2 source inputs, E2/E3 frozen source set,
provider worker bundle and frozen Technical/Volume V1/tactical owner remain unchanged.
The altered field helper module is outside those frozen source sets; its exact old
and new source hashes are recorded separately, and its execution is compared against
accepted E4. No old digest is returned to hide changed source bytes. V1/V2 digests
are recomputed using the standing construction, with no cross-version reuse or
production activation. No historical artifacts, receipts, manifests or sessions
are written, copied into an authority namespace or reinterpreted.

## Graph acceptance and remaining limits

Use the identical E0 analyzer/settings, including eager/lazy/dynamic edges. Freeze
accepted E4 sources and graph before editing. Model cuts first, then measure actual
source. Record removed inversions, internal edges, exact SCC membership, largest
component, total cyclic participation, fan-in/out and unresolved/unsupported loaders.
No sealed-baseline refresh, grandfathering expansion, relocation/admission exception
or analyzer weakening is authorized.

The initial 26-module SCC's relevant return edge is current official event projection
to orchestration solely for the cutoff predicate. The financial 12-module SCC imports
OCR from assurance and period recognition solely for heading normalization. Financial
Currency's two-module cycle imports the decision packet solely for a tuple. These
edges must be absent after migration; restoring them in a diagnostic graph must
restore original cyclic participation. Seven core-to-root field helper edges are
also eliminated rather than hidden.

Remaining feedback/calendar and legacy serializer cycles cross frozen V1 inputs;
Technical V1 verifier/dispatch and provider containment cycles have separate frozen
contracts/bundles. Financial extraction/admission and Daily orchestration retain
real consumer relationships. E5 does not rewrite these contracts to chase zero SCCs.

## Validation and closeout

Execute accepted E4 and candidate against identical synthetic primitives and consumer
fixtures. Cover public/new imports in both orders, callable/tuple/exception/mutable
policy identity, monkeypatch propagation, malformed/missing/naive/future inputs,
Unicode normalization, superscript/literal separation, NaN/default-str/mixed-key
canonical bytes/hashes, PIT/evidence gates and circular-import negative controls.
Run affected, E4 parity, architecture/layout/loader/launcher, production call-shape,
focused hermetic and retained-accounting selections. Never reconstruct missing real
retained fixtures. Baseline/environment failures are separate from E5 regressions.

CI adds E5 tests to its existing focused selection; E4's full-history checkout already
provides accepted baseline blobs. Only the reviewed workflow hash changes in the
launcher manifest, with no Daily command/target/Python launcher changes. Native local
closeout requires qualified scope and clean checkpoint; hosted CI and separate Owner
merge review remain release gates. [Acceptance](e5_runtime_cycle_acceptance.md).
