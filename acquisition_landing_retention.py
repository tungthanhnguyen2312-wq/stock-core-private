"""Content-addressed immutable retention - the single-document write path.

retain() decides ACQUIRED vs ALREADY_PRESENT_IDENTICAL vs QUARANTINED vs a
FAILED_*/UNSUPPORTED/BLOCKED_BY_POLICY outcome for one document, and
performs (or refuses) the corresponding write. It never touches aggregate
manifest/checkpoint state - see acquisition_landing_checkpoint.py for the
batch/resume orchestration that calls this once per document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping

from acquisition_landing_atomic_io import atomic_write_bytes
from acquisition_landing_contract import (
    AcquisitionOutcome,
    AcquisitionSpec,
    FetchError,
    HashConflictError,
    RawDocumentRecord,
    build_record,
)
from acquisition_landing_identity import content_sha256
from acquisition_landing_isolation import assert_write_allowed
from acquisition_landing_quarantine import quarantine_item
from temporal_retention import capture_raw_receipt

BLOBS_SUBDIR = ("raw", "blobs")

Validator = Callable[[bytes, "str | None"], "str | None"]


def blobs_dir(landing_root: Path) -> Path:
    result = Path(landing_root)
    for part in BLOBS_SUBDIR:
        result = result / part
    return result


def blob_path(landing_root: Path, sha256: str, suffix: str) -> Path:
    return blobs_dir(landing_root) / f"{sha256}{suffix}"


def default_pdf_validator(data: bytes, content_type: str | None) -> str | None:
    """Returns None if valid, else a short machine-readable reason."""
    if not data:
        return "empty_document"
    if not data.startswith(b"%PDF-"):
        return "not_a_pdf_header"
    if content_type is not None and content_type != "application/pdf":
        return f"content_type_mismatch:{content_type}"
    return None


def retain(
    landing_root: Path,
    spec: AcquisitionSpec,
    *,
    run_id: str,
    observed_at: str,
    allowed_root: Path,
    protected_roots: Iterable = (),
    extra_protected_paths: Iterable = (),
    data: bytes | None = None,
    fetch_error: FetchError | None = None,
    declared_sha256: str | None = None,
    http_status: int | None = None,
    content_type: str | None = None,
    original_filename: str | None = None,
    source_published_at: str | None = None,
    publication_authority_tier: str = "UNVERIFIED",
    provider_or_source: str | None = None,
    provider_reported_date: str | None = None,
    provider_record_update_at: str | None = None,
    provider_event_at: str | None = None,
    http_headers: Mapping[str, object] | None = None,
    known_first_observed_at: str | None = None,
    legacy_first_observed_unknown: bool = False,
    known_latest_hash_for_logical_identity: str | None = None,
    validator: Validator | None = default_pdf_validator,
    file_suffix: str = ".pdf",
) -> RawDocumentRecord:
    landing_root = Path(landing_root)

    if data is None and fetch_error is None:
        raise ValueError("retain() requires data or fetch_error - never a silent empty success")

    if fetch_error is not None and data is None:
        return build_record(
            run_id=run_id,
            spec=spec,
            observed_at=observed_at,
            outcome=fetch_error.outcome(),
            outcome_reason=fetch_error.detail,
            http_status=http_status,
            source_published_at=source_published_at,
        )

    assert data is not None
    temporal = capture_raw_receipt(
        data=data,
        raw_received_at=observed_at,
        source_identity=spec.source_locator,
        provider_or_source=provider_or_source or spec.source_authority_class,
        acquisition_method=spec.acquisition_method,
        source_published_at=source_published_at,
        publication_authority_tier=publication_authority_tier,
        provider_reported_date=provider_reported_date,
        provider_record_update_at=provider_record_update_at,
        provider_event_at=provider_event_at,
        http_headers=http_headers,
        content_type=content_type,
        known_first_observed_at=known_first_observed_at,
        legacy_first_observed_unknown=legacy_first_observed_unknown,
    )

    if declared_sha256 is not None:
        actual = content_sha256(data)
        if actual != declared_sha256:
            q = quarantine_item(
                landing_root,
                allowed_root=allowed_root,
                protected_roots=protected_roots,
                extra_protected_paths=extra_protected_paths,
                run_id=run_id,
                domain=spec.domain,
                source_locator=spec.source_locator,
                reason=f"declared_sha256_mismatch:declared={declared_sha256}:actual={actual}",
                observed_at=observed_at,
                data=data,
                sha256=actual,
                content_type=content_type,
                original_filename=original_filename,
            )
            return build_record(
                run_id=run_id,
                spec=spec,
                observed_at=observed_at,
                outcome=AcquisitionOutcome.QUARANTINED,
                outcome_reason=q.reason,
                http_status=http_status,
                content_type=content_type,
                byte_size=len(data),
                sha256=actual,
                original_filename=original_filename,
                source_published_at=source_published_at,
                temporal_retention=temporal,
            )

    invalid_reason = validator(data, content_type) if validator else None
    if invalid_reason:
        q = quarantine_item(
            landing_root,
            allowed_root=allowed_root,
            protected_roots=protected_roots,
            extra_protected_paths=extra_protected_paths,
            run_id=run_id,
            domain=spec.domain,
            source_locator=spec.source_locator,
            reason=invalid_reason,
            observed_at=observed_at,
            data=data,
            sha256=content_sha256(data) if data else None,
            content_type=content_type,
            original_filename=original_filename,
        )
        return build_record(
            run_id=run_id,
            spec=spec,
            observed_at=observed_at,
            outcome=AcquisitionOutcome.QUARANTINED,
            outcome_reason=q.reason,
            http_status=http_status,
            content_type=content_type,
            byte_size=len(data),
            sha256=q.sha256,
            original_filename=original_filename,
            source_published_at=source_published_at,
            temporal_retention=temporal,
        )

    sha256 = content_sha256(data)
    target = blob_path(landing_root, sha256, file_suffix)
    assert_write_allowed(
        target,
        allowed_root=allowed_root,
        protected_roots=protected_roots,
        extra_protected_paths=extra_protected_paths,
    )

    if target.exists():
        on_disk_hash = content_sha256(target.read_bytes())
        if on_disk_hash != sha256:
            raise HashConflictError(
                f"existing blob at {target} hashes to {on_disk_hash}, expected {sha256}"
            )
        return build_record(
            run_id=run_id,
            spec=spec,
            observed_at=observed_at,
            outcome=AcquisitionOutcome.ALREADY_PRESENT_IDENTICAL,
            outcome_reason=None,
            http_status=http_status,
            content_type=content_type,
            byte_size=len(data),
            sha256=sha256,
            storage_locator=str(target.relative_to(landing_root)),
            original_filename=original_filename,
            source_published_at=source_published_at,
            temporal_retention=temporal,
        )

    atomic_write_bytes(target, data)
    verify_hash = content_sha256(target.read_bytes())
    if verify_hash != sha256:
        raise HashConflictError(
            f"post-write verification failed for {target}: wrote {sha256}, read back {verify_hash}"
        )

    supersedes = None
    if known_latest_hash_for_logical_identity and known_latest_hash_for_logical_identity != sha256:
        supersedes = known_latest_hash_for_logical_identity

    return build_record(
        run_id=run_id,
        spec=spec,
        observed_at=observed_at,
        outcome=AcquisitionOutcome.ACQUIRED,
        outcome_reason=None,
        http_status=http_status,
        content_type=content_type,
        byte_size=len(data),
        sha256=sha256,
        storage_locator=str(target.relative_to(landing_root)),
        original_filename=original_filename,
        source_published_at=source_published_at,
        supersedes_sha256=supersedes,
        temporal_retention=temporal,
    )
