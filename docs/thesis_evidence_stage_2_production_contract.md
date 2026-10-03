# Thesis Evidence Stage 2 production contract

Milestone: `THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION`.
Starting main: `d610db689c1f512b3363e86cdf005c248343f422`.
Authority: `NONE / NON_VOTING_THESIS_PRODUCTION_PROJECTION_ONLY`.
Projection binding version: `thesis_production_projection/v1`.

Stage 1 adapters, registry, reducers, conflict policies and retained acceptance are frozen.
The production child calls those exact adapters and reducers for one ticker at a time;
their internal offline/diagnostic scope remains intact. The outer production projection
is non-voting and never supplies a decision input, action, ranking or overall verdict.

## Seal bindings and evidence eligibility

`prospective_t0_seal_index/v1` retains the original authority model. Its read protocol
exposes snapshot/index/write-receipt identities and exact Integrated Decision and
Technical context membership. New snapshot writes additionally index decisions without
Technical context; such entries have null Technical fields and do not enter the existing
Flow Technical bindings. Existing indexes and snapshots are never rewritten.
Every ordinary read verifies the compact index, receipt and snapshot file fingerprint;
the receipt's original SHA binds the write boundary. No ordinary full-snapshot parse or
Stage-1 whole-snapshot validator is called. Explicit retained retry can stream the
original snapshot and independently verify its canonical identity/count.

Physical sealing, adapter `T0_SEALED` classification and axis direction eligibility are
three separate predicates. Integrated Decision items require exact decision identity
and the unchanged adapter basis policy. Exactly sealed `RETROSPECTIVE_ADJUSTED` Technical
1D evidence remains POST. Qualified synthetic `PIT_CA_ADJUSTED` can seal. Missing W/M
scaffolds can be classified T0 under Stage 1 while remaining UNKNOWN/non-directional.
Flow and foreign evidence remain POST and FACTS_ONLY in the Thesis adapter. Therefore
LONG T0 can have Fundamental/Valuation/Market-Sector evidence while SHORT T0 can remain
INSUFFICIENT_EVIDENCE. Those ceilings are expected evidence states, never actions.

## Boundary, process and products

Normal sequence: retained T0 → seal index → `daily_boundary`/first-marker logic → T0
sidecar attempt → handoff → velocity/foreign/price-flow/VolumeFlow V2 → current sidecar
→ existing outcome feedback. Both canonical kernel and post-close diagnostic share
the existing seams. The first marker is published before Thesis is attempted.

The parent invokes a retained-only child and reads a result capped at 64 KiB. Input
sources are verified, staged in temporary SQLite with a 2 MiB cache and 16 MiB member
limit, then processed per ticker. Technical contexts are individually verified. Source
file fingerprints must remain stable through staging/hash. No 244 MB Stage-1 session
artifact or duplicate evidence ledger is produced by Daily. No network/provider is
allowed in the child; calls/import attempts are blocked and counted.

`thesis_t0_view/v1` + `thesis_t0_card/v1` retain exact source identities, snapshot/index/
receipt bindings, registry/matrix/card/record identities, independent lenses/anchors/
axis states, conflicts/counter-thesis/group/item/register references, blockers and T0
stage/direction coverage. POST items are filtered before the T0 reducer.
`origin=SEAL_TIME` is the only potentially future-learning cohort origin;
`LATE_REBUILD` cannot enter prospective learning. Existing COMPLETE origin never upgrades
on retry. No R6 or calibration policy changes.

`thesis_current_view/v1` + `thesis_decision_card/v2` additionally retain `t0_basis`,
`current_basis`, `delta_vs_t0`, `post_t0_annotations` and Flow fact references. Exact
original sealed IID/context may be retained separately from a later POST IID/context.
The T0 manifest reference is bound when available. Annotation vocabulary is closed:
ENRICHES_UNKNOWN, ADDS_FACTS_ONLY, SAME_DIRECTION_AS_T0, OPPOSES_T0, REFRESHES_STALE.
These annotations never mutate T0. Card v2 retains the exact Stage-1 card identity.
LONG/SHORT states remain independent; UNKNOWN/INSUFFICIENT carry reason/blocker classes.

## Durable compact retention and retry

Products are retained beneath:

- `operations-review/thesis-evidence-t0-v1/<session>/<input_digest>/`
- `operations-review/thesis-evidence-current-v1/<session>/<input_digest>/`

The T0 digest includes exact snapshot/index/receipt and retained-source bindings rather
than only the snapshot digest. Both directories contain `views.ndjson`, `cards.ndjson`,
small `manifest.json` and immutable `COMPLETE.json` published last. A SQLite publication
lock excludes concurrent writers and is automatically released when a child exits.
Sibling temporary files are flushed/fsynced and atomically promoted. An incomplete
directory can deterministically rebuild; COMPLETE bytes are validated before reuse,
and differing bytes fail `IMMUTABLE_CONFLICT`. A current pointer atomically selects the
latest complete digest; replay diagnostics never publish that pointer.

Input digest binds session, all source identities/SHA/path pointers, snapshot/index/
receipt, Technical contexts, Flow identity, price-flow/velocity/T0-manifest observer
identities, adapter registry and projection contract. New POST input creates a new
current digest. Sources retain factual authority; compact products retain references.
`tools/run_thesis_evidence_stage2.py` supports explicit session/stage, optional original
sealed IID/snapshot, and `--manifest … --verify-ticker …`. One-ticker verification
rebuilds from original retained inputs and compares the complete compact record and
matrix identity. It makes no source/clock/marker writes.

## Failure and presentation

Ticker computation exceptions including MemoryError produce UNAVAILABLE with a reason
and null lenses. Other names remain valid and session status becomes PARTIAL. Missing
optional Flow is PARTIAL with explicit availability accounting. Child/source/process
failure returns component-local UNAVAILABLE/WARN; capture/marker/T0/VolumeFlow and other
products retain their validity. INSUFFICIENT_EVIDENCE remains a computed lens state and
is never substituted for an unavailable computation.

Handoff and presentation attestation carry portable compact identities/status/counts.
AI publication copies deterministic references and a bounded existing-focus selection;
it introduces no new generated verdict or dependency. Dashboard renders the same
card/matrix identities, independent states, cap/reason/blockers, conflict kinds and
T0/current availability. Existing owner focus selection and action posture remain primary;
no sorting by Thesis. Readers verify manifest/file/card/view identities and parity.

`first_real_session_acceptance/v1` adds 13 independent Stage-2 rows: both component
statuses/coverage, exact T0 bindings, zero POST, LONG/SHORT distributions, retrospective
exclusion, separate delta, Flow FACTS_ONLY, zero second-posture and zero action delta.
Missing Thesis does not gate capture rows. Products must be same session and actually
known by the requested cutoff. Distribution rows account for all computed records;
they do not require desired state proportions.

## Pathology, rehearsal and release

Correctness checks fail on POST-in-T0, forbidden fields, Flow directional votes, foreign
breadth overclaim, card/state mismatch, duplicate votes, action delta or unavailable
records without reasons. Descriptive warnings report concentration, supportive count,
identical lens states and conflict kinds/counts. Churn/availability transitions and
collapse/explosion comparisons require an explicit prior product; otherwise they are
NOT_EVALUABLE. No thresholds or reducer tuning are introduced.

The bounded acceptance tool is `tools/run_thesis_evidence_stage2_acceptance.py`. It uses
explicit retained October 2 sources and the frozen Stage-1 artifact, measures child and
parent RSS/time, verifies all 1,683 matrix/lens identities, compact sizes, retry and
one-ticker reconstruction, tests exact synthetic T0 basis gates and failure/presentation
boundaries, and proves protected-source/T0/receipt/foreign/clock non-mutation.
The resulting [single acceptance](internal/THESIS_EVIDENCE_STAGE_2_PRODUCTION_ACCEPTANCE.json)
remains REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE. Hook enablement requires this measured
proof plus candidate/main CI; failure leaves the automatic hook DISABLED_FAIL_SOFT.

Calendar readiness verifies original raw bytes and actual retrieval/documentation
timestamps and prepares a local exact command only. Real registration is not executed.
No live Monday Daily, retrospective T0 registration, source authority promotion or
analytical successor is started. After release the exact next operational gate is
`FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` on the actual Monday session.
