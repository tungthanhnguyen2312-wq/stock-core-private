"""Quarantine: first-class isolation for claimed-but-invalid documents.

Quarantine never becomes qualified evidence by side effect: nothing in
this module, or anywhere else in this framework, moves a quarantined item
into the content-addressed retention store (raw/blobs/). See
docs/acquisition_landing_framework.md, "Quarantine semantics".
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import Iterable

from acquisition_landing_atomic_io import atomic_write_bytes, atomic_write_json, read_json
from acquisition_landing_isolation import assert_write_allowed

QUARANTINE_MANIFEST_FILENAME = "quarantine_manifest.json"


@dataclasses.dataclass(frozen=True)
class QuarantineRecord:
    run_id: str
    domain: str
    source_locator: str
    reason: str
    observed_at: str
    byte_size: int | None
    sha256: str | None
    stored_relative_path: str | None
    content_type: str | None
    original_filename: str | None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def quarantine_root(landing_root: Path) -> Path:
    return Path(landing_root) / "quarantine"


def _manifest_path(landing_root: Path) -> Path:
    return quarantine_root(landing_root) / QUARANTINE_MANIFEST_FILENAME


def load_quarantine_manifest(landing_root: Path) -> list:
    return read_json(_manifest_path(landing_root), default=[])


def quarantine_item(
    landing_root: Path,
    *,
    allowed_root: Path,
    protected_roots: Iterable = (),
    extra_protected_paths: Iterable = (),
    run_id: str,
    domain: str,
    source_locator: str,
    reason: str,
    observed_at: str,
    data: bytes | None,
    sha256: str | None,
    content_type: str | None,
    original_filename: str | None,
) -> QuarantineRecord:
    """Append one quarantine record, preserving bytes when given (even
    zero-length) since they are safe and useful to keep for diagnosis.
    Never writes to raw/blobs/ - only ever under quarantine/."""
    landing_root = Path(landing_root)
    stored_relative_path = None

    if data is not None:
        if sha256:
            blob_name = f"{sha256}.bin"
        else:
            fallback = hashlib.sha256(f"{run_id}\n{source_locator}".encode("utf-8")).hexdigest()
            blob_name = f"unhashable-{fallback}.bin"
        blob_path = quarantine_root(landing_root) / "blobs" / blob_name
        assert_write_allowed(
            blob_path,
            allowed_root=allowed_root,
            protected_roots=protected_roots,
            extra_protected_paths=extra_protected_paths,
        )
        atomic_write_bytes(blob_path, data)
        stored_relative_path = str(blob_path.relative_to(landing_root))

    record = QuarantineRecord(
        run_id=run_id,
        domain=domain,
        source_locator=source_locator,
        reason=reason,
        observed_at=observed_at,
        byte_size=len(data) if data is not None else None,
        sha256=sha256,
        stored_relative_path=stored_relative_path,
        content_type=content_type,
        original_filename=original_filename,
    )

    manifest_path = _manifest_path(landing_root)
    assert_write_allowed(
        manifest_path,
        allowed_root=allowed_root,
        protected_roots=protected_roots,
        extra_protected_paths=extra_protected_paths,
    )
    existing = load_quarantine_manifest(landing_root)
    existing.append(record.to_dict())
    atomic_write_json(manifest_path, existing)

    return record
