# Isolated Bulk Acquisition Framework V1

Reusable foundation for bounded, resumable, provenance-preserving bulk
document acquisition and immutable retention. First supported domain:
official financial filings.

## Purpose

Future work needs to retain many official documents (financial filings
today; corporate-action notices or other domains later) at scale, without
repeating the collection/checkpoint/quarantine machinery per domain. This
framework provides that reusable substrate: acquire, hash, deduplicate,
version, and quarantine raw documents into an isolated, content-addressed
landing area, with crash-safe checkpoint/resume and a machine-readable
manifest. It is deliberately **not** a large generic platform - it
implements exactly the separation of concerns required to add a second
document domain later without rewriting the retention core.

This side program is independent of, and does not modify, the core
product gate `P0-A.3E` (governed multi-session prospective PIT price
qualification) or the existing pillar-B official-document pipeline
(`official_document_acquisition.py`, `official_document_store.py`,
`official_source_registry.py`, `official_document_discovery.py`). Those
modules remain the production authority for corporate-action document
acquisition; this framework does not replace, wrap, or call them, and
nothing here changes their behavior.

## Acquisition vs qualification

**Retention of raw official evidence does not itself promote the
evidence, observation, financial fact, feature, or provider to analytical
authority.** Every `RawDocumentRecord` this framework produces carries
`qualification_state = "unknown"` unconditionally - see
`acquisition_landing_contract.QUALIFICATION_STATE_UNKNOWN`. No code path
in this framework ever sets it to anything else; a later, separate
milestone owns semantic qualification, extraction, or promotion. This
framework does not implement canonical financial-fact extraction, does
not perform OCR, and does not touch existing evidence cohorts, citations,
or research eligibility.

## What this framework does not infer

Per its own contract, this framework never infers or fabricates:
publication date (only recorded when the source directly states it),
document semantics, statement scope, audit status, financial period, or
supersession from filenames or URL patterns. A "new version" relationship
(`supersedes_sha256`) is only ever recorded when *directly observed*: the
same logical identity (domain + source locator) previously resolved to a
different content hash. Nothing is inferred from a date, filename, or
plausibility.

## Architecture

Seven separated concerns, each owned by one small module (repository
convention here is small, single-purpose modules at the repo root, not a
package directory - this follows the same shape as the existing
`official_document_*.py` family):

| # | Concern | Module |
|---|---|---|
| 1 | Acquisition specification | `acquisition_landing_contract.py` (`AcquisitionSpec`) |
| 2 | Source/document identity | `acquisition_landing_identity.py` |
| 3 | Raw immutable blob | `acquisition_landing_retention.py` (`raw/blobs/`) |
| 4 | Acquisition observation | `acquisition_landing_contract.py` (`RawDocumentRecord`) |
| 5 | Manifest/checkpoint state | `acquisition_landing_checkpoint.py` |
| 6 | Quarantine/failure record | `acquisition_landing_quarantine.py` |
| 7 | Qualification state | `acquisition_landing_contract.QUALIFICATION_STATE_UNKNOWN` (marker only) |

Supporting modules: `acquisition_landing_atomic_io.py` (shared crash-safe
JSON/bytes write primitive - tempfile in the target directory, then
`os.replace`, used by every writer so there is one write discipline, not
three) and `acquisition_landing_isolation.py` (the protected-root guard).

Required dependency direction, enforced by import structure (verified by
`tests/test_acquisition_landing_no_network_dependency.py`'s module list
and by inspection - nothing here imports the other direction):

```
source adapter (financial_filings_replay_adapter.py)
        v
acquisition contract (acquisition_landing_contract.py)
        v
retention / checkpoint / quarantine
        v
manifest / report
```

Nothing in this framework imports valuation engines, research-eligibility
code, AI/Consumer code, or Dashboard code. `acquisition_landing_retention.py`,
`_checkpoint.py`, `_quarantine.py`, `_identity.py`, `_isolation.py`, and
`_atomic_io.py` import no networking or LLM library (enforced by AST
inspection in the no-network-dependency test, not a substring check).

### First domain: official financial filings

`financial_filings_replay_adapter.py` is the one domain-specific module.
It reads Stock Lookup's existing governed evidence corpus
(`stock-core-private/operations-review/governed-official-evidence-v1/`,
read-only) and turns each already-retained record into an
`AcquisitionSpec` + bytes, replayed through the domain-agnostic core. It
performs no network call.

## Landing layout

Root: `C:\Projects\StockLookup\data-landing\official-financial-filings-v1\`

```
raw/blobs/<sha256>.pdf          content-addressed immutable blobs
manifests/content_manifest.json  durable truth: sha256 -> blob info,
                                  logical_identity -> latest sha256
checkpoints/<run_id>.checkpoint.json   per-run resumable progress marker
quarantine/blobs/...             quarantined bytes (preserved when safe)
quarantine/quarantine_manifest.json   append-only quarantine records
run-reports/<run_id>.report.json      terminal per-run summary
```

No generated/raw acquisition payload is written into source Git; this
entire tree lives outside both `stock-core-private` and any other
repository.

## Manifest schema

`manifests/content_manifest.json`:

```json
{
  "schema_version": "1.0.0",
  "blobs": {
    "<sha256>": {
      "sha256": "...", "byte_size": 12345, "storage_locator": "raw/blobs/<sha256>.pdf",
      "content_type": "application/pdf", "first_observed_at": "...", "first_acquired_run_id": "..."
    }
  },
  "latest_hash_by_logical_identity": {"<sha256(domain\\nsource_locator)>": "<sha256>"}
}
```

`run-reports/<run_id>.report.json` carries `run_id`, `domain`, `status`,
`attempted`/`succeeded`/`skipped`/`quarantined`/`failed_retryable`/
`failed_permanent` counts, and the full list of per-document
`RawDocumentRecord` dicts (the section-5 raw-document contract: run
identity, domain, issuer/document-type when known, source authority
class, source locator, observed-at, source-published-at only when
directly known, HTTP status, filename, content type, byte size, SHA-256,
storage locator, acquisition method/version, `supersedes_sha256` only
when deterministically known, outcome, outcome reason, and the
`qualification_state` boundary marker).

Both files are written via `acquisition_landing_atomic_io.atomic_write_json`
(tempfile in the same directory, then `os.replace`) and with
`sort_keys=True`, so equivalent completed state serializes byte-identically
run to run (proven in `test_acquisition_landing_checkpoint.py::ManifestDeterminismTests`).

## Checkpoint/resume semantics

`content_manifest.json` is the durable source of truth for "what content
is already retained." The per-run `checkpoints/<run_id>.checkpoint.json`
is a lighter, run-scoped optimization: it records which logical
identities this exact run has already completed, so restarting the same
`run_id` after an interruption skips them without re-reading or
re-hashing their bytes. It is written after *every* item, not just at the
end, so an interruption at any point leaves a valid, resumable file.

If the checkpoint is ever lost but `raw/blobs/` and
`manifests/content_manifest.json` survive, correctness is not affected:
`retain()` independently re-verifies content-addressed existence on disk
before treating anything as already-present, so no blob is ever
duplicated. Only the resume *optimization* is lost (a lost checkpoint
costs a re-hash per item, not a re-download, and never costs a duplicate
write); if `content_manifest.json` itself is lost while blobs survive,
existing blobs are still correctly recognized (their `first_observed_at`/
`first_acquired_run_id` provenance is then reconstructed from the
recovery run rather than the true original values - restore
`content_manifest.json` from backup/VCS if that provenance matters more
than the bytes).

Resuming never repeats completed immutable work unnecessarily, never
duplicates a blob, and reruns after an interruption converge on the same
retained corpus as one uninterrupted run - see
`tests/test_acquisition_landing_checkpoint.py`.

## Quarantine semantics

Quarantine is first-class, not a side effect of retention failing. A
claimed document that arrives with bytes but fails validation (invalid
PDF header, empty payload, content-type mismatch, or a declared-vs-actual
SHA-256 contradiction) is routed to `quarantine_item()`: its bytes are
preserved (when given, even zero-length) alongside a reason and
provenance record in `quarantine/quarantine_manifest.json`, appended
atomically. Quarantine **never** writes into `raw/blobs/` and is never
consulted by the dedup/reuse path - re-submitting the same bad bytes
quarantines again rather than silently becoming evidence (see
`test_quarantine_never_becomes_qualified_evidence_automatically`). A pure
transport failure (no bytes obtained at all) is a `FAILED_RETRYABLE` or
`FAILED_PERMANENT` outcome, not quarantine - quarantine specifically
means "we received something, and it's bad."

## Acquisition outcomes

`AcquisitionOutcome`: `ACQUIRED`, `ALREADY_PRESENT_IDENTICAL`,
`QUARANTINED`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, `UNSUPPORTED`,
`BLOCKED_BY_POLICY`. Every non-success record carries an explicit
`outcome_reason`; `build_record()` structurally refuses to construct a
success record with no content hash or a failure record with no reason -
a missing/failed document can never become a silently-empty success.

A concrete `official_document_acquisition.py` fetch-layer `state` (e.g.
`cached_valid`, `timeout`, `hash_conflict`, `refused_by_source_registry`)
is a lower-level, transport-specific classification that a future adapter
integrating that fetcher would map into this framework's more general
seven-value outcome (for example: `cached_valid` -> `ALREADY_PRESENT_IDENTICAL`,
`timeout` -> `FAILED_RETRYABLE`, `refused_by_source_registry` ->
`BLOCKED_BY_POLICY`). No such adapter is implemented in this milestone.

## Protected roots

`acquisition_landing_isolation.assert_write_allowed()` runs before every
write this framework performs, and fails closed on two independent
checks: the target must resolve strictly under the allowed landing root,
**and** must not resolve under any protected root. At minimum, protected
by default (relative to the workspace root): `dashboard-runtime`,
`ai-runtime`, `ai-core-private`, `publish`, and the primary
`stock-core-private` checkout (this framework's own worktree is a
sibling of that checkout, not inside it). Any filename beginning
`vn_stock.db` is additionally rejected regardless of directory. The
financial-filings CLI also passes the real governed-evidence source root
as an `extra_protected_paths` entry, so the very corpus this domain reads
from can never be accidentally written to. See
`tests/test_acquisition_landing_isolation.py` (uses the real absolute
protected paths as inputs; the guard performs no filesystem I/O of its
own, so this is safe without touching those directories) and
`tests/test_acquisition_landing_retention.py::ProtectedRootIntegrationTests`.

## Operator invocation

Foreground, bounded, single-shot - no daemon, scheduler, timer, or
background loop; the operator starts every run.

```bash
python tools/acquisition_landing_operator.py replay-financial-filings \
    --run-id <run-id> \
    --tickers HPG,VNM,VCB \
    --workspace-root "C:\Projects\StockLookup"
```

Omit `--run-id` to auto-generate one. Reuse an existing `--run-id` to
resume an interrupted run; pass `--no-resume` to ignore any existing
checkpoint for that id and start over (this still deduplicates at the
content layer - it only discards the run-scoped skip optimization).
`--governed-evidence-root` and `--landing-root` override their computed
defaults when needed. The command prints `attempted/succeeded/skipped/
quarantined/failed_retryable/failed_permanent` and writes the full
run-report JSON.

## Recovery procedure

- **Interrupted run**: rerun the identical command with the same
  `--run-id`. Already-completed items are skipped via the checkpoint;
  remaining items are processed; no blob is duplicated.
- **Lost checkpoint, landing root intact**: rerun with the same
  `--run-id` (or a new one - it no longer matters for correctness).
  Every already-retained document is recognized as
  `ALREADY_PRESENT_IDENTICAL` via on-disk hash verification; nothing is
  duplicated. A fresh checkpoint is written going forward.
- **Suspected corruption of a retained blob**: any acquisition attempt
  that resolves to that blob's content address will raise
  `HashConflictError` instead of silently trusting it (see
  `HashVerificationTests.test_existing_blob_hash_is_verified_before_reuse`).
  Investigate and restore the specific blob from a known-good source
  before retrying; do not delete-and-reacquire blindly, since that would
  also require re-verifying every manifest entry that names it.
- **Lost `content_manifest.json`, blobs intact**: recognized without
  duplication as above; original `first_observed_at`/`first_acquired_run_id`
  provenance for pre-existing blobs is not recoverable from the blobs
  alone (they get regenerated from the recovery run) - restore from
  backup/VCS if that specific provenance matters.

## Future reuse: a corporate-actions adapter (not implemented here)

A future corporate-action-notice acquisition domain could reuse every
domain-agnostic module unchanged (`_contract.py`, `_identity.py`,
`_isolation.py`, `_retention.py`, `_checkpoint.py`, `_quarantine.py`,
`_atomic_io.py`) by adding one new source adapter analogous to
`financial_filings_replay_adapter.py` - e.g.
`corporate_action_notice_acquisition_adapter.py` - that yields
`AcquisitionSpec`s with `domain="official-corporate-action-notices-v1"`
and its own `source_authority_class`/`issuer_identity`/`document_type`
values, plus a landing root
`data-landing/official-corporate-action-notices-v1/`. No corporate-action
acquisition code is implemented in this milestone; this section documents
the extension point only, per this milestone's explicit scope boundary.
