# Monday live readiness engineering closeout

`MONDAY_LIVE_READINESS_BLOCKER_CLOSEOUT_V1` starts from verified main
`97a19163f66f3d3d4f412e8bedeafbb47ea4bd25` under explicit owner implementation,
offline acceptance and release autonomy. Authority effect:
`NONE / MONDAY_LIVE_READINESS_ENGINEERING_ONLY`. No live Daily, historical T0
reconstruction, retained-evidence patching, tactics/posture/policy change or
source/PIT/RAW/CA/execution/Thesis authority promotion is performed.

## Known-at calendar and canonical completeness

`governed_calendar_evidence_at_cutoff/v1` in `governed_session_chain.py` is the
single lookup boundary over the explicit historical ledger and immutable DNSE
working-dates receipts. Receipts verify content/source/scope, original raw hash/dates
and API/documentation knowledge times. Only receipts known by the consumer cutoff
contribute. DNSE unspecified scope cannot establish exchange-specific authority.

The projection preserves supported dates, exact source identities/known times,
separate coverage segments, unsupported gaps, overlap disagreements and fitness.
Only overlapping intervals join. Civil adjacency never stitches unsupported gaps;
disputed omissions remain continuity barriers. Static-ledger provenance is retained.

Normal canonical D/W/M construction consumes this projection; Technical consumes
canonical completeness without another calendar algorithm. W/M needs undisputed
coverage of the whole period, all expected observations known by cutoff, compatible
source/basis and passage of the final governed session's existing post-close floor.
Future weeks can complete after their final governed session; insufficient
coverage/lookahead/missing constituents remain explicit.

The static ledger ends September 4 and the original forward receipt starts October 2.
**September 5 through October 1 remains unsupported.** September 2026 and the
September 28 week are not repaired. No weekday inference or synthetic date enters
production calendar evidence.

## Overlap and explicit registration

The existing `/market/working-dates` request has an empty query and qualified forward
coverage. No supported prior-overlap parameter was established; no query, request or
retry is added. Existing registered overlapping receipts can supply cross-window proof.

`tools/register_working_dates_receipt.py` is an explicit offline registration tool.
It requires original raw path, expected SHA, original retrieval time, documentation
SHA/known time and explicit destination root. It preserves original bytes/time/hash
and records original location/provenance under `governed_calendar_registration/v1`.
It cannot widen coverage or silently import an operations-review artifact. **No real
registration is executed by this corrective.** Missing overlap remains fail-closed.

The original October 2 receipt has raw SHA
`fce46fe3c9003d094ff22910d122622566d33d39076437c06a459f2511c33d6d`, retrieval
`2026-10-02T03:36:48.399047+00:00`, documentation SHA
`7ffc05d537f8f6bc982dbf8108960e6c6eb5337482710b4309d189919fb40858`, documentation
known time `2026-10-02T03:40:02.445723+00:00`. An operator-authorized registration must
supply the original raw location, never reconstructed dates. Without availability
under the normal governed root, Friday-to-Monday continuity remains UNKNOWN.

## Governed continuity

`are_consecutive_governed_sessions(previous, current, cutoff, calendar_evidence)`
returns TRUE/FALSE/UNKNOWN with proof sources. TRUE requires supported endpoints in
one undisputed segment with no intervening governed session. FALSE requires actual
intervening sessions; uncovered/disputed intervals are UNKNOWN. No weekend/civil-day
or price-file fallback establishes future continuity.

Foreign windows/streaks and V2 daily volume trajectories reaching the existing
post-release capture boundary (October 3) or later
share this primitive. VALUE formulas, cohort and participant authority remain exact.
Frozen V1 source bytes remain unchanged; V2 supplies the scoped shared proof to its
reused VALUE reader. Historical windows preserve legacy semantics. Future feedback,
outcome and learning already use the shared GovernedSessionChain strict realized
prefix; their source and old cohort behavior remain unchanged. Projection alone
never matures an outcome. Five-session fixtures spanning September29/30 and
October1/2/5 need exact fixture coverage; the real October 2 receipt cannot prove
their earlier dates. Old retained artifacts are not recomputed or rewritten.

## Completion publication recovery

The normal boundary writes immutable complete-session record, first marker, then
readiness. New records retain the original Phase-B gate. Rerun revalidates original
record/hash, completion time/window, calendar support, source manifest/receipts,
listing/binding batches and genuinely complete count before recovering a missing
marker. Original evidence time controls recovery, never later rerun time.

Invalid/incomplete/late/mismatched evidence, an earlier qualifying record or a
conflicting marker fails closed. The earliest valid record can recover through its
normal boundary. Existing correct marker is idempotent; session records stay immutable.
Repository-standard sibling temp, fsync and exclusive atomic immutable promotion are
used. Tests inject failures before session publication, before marker, during marker
fsync, after marker/before readiness and during readiness fsync; rerun recovers all
valid stranded publications.

## Compact T0 seal index

Final first-real acceptance guardrail (2026-10-04): the independent
`t0_snapshot_availability` row reports AVAILABLE only with a verified nonempty T0
snapshot basis; otherwise it reports STILL_BLOCKED / UNAVAILABLE with
`VERIFIED_T0_SNAPSHOT_UNAVAILABLE`. An unverifiable or missing seal-index basis
cannot establish availability in this bounded observer. This row never gates
capture or marker publication: `t0_snapshot_identity=None` remains allowed and
the marker remains `CAPTURE_COMPLETENESS_ONLY`.

`post_to_t0_leakage` is NOT_EVALUABLE with
`T0_UNAVAILABLE_FOR_LEAKAGE_EVALUATION` when the verified snapshot or relevant T0
items are unavailable. OPEN requires a nonempty T0 basis, an evaluation actually
performed, and zero leaks; detected leakage is STILL_BLOCKED. Thesis T0 diagnostic
rows likewise require an available, computed T0 basis, without changing reducers.
A complete first capture may open capture/marker and progress depth to 1 while T0,
seal-index/native T0, continuous PIT/RAW/CA and Thesis T0 capabilities remain
unavailable or unopened. No false T0_READY is inferred from capture success.

`prospective_t0_seal_index/v1` binds session, original snapshot identity/file hash,
decision artifact/operation, ticker, exact technical version/context and original
snapshot record identity. It contains pointers only. The companion
`prospective_t0_snapshot_write_receipt/v1` binds index identity/hash to the successful
snapshot write hash and immutable file fingerprint. The snapshot remains authority.

For new sessions, the existing writer's optional callback supplies the exact write
hash. Extraction verifies the already-built snapshot, with no second full parse.
Index failure is visible without invalidating successful snapshot retention; the
handoff carries index/write-receipt references. Ordinary V2 lookup reads only compact
companions and stats the immutable snapshot. It never opens/hashes/deserializes its
payload. Fingerprint drift fails closed and requires explicit verification/recovery.
Only exact V2 context binding gives native-volume T0. Missing index demotes to POST
with `T0_SEAL_INDEX_UNAVAILABLE`; invalid bindings cannot create seals. V1 reader stays
unchanged. A 2 MiB padded snapshot test produces the same-size index and forbids any
snapshot read during ordinary lookup.

`tools/recover_t0_seal_index.py` explicitly streams the original once with 16 MiB
member bound, verifies every extracted record/context and complete snapshot identity,
preserves its bytes, and separates index-created time from T0. Partial publication
reuses original creation time/receipt. Empty/missing snapshots cannot be sealed.
Historical recovery requires `--replay-diagnostic`, producing NON_AUTHORITATIVE
indexes that ordinary T0 observers cannot use. No real historical recovery is run.

## Acceptance harness and Monday operation

`first_real_session_acceptance/v1` covers calendar/continuity, capture/marker/readiness,
listing/representation/official verification, V2 routing/seal/native volume/leakage,
foreign1/5/10/20 and continuity, owner price-flow relations, W/M, Thesis release state,
PIT/RAW/CA, valuation and liquidity/execution. Each row has explicit opening predicates
and OPEN/PROGRESSED/STILL_BLOCKED/NOT_EVALUABLE. OPEN is their conjunction for every
capability, not a three-capability allowlist. There is no aggregate score/percentage;
first capture alone cannot open broad PIT or RAW.

The read-only harness takes explicit session/cutoff/root and optional exact handoff,
technical/flow/decision artifacts. Each source streams once into compact summaries;
missing optional evidence is NOT_EVALUABLE. It writes only a diagnostic report, never
sources, recovery, markers or authority. It references Stage1 release status without
importing Thesis or its 244MB artifact; Stage2 stays NOT_STARTED.

On Monday **2026-10-05**, target approximately **16:00 Asia/Ho_Chi_Minh** for normal
owner `stocklookup.ps1 daily`, only after unchanged Phase-A eligibility. The existing
15:30 attempt floor is not lowered. Phase B still requires genuine exact-session
evidence and capture completion must satisfy its contractual close/window. This
corrective does not run Daily or hard-code October 5 in production gates.

Isolated offline dry-run:

```powershell
python tools/run_first_real_session_acceptance.py --dry-run --session 2026-10-05 --cutoff 2026-10-05T12:10:00Z --output .stocklookup/scratch/monday-dry-run.json
```

After genuine Daily, pass actual root/cutoff and artifacts with `--source-root`,
`--handoff`, `--technical-artifact`, `--volume-flow-artifact`, `--decision-artifact`.
Write beneath `operations-review/first-real-session-acceptance-v1/SESSION/`.
Reusable normal logic accepts any explicit session. First-real acceptance is PENDING.

## Retained acceptance and release

[Portable acceptance](internal/MONDAY_LIVE_READINESS_CLOSEOUT_ACCEPTANCE.json) records
real calendar proof/gap, unchanged 19 T0 files/908 receipts/protected products/foreign
facts, frozen Thesis/V1/tactical/outcome sources, zero real marker/count advancement
and zero action/posture/policy delta. Separate synthetic fixtures prove future periods,
weekend proof/fail-closed behavior, failure recovery, index tampering/recovery/no-full-
parse and all four harness states. Timing measurements describe small fixtures and
have no arbitrary threshold or production-speed claim.

Focused/affected Producer tests and all four exact-candidate and merged-main CI jobs
gate release. External evidence blockers are unchanged. Next gate:
`THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION` — NOT STARTED.
