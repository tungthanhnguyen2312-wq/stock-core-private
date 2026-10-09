# Capacity Recovery Phase 1 — writer completion

Owner authorization: `PR98_RELEASE_AND_CAPACITY_RECOVERY_PHASE1_END_TO_END`, October 9,
2026. PR98 merged with exact-head protection, authorized head
`62bf8386eaa153eb4674b412f566cc0540ecc025`; merge and capacity base
`1d6b8a8b9bce430a0b0f8cdd735a1cb90b8556f8`.
Only `STOCKLOOKUP_CAPACITY_RECOVERY_PHASE1_LINK_DEDUP_AND_COLD_CATALOG_V1` is admitted
through native `--can-start ... --owner-override`. Queue stays empty. Authority effect NONE.

The prior **PARTIAL_READ_ONLY_CAPACITY_FOUNDATION_READY** checkpoint remains recorded.
Owner directive `STOCKLOOKUP_CAPACITY_PHASE1_END_TO_END_COMPLETION` explicitly continues
that subset from PR99 head `14d7f02515380ac34557e87271fa12c050959e4e` without starting a
successor. Native `--continue-scope ... --owner-override --scope-note ...` preserves the
prior completion and records `allows_reopen=true`. Phase 1 is ACTIVE until engineering
and exact-head CI/release gates close. Only a fully qualified exact-head normal merge is
authorized. No production deployment/activation, source deletion, relink, retention apply,
Daily, provider acquisition or T0 relocation is authorized.

## Catalog and acquisition boundary

`config/retained_evidence_cold_catalog.json` ships with an empty `entries` list. Entries
are explicit location records with exact session, source-relative path, artifact identity
and resolver `artifact_role`. They add no factual or historical authority.
States are separately represented:

| State | Resolver behavior |
|---|---|
| PRESENT_ON_C | Verify claimed native size/SHA; existing semantic reader still governs. Missing/corrupt claimed local bytes raise integrity error. |
| ARCHIVED_COLD | Raise `ArchiveRestoreRequired`, code `RESTORE_REQUIRED`, carrying exact Vault locator. Manual copy does not silently restore a catalog state. |
| NEVER_RETAINED | Preserve governed acquisition eligibility, subject to the original gates. A contradictory existing local file fails closed. |
| UNKNOWN_OR_CONFLICTED | Raise integrity error; no guessed availability or acquisition. |

Cold entries require original size/SHA, source/seal provenance, snapshot identity,
manifest path/SHA, object path/SHA, exact volume ID, restore procedure and preconditions.
The catalog records a previously verified locator; resolution does not mount W, verify
a fresh snapshot, transparently read W, or download anything. Qualification and restoration
must verify the original bytes independently. Duplicate/case-colliding entries, malformed
catalogs, invalid relative paths and session mismatches fail closed.

An empty/absent catalog preserves legacy fixture behavior. Existing local files still use
the original snapshot quality/license gate. Unregistered missing paths are NEVER_RETAINED,
but a governed completed-session registry claim prevents reacquisition when both exact
snapshots are missing. `ensure_exact_session_snapshot` checks the selected exact path,
then the DNSE fallback, and before provider candidate/credential/network work checks cold
snapshot entries for the exact session at both execution and artifact roots. A new attempt
root cannot evade this pre-network guard. A valid local MVA snapshot can be reused without
reading a cold DNSE fallback. Feedback's exact-session snapshot reader uses the same guard.

Historical T0, its index, receipt, fingerprints and knowledge times remain unchanged.
No definition of completed session changes. No catalog writer or production restore API
is shipped. Future catalog events require a separately approved immutable event/receipt
binding and exact-path approval; the empty tracked file cannot authorize retirement.

## Offline exact-path plan

`python -m tools.storage_capacity_plan --proposal FILE --proposal-sha CANONICAL_SHA
--source ROOT --vault W_ROOT --manifest FILE --manifest-sha SHA --volumes FILE
[--max-bytes N]` emits deterministic JSON to stdout. The proposal SHA is SHA-256 of
compact sorted UTF-8 JSON (`tools.vault_snapshot.canonical`), not the formatted file SHA.
Default dual-hash input ceiling is 64 MiB. No inventory, recursion, acquisition, apply,
mirror-delete, second-copy migration or production restore command exists.

Proposal schema `capacity_exact_path_proposal/v1` requires `keep_sessions` containing
current and previous two completed sessions, plus exact candidate rows. Each row names
`relative_path`, `group`, `session_identity`, `artifact_identity`, reader/dependency
closure, restore procedure/preconditions and second-copy policy. Dependency proof slots
are runtime/code/manifest/cross_session/external; unknown or nonempty closure blocks.
These are audited operator inputs, not inferred consumer absence. A proof SHA is a
locator for the external closure audit, not independently established closure authority.
The plan does not prove the operator chose the correct latest three sessions; that remains
part of the owner-approved input review. Single-copy acceptance is only a proposed gate.

G1/G2/G3/G5 are considered, G4 and unknown groups deferred. T0, seals, receipts, handoffs,
run manifests, canonical IID, MVA, accumulators, config/data/runtime and recent sessions
are protected. Mere age/SHA equality never makes a row eligible. G1 always reports
`HARDLINK_WRITE_LIFECYCLE_UNPROVEN`. G2/G3/G5 can qualify only for a future owner review.
They never become deletion-authorized.

Vault coverage requires a pinned **Vault V1 COMPLETE manifest**, exact source root and
source/destination volume identities. Only explicit covered candidates are examined;
both source and Vault objects are locked against Windows writes/deletes, strong fingerprints
must match the manifest, and both native SHAs are streamed under the byte ceiling. Manifest
identity, fingerprints and volumes are rechecked. Multi-link files are blocked without link
closure. Unique physical allocation counts each `(volume, device, inode)` once and stays
separate from logical bytes, proposed allocation and actually reclaimed bytes (always zero).
Legacy October-8 ledger import is deliberately absent: its weaker fingerprints cannot
be silently treated as a Vault V1 cache lease. Production qualification requires fresh,
separately authorized bounded coverage/closure proofs.

`rehearsal(bytes)` accepts at most 1 MiB, creates its own temporary fixture tree and
exercises hardlink publication, two consumer reads, a fresh-inode undo and verified
copy/restore. It accepts no caller filesystem destination and cannot mutate production.
This proves mechanics, not safe production hardlink lifecycle or production restore authority.

## Opt-in Vault adapter

`python -m tools.vault_post_daily_adapter --opt-in --source ROOT --vault W_ROOT
--boundary FILE --boundary-sha SHA --volumes FILE [--previous FILE --previous-sha SHA]
[--max-bytes N]` consumes an already qualified, explicitly pinned
`vault_completed_boundary/v1`. It reuses `tools.vault_snapshot.snapshot`; no new copier,
Daily stage, scheduler or launcher hook. It does not automatically discover/generate a
closure from every Daily directory. Automatic boundary emission remains deferred until
the full immutable dependency closure can be proven.

Additional `completion_proof` references pin registry, original completion record, handoff,
producer manifest and sealed operation manifest by native SHA. Proof documents are capped
at 8 MiB each and held under source locks during snapshot publication. Registry must claim
COMPLETED_RETAINED_EVIDENCE with a validated trading day; original completion must carry
LOCAL_COMPLETE, COMPLETED, runtime/trusted READY and exact acquisition session. Operation
identity and Producer run identity recompute using existing owners. Handoff must bind the
same session/run/operation with COMPLETED status. Completion, handoff, Producer and operation
refs must be included in the pinned receipt/seal closure. Source identity is the sealed
operation identity. Mutable/config/runtime/data/accumulator boundary rows refuse.
Included T0 requires the existing original seal-index verifier and the exact bound snapshot
path; no index or receipt is rewritten. Vault V1 verifies all native bytes and source stability,
resumes interrupted copies and publishes immutable COMPLETE manifests/receipts append-only.
Missing/wrong/unhealthy volume returns OPTIONAL_BACKUP_UNAVAILABLE without changing Daily.
Tampered or incomplete completion proof refuses qualification. W identity is a pinned operator
configuration checked against native observation, never inferred from the drive letter alone.

## Writer investigation and remaining blockers

The original DRO and Producer delivery writers rewrote equal bytes in place. They now
publish through private staging and exclusive creation, with exact replay a no-op and
conflicting/partial existing content an explicit refusal. Existing legacy paths are
neither replaced, sealed nor linked by the new reuse path.

`run_daily_producer(..., reuse_immutable_delivery=True)` is the opt-in integration.
It asks DRO to protect newly published `ai_research_full_universe.ndjson` and
`ai_research_session_bundle.json`, then uses `_retain_owner_delivery` to publish the
Producer paths on the same verified NTFS volume (GUID) or POSIX device. Windows uses
private fsynced staging, read-only attributes and exclusive rename; POSIX uses private
fsynced staging, mode 0444 and exclusive hardlink publication plus directory fsync.
No partially written file is published. Legacy/unprotected or cross-volume inputs
retain an independent verified copy. Alias SHA/size, identity and protection are checked;
no generic cross-run content-addressable store or historical relink exists.

The switch defaults FALSE and no launcher/CLI/Daily call enables it. Deployment and
future activation require their separate gate. Disabling reuse safely retains existing
shared files with exact-byte no-op replay; keep the corrected immutable publishers when
rolling back activation. Reverting to the old in-place writers is not a safe rollback.
Completed shared paths never permit replacement through these publishers. OS protection
is against ordinary writes, not privileged administrator removal of protection.

Readers keep all original paths: AI handoff, ticker extractor, canonical runtime release,
previous-operation/Brief resolution and tiered bundles. Manifest native SHA/size and
artifact/run/operation identities are unchanged. Linked sources are supported by Vault's
explicit context-local `(device,inode)` owner: one locked descriptor, separately verified
pathnames, and no simultaneous alias borrowers. Link creation precedes snapshot sealing;
its changed link count/ChangeTime cannot reuse an old Vault fingerprint lease silently.

**IID remains BLOCKED for shared publication.**
`canonical_post_close_pipeline._copy_iid_working_view` verifies a write receipt and
replaces a working view; `_write_json` replaces the canonical working artifact. These
paths are not a proven write-once shared object lifecycle. Existing tests also require
source stat parity. We preserve copy behavior rather than claim immutable publication
alone protects every linked pathname. Needed: migration of **every** affected writer,
exclusive publication/race handling, explicit write protection and retry/rollback review.
No historical sealed alias or canonical source is relinked.

G2 feedback readers/tool oracles and G5 external/manual reference closure are not yet
fully catalog-aware. Whole-history glob inputs, canonical IIDs, MVA and T0 stay hot.
No G2/G3/G5 production action may proceed on this subset alone. Future event binding,
production restore verification and strong legacy coverage import remain independent gates.

## Capacity assessment (retained report, not a fresh production measurement)

The completed architecture report reports 2,503 large file IDs, all nlink=1, 253 SHA
groups and 16.32 GiB independently allocated duplicate aliases. Its exact candidate
manifest contains G1 539 aliases / 17,526,431,744 estimated allocated bytes;
G2 31 eligible rows / 11,568,001,024 bytes (October-2 oracle protected);
G3 23 rows / 6,942,674,944 bytes. G5 overlaps G1 and must not be added naively.
Report union is 36.1 GiB before recent-session protection, about 33.4 GiB with recent
sessions retained. These are conditional proposal figures, not newly qualified reclaim.
The previous reconciliation disclosed incomplete external/manual consumers and growth
outside the core dated families. This job repeats no inventory or large SHA exercise.

Exact proposed groups are the original architecture `CANDIDATE_GROUPS.json`: G1 aliases
under dated canonical-post-close enrichment and Producer/DRO output families; G2 dated
pre/post feedback; G3 dated p3f9b DNSE-only snapshots; G5 exact unreferenced one-off families.
Their exact owner-local path manifest and hashes are recorded in the acceptance record;
it is an implementation input, not a manifest compatible with this new production planner.

**Measured isolated delivery allocation: 2,236,416 → 1,118,208 bytes (50%).**
The genuine 1,683-row builder fixture uses no padding. Its four source/consumer paths
retain native SHA, manifest and replay parity while physical file identities fall 4 → 2.
Actual Producer entry-point fixtures preserve completed run identity and parity checks.
Retained October-7 inputs project 505,257,984 bytes (~0.471 GiB) avoided per equivalent
future session after activation, not the unimplemented 1.8-GiB all-family scenario.
This falls below the preferred 1-GiB target; IID remains explicitly blocked.
**Actual production growth reduction and historical reclaim: 0 bytes.**
The architecture's 8.19 → 5.0 GiB/session scenario depends on about 1.8 GiB future link
avoidance plus rolling historical retirement; neither is activated or claimed here.
At the retained 125.1-GiB free-space observation and unchanged 25-GiB guard, conservative
8.2-GiB growth allows 12 whole sessions; stressed 12-GiB growth allows 8. No new capacity
measurement, permit to launch Daily or unrelated scratch reclaim is implied. Conditional
33.4-GiB recovery would permit 16 or 11 whole sessions at those same growth assumptions.
The proposed 5.0-GiB scenario permits about 26 whole sessions after 33.4-GiB recovery,
excluding scratch, failed attempts and unrelated growth. It is not a guaranteed outcome.

Remaining owner gates: production read-only dual-hash plan/legacy import; exact plan SHA
and path approval for historical dedup; separate cold retirement approval plus verified
second copy or accepted risk; explicit restore/event qualification; adapter activation;
scratch cleanup; and a separate Phase 2 for MVA/T0 portability. PR99 merge requires all
exact-head CI/review/mergeability gates plus the measured writer integration. No successor.

The deterministic `tools.capacity_retained_eligibility` report consumes only pinned small
architecture inputs and the legacy backup receipt; it performs no production content reads
or apply. Exact G1/G2/G3/G5 paths, native historical source/W identities, restore paths,
physical estimates and blockers are retained in
`internal/CAPACITY_PHASE1_RETAINED_ELIGIBILITY_20261009.json`. Keep current plus previous
two sessions (October 8/7/6); cross-group physical IDs count once. Conditional union is
32,066,560,000 bytes (~29.86 GiB), freshly verified reclaimable capacity remains zero.
Fresh dual hashes/strong fingerprints, resolver/external closure, exact owner plan approval
and second-copy/risk acceptance remain mandatory. G4/T0/MVA/accumulators stay excluded.

PR99 lock corrective: qualification owns an explicit `LockedSources` context and
passes it into Vault V1. Nested reads borrow the original descriptor, restore its
cursor, and retain all source handles until qualification exits. No global lock
registry or unlocked handoff exists. Windows retains its deny-write/delete opener;
POSIX retains exclusive nonblocking flock. Path lstat and held-descriptor fstat
device/inode identities are checked on borrowing and before manifest publication.
Pinned boundary/completion hashes are also rechecked before publication, including
registry proofs outside the payload closure. Native payload SHA/fingerprint checks,
T0 verification, append-only receipts and the separate destination writer lock
remain mandatory. Standalone Vault calls keep their existing locking behavior.
