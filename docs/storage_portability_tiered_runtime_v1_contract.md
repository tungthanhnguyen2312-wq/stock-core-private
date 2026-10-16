# Storage portability and tiered runtime foundation V1

Owner scope: `STOCKLOOKUP_STORAGE_PORTABILITY_AND_TIERED_RUNTIME_FOUNDATION_V1`.
This is a local source foundation and offline acceptance. Production cutover,
acquisition, publication, source retirement and deletion remain unauthorized.
The [capacity](capacity_recovery_phase1_contract.md), [Vault](vault_incremental_snapshot_contract.md),
[host](owner_daily_host_preflight_contract.md) and released T0 origination contracts remain binding.

## Workspace and admission

`runtime_paths.py` extends the existing runtime configuration. With no
`STOCK_LOOKUP_WORKSPACE_PROFILE`, legacy resolution remains in place and W is not
required. An explicitly selected JSON profile has:

```json
{
  "schema": "stocklookup_workspace/v1",
  "parent": "<absolute workspace parent>",
  "roles": {
    "producer": "<parent>/stock-core-private",
    "consumer": "<parent>/ai-core-private",
    "dashboard": "<parent>/market-dashboard",
    "runtime": "<parent>/dashboard-runtime",
    "handoff": "<parent>/stocklookup-ai-handoffs",
    "logs": "<parent>/run-logs",
    "retained": "<parent>/retained-evidence"
  },
  "hot_volume": {"id": "<observed volume GUID>", "label": "<label>", "healthy": true},
  "capacity": {
    "system": {
      "path": "<system volume root>",
      "volume": {"id": "<system GUID>", "label": "<label>", "healthy": true},
      "reserve_bytes": 26843545600
    },
    "workload": {
      "path": "<workspace parent>",
      "volume": {"id": "<hot GUID>", "label": "<label>", "healthy": true},
      "reserve_bytes": 150323855360
    }
  },
  "staging_bytes": 10737418240,
  "writer_bytes": 21474836480
}
```

Paths must be absolute, existing canonical siblings. Missing roles, junctions,
symlinks, wrong GUID/label, unhealthy/missing volumes and conflicting runtime
environment bindings refuse. A profile is operator configuration, not evidence
authority. No profile is installed or activated by this change. Keep it outside
source/evidence; do not put credentials in it.

`workspace_environment()` returns explicit bindings for the existing runtime,
retained-evidence and operation-output contracts plus the exact catalog root.
It does not launch anything. The Owner workflow validates those bindings before
using them. The Python launcher and PowerShell front door use the same configured
roles. `STOCK_LOOKUP_PYTHON` optionally selects an existing interpreter; the legacy
interpreter default remains. `stocklookup.ps1 daily` remains the single Owner
entrypoint. The actual Desktop shortcut is not replaced during offline development.

Release guards preserve canonical path, exact main/origin and publisher/runtime
separation. Origin matching is exact rather than substring based. Volume identity
is rechecked at release boundaries, and changing profile/roots mid-process refuses.
Repository preflight cleanliness, single-writer and safe synchronization remain.
The common sibling layout preserves existing Consumer imports and Dashboard routing.

Capacity admission separately verifies system and workload volumes, free bytes and
directory create rights without writing a probe. Required workload free space is
`max(configured reserve, 140 GiB floor) + staging_bytes + writer_bytes`; the system
floor is 25 GiB on its distinct pinned volume. Invalid lower reserves refuse.
Caller estimates require later measurement; they are not capacity guarantees.
The actual Daily memory/commit/writer gate remains unchanged. Configured storage
admission adds a separate BLOCKED dimension; C system observation is retained.
The workload guard must bind the exact qualified workspace parent and hot-volume
identity; a different disk's free space cannot qualify the hot runtime.
Cold availability is checked only for an explicitly requested archived dependency.

## Immutable identity and storage proofs

`retained_evidence_catalog.register_copy` is an explicitly invoked,
bounded offline API for an already copied immutable file. It reads locked original
and copied files, compares streamed native SHA, verifies volume and stable native
fingerprints, then publishes an exclusive immutable receipt. The caller pins the
returned `{path, sha256}` in the governed catalog or exact in-memory reference.
No existing receipt is replaced. Missing original provenance remains unqualified.
Database, journal, accumulator, cache and temporary candidates refuse.

The receipt schema `stocklookup_storage_location/v1` records original absolute
path, original artifact/session identity, original fingerprint and provenance,
current path/volume/fingerprint, native byte SHA/size and optional T0 proof. A new
location never changes the historical source identity or knowledge time.
`verify_location` rechecks the pinned receipt, current volume, fingerprint and SHA.
It distinguishes invalid proof/identity, wrong or unavailable volume and changed
content through explicit refusal reasons. No pathname-prefix replacement exists.

For T0, `prospective_t0_seal_index.register_portable_copy` additionally calls the original seal verifier against the
original reference. It pins the untouched original index/write-receipt native SHAs,
reference identities and original T0 fingerprint. `load_verified` accepts a copied
snapshot only when both the original seal and this separate location proof match.
The original receipt fingerprint is never fabricated or updated. A storage-only
restore proof cannot qualify T0. The origination reader retains both operation
proofs, original decision identity, handoff, original capture selection, record
identity, byte hash, session and cutoff checks. Storage qualification is additive.
Historical diagnostic/V1 behavior and V2 technical-policy gates remain unchanged.

No sealed JSON, manifest, capture binding, index or original receipt is rewritten.
Storage verification and opt-in feedback reuse digests include both catalog and
storage proof modules. E4's frozen V1 digest construction stays intact; registered
storage inputs have a separate reuse domain. Native fingerprints and hashes still isolate copies.
The existing historical-source diagnostic consumes a separate versioned storage
transition with six exact pre-storage source archives. It verifies active source,
archive hash and the original frozen pins before returning historical bytes.
The released origination V2 transition and every E4 V1/V2 pin remain unchanged;
these archives never execute and never supply live verification/cache identities.

## Catalog, archive and explicit restoration

The existing `retained_evidence_cold_catalog/v1` and its four legacy states remain.
`PRESENT_QUALIFIED` adds `original_path` and pinned `storage_location` to the existing
identity, role, original size/SHA and source/seal provenance fields. The verified
target must equal the catalog root plus its exact `relative_path`. Staged files
elsewhere require explicit qualification at the consumer's chosen root; arbitrary
fallback locations are refused.

`original_path(path, root=...)` resolves only an exact registered original path.
Historical absolute references require an explicit catalog root, or the qualified
workspace environment. Unregistered paths keep legacy behavior. Duplicate original
locations, wrong session, invalid proof and contradictory state fail closed.

`historical_paths` unions exact-depth local discovery with registered dependencies
before sample selection. T0, operations, handoffs, IID, calendars, capture sessions,
marker and verification readers use this boundary. An archived dependency raises
`ArchiveRestoreRequired`; its absent directory cannot shorten a cohort, completed
session depth or maturity. Exact-session MVA/DNSE acquisition guards remain before
network work. W absence is never `NEVER_RETAINED`. A valid qualified hot dependency
can be read independently of W.

Explicit offline archive/restore sequence:

1. Use the existing Vault snapshot API with an exact pinned completed immutable
   boundary and seal/receipt closure; no new inventory or acquisition is performed.
2. While the original is observable, register an archive-object location receipt.
   T0 must pass its original verifier at this step. Pin this as `archive_location`
   in the archive entry; preserve the existing Vault locator.
3. `restore_registered(entry, vault_root, staging_root, receipt_path, ...)` verifies
   the exact pinned COMPLETE Vault manifest, plan/session/source identity, exact
   path/object/SHA/size, archive GUID and optional original location proof. It
   exclusively copies one bounded exact object into staging and verifies SHA and
   both volumes again. A partial failure publishes no qualifying receipt and
   never overwrites a destination. Inspection/recovery of staging is explicit.
4. Restore the complete semantic dependency closure with independent exact entries.
   T0's original index and receipt bytes must accompany its snapshot. No new seal
   is generated. A previously qualified archive T0 proof travels in a new separate
   restore receipt; generic Vault bytes alone grant no T0 authority.
5. Explicitly record `PRESENT_QUALIFIED` with the pinned new receipt in the selected
   operator catalog. Semantic consumers then apply their original qualification.

All functions are ordinary importable APIs. No scheduler, production archive
activation, transparent W reader, redownload, reconstructed capture or retirement
command is introduced. Catalog registration and later cutover need exact operator
review; the empty tracked production catalog remains untouched.

## Acceptance and cross-component boundary

`tests/test_storage_portability.py` uses bounded temporary roots, fake GUID
observers, actual small temporary main-branch Git repositories, native file copies,
Vault manifests and fresh-inode restores. It covers G1–G8 primitives and G10:
legacy behavior, complete sibling role binding, exact branch/origin guards,
capacity/permission refusal, tampering, false reuse, missing/swapped volumes,
portable T0, restoration, origination and capture/maturity continuity.

The G9 boundary test executes the actual Consumer builder and Dashboard publisher
module source with isolated workspace locations and an isolated SQLite database.
Consumer's existing read-only DB connection and Dashboard's existing runtime
resolver read the configured sibling runtime. A child audit guard denies network
and protected source writes; its deliberate forbidden write is denied before I/O.
Neither sibling repository needs source changes for this common-parent layout.
Required release order: Producer foundation first; then separately approve an
operator profile and copy matching Consumer/Dashboard sources. No analytical or
publication transformation is changed. Host-local integration tests explicitly
skip with evidence if those source files are absent in a foreign clone.

This verifies boundary parity, not a full production Daily, public deployment,
real USB/controller failover, large-corpus restore throughput or actual writer
transfer. The historical 45,441-row feedback artifact and October5/October9
production evidence are not loaded or rewritten; their claims rely on preserved
released acceptance, plus hermetic regression coverage. T5/T10/T20 are not inflated.

## Local governance and later gates

The initial exact-file admission was replaced through normal terminal/admit
operations when the launcher ratchet exposed additional manifest/cache scopes.
The recovery commit is retained. The scoped-completion lane belongs to the same
milestone, branch, worktree and Owner directive; it starts no successor.
`ACTIVE_STATE.md` remains under the unrelated VRE lease, so this contract and the
native local checkpoint describe this foundation without editing that leased view.

Later production gates: independently copy and verify standalone Git metadata and
worktrees (the current T worktree still points to C Git metadata), provision and
qualify Python environments, pin actual volumes and measured staging/writer
headroom, verify a consistent staged DB migration, qualify all retained dependency
closures and restored source semantics, update the actual Desktop launcher,
rehearse the full release and writer transfer, then obtain explicit cutover and
exact source-retirement authorization. Offline success grants none of those acts.
S0, LegalCrawler, VRE, Daily runtime, production DB and original evidence are untouched.
