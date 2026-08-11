"""Versioned Structured Observability Event Contract for Producer Pipeline.

Emits deterministic, machine-readable event records for artifact generation,
pre-promotion validation, atomic promotion, manifest verification, and publishing.
Prevents logging payload contents, secrets, or ambiguous success states.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"


class EventStage(str, Enum):
    ARTIFACT_GENERATION = "artifact_generation"
    POST_FOCUS_STAGE = "post_focus_stage"
    PRE_PROMOTION_VALIDATION = "pre_promotion_validation"
    ATOMIC_PROMOTION = "atomic_promotion"
    MANIFEST_VERIFICATION = "manifest_verification"
    PUBLISH_DASHBOARD = "publish_dashboard"


class EventOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


def build_observability_event(
    stage: str | EventStage,
    outcome: str | EventOutcome,
    *,
    artifact_filename: str | None = None,
    sha256: str | None = None,
    size_bytes: int | None = None,
    price_basis: str | None = None,
    volume_basis: str | None = None,
    is_actionable: bool | None = None,
    reason: str | None = None,
    error_type: str | None = None,
    is_live_write: bool = False,
    target_path: str | Path | None = None,
    provenance: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, versioned observability event record."""
    stage_str = str(stage.value if isinstance(stage, EventStage) else stage).strip().lower()
    outcome_str = str(outcome.value if isinstance(outcome, EventOutcome) else outcome).strip().lower()

    ts = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": ts,
        "stage": stage_str,
        "outcome": outcome_str,
        "artifact_identity": {
            "filename": artifact_filename,
            "sha256": sha256,
            "size_bytes": size_bytes,
        },
        "basis_contract_status": {
            "price_basis": price_basis,
            "volume_basis": volume_basis,
            "is_actionable": is_actionable,
        },
        "failure_reason": {
            "reason": reason,
            "error_type": error_type,
        } if outcome_str == EventOutcome.FAILED.value or reason else None,
        "production_state": {
            "is_live_write": is_live_write,
            "target_path": str(target_path) if target_path else None,
        },
        "provenance": dict(provenance) if isinstance(provenance, Mapping) else None,
    }


def emit_observability_event(
    event: Mapping[str, Any],
    log_path: Path | str | None = None,
) -> str:
    """Serialize observability event to deterministic JSON string and optionally append to log_path."""
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    return payload
