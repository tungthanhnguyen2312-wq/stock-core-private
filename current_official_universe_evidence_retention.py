"""Bounded, operator-safe migration/seed tool logic for
OFFICIAL_SCOPE_EVIDENCE_OPERATIONALIZATION_AND_DASHBOARD_CUTOVER_READINESS_V1.

Promotes an explicitly-named, already-qualified ``current_official_market_universe`` artifact
(optionally HNX/UPCoM security-status enriched -- both share the same identity/contract shape,
see ``current_official_market_universe.verify_retained_artifact``) into its durable, git-tracked
retained-evidence location, so a clean checkout of this repository can resolve it without
depending on the specific worktree that originally produced it.

This is retention/promotion of already-qualified evidence, never new qualification: it performs
no network access, no re-derivation, and no listing-status inference. It never discovers its
source path automatically (no glob, no sibling-worktree search, no latest-mtime pick) -- the
operator names the exact evidence file, exactly like ``entity_classification_contract.py``'s
layered ``config/promoted_*.json`` tiers are populated by an explicit, named tool run rather than
a search.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atomic_io import atomic_copy_file
import current_official_market_universe

CONTRACT_VERSION = "current_official_universe_evidence_retention/v1"

STATUS_RETAINED = "RETAINED"
STATUS_ALREADY_RETAINED_IDENTICAL = "ALREADY_RETAINED_IDENTICAL"


class RetentionError(ValueError):
    """A retention precondition failed; the caller must not proceed with promotion."""


def retain_evidence(
    *,
    source_path: Path | str,
    destination_path: Path | str,
    expected_identity: str | None = None,
) -> dict[str, Any]:
    """Idempotently promote ``source_path`` into ``destination_path``.

    Fails closed (raises ``RetentionError``) on:
      - a missing or unreadable source, or one that is not valid JSON;
      - a source that fails its own self-hash / contract check
        (``current_official_market_universe.verify_retained_artifact``);
      - a source whose ``artifact_identity`` does not match ``expected_identity`` when supplied;
      - an existing destination whose ``artifact_identity`` differs from the source's -- this
        function never silently overwrites a different qualification at the same governed path.

    An existing destination already holding the byte-for-byte same ``artifact_identity`` is a
    no-op success (idempotent: running the same promotion twice is safe).
    """
    src = Path(source_path)
    if not src.is_file():
        raise RetentionError(f"SOURCE_NOT_FOUND:{src}")
    try:
        source_text = src.read_text(encoding="utf-8")
        artifact = json.loads(source_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetentionError(f"SOURCE_NOT_READABLE_JSON:{src}:{exc}") from exc

    current_official_market_universe.verify_retained_artifact(
        artifact, label="RETENTION_SOURCE", expected_identity=expected_identity,
    )

    dest = Path(destination_path)
    if dest.is_file():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RetentionError(f"DESTINATION_NOT_READABLE_JSON:{dest}:{exc}") from exc
        existing_identity = existing.get("artifact_identity")
        if existing_identity != artifact.get("artifact_identity"):
            raise RetentionError(
                f"DESTINATION_CONFLICT:{dest} already holds identity {existing_identity!r}; "
                f"refusing to overwrite with {artifact.get('artifact_identity')!r}"
            )
        return {
            "status": STATUS_ALREADY_RETAINED_IDENTICAL,
            "source": str(src),
            "destination": str(dest),
            "artifact_identity": artifact.get("artifact_identity"),
        }

    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_copy_file(src, dest)
    return {
        "status": STATUS_RETAINED,
        "source": str(src),
        "destination": str(dest),
        "artifact_identity": artifact.get("artifact_identity"),
    }
