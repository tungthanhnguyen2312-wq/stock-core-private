# Original T0 reuse: versioned reader transition

Owner-scoped corrective `PROSPECTIVE_T0_REUSE_ORIGINATION_LINEAGE_CORRECTIVE_V1`.
Reader contract: `prospective_t0_origination_lineage/v2`. Snapshot, operation,
decision, seal, price and feedback artifact identity algorithms are unchanged.
This is local source validation, not production activation or authority promotion.

## Two identity sets

Ordinary same-operation snapshot/handoff admission keeps its existing strict
behavior. A mismatch is never waived merely because sessions or snapshot IDs match.
The additional route requires explicit `RETAINED / ORIGINAL_SESSION_T0_REUSED`,
one unambiguous handoff, its exact original snapshot path and identity, and the
original source identity carried in the existing snapshot reference.

Origination proof verifies the immutable snapshot and every original record using
the ordinary validator or its bounded streaming equivalent. The original operation
manifest must have a valid native content identity at its exact registered path,
same session, original completed-producer generation context, and an output binding
to the original Integrated Decision identity. The later handoff's own operation is
independently verified in the same domain and binds its own decision output. Their
operation and decision identities can differ; neither replaces origination identity.

The original seal/index/write receipt must verify using the existing native seal
hash domains, exact interface bindings, original source/operation and non-diagnostic evaluation scope. Each
snapshot record must match its sealed record identity, original operation, session
and source. Both ordinary and streamed validation verify the raw snapshot hash
against the original write receipt; streaming verifies source stability without a cache write.
Original selection follows the existing writer: a present valid capture record's
bound T0, otherwise exactly one sealed directory. Competing T0, ambiguous handoffs,
replay indexes, missing/corrupt proofs and arbitrary operation differences fail closed.
This read of a capture binding never completes a capture or changes its fitness.

Proofs are in-memory discovery metadata. No new authoritative layer, database,
manifest writer, seal, cache schema or historical artifact is introduced.

## Historical source verification and active execution

The unchanged `e2e3_frozen_sources.json` retains the original reader SHA256 pin.
`retention_reader_v1.py.txt` preserves those exact normalized source bytes from
released commit `28e2d0e8b991433df4bd14bbd0939464e1679463`; it is verification-only,
never imported by production. `retention_reader_transition_v2.json` binds that
original pin and the exact active reader source hash under a separate version.
No entry is added to the older reviewed-amendments escape hatch.

`tools/verify_retention_reader_transition.py` verifies both sides before providing
historical bytes. E4/E5/E6 conservation still compare original bytes to the immutable
Git base/pin; only this one file obtains its historical bytes from the verified
archive. Every other protected path retains its original checks. Legacy V1 and V2
closed-set digests are recomputed from the original archive plus unchanged inputs:

- V1: `fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46`.
- V2: `07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567`.

These values are asserted after computation, never returned as substitute hashes.
The unchanged E4 qualifier against the active tree reports its actual changed
source digests; those are not represented as the preserved historical versions.

Active `prospective_feedback_streaming.code_digest()` hashes the active reader,
as does `_verification_code_digest()`. The reader version and exact active digest
are exposed by the offline transition diagnostic. Existing cache paths/schema
remain unchanged: terminal reuse requires the exact execution code digest and
input identity; snapshot verification receipts require the exact verifier digest,
raw source hash and size. Thus both directions reject cross-version receipts.
There is no legacy adoption adapter or migration. A derived cache miss may be
rebuilt only by its existing authorized runtime path, not by this corrective on
retained production data. Settled outcomes use original T0/endpoint identities and
existing arithmetic; this transition changes neither price evidence nor maturity.

## Retained acceptance and limits

October 5 is inspected in place with bounded streaming, original source hashes
before/after, exact original/new operation manifests, original seal/index and
capture binding. The archived reader's rejection and corrected reader's result
are diagnostic projections, never replacements for retained feedback. Additional
qualified T0 decisions do not imply additional mature outcomes.

October 9 still lacks a terminal complete-session record. Its strict-chain gap,
all existing feedback rows, outcome arithmetic, horizon taxonomy, sample floors,
Daily paths, runtime, VRE leases and authority remain unchanged. No provider,
Daily, production write, publication, push, merge or automatic successor is allowed.
