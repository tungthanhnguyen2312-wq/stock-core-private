# Post-first-real Daily Phase C resource simplification — 2026-10-06

Disposition: **PHASE_C_RESOURCE_SIMPLIFICATION_READY_FOR_REVIEW** (acceptance A).
Authority effect: **NONE / RESOURCE_AND_RUNTIME_SIMPLIFICATION_ONLY**.

Explicit owner override authorizes this isolated local candidate and one checkpoint only.
Starting production/main checkpoint: `802b11e00a2bb38db7f57644dca9f3ba463e1522`.
Candidate branch: `perf/post-first-real-daily-phase-c-resource-simplification-20261006`.
Its checkpoint is the commit introducing this report (`HEAD` sentinel in roadmap state).
No production Daily, acquisition, T0 builder, push, merge, deploy, publication or production
DB/runtime write was performed. No successor is queued. Production baseline remains unchanged.

## Evidence and limits

Read-only sources: retained `run-logs/stock_lookup_daily_20261005_180019.progress.jsonl`,
`stock_lookup_daily_20261005_195640.progress.jsonl`, and
`stock_lookup_daily_20261006_160503.progress.jsonl`; the corresponding completed artifacts under
`operations-review/`; capture/readiness/calendar/marker/seal receipts; retained post-handoff
feedback. Progress log SHA256 respectively:
`baa9d06bccfbc361fa673c98d31b92767a43a263e8c7ca7e52bc9fe66e8ca193`,
`f19f7b6497ac7f39483bb9bf77a6208bdc218e37f191576254bc111f7797292b`,
`193d55b347bde396914fbf6e78e2ba1437848a70cf80bedb88ef1088e563304a`. Diagnostics live outside
the repository in the owner's `tmp/phase-c-20261006` scratch namespace. They are not published
evidence or authoritative replacements. Sixteen protected capture/readiness/listing/binding/
marker/T0/seal files were SHA256 checked before and after; every benchmark input is likewise
hashed before/after. No protected bytes changed.

Historical telemetry samples process RSS and lifetime peak at progress boundaries. It cannot
identify the exact instruction at a peak inside a silent interval. Historical stage IO and
per-allocation object sizes are **unmeasured**, not zero. System commit is host-wide pressure,
not this process's allocation. The rehearsal records system commit at each observation and
process private commit/RSS/IO separately. No physical-disk versus OS-cache attribution is made.

## Root cause: proven allocations versus historical attribution

The **10,985,897,984-byte (10.23 GiB) peak belongs to the October 5 rerun**, not October 6.
October 6 Canonical-child lifetime peak is **10,666,430,464 bytes (9.93 GiB)**. Both attain their
highest sampled lifetime peak before post-handoff feedback. Feedback is not the demonstrated
cause: the Daily parent stays about 6.04 GB around its bounded calls; feedback child peaks are
598,679,552 bytes pre-handoff and 607,027,200 post-handoff.

Three measured structural costs explain why artifact sizes do not bound process memory:

1. `integrated_investment_decision_product.content_identity -> _sha256 ->
   _canon(payload).encode('utf-8')` kept the resident IID graph while materializing a canonical
   Unicode string and encoded bytes. Retained IID **file size** is 1,394,317,136 bytes (pretty
   JSON); rehydrated **resident process private bytes** are about 2,461,810,688 (includes Python
   runtime/other metadata, not an exact deep-size count). Baseline canonical text contains
   813,475,819 characters and its Python string occupies **1,626,951,696 bytes**. At `_canon`
   return private bytes are 4,091,715,584; the subsequent encode/hash expression raises the
   process private high-water to **6,536,986,624**. JSON construction also has transient pressure
   (private peak 5,307,101,184 before encode). Internal allocator over-allocation is an inference;
   whole-string/encoded-copy coexistence and the measured high-water are proven.
2. `canonical_post_close_pipeline -> bind_integrated_decision_brief_before_sealing` deep-copied
   the entire operation, including the already-built full IID and input graphs. Real baseline
   binding adds **1,341,845,504 private bytes** (1.25 GiB) and takes **53.944 s**. Original
   enrichment plus the bound producer operation coexist and remain reachable through the Daily
   result until return. This is a persistent duplicate graph, not merely disk duplication.
3. `build_delivery` projected all records, scoped the primary, retained all NDJSON Unicode row
   strings, joined them, added a newline (another string) and encoded the aggregate while
   those graphs remained live. The bounded baseline fails with **MemoryError at that exact
   join/newline/UTF-8 expression**, private peak 6,734,299,136 under a 7-GiB Job ceiling. The
   dashboard also built a full-universe overlay only to discard its records. The corrected
   real-scale stage completes with a private peak **4,452,204,544**.

These paths are causally proven by code, allocation observations and bounded rehearsal.
They are present in fresh Daily execution. They do **not** prove which single instruction set
the historical 10.23-GiB global peak: the historical logs lack allocation traces. The later
observer interval also raises the high-water. `multi_session_signal_velocity.discover_retained_snapshots`
uses `read_text + json.loads`, validates entire T0s, retains all qualified snapshots in a list,
then reduces to seven categorical axes. This unchanged path is a residual structural pressure
source; assigning the exact final historical peak to it would exceed the telemetry.

## Deterministic October 6 resource map

Times are seconds relative to Owner-run start. RSS numbers below belong to the Daily child
unless explicitly marked Owner. A boundary lifetime peak covers everything since process
start; it is not the current stage's isolated peak. GB values in this table are decimal.

| Stage | Window / elapsed | Resource observation and ownership |
|---|---:|---|
| Owner repository/host preflight | 0.405–8.519 / 8.114 | Read-only host admission; existing thresholds unchanged. |
| Exact-session acquisition | 12.379–824.265 / 811.886 | RSS ~0.128→0.827 GB; lifetime peak 1.689 GB. Full exact-session graph retained as acquisition result. |
| Liquidity batches | 294.861–755.986 / 461.125 | Within acquisition; bounded batch progress, no separate isolated IO/peak proof. |
| Technical/descriptive/screening/tactical | 758.605–787.645 | Technical 16.448 s; descriptive 9.772; screening 1.141; tactical 1.677. Whole snapshot consumers share/revisit evidence. |
| CI/valuation/sector/relative/risk | 787.646–809.807 | CI .971 s; valuation 12.868; sector 1.624; relative 3.070; risk 3.624. Historical/financial context parsed by enrichment consumers. |
| Enrichment + IID + Producer/delivery + runtime + T0/seal + Thesis T0 + decision packet | 824.265–2015.068 / **1190.803** | Silent window: distinct stage durations unavailable. End RSS 6,037,188,608; lifetime peak **10,521,595,904**. Resident acquisition/IID/operation; canonical serialization and deepcopy identified above. T0 builder shallow-copies each decision, sharing nested graph, and streams hash/write; no proven fresh deep T0 graph here. |
| Cohort observation | 2015.068–2018.229 / 3.161 | Retained observer, no authority promotion. |
| Pre-handoff feedback | 2018.258–2173.825 / 155.567 | Parent RSS 6,037,372,928→6,036,652,032; child peak commit 598,679,552. Streaming boundary; no full feedback graph returned. |
| Tactical shadow | 2173.832–2425.620 / 251.788 | Separate observer work, bounded attribution only. |
| Handoff/tiered bundle + signal velocity + foreign/divergence/volume observers + Thesis current | 2425.620–3306.755 / **881.135** | Silent window, no individual stage timing. End lifetime peak **10,666,430,464**. Signal velocity whole-T0 loading/retention remains. Thesis compact child sidecars do not return full parent graphs. |
| Post-handoff feedback | 3306.755–3440.746 / 133.991 | Parent RSS 6,016,364,544→6,016,557,056; child peak commit 607,027,200. Lifetime peak already reached before this call. |
| Remaining Canonical presentation preparation | 3440.746–3510.749 / 70.003 | Parent retains earlier operation/acquisition/enrichment till return. |
| Canonical total | **3502.230 / 58m22.23s** | Lifetime child RSS peak 9.93 GiB; not a candidate whole-Daily measurement. |
| Completion verification / state / dashboard / AI handoff / Action Center | .468 / 4.696 / 199.517 / 57.452 / 25.617 | Owner publication phases. Owner lifetime peak 7,005,794,304 at Action Center is a different process lifetime. |
| Owner total | **3799.142 / 63m19.14s** | All nine phases completed in retained production evidence. |

Repeated whole parsing: exact snapshot feeds acquisition/enrichment/operation input resolution;
signal velocity loads each T0; delivery verification reloads small primary/cockpit/manifest.
The producer copy into its sealed run directory is an intentional file boundary. The IID
canonical-post-close mirror copies already serialized bytes under receipt; it is not a second
full canonical serialization. Candidate does not alter any of those authority boundaries.

## October 5 versus October 6

| Observation | Oct 5 initial | Oct 5 successful rerun | Oct 6 fresh run |
|---|---:|---:|---:|
| Canonical lifetime RSS peak bytes | 10,687,537,152 | **10,985,897,984** | **10,666,430,464** |
| Acquisition ends, relative seconds | 820.738 | 62.723 | 824.265 |
| Before pre-feedback, relative seconds | 1997.505 | 861.637 | 2018.258 |
| Canonical elapsed seconds | initial tier-bundle failure | 1700.479 | 3502.230 |
| IID records | 1683 | 1683 | 1683 |
| IID file bytes | 1,392,153,144 | same session family | 1,394,317,136 |
| Immutable T0 file bytes | 1,486,660,011 | original reused | 1,487,255,738 |

IID increases only 0.155%; T0 about 0.040%. Near-10-GiB peaks repeat. The rerun reuses
acquisition/T0 and skips already-retained feedback, so its shorter elapsed time cannot be
credited to cache alone or used as a fresh-Daily speed baseline. Structural costs recur in
fresh runs; this is a justified per-Daily correction, not solely first-capture overhead.
Two sessions with identical record counts do not establish a quantitative record-count or
byte-size scaling slope. The measured copy/serialization costs scale with resident content;
cache effects and different observer workloads remain confounders.

## Artifact/consumer and duplication inventory

Sizes below are Oct 6 bytes. Retention is governed retained session evidence with **no
new TTL/deletion policy**; no numerical retention horizon is inferred when the contract has
none. Historical zero-byte October 2 T0 remains permanently unavailable. Every row is retained,
not deleted or renamed by this candidate.

| Family / bytes | Producer → consumers; identity | Duplication, scope and authority |
|---|---|---|
| Exact-session snapshot 301,423,666; history 162,517,852 | DNSE acquisition/history → current products, enrichment, capture; source/session receipts and governed content identities | Full evidence reused/loaded by multiple consumers; intentional source boundary. Current exact evidence is not official RAW/PIT authority. |
| IID 1,394,317,136 in enrichment and product family | IID builder → Producer, T0, Brief, observers, AI; canonical SHA256 excludes requested_at/identity/hash | Two physical representations of the same artifact identity. Pretty file versus compact hash are representation duplication; resident deepcopy was avoidable. Full immutable decision universe 1683, no policy changes. |
| T0 1,487,255,738 | retention builder → feedback, signal velocity, seals/Thesis; immutable canonical snapshot identity + seal index | Shares decision meaning with IID but is an **intentional immutable authority boundary** including original known-at lineage. Full object needed only by some legacy observers; bounded readers exist. Never replace from current IID/rerun. |
| AI primary 25,107,987 | delivery → AI/human handoff and verifier; exact bytes SHA256 in bundle manifest | Scoped 72 ticker contexts / 10 owner-watchlist tickers. Semantic projection of IID and product; contractually distinct delivery view. Operation and sealed-run file copies are intentional audit boundary. |
| Full-universe NDJSON 474,852,112 | delivery → lookup/handoff consumers; manifest byte SHA256 | Full 1683 ordered lookup records. Overlaps primary semantically, different required scope. Candidate writes one row at a time to a byte buffer; retains bytes-returning interface. |
| Cockpit 1,642,365 | delivery → dashboard; deterministic canonical JSON and manifest SHA256 | Bounded watchlist cards + overlay metadata; previously an unnecessary full-universe intermediate. Non-authoritative projection. |
| Workspace 187,176,312; screener 7,531,514 | product/projection builders → dashboard/Owner views; respective product/source bindings | Distinct browsing contexts, not substitutes for IID/T0. New post-handoff sidecars bind presentation without revising sealed Producer. |
| Scenario 61,034,195; strategy 25,202,384 | operation component builders → current product, delivery, snapshot; respective deterministic canonical artifact identities | Full operation component graphs, borrowed read-only by Brief binding. Sealed analytical components have distinct scenario/strategy semantics; delivery needs projections, not independent deep copies. |
| Feedback pre 546,784,419; post 583,618,622 | bounded feedback child → learning/review/observers; canonical streamed identity/source lineage | Two different information cutoffs, **not duplicate snapshots**. Full growing corpus retained; ~0.56-GiB child commit. Non-voting; no calibration activation. |
| Signal velocity 285,614,098 | retained T0 observer → current/handoff views; deterministic artifact identity | Seven-axis history projection, semantic duplication justified by observer contract. Its all-T0 parse/list remains a resource risk. Non-voting. |
| Thesis T0 cards/views 17,397,698 / 21,443,002; current cards/views 22,477,225 / 45,237,436 | bounded Thesis builders → matrices/lenses/handoff; exact source IID/T0 seals and manifest NDJSON hashes | Compact T0/current boundaries differ in known-at/observer context. Non-voting; original seals unchanged. |
| Operation manifest 29,794; AI manifest 4,641; Brief 2,778 | operation/delivery → resume, verifier, consumer binding; deterministic operation ID / output digests | Tiny operational identity bindings. No new analytical authority. Same sealed operation can be copied into run directory. |

## Minimum implementation and ownership

Four production files change: `bounded_artifact_stream.py` adds canonical record-wise digest;
`integrated_investment_decision_product.py` uses it only for artifact content identity;
`daily_research_session_operations.py` borrows read-only analytical payloads and independently
replaces binding/manifest/output spine; `ai_research_session_delivery.py` shares overlay header,
encodes NDJSON rows into BytesIO, and releases primary/overlay after their last consumer.
The manifest and outputs remain independently copied before mutation; invalid binding leaves
the original untouched. No cross-process full graph is newly introduced.

IID decision-level hashing, sorted ticker ordering, strict JSON numeric semantics, Unicode,
identity exclusions and JSON layout remain exact. Hashing transient size is bounded by the
largest record plus metadata; resident graph is still required by existing builders. Delivery
still returns its full ~0.5-GB bytes payload; this is a small safe correction, not a claim of
fully file-backed architecture. Residual observer loading and earlier product graph lifetimes
are unchanged. No thresholds or source/RAW/PIT/CA/action/probability/eligibility policy changed.

## Bounded real-scale qualification

`tools/run_phase_c_resource_rehearsal.py` rehydrates the retained Oct 6 IID and operation,
then calls actual content identity, pre-seal Brief binding and build_delivery. It invokes no
analytical builders/Daily/T0 writer. A Windows Job contains/reaps the full child tree, hard
7-GiB private-memory ceiling and 1200-second total deadline; output/result must lie outside
retained source root. Global host Python 3.13 + psutil 7.2.2 were used, no borrowed virtualenv.
No memory ceiling was raised after baseline failure.

| Rehearsal | Wall s | Peak private bytes (GiB) | Result |
|---|---:|---:|---|
| Exact baseline full Producer | 142.206 | 6,734,299,136 (6.27) | MemoryError at NDJSON join/encode; safely reaped, EXIT_NONZERO. **Lower bound**, not a completed baseline runtime/peak. |
| Baseline identity + binding | 139.277 | 6,537,588,736 (6.09) | Complete; identity 19.925 s, binding 53.944 s. |
| Intermediate candidate hash/copy only | 121.503 | 6,850,965,504 (6.38) | Complete, all five outputs equal; delivery Unicode buffers still present. |
| Final candidate full Producer | **143.585** | **4,452,204,544 (4.15)** | Complete, all five outputs equal, Job reaped, no reason code. RSS peak 4,186,656,768 (3.90 GiB). |

Final identity 16.341 s; binding **.001968 s / +4096 private bytes**; delivery 50.273 s.
Final child elapsed 139.552 s includes rehydration, proof hashes and disk output. Private peak
is 33.9% below the failed baseline's observed lower bound and 35.0% below the completed
intermediate candidate. Single runs, changing cache/host pressure and proof IO mean no
whole-stage elapsed speedup claim; the isolated copy removal's 54-s cost is directly measured.
Final stage is comfortably inside the existing 6.5–8.0-GiB planning band, but **no candidate
whole Daily was run**. This does not requalify whole-Daily capacity or amend host preflight.

Final unique input sizes: **1,604,872,426** bytes. Output data written: **501,609,883** bytes.
Process IO-counter delta: read **5,316,228,845**, write **501,619,760** bytes, including
proof rereads and diagnostics. These are logical process IO, not physical-disk throughput.
Stage memory and host commit samples are in each `result.json` observations; containment peak
is in `containment.json`. Historical production stage read/write values remain unavailable.

Candidate host admission observations (GlobalMemoryStatusEx, host total physical
16,859,357,184 bytes): available physical / available commit at resident IID
3,636,838,400 / 10,880,593,920; after identity 4,210,520,064 / 12,542,058,496;
before binding 3,619,110,912 / 11,925,569,536; after binding
3,617,693,696 / 11,923,390,464; after delivery 3,187,666,944 / 11,231,031,296.
These are sampled host headroom, not isolated stage commit consumption or minimum headroom.

Portable invocation (substitute absolute paths for the local retained source, exact baseline
or candidate code and external scratch directories):

```powershell
python -B tools/run_phase_c_resource_rehearsal.py --source-root $retainedSource --code-root $candidateCode --output $scratchOutputs --result $scratchResult --session 2026-10-06 --stage producer --deadline 1200 --memory-gib 7 --write-outputs
```

## Semantic parity proof

The retained real IID stream validates its canonical digest, 1683 records and artifact ID:
`integrated_investment_decision_product/v1:ef756cbacdd88e6676ffb32670d3c515e7ad5e806e3c555d6c29a5ed4e2f2389`.
Candidate pre-seal binding preserves operation ID:
`daily_research_session_operation:e756b5b202b4338b08e958e21b1866aa3e36397773a2bc2751e1deec4652b26c`.

| Output | Retained = candidate raw SHA256 |
|---|---|
| Primary | `b7a8c335ccf13d904e7da255792e15e6ade579b651f8ca0fa0e5c4c68daa4264` |
| Full-universe NDJSON | `1557f0367b20010a1fb97a73a6af117fd39d79403a0df10dab9e1dc9c4e84b76` |
| Bundle manifest | `818462326ced8b21a5bcc68b50e22a648e7273d546f58929f1a19368a27f814c` |
| Brief | `f066ed0daaa2e32dbcf8d77804b374394ad170d442281f9822f2dca5b3718e91` |
| Cockpit | `3109e0fc5b2830ceb9ac1446414a68e3a7154a38743ba0b2e27a2f2e498af605` |

Byte equality is stronger than formatting-tolerant content equality: same ticker coverage,
record ordering, decision content, reasons, warnings, eligibility, tactical/strategy/scenario
fields, source identities and downstream delivery interpretation. No T0 generation path was
changed or rerun; both original T0s/seals retain exact bytes/identities. October 5 rerun IID
differs from its original T0 lineage, which is intentionally preserved rather than repaired.
Tests cover empty records, Unicode, negative zero, exponent floats, nested records, identity
exclusions, NaN rejection, borrowed graph and independently writable binding/manifest spine.

## Prospective gate accounting (cutoff 2026-10-06T16:00:00Z)

Governed capture chain: **October 5 and October 6, 2 contiguous complete sessions, no gaps**.
Capture-complete tickers: 658 then 654. Readiness remains **DEPTH_PENDING**, representation
tier 857 `SOURCE_NATIVE_SCALE_CONSISTENT`. Per-ticker contiguous depth distribution:
**589 at depth 2, 65 at depth 1, 293 at depth 0** (947 members). Counts reaching
20/21/50/60/120/250 are all zero. Representation tier is distinct from historical depth.

Post-marker T0s: **2 available, 0 unavailable**. Entire known T0 namespace has 21 paths,
20 nonempty plus the immutable zero-byte October 2 failure. Two extra September 11 family
paths mean 19 distinct sessions, 18 with a nonempty T0; do not count paths as new sessions.

| Gate | Current / additional governed completed captures |
|---|---|
| Depth 20 / 21 / 50 / 60 | **18 / 19 / 48 / 58 more** for the depth-2 cohort; incomplete tickers keep their own clocks. |
| October 5 T0 first T+20 | 1 subsequent completed capture; **19 more**. Governed source-calendar projection November 2. |
| October 6 T0 first T+20 | 0 subsequent completed captures; **20 more**. Governed source-calendar projection November 3. |
| New-chain T5 / T10 / T20 maturity | **0 mature** for October 5/6 cohorts. Original October 5 lineage is excluded from post-feedback after rerun mismatch, not rewritten. |
| Retained legacy T5 | **10,338 mature ticker rows in 15 decision-session cohorts**: Sep 3,8,9,10,11,15,16,17,18,21,22,23,24,28,29. |
| Retained legacy T10 | **6,544 mature rows in 10 cohorts**: Sep 3,8,9,10,11,15,16,17,18,21. |
| Retained legacy T20 | **16 mature rows, 1 cohort (September 3)**. |
| T+60 | Registered by capture/durable-case contracts, **not emitted by current forward feedback** (horizons 1,3,5,10,20). New chain max 1 future session; retained feedback chain has 22 sessions/max21 future, so no T60 window is possible there. No fabricated product maturity count. |

October 6 post-feedback has 1683 rows: for each emitted horizon, 857 pending future sessions
and 826 close price not retained. Legacy mature outcomes are not zero and do not authorize
calibration. Calendar dates are projections conditional on complete governed captures, not
civil-day maturity or guarantees. Missing closes, price-basis incompatibility, lineage
exclusions and official RAW/PIT/CA/listing blockers mean the system does more than merely
wait for elapsed T5/T10/T20 time. Learning/calibration policy is unchanged.

## Validation and review boundary

- Focused initial component/retention/control checks: **132 passed**; final delivery checks
  **47 passed**; final feedback/capture/calendar/progress checks **145 passed**; seal/Thesis/
  active-control checks **88 passed**; post-doc identity/active/roadmap checks **54 passed**.
  These overlap; do not sum as unique coverage.
- Broad 15-suite candidate and exact-baseline detached checkout: both **428 passed, 8 failed,
  10 errors**. All 18 failing node IDs and failure/error classifications match; every one is
  a missing retained-evidence fixture `FileNotFoundError`. Candidate-only regressions **0**.
  No fixture fabrication or unrelated test repair. Scratch runtime root used for tests.
- Changed Python files compile; diff whitespace and roadmap check pass. Roadmap records
  explicit override, completed local milestone, review disposition and empty successors.
- Exact staged allowlist contains four production Python files, the rehearsal tool, focused
  test, this report and five current-control docs. Runtime/generated evidence is not staged.
- Canonical main remains the exact starting checkpoint; its pre-existing untracked `data/`
  is preserved. Candidate is isolated and has no production effect until reviewed/merged.

**One next recommendation: merge this Phase C candidate after review.** Whole-Daily capacity
must be judged from subsequent governed production telemetry after a separately authorized
merge; unchanged observer pressure prevents claiming a new global peak from this stage test.
Do not start a successor or change preflight thresholds from this report.
