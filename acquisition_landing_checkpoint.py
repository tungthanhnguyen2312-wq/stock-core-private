"""Run-level checkpoint/manifest state: crash-safe, atomic, resumable.

content_manifest.json is the durable source of truth for "what content is
already retained" (keyed by sha256, plus a locator -> latest-hash index for
deterministic supersession). A per-run checkpoint file is a lighter,
run-scoped progress marker that lets an interrupted run skip specs it
already finished without re-reading/re-hashing their bytes; if the
checkpoint were ever lost, the content manifest alone (via retain()'s own
on-disk existence + hash-reverification check) is still sufficient to
resume correctly - dedup would just cost a re-hash instead of being free.
See docs/acquisition_landing_framework.md, "Checkpoint/resume semantics".
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Callable, Iterable

from acquisition_landing_atomic_io import atomic_write_json, read_json
from acquisition_landing_contract import (
    MANIFEST_SCHEMA_VERSION,
    AcquisitionContractError,
    AcquisitionOutcome,
    AcquisitionSpec,
    PERMANENT_FAILURE_OUTCOMES,
    RETRYABLE_OUTCOMES,
    RawDocumentRecord,
    SUCCESS_OUTCOMES,
)
from acquisition_landing_identity import logical_identity
from acquisition_landing_isolation import assert_write_allowed
from acquisition_landing_retention import retain

CONTENT_MANIFEST_FILENAME = "content_manifest.json"


def content_manifest_path(landing_root: Path) -> Path:
    return Path(landing_root) / "manifests" / CONTENT_MANIFEST_FILENAME


def checkpoint_path(landing_root: Path, run_id: str) -> Path:
    return Path(landing_root) / "checkpoints" / f"{run_id}.checkpoint.json"


def run_report_path(landing_root: Path, run_id: str) -> Path:
    return Path(landing_root) / "run-reports" / f"{run_id}.report.json"


def _empty_manifest() -> dict:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "blobs": {},
        "latest_hash_by_logical_identity": {},
    }


def load_content_manifest(landing_root: Path) -> dict:
    manifest = read_json(content_manifest_path(landing_root), default=None)
    return manifest if manifest is not None else _empty_manifest()


def load_checkpoint(landing_root: Path, run_id: str) -> dict:
    return read_json(
        checkpoint_path(landing_root, run_id),
        default={"run_id": run_id, "status": "not_started", "completed": {}},
    )


def _write_content_manifest(landing_root, allowed_root, protected_roots, extra_protected_paths, manifest: dict) -> None:
    path = content_manifest_path(landing_root)
    assert_write_allowed(
        path, allowed_root=allowed_root, protected_roots=protected_roots, extra_protected_paths=extra_protected_paths
    )
    atomic_write_json(path, manifest)


def _write_checkpoint(landing_root, allowed_root, protected_roots, extra_protected_paths, checkpoint: dict) -> None:
    path = checkpoint_path(landing_root, checkpoint["run_id"])
    assert_write_allowed(
        path, allowed_root=allowed_root, protected_roots=protected_roots, extra_protected_paths=extra_protected_paths
    )
    atomic_write_json(path, checkpoint)


def _record_into_manifest(manifest: dict, spec: AcquisitionSpec, record: RawDocumentRecord) -> dict:
    if record.outcome not in SUCCESS_OUTCOMES or record.sha256 is None:
        return manifest
    if record.sha256 not in manifest["blobs"]:
        manifest["blobs"][record.sha256] = {
            "sha256": record.sha256,
            "byte_size": record.byte_size,
            "storage_locator": record.storage_locator,
            "content_type": record.content_type,
            "first_observed_at": record.observed_at,
            "first_acquired_run_id": record.run_id,
        }
    manifest["latest_hash_by_logical_identity"][logical_identity(spec)] = record.sha256
    return manifest


@dataclasses.dataclass
class RunReport:
    run_id: str
    domain: str
    status: str
    attempted: int = 0
    succeeded: int = 0
    skipped: int = 0
    quarantined: int = 0
    failed_retryable: int = 0
    failed_permanent: int = 0
    records: list = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def process_batch(
    landing_root: Path,
    items: Iterable[tuple[AcquisitionSpec, dict]],
    *,
    run_id: str,
    domain: str,
    allowed_root: Path,
    protected_roots: Iterable = (),
    extra_protected_paths: Iterable = (),
    observed_at_fn: Callable[[], str],
    resume: bool = True,
) -> RunReport:
    """items yields (spec, retain_kwargs) pairs; retain_kwargs holds the
    data=/fetch_error=/declared_sha256=/... arguments retain() accepts
    beyond spec/run_id/observed_at/allowed_root/protected_roots/
    known_latest_hash_for_logical_identity (all supplied here).

    Crash-safe and resumable: the checkpoint is written after every single
    item, not just at the end, and a spec already marked completed in a
    prior attempt at this exact run_id is skipped without being reread or
    rehashed. One item's failure (including an unexpected
    AcquisitionContractError) is recorded and the batch continues - it
    never aborts unrelated remaining items.
    """
    landing_root = Path(landing_root)
    manifest = load_content_manifest(landing_root)
    checkpoint = (
        load_checkpoint(landing_root, run_id) if resume else {"run_id": run_id, "status": "not_started", "completed": {}}
    )
    checkpoint["status"] = "in_progress"
    checkpoint.setdefault("completed", {})

    report = RunReport(run_id=run_id, domain=domain, status="in_progress")

    for spec, retain_kwargs in items:
        report.attempted += 1
        li = logical_identity(spec)

        if li in checkpoint["completed"]:
            report.skipped += 1
            report.records.append(checkpoint["completed"][li])
            continue

        try:
            known_latest = manifest["latest_hash_by_logical_identity"].get(li)
            record = retain(
                landing_root,
                spec,
                run_id=run_id,
                observed_at=observed_at_fn(),
                allowed_root=allowed_root,
                protected_roots=protected_roots,
                extra_protected_paths=extra_protected_paths,
                known_latest_hash_for_logical_identity=known_latest,
                **retain_kwargs,
            )
        except AcquisitionContractError as exc:
            record_dict = {
                "run_id": run_id,
                "domain": spec.domain,
                "source_locator": spec.source_locator,
                "outcome": AcquisitionOutcome.FAILED_PERMANENT.value,
                "outcome_reason": f"{type(exc).__name__}: {exc}",
            }
            report.failed_permanent += 1
            report.records.append(record_dict)
            checkpoint["completed"][li] = record_dict
            _write_checkpoint(landing_root, allowed_root, protected_roots, extra_protected_paths, checkpoint)
            continue

        record_dict = record.to_dict()
        report.records.append(record_dict)
        checkpoint["completed"][li] = record_dict

        if record.outcome in SUCCESS_OUTCOMES:
            report.succeeded += 1
            manifest = _record_into_manifest(manifest, spec, record)
            _write_content_manifest(landing_root, allowed_root, protected_roots, extra_protected_paths, manifest)
        elif record.outcome == AcquisitionOutcome.QUARANTINED:
            report.quarantined += 1
        elif record.outcome in RETRYABLE_OUTCOMES:
            report.failed_retryable += 1
        elif record.outcome in PERMANENT_FAILURE_OUTCOMES:
            report.failed_permanent += 1

        _write_checkpoint(landing_root, allowed_root, protected_roots, extra_protected_paths, checkpoint)

    checkpoint["status"] = "completed"
    _write_checkpoint(landing_root, allowed_root, protected_roots, extra_protected_paths, checkpoint)

    report.status = "completed"
    report_path = run_report_path(landing_root, run_id)
    assert_write_allowed(
        report_path,
        allowed_root=allowed_root,
        protected_roots=protected_roots,
        extra_protected_paths=extra_protected_paths,
    )
    atomic_write_json(report_path, report.to_dict())

    return report
