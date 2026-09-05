"""Immutable prospective T0 snapshots for canonical Integrated Decisions.

The canonical post-close bundle is a useful handoff index, but its historical
``integrated_investment_decision_product`` path is a session-shaped working
path.  It is not itself an immutable T0 container.  This module seals the
already-produced decision record at T0 under a content-addressed path, binds it
to the completed Daily operation, and leaves every later outcome observation in
a separate downstream artifact.

It deliberately serializes only conditions already emitted by
``tactical_confirmation_invalidation_boundaries``.  It neither creates a
second strategy engine nor turns a research boundary into an execution order.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "prospective_decision_snapshot/v1"
CONDITION_CONTRACT_VERSION = "retained_strategy_boundary_condition/v1"
HEALTH_CONTRACT_VERSION = "prospective_decision_corpus_health/v1"
SNAPSHOT_PREFIX = "prospective_decision_snapshot:"
RECORD_PREFIX = "prospective_decision_snapshot_record:"

GENUINE = "GENUINE_PROSPECTIVE_DECISION"
EXCLUDED = "EXCLUDE_TEMPORAL_PROVENANCE_UNQUALIFIED"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"

REQUIRED_AXES = (
    "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM",
    "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "OPPORTUNITY_PRIORITY",
)
_REQUIRED_AXIS_FIELDS = (
    "state", "fitness", "supporting_reason_codes", "contradicting_reason_codes",
    "blocker_reason_codes", "method", "lineage",
)


class ProspectiveDecisionRetentionError(ValueError):
    """Raised when a prospective snapshot cannot prove its retained lineage."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _identity(payload: dict[str, Any], prefix: str, field: str) -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _condition_operator(operator: Any) -> str | None:
    return {
        "FUTURE_CLOSE_GT_RESISTANCE_LEVEL": ">",
        "FUTURE_CLOSE_LT_RESISTANCE_LEVEL": "<",
        "FUTURE_CLOSE_LT_SUPPORT_LEVEL": "<",
    }.get(operator)


def serialize_boundary_condition(
    boundary: Mapping[str, Any] | None, *, role: str, source_strategy_identity: str | None,
) -> dict[str, Any]:
    """Preserve existing boundary semantics without reducing a narrative rule to one.

    Only an existing ``READY`` close-vs-fixed-T0-level boundary is evaluable
    from the retained close-series contract.  Dynamic MA/momentum boundaries
    stay fully serialized, but explicitly require an already-retained future
    strategy measurement rather than a new evaluator here.
    """
    raw = dict(boundary or {})
    operator = _condition_operator(raw.get("comparison_operator"))
    level = raw.get("baseline_value")
    fixed_close = (
        raw.get("status") == "READY"
        and raw.get("source_metric") in {"support", "resistance"}
        and operator is not None
        and isinstance(level, (int, float))
    )
    if fixed_close:
        status = "MACHINE_EVALUABLE"
        reason_codes = ["EXISTING_READY_FIXED_T0_CLOSE_BOUNDARY"]
        reference_field = "close"
        activation = "FIRST_LATER_COMPLETED_SESSION_WITH_RETAINED_CLOSE_SATISFIES_FIXED_T0_BOUNDARY"
    elif raw:
        status = "NOT_MACHINE_EVALUABLE"
        reason_codes = [
            "EXISTING_BOUNDARY_NOT_REDUCED_TO_NEW_TRIGGER_ENGINE",
            "FUTURE_STRATEGY_MEASUREMENT_REQUIRED" if raw.get("status") == "READY" else "BOUNDARY_NOT_READY_OR_NARRATIVE",
        ]
        reference_field = raw.get("source_metric")
        activation = "SERIALIZED_EXISTING_STRATEGY_SEMANTICS_ONLY"
    else:
        status = "NOT_MACHINE_EVALUABLE"
        reason_codes = ["BOUNDARY_NOT_RETAINED_AT_T0"]
        reference_field = None
        activation = "NO_RETAINED_BOUNDARY"
    payload: dict[str, Any] = {
        "condition_version": CONDITION_CONTRACT_VERSION,
        "role": role,
        "status": status,
        "operator": operator,
        "strategy_operator": raw.get("comparison_operator"),
        "reference_field": reference_field,
        "reference_level": level if fixed_close else None,
        "required_state": raw.get("boundary_type"),
        "activation_semantics": activation,
        "source_strategy_identity": source_strategy_identity,
        "source_rule": raw.get("source_rule"),
        "source_metric": raw.get("source_metric"),
        "source_boundary_status": raw.get("status"),
        "source_boundary_type": raw.get("boundary_type"),
        "source_method": raw.get("method"),
        "source_lineage": raw.get("evidence_lineage") or {},
        "reason_codes": reason_codes + list(raw.get("warnings") or []),
        "narrative_reason": raw.get("reason"),
        "authority_boundary": "RETAINED_RESEARCH_BOUNDARY_NOT_EXECUTION_OR_STOP_LOSS",
    }
    return _identity(payload, "retained_strategy_boundary_condition:", "condition_identity")


def _axis_completeness(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = record.get("evidence_axes")
    if not isinstance(axes, Mapping):
        return {"status": FIELD_NOT_RETAINED, "missing_axes": list(REQUIRED_AXES), "complete": False}
    missing: list[str] = []
    incomplete: dict[str, list[str]] = {}
    for name in REQUIRED_AXES:
        axis = axes.get(name)
        if not isinstance(axis, Mapping):
            missing.append(name)
            continue
        absent = [field for field in _REQUIRED_AXIS_FIELDS if field not in axis]
        if absent:
            incomplete[name] = absent
    portfolio = axes.get("PORTFOLIO_FIT")
    if isinstance(portfolio, Mapping) and portfolio.get("state") not in {None, "NOT_PROVIDED"}:
        absent = [field for field in _REQUIRED_AXIS_FIELDS if field not in portfolio]
        if absent:
            incomplete["PORTFOLIO_FIT"] = absent
    return {
        "status": "COMPLETE" if not missing and not incomplete else "INCOMPLETE",
        "complete": not missing and not incomplete,
        "missing_axes": missing,
        "incomplete_axis_fields": incomplete,
        "portfolio_fit_retained": isinstance(portfolio, Mapping) and portfolio.get("state") != "NOT_PROVIDED",
    }


def build_snapshot(
    *, session: str, operation_identity: str, producer_run_identity: str | None,
    integrated_artifact: Mapping[str, Any], exact_session_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the immutable T0 payload from the current canonical decision artifact."""
    if integrated_artifact.get("contract_version") != "integrated_investment_decision_product/v1":
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_CONTRACT_INVALID")
    if integrated_artifact.get("session") != session:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_SESSION_MISMATCH")
    artifact_identity = integrated_artifact.get("artifact_identity")
    if not isinstance(artifact_identity, str) or not artifact_identity:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_IDENTITY_MISSING")
    if not isinstance(operation_identity, str) or not operation_identity:
        raise ProspectiveDecisionRetentionError("DAILY_OPERATION_IDENTITY_MISSING")
    records = integrated_artifact.get("records")
    if not isinstance(records, Mapping) or not records:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORDS_MISSING")
    retained: dict[str, Any] = {}
    price_records = (exact_session_snapshot or {}).get("records") or {}
    for ticker, decision in sorted(records.items()):
        if not isinstance(decision, Mapping) or decision.get("ticker") != ticker or decision.get("as_of_session") != session:
            raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORD_SESSION_OR_TICKER_MISMATCH:" + str(ticker))
        decision_identity = decision.get("decision_identity")
        if not isinstance(decision_identity, str) or not decision_identity:
            raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORD_IDENTITY_MISSING:" + str(ticker))
        record: dict[str, Any] = {
            "ticker": ticker,
            "decision_session": session,
            "integrated_decision_identity": decision_identity,
            "canonical_operation_identity": operation_identity,
            "source_decision_artifact_identity": artifact_identity,
            "prospective_snapshot_contract_version": CONTRACT_VERSION,
            "evidence_axis_snapshot": _axis_completeness(decision),
            "trigger_condition": dict((decision.get("trigger") or {}).get("condition") or {
                "status": FIELD_NOT_RETAINED, "reason_codes": [FIELD_NOT_RETAINED],
            }),
            "invalidation_condition": dict((decision.get("invalidation") or {}).get("condition") or {
                "status": FIELD_NOT_RETAINED, "reason_codes": [FIELD_NOT_RETAINED],
            }),
            "t0_close_observation": next((dict(row) for row in ((price_records.get(ticker) or {}).get("observations") or [])
                                            if isinstance(row, Mapping) and row.get("session") == session), None),
            # This is the complete known-at-T0 Integrated Decision record.  It
            # includes posture, priority, why-now, coherence, all axes and the
            # source lineage; nothing is reconstructed by a later evaluator.
            "integrated_decision_at_t0": dict(decision),
        }
        retained[ticker] = _identity(record, RECORD_PREFIX, "prospective_snapshot_record_identity")
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "daily_session_operation_identity": operation_identity,
        "daily_producer_run_identity": producer_run_identity,
        "source_integrated_decision_artifact": {
            "contract_version": integrated_artifact.get("contract_version"),
            "artifact_identity": artifact_identity,
            "artifact_sha256": integrated_artifact.get("artifact_sha256"),
            "session": session,
        },
        "t0_price_snapshot": {
            "snapshot_identity": (exact_session_snapshot or {}).get("snapshot_identity"),
            "resolved_completed_session": (exact_session_snapshot or {}).get("resolved_completed_session"),
        },
        "decision_count": len(retained),
        "records": retained,
        "authority_boundary": {
            "immutable_t0_only": True,
            "future_market_observations_not_embedded": True,
            "no_policy_mutation": True,
            "no_recommendation_reconstruction": True,
            "no_execution_or_stop_loss": True,
        },
    }
    return _identity(payload, SNAPSHOT_PREFIX, "snapshot_identity")


def snapshot_path(root: str | Path, snapshot: Mapping[str, Any]) -> Path:
    identity = str(snapshot.get("snapshot_identity") or "")
    digest = identity.removeprefix(SNAPSHOT_PREFIX)
    if len(digest) != 64:
        raise ProspectiveDecisionRetentionError("SNAPSHOT_IDENTITY_INVALID")
    return Path(root) / "operations-review" / "prospective-decision-retention-v1" / str(snapshot["session"]) / digest / "prospective_decision_snapshot.json"


def write_immutable_snapshot(root: str | Path, snapshot: Mapping[str, Any]) -> Path:
    path = snapshot_path(root, snapshot)
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != serialized:
        raise ProspectiveDecisionRetentionError("IMMUTABLE_PROSPECTIVE_SNAPSHOT_CONFLICT:" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")
    return path


def validate_snapshot(snapshot: Mapping[str, Any]) -> bool:
    body = dict(snapshot)
    identity = body.pop("snapshot_identity", None)
    if identity != SNAPSHOT_PREFIX + _hash(body):
        return False
    if snapshot.get("contract_version") != CONTRACT_VERSION:
        return False
    for ticker, row in (snapshot.get("records") or {}).items():
        if not isinstance(row, Mapping) or row.get("ticker") != ticker:
            return False
        record = dict(row)
        record_identity = record.pop("prospective_snapshot_record_identity", None)
        if record_identity != RECORD_PREFIX + _hash(record):
            return False
    return True


def _operation_manifests(root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    base = root / "operations-review" / "daily-research-session-operations-v1"
    for path in sorted(base.glob("*/*/run_manifest.json")) if base.is_dir() else []:
        manifest = _load(path)
        identity = (manifest or {}).get("operation_identity")
        if isinstance(identity, str) and identity:
            rows[identity] = {"path": _relative(root, path), "manifest": manifest}
    return rows


def _handoff_by_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    base = root / "operations-review" / "canonical-post-close-v1"
    for path in sorted(base.glob("*/**/session_handoff_bundle.json")) if base.is_dir() else []:
        bundle = _load(path)
        snapshot = (bundle or {}).get("prospective_decision_snapshot") or {}
        identity = snapshot.get("identity") if isinstance(snapshot, Mapping) else None
        if isinstance(identity, str) and identity:
            result[identity] = {"path": _relative(root, path), "bundle": bundle}
    return result


def _handoff_snapshot_inventory(root: Path) -> list[dict[str, Any]]:
    base = root / "operations-review" / "canonical-post-close-v1"
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/**/session_handoff_bundle.json")) if base.is_dir() else []:
        bundle = _load(path) or {}
        declared = bundle.get("prospective_decision_snapshot") or {}
        rows.append({
            "session": bundle.get("session"), "canonical_handoff_path": _relative(root, path),
            "snapshot_identity": declared.get("identity") if isinstance(declared, Mapping) else None,
            "snapshot_status": declared.get("status") if isinstance(declared, Mapping) else "NOT_RETAINED_LEGACY_HANDOFF",
            "snapshot_reason": declared.get("reason") if isinstance(declared, Mapping) else "NO_MODERN_PROSPECTIVE_SNAPSHOT_FIELD",
        })
    return rows


def discover_snapshots(root: str | Path) -> dict[str, Any]:
    """Inventory immutable snapshots and admit only canonical-operation-bound ones."""
    repository = Path(root)
    operations = _operation_manifests(repository)
    handoffs = _handoff_by_snapshot(repository)
    base = repository / "operations-review" / "prospective-decision-retention-v1"
    inventory: list[dict[str, Any]] = []
    genuine: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/*/prospective_decision_snapshot.json")) if base.is_dir() else []:
        snapshot = _load(path)
        if not snapshot:
            continue
        identity = snapshot.get("snapshot_identity")
        source = snapshot.get("source_integrated_decision_artifact") or {}
        operation_identity = snapshot.get("daily_session_operation_identity")
        operation = operations.get(operation_identity) if isinstance(operation_identity, str) else None
        handoff = handoffs.get(identity) if isinstance(identity, str) else None
        reasons: list[str] = []
        if not validate_snapshot(snapshot):
            reasons.append("SNAPSHOT_CONTENT_IDENTITY_INVALID")
        if not isinstance(operation, Mapping):
            reasons.append("DAILY_OPERATION_MANIFEST_NOT_RETAINED")
        else:
            manifest = operation["manifest"]
            if manifest.get("market_session") != snapshot.get("session"):
                reasons.append("DAILY_OPERATION_SESSION_MISMATCH")
            if manifest.get("generation_context") != "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION":
                reasons.append("DAILY_OPERATION_REPLAY_OR_UNQUALIFIED")
        if not isinstance(handoff, Mapping):
            reasons.append("CANONICAL_HANDOFF_SNAPSHOT_BINDING_MISSING")
        else:
            bundle = handoff["bundle"]
            bound = bundle.get("prospective_decision_snapshot") or {}
            if bound.get("identity") != identity:
                reasons.append("HANDOFF_SNAPSHOT_IDENTITY_MISMATCH")
            if bundle.get("session") != snapshot.get("session"):
                reasons.append("HANDOFF_SESSION_MISMATCH")
            if bundle.get("daily_session_operation_identity") != operation_identity:
                reasons.append("HANDOFF_OPERATION_IDENTITY_MISMATCH")
            if bundle.get("integrated_investment_decision_product_identity") != source.get("artifact_identity"):
                reasons.append("HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH")
        status = GENUINE if not reasons else EXCLUDED
        row = {
            "snapshot_path": _relative(repository, path), "snapshot_identity": identity,
            "session": snapshot.get("session"), "decision_count": snapshot.get("decision_count"),
            "source_decision_artifact_identity": source.get("artifact_identity"),
            "daily_session_operation_identity": operation_identity, "classification": status,
            "proof_reason_codes": reasons or [
                "IMMUTABLE_SNAPSHOT_CONTENT_IDENTITY_VALID",
                "CANONICAL_HANDOFF_BINDS_SNAPSHOT_AND_SOURCE_DECISION",
                "RETAINED_DAILY_OPERATION_BINDS_SAME_COMPLETED_SESSION",
            ],
            "canonical_handoff_path": handoff.get("path") if isinstance(handoff, Mapping) else None,
            "operation_manifest_path": operation.get("path") if isinstance(operation, Mapping) else None,
        }
        inventory.append(row)
        if status == GENUINE:
            genuine.append({"snapshot": snapshot, "inventory": row})
    return {
        "contract_version": CONTRACT_VERSION,
        "inventory": inventory,
        "genuine_snapshots": genuine,
        "classification_counts": dict(sorted(Counter(row["classification"] for row in inventory).items())),
        "handoff_snapshot_inventory": _handoff_snapshot_inventory(repository),
    }


def maturity_state(*, horizon_status: str, later_completed_sessions: int, required_sessions: int) -> str:
    """Map existing forward-bridge facts to the retention maturation contract."""
    if horizon_status == "MATURE":
        return "MATURED"
    if horizon_status in {"CLOSE_PRICE_NOT_RETAINED", "PRICE_BASIS_INCOMPATIBLE"}:
        return "PRICE_SERIES_UNQUALIFIED"
    if horizon_status == "T0_SESSION_NOT_IN_GOVERNED_CHAIN":
        return "TEMPORAL_PROVENANCE_UNQUALIFIED"
    if later_completed_sessions == 0:
        return "PENDING"
    if later_completed_sessions < required_sessions:
        return "INSUFFICIENT_FUTURE_DEPTH"
    return "PRICE_SERIES_UNQUALIFIED"


def evaluate_serialized_close_condition(
    condition: Mapping[str, Any] | None, *, ticker: str, chain: Sequence[str], start_session: str,
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate only an already-serialized fixed-level close condition.

    This is a generic comparison over the retained condition, not a trigger
    generator; dynamic strategy measurements remain explicitly non-evaluable.
    """
    condition = condition or {}
    if condition.get("status") != "MACHINE_EVALUABLE":
        return {"status": "NOT_MACHINE_EVALUABLE", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": list(condition.get("reason_codes") or [])}
    if start_session not in chain:
        return {"status": "TEMPORAL_PROVENANCE_UNQUALIFIED", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["T0_SESSION_NOT_IN_GOVERNED_CHAIN"]}
    level, operator = condition.get("reference_level"), condition.get("operator")
    if not isinstance(level, (int, float)) or operator not in {">", "<"}:
        return {"status": "NOT_MACHINE_EVALUABLE", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["SERIALIZED_CONDITION_INCOMPLETE"]}
    observed = 0
    for session in chain[chain.index(start_session) + 1:]:
        row = ((snapshots.get(session) or {}).get("records") or {}).get(ticker) or {}
        matches = [item for item in (row.get("observations") or []) if isinstance(item, Mapping) and item.get("session") == session]
        if len(matches) != 1 or not isinstance(matches[0].get("close"), (int, float)):
            continue
        observed += 1
        close = matches[0]["close"]
        if (operator == ">" and close > level) or (operator == "<" and close < level):
            return {"status": "SATISFIED", "event_session": session, "condition_identity": condition.get("condition_identity"), "reason_codes": ["SERIALIZED_FIXED_T0_LEVEL_SATISFIED"]}
    return {"status": "NOT_SATISFIED_YET" if observed else "PRICE_SERIES_UNQUALIFIED", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["NO_LATER_RETAINED_CLOSE" if not observed else "NO_LATER_CLOSE_SATISFIED_FIXED_T0_LEVEL"]}


def build_corpus_health(
    *, snapshot_inventory: Mapping[str, Any], feedback_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact operational health view; never reconstructs a missing legacy T0 field."""
    feedback_by_snapshot: set[str] = {
        str(row.get("t0_snapshot_identity")) for row in ((feedback_artifact or {}).get("feedback_records") or [])
        if row.get("t0_snapshot_identity")
    }
    rows: list[dict[str, Any]] = []
    for entry in snapshot_inventory.get("inventory") or []:
        rows.append({
            "session": entry.get("session"), "canonical_prospective_snapshot_exists": True,
            "identity_qualified": entry.get("classification") == GENUINE,
            "snapshot_identity": entry.get("snapshot_identity"), "decision_count": entry.get("decision_count"),
            "outcome_artifact_exists": entry.get("snapshot_identity") in feedback_by_snapshot,
            "reason_codes": entry.get("proof_reason_codes") or [],
        })
    known_sessions = {row["session"] for row in rows}
    for handoff in snapshot_inventory.get("handoff_snapshot_inventory") or []:
        session = handoff.get("session")
        if not isinstance(session, str) or session in known_sessions:
            continue
        rows.append({
            "session": session, "canonical_prospective_snapshot_exists": False,
            "identity_qualified": False, "snapshot_identity": None, "decision_count": None,
            "outcome_artifact_exists": False,
            "reason_codes": [str(handoff.get("snapshot_status")), str(handoff.get("snapshot_reason"))],
        })
    return _identity({
        "schema_version": "1.0.0", "contract_version": HEALTH_CONTRACT_VERSION,
        "sessions": sorted(rows, key=lambda row: (str(row["session"]), str(row["snapshot_identity"]))),
        "authority_boundary": "OPERATIONS_HEALTH_ONLY_NO_POLICY_OR_DECISION_INPUT",
    }, "prospective_decision_corpus_health:", "artifact_identity")
