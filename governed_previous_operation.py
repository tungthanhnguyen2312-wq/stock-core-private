"""One fail-closed resolver for a prior governed Daily operation.

The registry selects the prior *session*.  An immutable Daily Producer run then
selects one exact operation for that session.  Filesystem enumeration is used
only to inspect candidates; it is never a selection rule.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from daily_research_session_operations import frozen_input_identities


AVAILABLE = "AVAILABLE"
NO_PRIOR_GOVERNED_SESSION = "NO_PRIOR_GOVERNED_SESSION"
MISSING_GOVERNED_PREVIOUS_OPERATION = "MISSING_GOVERNED_PREVIOUS_OPERATION"
AMBIGUOUS_GOVERNED_PREVIOUS_OPERATION = "AMBIGUOUS_GOVERNED_PREVIOUS_OPERATION"
GOVERNED_PREVIOUS_OPERATION_LINEAGE_MISMATCH = "GOVERNED_PREVIOUS_OPERATION_LINEAGE_MISMATCH"

_OPERATIONS = Path("operations-review") / "daily-research-session-operations-v1"
_PRODUCER_RUNS = Path("operations-review") / "daily-producer-runs-v1"


def _read(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, Mapping) else None


def _identity_map(artifacts: Any) -> dict[str, str] | None:
    if not isinstance(artifacts, Mapping):
        return None
    identities: dict[str, str] = {}
    for name, entry in artifacts.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("artifact_identity"), str):
            return None
        identities[str(name)] = entry["artifact_identity"]
    return identities


def _candidate(operation_dir: Path, session: str, frozen: Mapping[str, str]) -> dict[str, Any]:
    manifest_path = operation_dir / "run_manifest.json"
    bundle_path = operation_dir / "ai_research_session_bundle.json"
    manifest, bundle = _read(manifest_path), _read(bundle_path)
    result: dict[str, Any] = {
        "operation_directory": str(operation_dir),
        "run_manifest_path": str(manifest_path),
        "bundle_path": str(bundle_path),
        "operation_identity": manifest.get("operation_identity") if manifest else None,
        "product_identity": None,
        "bundle_identity": None,
        "disposition": "REJECTED",
        "reason_code": None,
    }
    if manifest is None:
        result["reason_code"] = "RUN_MANIFEST_INVALID_OR_MISSING"
        return result
    if bundle is None:
        result["reason_code"] = "SESSION_BUNDLE_INVALID_OR_MISSING"
        return result
    if manifest.get("market_session") != session or bundle.get("session") != session:
        result["reason_code"] = "SESSION_MISMATCH"
        return result
    operation_identity = manifest.get("operation_identity")
    if not isinstance(operation_identity, str) or bundle.get("operation_identity") != operation_identity:
        result["reason_code"] = "OPERATION_IDENTITY_MISMATCH"
        return result
    product_identity = (manifest.get("outputs") or {}).get("daily_product")
    if not isinstance(product_identity, str) or bundle.get("product_identity") != product_identity:
        result["reason_code"] = "PRODUCT_IDENTITY_MISMATCH"
        return result
    if _identity_map(manifest.get("input_artifacts")) != dict(frozen):
        result["reason_code"] = "FROZEN_INPUT_LINEAGE_MISMATCH"
        return result
    result.update(
        operation_identity=operation_identity,
        product_identity=product_identity,
        bundle_identity=hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        disposition="LINEAGE_QUALIFIED",
        reason_code=None,
    )
    return result


def _pointer_selected_operation(root: Path, session: str) -> tuple[str | None, str | None, str | None]:
    """Return the operation chosen by the immutable run addressed by the latest pointer.

    ``LATEST_COMPLETED_RUN`` is a navigation record, not a standalone authority
    claim.  It is accepted here only when it resolves to a self-consistent,
    immutable Producer run for the registry-selected prior session.
    """
    pointer = _read(root / _PRODUCER_RUNS / "LATEST_COMPLETED_RUN.json")
    if not pointer or pointer.get("session") != session or pointer.get("navigation_only") is not True:
        return None, None, None
    relative = pointer.get("relative_directory")
    run_identity = pointer.get("run_identity")
    operation_identity = pointer.get("daily_session_operation_identity")
    if not all(isinstance(value, str) and value for value in (relative, run_identity, operation_identity)):
        return None, None, "LATEST_COMPLETED_POINTER_INVALID"
    run_dir = (root / _PRODUCER_RUNS / relative).resolve()
    runs_root = (root / _PRODUCER_RUNS).resolve()
    if runs_root not in run_dir.parents:
        return None, None, "LATEST_COMPLETED_POINTER_PATH_INVALID"
    manifest = _read(run_dir / "run_manifest.json")
    if not manifest:
        return None, None, "LATEST_COMPLETED_PRODUCER_RUN_MISSING"
    linked = manifest.get("daily_session_operation") or {}
    if (
        manifest.get("run_identity") != run_identity
        or manifest.get("target_market_session") != session
        or not isinstance(linked, Mapping)
        or linked.get("identity") != operation_identity
        or not isinstance(manifest.get("daily_product_identity"), str)
    ):
        return None, None, "LATEST_COMPLETED_PRODUCER_RUN_LINEAGE_MISMATCH"
    return operation_identity, str(manifest["daily_product_identity"]), None


def resolve_governed_previous_operation(
    current_session: str,
    registry: Mapping[str, Any],
    retained_evidence_root: Path,
) -> dict[str, Any]:
    """Resolve the exact prior Daily operation or return an explicit failure state."""
    completed = registry.get("completed_sessions") or {}
    prior_sessions: list[tuple[str, dict[str, str]]] = []
    for candidate in completed:
        candidate_session = str(candidate)
        if candidate_session >= current_session:
            continue
        try:
            frozen = frozen_input_identities(registry, candidate_session)
        except ValueError:
            continue
        if frozen is not None:
            prior_sessions.append((candidate_session, frozen))
    if not prior_sessions:
        return {"status": NO_PRIOR_GOVERNED_SESSION, "previous_session": None,
                "candidate_count": 0, "qualified_candidate_count": 0, "candidates": []}

    previous_session, frozen = max(prior_sessions, key=lambda item: item[0])
    session_dir = Path(retained_evidence_root) / _OPERATIONS / previous_session
    operation_dirs = [path for path in session_dir.iterdir() if path.is_dir()] if session_dir.is_dir() else []
    candidates = [_candidate(path, previous_session, frozen) for path in operation_dirs]
    qualified = [candidate for candidate in candidates if candidate["disposition"] == "LINEAGE_QUALIFIED"]
    result: dict[str, Any] = {
        "status": None,
        "previous_session": previous_session,
        "candidate_count": len(candidates),
        "qualified_candidate_count": len(qualified),
        "candidates": candidates,
        "selection_basis": None,
    }
    if not candidates:
        result["status"] = MISSING_GOVERNED_PREVIOUS_OPERATION
        return result
    if not qualified:
        result["status"] = GOVERNED_PREVIOUS_OPERATION_LINEAGE_MISMATCH
        return result

    pointed_identity, pointed_product_identity, pointer_error = _pointer_selected_operation(
        Path(retained_evidence_root), previous_session,
    )
    if pointed_identity:
        selected = [
            candidate for candidate in qualified
            if candidate["operation_identity"] == pointed_identity
            and candidate["product_identity"] == pointed_product_identity
        ]
        if len(selected) == 1:
            chosen = selected[0]
            result.update(chosen, status=AVAILABLE,
                          selection_basis="LATEST_COMPLETED_RUN_IMMUTABLE_PRODUCER_RUN_LINEAGE")
            return result
        result["status"] = GOVERNED_PREVIOUS_OPERATION_LINEAGE_MISMATCH
        result["pointer_reason_code"] = "LATEST_COMPLETED_OPERATION_NOT_LINEAGE_QUALIFIED"
        return result
    if len(qualified) == 1:
        result.update(qualified[0], status=AVAILABLE,
                      selection_basis="SOLE_FROZEN_INPUT_LINEAGE_QUALIFIED_OPERATION")
        return result
    result["status"] = AMBIGUOUS_GOVERNED_PREVIOUS_OPERATION
    if pointer_error:
        result["pointer_reason_code"] = pointer_error
    return result
