# Phase C whole-pipeline resource architecture closeout V2

Candidate-local continuation from `8ca12295a47a09a8fafb8055312a9a9f06cbff2e` on
`perf/post-first-real-daily-phase-c-resource-simplification-20261006`.
Owner override: `POST_FIRST_REAL_DAILY_PHASE_C_WHOLE_PIPELINE_RESOURCE_ARCHITECTURE_CLOSEOUT_V2`.
Authority effect: **NONE / RESOURCE_AND_RUNTIME_SIMPLIFICATION_ONLY**.
Canonical main remains `802b11e00a2bb38db7f57644dca9f3ba463e1522`.
No production Daily, provider acquisition, publication, push, merge, deployment, runtime DB
write, historical T0/capture/marker replacement or authority promotion is authorized/performed.
All diagnostic files are outside the repository in the host-local Phase C scratch namespace.
The local checkpoint introducing this report is recorded by the roadmap `HEAD` sentinel.

This extends the [V1 resource map, inventory and parity record](POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_SIMPLIFICATION_20261006.md).
V1 remains an intermediate proof; its 4.15-GiB Producer result is not substituted for a
whole-pipeline measurement. The final measured qualification is appended below.

## Lifetime graph and memory model

**Process peak is not file size or an exact sum of Python deep sizes.** Boundary private-byte
deltas include allocator/runtime effects; shared leaves prevent adding independent graph
estimates. Every individual family below has its exact disk path/size in the host-local
`v2-disk-inventory.json`. Combined graph contributions are measured at actual stage boundaries.
No expensive `gc.get_objects` traversal or blanket production GC is introduced.

| Family / source size | Creation → owner/reference → last consumer → release; duplication |
|---|---|
| Market exact snapshot 301,423,666 bytes | Acquisition → `acquisition.snapshot` and kernel `snapshot` → T0, tiered bundle and final record metadata → Daily return. IID independently reads another exact-session graph inside its builder; final rehearsal intentionally holds the acquired original concurrently. UTF-8 decoding has a temporary string/byte cost. |
| Descriptive; screening; tactical; triage | Level2 → retained files, local enrichment inputs and `operation.inputs` → current products/delivery → builder locals or final returned Producer graph. Repeated reads are legitimate distinct call seams but extend concurrent residency. Frozen input reconstruction uses exact retained paths; no provider call. |
| Fundamentals; valuation; catalyst; Corporate Intelligence | Level2/Financial V2/CI → local input contexts, evaluated valuation/compact financial products, operation inputs and IID evidence axes → IID/product/delivery → locals die, embedded/shared decision context remains. Source-specific scalar/context projections remain unchanged. |
| Historical context 162,517,852 bytes; financial momentum; corporate events | Enrichment → `enrichment[name].artifact` → IID, tiered handoff, presentation → Daily return. Rehearsal holds these from before IID construction, and shares historical context with the builder exactly as the kernel does. |
| IID 1,394,317,136 bytes | `iid.build_artifact` → enrichment artifact, `integrated_delivery`, operation binding → Brief, delivery, T0 and handoff → Daily return. V1 removes the full canonical Unicode/UTF-8 aggregate and redundant operation deepcopy. No extra process-boundary transfer is added. |
| Operation; scenario 61,034,195; strategy 25,202,384 | Producer → `producer_result.operation` and kernel `operation` → runtime staging, T0, handoff, presentation → returned record. Borrowed analytical leaves share IID; only manifest/output/binding spine is writable and copied. Public result contract is preserved. |
| Daily Brief 2,778-byte presentation; retained wrapper | Pre-seal builder → integrated binding and manifest declaration → delivery/index verifier → operation return. Compact deterministic status/index binding, not a universe graph copy. |
| Delivery primary 25,107,987; NDJSON 474,852,112; cockpit 1,642,365 | Delivery → local byte payload → operation files, manifest digests and `_verify_delivery` → Producer returns without bytes. V1 per-row UTF-8 buffering avoids universe Unicode buffers; header-only cockpit avoids a second overlay. Source and destination necessarily overlap while building contractually required bytes. |
| T0 1,487,255,738 | Retention builder → `prospective_decision_snapshot.artifact` → seal/index, T0 Thesis and handoff → returned detail. Nested IID leaves are shared; per-ticker T0 wrapper is shallow. Rehearsal constructs diagnostic content only under scratch and compares original identity/raw bytes; retained historical T0 is never replaced. |
| T0 seal/index and receipt | Snapshot writer callback → small index/reference → Thesis/Flow/readiness/reporting → compact references. Index equality is exact; scratch receipt fingerprint intentionally describes the scratch file, not the original filesystem inode/time. |
| Thesis T0/current cards/views | Existing bounded child → per-record SQLite staging/adapter/reducer → compact NDJSON + <64-KiB parent result → child exit releases pages. T0 cards/views 17,397,698/21,443,002; current 22,477,225/45,237,436 bytes. Existing process boundary is retained. |
| Feedback pre/post 546,784,419/583,618,622 | Existing contained streaming child → bounded records/price indexes/spools → retained output + compact result → child exit. Parent retention tiny; production child peak commit 598,679,552/607,027,200 bytes. No corpus graph crosses back. |
| AI bundle/handoff verification | Owner loads retained IID, canonical Brief and scoped product → expected overlay projections and streaming NDJSON comparison → function return. Owner process is a separate lifetime from Canonical child. Real consumer validation is measured separately; no publication occurs. |
| Signal velocity 285,614,098 | Registry → exact handoff/operation → every qualified T0 → observer histories/output → write/summary → return. **Corrected:** source records are verified one at a time and reduced to seven axes before advancing. Full T0 list no longer exists in the production root builder. Result histories remain necessary for exact categorical trajectory counts. |
| Foreign flow/divergence/VolumeFlow | Retained observer/runtime evidence → current small views and velocity artifact → tier1/Thesis current/presentation → local return. Modern Flow consumes compact verified T0 index. Source VALUE facts remain non-voting/POST. No network collector is run in rehearsal. |
| Opportunity queue; workspace 187,176,312; screener 7,531,514; presentation state | Existing product and post-handoff projections → source/operation manifests and dashboard consumers → files/compact references. Non-voting views overlap IID semantically but remain required products. Sealed operation/run copies remain intentional audit boundaries. |
| Action Center | Owner completion/handoff provides session/operation/path bindings; portfolio-aware resolver reads operation-bound IID → scoped owner decision → local return. No full Canonical child result is transferred to Owner. Existing measured Owner high-water is accounted separately; investment labels and sizing contracts are untouched. |

Production stage order/timings and the two long historical silent intervals are retained in
the V1 map. October 6 acquisition is ~812 s, pre-feedback 156 s, tactical shadow 252 s,
observer/handoff silent interval 881 s, post-feedback 134 s, Canonical total 3502.230 s.
The 1190.803-s enrichment/Producer/T0 interval and 881.135-s observer interval cannot yield
historical instruction-level attribution. The V2 rehearsal supplies deterministic boundaries.

## Residual defect, T0 consumers and hashing/copy audit

The safe `8ca12295` baseline observer failed in **182.498 s**, private peak
**6,480,252,928 bytes**, under the unchanged 7-GiB process ceiling. Trace:
`build_from_retained_root → discover_retained_snapshots → _load → Path.read_text →
UTF-8 decode → MemoryError`. Earlier parsed snapshots remain retained in `qualified` while
later T0 text is decoded/parsed. This is a causal residual allocation proof, not a guess from
large file sizes. Failure was reaped with confirmed tree termination; its peak is a lower bound.

| T0 consumer | Classification and treatment |
|---|---|
| Production signal velocity | **LEGACY_OVERREAD → STREAMABLE.** Verify complete snapshot and per-record canonical hashes, keep only `_axis` outputs. Original source paths/qualification reasons/identity remain. Full public discovery is retained for explicit offline callers. |
| Production pre/post feedback | **STREAMABLE, already bounded.** Raw source SHA receipts bind exact source bytes/code; re-streamed records verify proof/use binding. Compact exact price indexes. Existing legacy in-memory CLI is FULL_CONTENT_REQUIRED/reference-only, not the Daily default. |
| Thesis T0/current | **STREAMABLE + INDEXABLE.** Modern seal receipt/index lookup and one-record child staging. Stage1 whole-snapshot validator is an offline reference; ordinary production never calls it. |
| Modern VolumeFlow V2 | **INDEXABLE.** Compact verified seal bindings; no full T0 parse. Historical V1 fallback is legacy full content, outside new production cohort. |
| Foreign-flow enrichment / divergence | **IDENTITY_ONLY or no T0 consumer.** Uses retained foreign observations and velocity projection; does not reconstruct sealed decisions. |
| Capture acceptance/readiness/host preflight | **IDENTITY_ONLY / INDEXABLE.** Compact capture, marker, receipt and fingerprint verification; explicit recovery is STREAMABLE. Host preflight stats file sizes, never parses payloads. |
| Presentation/Owner reports | **SUBSET_ONLY / IDENTITY_ONLY.** Thesis focus reads bounded cards; reports verify NDJSON. Other `validate_snapshot` names in dashboard/qualified research refer to different snapshot contracts, not immutable prospective T0. |

`_project_snapshot` never publishes a replacement T0 or cached authority. Root/record keys
must be sorted unique; duplicate, malformed and trailing JSON fail closed. The original
snapshot hash excludes only `snapshot_identity`; every row hash excludes only its row ID.
Hash validity, contract/session, exact handoff/source/operation qualification are separate
checks. A private `axis_projection` flag sits on the discovery item, not on an untrusted T0
record, so an extra immutable row field cannot spoof the projection route.

Heavy hashing classification:

- IID artifact canonical aggregate: **ALREADY_FIXED** by V1 record-wise digest; decision-level
  hashes remain per ticker and strict JSON semantics remain exact.
- T0 build/validate/record/index hashes: **STREAMABLE**. `_hash(dict)` now uses the same
  record-wise canonical digest, replacing slow whole-graph `iterencode` without a large string.
  Other value types retain the old bounded encoder. No validation is silently skipped.
- Velocity result list hash: **STREAMABLE**, preserving list order one record at a time.
- Velocity pretty serialization/readback: **REDUNDANT construction temporaries**, replaced
  with the existing bounded native-newline encoder and exclusive immutable file publication.
- T0/velocity pretty emission: **STREAMABLE record-sized encoding**. Standard indent=2
  encoding and native newline translation are preserved exactly, with one record's text
  rather than Python per-token byte batching or a whole-universe string. Metadata stays
  field-bounded. Empty/list/mapping/nested/Unicode/float cases match the stdlib oracle.
- Warm T0 comparison: **REDUNDANT temporary write** removed. Existing bytes and newly
  encoded expected bytes are SHA256/size compared under before/after stat checks; exact
  callback behavior and immutable conflict are preserved. No identity-only cache is trusted.
- Operation/Brief/compact manifests: **REQUIRED small hashes**, unchanged.
- Legacy full CLI/reference builders: **REQUIRED for their explicit APIs**, not mechanically
  rewritten; they remain distinct from the bounded production route.

Large-copy classification: V1 whole-operation deepcopy was redundant; manifest/output spine
copies are required; per-ticker scoped delivery copies protect mutation; sorted ticker keys
are bounded by 1683 identifiers; velocity histories retain small axes rather than decisions;
T0 shallow decision wrapper preserves all known-at content with shared leaves. No global cache
or TTL is introduced. Existing feedback caches bind source bytes plus code digest; changed
verification code therefore cannot reuse an unqualified old proof.

## Audit of the intermediate checkpoint

V1 remains safe to keep. Incremental canonical hashing matches stdlib float/Unicode/exclusion
semantics, and the final audit adds stdlib fallback for non-string JSON keys (outside the
artifact schema) instead of hashing an invalid unquoted key. Mixed-key errors remain stdlib
errors. New tests reject whole-artifact/records-map encoding on the valid universe path.
`canonical_bytes` calls the same stdlib `JSONEncoder.encode` accelerator for one member;
it is not a custom numeric/string codec.

Binding changes only independent manifest/outputs/binding objects; analytical leaves are
borrowed read-only, consistent with the existing build/binding APIs. Exceptions cannot mutate
the supplied manifest. Concurrent independent bindings share no writable spine. Delivery
buffer construction is local; exceptions discard buffers before any caller publishes files.
Sorted ticker order and byte interface remain exact. No hidden partial-write state is added.

The new velocity writer creates/fsyncs a temporary sibling, atomically hard-links it without
replacement, compares a competing destination in 1-MiB blocks and always cleans the temporary.
Identical concurrent writers reuse exact bytes; conflicting bytes raise the standing
`IMMUTABLE_ARTIFACT_CONFLICT`. Other atomic writer APIs are unchanged. Failure/cancellation
before link never exposes a partial destination. Windows hard-link behavior is exercised in
tests and the real scratch rehearsal.

## Process-boundary decision

IID, delivery and fresh T0 share the same nested decision graph. Moving one into a child would
require a multi-GB full graph transfer or a new file-handle/result contract and additional
parse/serialization work. The measured bounded live set after correction does not justify
that invasive change. Existing feedback and Thesis child boundaries already return memory
to the OS and pass only compact status/path/identity results. Observer streaming removes the
unneeded input graphs before considering isolation. No distributed architecture or new
production entrypoint is introduced.

Diagnostic boundaries measure object death, explicit `gc.collect` and a one-second idle
boundary; isolated observer comparison measures process-lifetime reclamation. Collection is
not added to production without a demonstrated material benefit. The final measurements
below determine whether allocator retention is material after logical release.

## Rehearsal scope and limitations

Contained sequence: frozen acquired/enrichment owners → **actual IID builder** over frozen
upstream products → actual identity/Brief binding/delivery → diagnostic T0 construction/write/
seal index → actual retained signal-velocity root builder and immutable writer → reference
deletion/GC/idle. Frozen products replace acquisition/Level2 recomputation only; source identities
and investment content are exact. All outputs are scratch-only. No capture/first-marker builder
or production orchestrator is called. Fresh source acquisition has a separately retained
1,688,571,904-byte production peak; its native/network latency is not benchmarked offline.

The first V2 diagnostic runs established IID/output parity but had weaker lifetime ordering;
they are explicitly **ablations**, not final whole-heavy-path proofs. The final run holds
original acquisition/enrichment graphs from before IID and retains IID/operation/T0 through
the observer, matching the kernel's documented ownership. It includes an independent second
exact graph in the IID builder. No memory ceiling was raised after failed baselines.

All runs use the existing Windows Job guard, hard per-process 7-GiB private ceiling, total
deadline (1200 s for baseline observer; 1800 s for whole path), whole-tree termination/reaping.
Production source and output/result paths are separated by the runner. No high-frequency
sampling, expensive production instrumentation or borrowed virtualenv is used. RSS/private
high-water, boundary host available commit/physical and process IO are distinct metrics.
Host commit includes unrelated applications; process IO includes proof rereads, not disk-only IO.

Real consumer qualification runs separately under the same containment: Owner completion,
M1 sealed operation/IID/Brief/index/primary/full-universe verifier and both Thesis reports.
Runtime bundle is read-only using the canonical Owner's configured path; no release is staged.
Unchanged feedback/Flow/foreign integration is covered by focused compatibility suites and
retained lineage references, rather than launching network/runtime writers.

## Disk growth and retention proposal

Explicit Oct 6 families/current-session Level2 sibling inventory: **8,645,330,817 bytes
(8.65 decimal GB / 8.05 GiB)** across unique paths. Shared older sources, runtime database,
raw lake, global feedback proof cache and run logs are excluded. This is a concrete major-family
footprint, not a whole-host storage census. Physical copies count separately even when equal.

| Storage class | Bytes | Meaning |
|---|---:|---|
| AUTHORITATIVE_REQUIRED | 2,100,859,560 | Exact evidence, original T0, capture/index/write receipts; never rebuild from later knowledge. |
| DERIVED_REGENERABLE | 4,945,991,636 | Versioned analytical products and operation files, conditional on exact source/code/cutoff restoration. Classification does not authorize deletion. |
| Presentation/observer derived (includes PRESENTATION_CACHE candidates) | 1,598,479,621 | AI/lookup/Thesis/workspace/observer views; existing retained audit boundaries still govern. |
| TEMPORARY | Not persistent session evidence | Rehearsal outputs/spools; separately inventoried outside production. No cleanup performed. |

| Additional sessions | Flat current-footprint GB | Growth sensitivity GB |
|---:|---:|---:|
| 20 | 172.91 | 187.16 |
| 60 | 518.72 | 651.47 |
| 120 | 1037.44 | 1572.94 |
| 250 | 2161.33 | 4495.71 |

Flat projection is `8.645330817 * N`. It underestimates cumulative full-corpus feedback and
history-observer output growth. Sensitivity adds **0.075 GB * N*(N-1)/2**, an explicit estimate
from two feedback increments (~0.058 GB per additional 1683-row cohort) plus velocity history
(~0.017 GB), assuming stable average row size and retained cumulative output each session.
These are planning scenarios, not empirical scaling laws or retention commitments.

Separate future policy proposal: preserve authority-required originals/receipts; consider
verified cold archival of completed immutable cohorts; permit derived regeneration only
with exact source bytes, code digest, cutoff and restore parity; distinguish owner handoff
retention from disposable presentation caches; set a scratch quota. Any TTL/deletion requires
an explicit owner decision and restore validation. **No deletion, deduplication or policy
implementation occurs in this milestone.**

## Prospective learning terminology and state

Cutoff `2026-10-06T16:00:00Z`: 2 contiguous complete captures, no gaps, `DEPTH_PENDING`.
589 tickers depth2 / 65 depth1 / 293 depth0; 857 SOURCE_NATIVE_SCALE_CONSISTENT tier.
Depth20/21/50/60 needs 18/19/48/58 more complete captures for the depth2 cohort. Tier is not depth.
Post-marker T0: 2 available. Entire namespace: 21 paths, 20 nonempty, 1 zero-byte Oct2 failure;
19 distinct sessions, 18 nonempty. Legacy: 17 distinct pre-marker sessions, 16 nonempty;
two extra September11 family copies do not add sessions. All original bytes remain immutable.

Governed capture identities:

- Oct5: `prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d`.
- Oct6: `prospective_capture_complete_session:efbffc15931cd6dd7515ec070bf7c66347164079816a25e76256927a8b1a6682`.

The chain is defined by these validated capture records plus exact calendar evidence at the
cutoff; no invented standalone chain authority ID is added. Its calendar source identities
and projected windows are recorded in host-local `v2-maturity.json`.

| Cohort | Projected T5 / T10 / T20 trading sessions | Additional sessions T5/T10/T20 |
|---|---|---|
| October5 | October12 / October19 / November2 | 4 / 9 / 19 |
| October6 | October13 / October20 / November3 | 5 / 10 / 20 |

Dates are governed-calendar projections conditional on future completed evidence, not civil-day
maturity. New cohorts have zero mature T5/T10/T20 outcomes. Oct5 original T0 remains available
but its later rerun handoff lineage mismatch excludes it from current post-feedback admission.
Oct6 has 857 pending and 826 missing-close rows at each implemented horizon.

Retained legacy outcomes: T5 **10,338 mature rows / 15 decision-session cohorts**; T10
**6,544 / 10**; T20 **16 / 1 (September3)**. Cohort dates are preserved in the V1 appendix.
Current `integrated_decision_prospective_feedback/v3` genuinely implements
`forward_close_return_1/3/5/10/20`, counted through governed trading-session continuity.
T5 is also the named legacy summary/diagnostic alias (`horizons.T5`, mature_T5 sample,
close MFE/MAE and false-transition review). T10 is a real forward-close horizon even where
the old summary does not expose a named `horizons.T10` alias. Neither is merely a historical
label, and elapsed time alone cannot cure missing/price-incompatible evidence.

T60 is registered by capture/durable-case contracts but **not emitted by the forward feedback
engine**. The capture calendar projects Dec29/Dec30 for Oct5/6 T60; this is informational only,
not a promised implemented product. New chain has at most1 future capture, retained legacy
feedback chain22 sessions/max21 future; no current T60 window is mature. Learning/calibration
policy, non-voting status and official RAW/PIT/CA/listing blockers remain unchanged.

## Validation, protection and checkpoint

Focused retention/velocity/identity checks include full-versus-streamed axes equality,
Unicode/non-ASCII/exponent/negative-zero/numeric-key parity, no whole-universe identity encoding,
immutable per-record/hash/session/handoff rejection, duplicate/unsorted/trailing/broken JSON,
projection-spoof rejection, binding-spine ownership, native output bytes, concurrent reuse,
immutable conflict and partial-write cleanup. V1 delivery parity is re-proven on real evidence.

Broad identical 15-suite selection: candidate **440 passed, 8 failed, 10 errors**; exact
`8ca12295` **428 passed, 8 failed, 10 errors**. Same18 missing-retained-fixture node IDs and
failure/error classifications; candidate-only regressions zero. New tests account for pass
delta. No fixture fabrication, unrelated repair or production runtime writes.
Final focused integrated/feedback/retention/Thesis/acceptance checks **250 passed**;
later edge-case components **79 passed** (overlapping selections, not additive unique coverage).
Later focused additions and final roadmap/compile/diff results are recorded at checkpoint.

Protected evidence uses streaming raw SHA256 before/after, including Oct5/6 T0/capture/first
marker/seal/write receipts, completed registry, benchmark source files and feedback/Thesis
consumer lineage. Final proof is reported below. Machine-specific raw diagnostics are not staged.
No historical evidence family is renamed, replaced, deleted or newly granted authority.

## Final qualification and terminal disposition

**RESIDUAL_PEAK_CORRECTIVE_READY**. Recommendation **MERGE_CANDIDATE_AFTER_REVIEW**.
The residual full-T0 observer accumulation is proven and corrected. Current retained heavy
path and actual separate Owner consumers complete under unchanged containment. This closes
the authorized candidate-local resource investigation; no automatic next milestone, live
launch or policy/authority promotion follows. Fresh host preflight remains mandatory.

### Before / intermediate / final

| Evidence / code | Wall seconds | Peak metric and bytes | Interpretation |
|---|---:|---|---|
| October5 initial production | Failed later tier bundle | Canonical RSS10,687,537,152 | Historical observed high-water; no instruction-level allocation trace. |
| October5 successful production rerun | 1700.479 Canonical | RSS10,985,897,984 (10.23GiB) | Warm/reused acquisition; cannot compare as fresh latency. |
| October6 fresh production | 3502.230 Canonical | RSS10,666,430,464 (9.93GiB) | Successful historical whole run; 1683 IID rows. |
| Exact802b11e full Producer | 142.206 to failure | Private6,734,299,136 (6.27GiB) | MemoryError at full NDJSON join/encode under7GiB; lower bound. |
| V1 hash/copy-only intermediate | 121.503 | Private6,850,965,504 (6.38GiB) | Completes; delivery aggregate Unicode remains. |
| V1 final8ca12295 Producer | 143.585 | Private4,452,204,544 (4.15GiB) | Five outputs byte-identical; Producer-only scope. |
| Exact8ca12295 observer | 182.498 to failure | Private6,480,252,928 (6.04GiB) | MemoryError decoding next T0 with prior full graphs retained; lower bound. |
| V2 strict-live fresh-write reference | 678.788 | Private4,322,533,376 | Actual IID/delivery/T0/index/observer; acquisition owners held from start. Earlier slower record writer; no final downstream ingress. |
| Final V2 strict-live heavy path | **495.979** | **Private4,324,007,936 (4.03GiB); RSS4,058,824,704 (3.78GiB)** | Stable guarded code; warm scratch T0 verification, full actual delivery buffers/parity, observer and two downstream parse/hash passes. |
| Final actual Owner completion/handoff + Thesis reports | **81.467** | **Private5,913,817,088 (5.51GiB); RSS4,941,590,528 (4.60GiB)** | Separate process lifetime after Canonical exit; no publication/runtime writes. |

RSS and private commit are different metrics. Do not subtract historical RSS from candidate
private peaks or claim a production runtime speedup from these retained single runs. Final
495.979s is the heavy-path Job wall including proof IO. Its child elapsed493.799s includes
actual IID77.631s, identity13.097s, binding0.001594s, delivery37.788s, T0/index98.279s,
observer build/parity174.366s plus writer/ingress/proof boundaries. T0 was already present
in scratch and streaming-verified; delivery was built and compared without writing another
persistent copy. The preceding strict-live fresh-write reference independently proves fresh
atomic emission and identical T0/index/velocity bytes; unit faults cover the final codec's
fresh-write failure path. These are not separate claimed fresh production Daily times.

102 protected heavy-path input files total **7,783,101,439 unique bytes**. Process logical
IO delta: **30,372,815,832 read /285,885,133 written bytes**, including protected-source
rereads, immutable velocity temporary write and progress/result IO. Actual physical disk
IO and OS cache hits are unmeasured. All10 code/driver SHA256 guards are unchanged before/
after this final run (Python3.13.12, Windows64-bit). Complete result records the exact hashes.
Containment:7,516,192,768-byte per-process private cap;1800s total deadline; exit0; no reason
code; non-degraded Windows Job; immediate child reaped and tree termination confirmed.
`CHILD_RESULT_OVERSIZE` in the guard's compact inline summary means it did not inline the
large diagnostic JSON; the separately retained result is complete and independently read.

### Live-set boundaries, allocation and release

| Boundary | Elapsed s | Private bytes | Ownership / change |
|---|---:|---:|---|
| Before input reconstruction | 36.7 | 323,624,960 | Python/driver/proof baseline. |
| Acquisition/enrichment owners live | 41.7 | 1,194,315,776 | +870,690,816 for exact/history/momentum/events; aggregate resident expansion≈1.88 times≈464MB sources. |
| Frozen IID inputs live | 52.3 | 2,542,882,816 | +1,348,567,040; retained upstream products coexist with originals. |
| Actual IID constructed | 130.0 | 3,381,432,320 | +838,549,504; builder's second exact graph exists during build; leaves shared. |
| Upstream locals deleted | 130.2 | 3,366,318,080 | Only15,114,240 returned because needed leaves remain in IID. |
| IID identity completed | 143.3 | 3,370,688,512 | No universe canonical string; largest recorded IID canonical string1807bytes across2258 calls. |
| Before/after binding | 150.3 | 3,374,714,880 | No measurable boundary increase; borrowed leaves, writable spine only. |
| Delivery built | 188.1 | 3,878,404,096 | +503,689,216 while required≈501.6MB output bytes coexist; RSS high-water set here. |
| Delivery references deleted | 189.5 | 3,375,681,536 | −502,722,560; buffers die before T0/observer. |
| T0 built | 217.5 | 3,379,224,576 | Shallow wrappers share IID; file1.487GB does not imply another1.487GB graph. |
| T0 existing bytes verified | 251.2 | 3,379,478,528 | Record emission/hash without aggregate Unicode or temp T0 copy. |
| Seal verified | 287.7 | 3,379,507,200 | Compact index; no full snapshot reread graph. |
| Velocity built | 456.6 | 3,376,902,144 | Full input graph list absent; one source record plus compact axes/output. |
| Observer released / GC | 467.6 /469.6 | 3,377,430,528 | No material boundary change at this scale. |
| Downstream parses and verifies0/1 | 472.2–479.4 | ≈3,377,455,104 | Retained285.6MB velocity fully parsed twice, one at a time; incremental canonical validation. |
| Tail graph references deleted | 479.4 | 3,375,759,360 | Caller still retains analytical roots. |
| All analytical roots deleted | 480.5 | 1,329,229,824 | −2,046,529,536 bytes (1.91GiB): live graph ownership dominates. |
| Explicit GC | 480.5 | 1,326,125,056 | Only3,104,768 more bytes;125 objects collected. |
| One-second idle | 481.5 | 1,326,149,632 | +24,576, no further material return. |

These are process-private deltas, **not exact independent Python deep sizes**. Transient
private high-water can exceed a logged boundary (Job final4,324,007,936). Residual1.326GB
contains allocator/native/runtime/newly imported module memory above the initial baseline;
the exact split is unmeasured. It does not set the peak and Canonical exit releases it before
Owner work. No unsupported assertion that the entire remainder is pymalloc fragmentation.
Process isolation of velocity would require a new transfer/result seam and preserve source
read IO; streamed inputs suffice for the measured current cohort. IID/delivery/T0 isolation
would transfer or reparse the same large immutable graph. Neither earns an invasive runtime
change at the measured current scale.

### Global peak owner and uncertainty

Highest **measured candidate** private high-water is the actual **Owner M1 completion/
sealed handoff verifier**,5,913,817,088bytes, before the `owner_m1_handoff_verified` boundary.
At that boundary private memory has already returned to397,807,616bytes. Thesis reports reach
399,781,888 and explicit GC358,752,256. This verifier consumes original IID/operation and
builds expected scoped/full-universe overlays while comparing exact delivery. Attribution is
at this stage, not an unrecorded individual allocation instruction.

Sequential whole-pipeline model: frozen acquisition/Level2 reconstruction and IID/delivery/
T0/observer live set → Canonical exit → separate Owner verification. Existing feedback
children add≈0.56GiB commit while Canonical baseline is live, **not** another full universe;
Thesis existing children similarly stage bounded rows and return compact results. No concurrent
sum of Owner and terminated Canonical is valid. Historical acquired-stage RSS1,688,571,904
and recorded feedback child commit598,679,552/607,027,200 remain accounted. Other unchanged
network/provider/presentation orchestration was not rerun; historical stage boundaries and
code lifetime review supply their model, not newly measured candidate peaks. Therefore5.51GiB
is the measured retained qualification envelope, **not a certified future live-host/global
commit ceiling**.250-session histories and future larger output cohorts require renewed
capacity evidence; current projection is not falsely described as constant memory forever.

### Exact semantic parity

- Actual IID construction:1683 records; `integrated_investment_decision_product/v1:ef756cbacdd88e6676ffb32670d3c515e7ad5e806e3c555d6c29a5ed4e2f2389`.
- Operation identity remains `daily_research_session_operation:e756b5b202b4338b08e958e21b1866aa3e36397773a2bc2751e1deec4652b26c`; binding shares read-only IID records.
- Original T0 identity `prospective_decision_snapshot:889139b902a14b229fcb201cfc4c7922e25fc7395c10a5576b0cc5f8dd769212`, raw SHA256 and every seal-index field equal. Diagnostic receipt describes scratch inode/time only; no original receipt rewritten.
- All five delivery raw hashes equal: primary25,107,987bytes; full universe474,852,112; manifest4641; Brief2778; cockpit1,642,365. Exact SHA256 values are preserved in the V1 parity table and final result.
- Signal velocity26,928rows/16sessions; `multi_session_signal_velocity:2b417cc05e5b27201ecfbba595f2f2fb99ef39d118fab56901c25c607f76d6f7`; canonical identity **and native raw bytes** equal retained production. Source inventory/session qualification/cohort counts unchanged. Two downstream whole parses reverify exact canonical content without aggregate string/bytes.
- Actual Owner completion succeeds forOct6; M1_BRIEF_AND_INDEX_VERIFIED;72 research contexts,10 owner-focus,1683 full-universe rows. Exact IID/Brief/current product authority bindings match original.
- Thesis t0 BUILT1683/partial0/unavailable0; current PARTIAL1683; every forbidden judgment/post-in-T0/flow vote/action-policy/state-card/duplicate-vote guard remains0. Existing current outcome limitations remain, without authority promotion.

Other feedback/foreign/VolumeFlow/Action Center behavior is unchanged and covered by retained
lineage plus affected suites. It is not claimed that network-dependent publication outputs
were freshly regenerated in this offline rehearsal.

### Patch risks and validation map

| Change | Reason/implementation | Material limit/risk and proof |
|---|---|---|
| Record-map/list digest | Avoid whole root strings; canonical per-record stdlib codec | Numeric keys outside schema fall back to stdlib behavior; strict nonfinite/Unicode/ordering/hash-exclusion tests and actual IID/T0/velocity identity parity. |
| Seven-axis T0 projection | Remove retained full T0 list at proven decode failure | Still validates every row/root and exact session/handoff/source/operation; malformed/duplicate/unsorted/trailing/corrupt data fail closed; offline full API remains. Projection-spoof and legacy oracle tests. |
| Bounded pretty emitter | Reduce per-token cost without universe text | One largest record may still be large; metadata field is field-bounded. Nested/list/empty/Unicode/float/native-newline byte oracle and real T0/velocity bytes. |
| Warm T0 comparison | Avoid redundant1.487GB temp write/fsync on reuse | Full expected emitted bytes and existing raw SHA/size, before/after stat; no identity-only reuse. Warm no-temp/no-fsync/callback/mtime test; fresh fsync-failure still retains original and exposes no partial target. |
| Velocity immutable writer | Replace whole serialization/direct write with fsynced sibling+exclusive hard link | Requires ordinary local filesystem hard-link support; unsupported filesystem fails closed. Identical concurrent reuse, conflicting writers, injected mid-encoding failure/temp cleanup and real Windows publication. |
| Flow/divergence ingress digest | Eliminate full velocity canonical Unicode/UTF8 aggregate | Same full body validation and exclusions; actual downstream hash passes, Flow/foreign/VolumeFlow integration suites. |
| Rehearsal tooling | Make live owners, stage peaks, deletion/GC/idle and source protection reviewable | Scratch-only diagnostic; does not replace production orchestrator. Exact guarded code hashes and explicit ablation exclusions. |

V1 copy/hash/delivery changes were audited independently and retained. No source, scoring,
posture, sizing, investment policy, historical T0 or threshold contract is simplified away.

### Host disk and retained scratch

Read-only final host preflight records C: available18,664,632,320bytes (17.38GiB), below unchanged
25GiB READY disk floor: **AMBER** (no active writer observed). Commit/physical dimensions
are READY; this point-in-time result does not authorize launch. No files deleted or auto-cleaned. This is a host admission
condition, distinct from corrective-code review readiness. Scratch contains intentionally
retained original/intermediate detached code, diagnostic T0/delivery/velocity outputs and
JSON/XML proofs; it is not counted as production evidence or committed. A cleanup/archive
choice requires separate explicit owner authorization; no permission flow is manufactured
here because no cleanup is attempted.

### Evidence paths and local checkpoint

Host-local exact Phase C namespace: `tmp/phase-c-20261006` beneath the owner's workspace.
Final heavy-path `v2-whole-qualified/final-result.json` and `containment.json`; preceding fresh
strict reference `v2-whole-qualified-ablation-result.json`/`-containment.json`; actual consumers
`v2-consumers/result.json`/`containment.json`; baseline observer `v2-baseline-observer/`;
final isolated observer and final protected verification/test-equivalence proofs below.
These paths are navigation to local diagnostics, not portable authority/source contracts.
Portable runner is `tools/run_phase_c_resource_rehearsal.py --stage whole` with explicit
source/code/output/result paths; source and output paths must not overlap. Existing V1
command template remains valid. Isolated `--stage observer` and `--stage consumers` qualify
production root observer and actual read-only Owner/Thesis consumers respectively.

Local checkpoint: same branch/worktree; V1 checkpoint8ca12295 retained and one V2 final local
commit. Roadmap HEAD sentinel resolves to the report's introducing checkpoint. Exact final
commit SHA and clean-worktree/source protection checks are provided in the final handoff.
No push, merge, deploy, main modification or next milestone.

### Isolated observer, final tests and protected evidence

Final isolated observer (`v2-isolated-observer-result.json`, guard at
`v2-whole-final/containment.json`) completes in **211.765s**, peak private**636,239,872bytes
(606.8MiB /0.5925GiB)**, RSS high-water**432,648,192bytes**. Same26,928rows/16sessions,
canonical identity and native raw bytes. Private at build629,829,632; result deletion
389,320,704; GC377,765,888. Versus exact8ca observer failure6,480,252,928bytes, this is
90.18% below its observed lower bound, not a ratio against a completed baseline. Isolation
is diagnostic; no production process boundary was added. All source hashes remain equal;
exit0, non-degraded Job and confirmed child/tree reap. Its wall differs from parent-live
observer due to host/cache/proof conditions; no isolated speedup claim.

Final15-suite candidate: **442passed,8failed,10errors (167.90s)**. Exact8ca baseline:
**428passed,8failed,10errors (245.81s)**. Every18 nonpassing node ID and failure/error
classification matches; **candidate-only regressions0**. `v2-final-baseline-equivalence.json`
contains exact node IDs; all failures arise from absent retained fixtures in isolated code
checkouts. No retained fixture fabrication or main/source mutations were used to pass them.
Additional final writer/retention/velocity/Thesis/acceptance selection **160passed**; additional
atomic/Owner/Flow/VolumeFlow/foreign/portfolio suite **253passed**. Selections overlap and
are not summed as unique tests. Final control-plane and Phase C checks: **61 passed in46.64s**.

**141 distinct protected paths, mutation_count0, all_unchanged=true**, proved by streaming
SHA256 against the original16 immutable gate files and the before hashes from finalheavy
path/actualOwner/isolatedobserver. `v2-final-protected-verification.json` contains every path,
before SHA, after SHA and equality. This includes Oct5/6 original T0/capture/seal/write
receipts, first marker, completed registry, analytical inputs, legacyT0observer sources,
retained operation/delivery/runtime bundle manifest and both Thesis products. No runtime
DB is modified; this is a read-only retained verification. Legacy/prospective feedback
engine/input authority and maturity contracts are untouched.

Final code validation:10 changed Python/driver/test files compile; all10 benchmark code/
driver raw SHA256 guards still match the stable final whole-run bytes.
Git diff whitespace check passes. ROADMAP drift check PASS/ON_TRACK before checkpoint,
with expected dirty-candidate warnings; post-commit clean check is provided in handoff.
All tracked material is code/tests/portable docs and runners. Host-local diagnostic JSON/XML,
retained source data, worktree metadata and scratch outputs are excluded from staging.
