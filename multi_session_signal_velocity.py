"""PIT-safe, retained-session signal-velocity research projection.

This module observes only immutable ``prospective_decision_snapshot/v1`` files
that are bound to a same-session canonical handoff and completed Producer
operation.  It does not rebuild a historical decision, request a provider, or
turn categorical transitions into a score, probability, recommendation, or
execution instruction.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import prospective_decision_retention as retention


CONTRACT_VERSION = "multi_session_signal_velocity/v1"
RESEARCH_TIER = "PIT_SAFE_RETAINED_SESSION_TRANSITION_RESEARCH_ONLY"
AXES = ("price_trend", "participation", "setup_maturation", "structural_repair", "market_sector_support")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()
    payload["artifact_sha256"] = digest
    payload["artifact_identity"] = "multi_session_signal_velocity:" + digest
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


def _completed_operation(root: Path, session: str, operation_identity: str) -> dict[str, Any] | None:
    """Read only the session-addressed operation directory; never scan all history."""
    base = root / "operations-review" / "daily-research-session-operations-v1" / session
    if not base.is_dir():
        return None
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*/run_manifest.json")):
        manifest = _load(path)
        if manifest and manifest.get("operation_identity") == operation_identity:
            matches.append((path, manifest))
    if len(matches) != 1:
        return None
    path, manifest = matches[0]
    if manifest.get("market_session") != session or manifest.get("generation_context") != "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION":
        return None
    return {"path": _relative(root, path), "manifest": manifest}


def discover_retained_snapshots(root: str | Path) -> dict[str, Any]:
    """Discover qualified snapshot files through bounded, exact session paths.

    A snapshot is admitted only when its own identity is valid and its matching
    canonical handoff and completed operation bind the same session and source
    integrated-decision identity.  Invalid or incomplete records remain in the
    inventory with reasons; they never become a substitute for another session.
    """
    repository = Path(root)
    snapshot_base = repository / "operations-review" / "prospective-decision-retention-v1"
    handoff_base = repository / "operations-review" / "canonical-post-close-v1"
    inventory: list[dict[str, Any]] = []
    qualified: list[dict[str, Any]] = []
    # The completed-session ledger is the bounded authority for which session
    # identities may be considered.  Do not enumerate either artifact tree:
    # both contain historical working material and must not act as a "latest"
    # or similarity-based selector.
    registry = _load(repository / "config" / "daily_research_session_input_registry.json") or {}
    completed = registry.get("completed_sessions") or {}
    session_ids = sorted(
        str(session) for session, entry in completed.items()
        if isinstance(session, str) and isinstance(entry, Mapping) and entry.get("status") == "COMPLETED_RETAINED_EVIDENCE"
    )
    for session_id in session_ids:
        session_dir = handoff_base / session_id
        handoff_path = session_dir / "session_handoff_bundle.json"
        handoff = _load(handoff_path)
        declared = (handoff or {}).get("prospective_decision_snapshot") or {}
        session = (handoff or {}).get("session")
        identity = declared.get("identity") if isinstance(declared, Mapping) else None
        digest = identity.removeprefix(retention.SNAPSHOT_PREFIX) if isinstance(identity, str) else ""
        path = snapshot_base / str(session) / digest / "prospective_decision_snapshot.json"
        snapshot = _load(path)
        if not snapshot:
            # A canonical handoff with no valid immutable identity is evidence
            # of an unavailable modern snapshot, not permission to scan for a
            # similar or newer file.
            if handoff:
                inventory.append({
                    "session": session, "snapshot_path": _relative(repository, path), "snapshot_identity": identity,
                    "source_integrated_decision_artifact_identity": handoff.get("integrated_investment_decision_product_identity"),
                    "daily_session_operation_identity": handoff.get("daily_session_operation_identity"),
                    "classification": "EXCLUDED", "reason_codes": ["EXACT_HANDOFF_SNAPSHOT_NOT_RETAINED_OR_UNREADABLE"],
                    "canonical_handoff_path": _relative(repository, handoff_path), "operation_manifest_path": None,
                })
            continue
        session = snapshot.get("session")
        source = snapshot.get("source_integrated_decision_artifact") or {}
        reasons: list[str] = []
        if not isinstance(session, str) or not session:
            reasons.append("SNAPSHOT_SESSION_MISSING")
        if not retention.validate_snapshot(snapshot):
            reasons.append("SNAPSHOT_CONTENT_IDENTITY_INVALID")
        operation = _completed_operation(repository, str(session), str(snapshot.get("daily_session_operation_identity") or "")) if isinstance(session, str) else None
        if not handoff:
            reasons.append("CANONICAL_HANDOFF_NOT_RETAINED")
        else:
            declared = handoff.get("prospective_decision_snapshot") or {}
            if handoff.get("session") != session:
                reasons.append("HANDOFF_SESSION_MISMATCH")
            if declared.get("identity") != snapshot.get("snapshot_identity"):
                reasons.append("HANDOFF_SNAPSHOT_IDENTITY_MISMATCH")
            if handoff.get("daily_session_operation_identity") != snapshot.get("daily_session_operation_identity"):
                reasons.append("HANDOFF_OPERATION_IDENTITY_MISMATCH")
            if handoff.get("integrated_investment_decision_product_identity") != source.get("artifact_identity"):
                reasons.append("HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH")
        if operation is None:
            reasons.append("COMPLETED_DAILY_OPERATION_NOT_RETAINED")
        row = {
            "session": session, "snapshot_path": _relative(repository, path),
            "snapshot_identity": snapshot.get("snapshot_identity"),
            "source_integrated_decision_artifact_identity": source.get("artifact_identity"),
            "daily_session_operation_identity": snapshot.get("daily_session_operation_identity"),
            "classification": "QUALIFIED" if not reasons else "EXCLUDED",
            "reason_codes": reasons or [
                "IMMUTABLE_SNAPSHOT_IDENTITY_VALID", "EXACT_CANONICAL_HANDOFF_BINDING_VALID",
                "EXACT_COMPLETED_DAILY_OPERATION_BINDING_VALID",
            ],
            "canonical_handoff_path": _relative(repository, handoff_path) if handoff else None,
            "operation_manifest_path": operation.get("path") if operation else None,
        }
        inventory.append(row)
        if not reasons:
            qualified.append({"snapshot": snapshot, "inventory": row})
    qualified.sort(key=lambda item: str(item["snapshot"].get("session")))
    return {
        "contract_version": CONTRACT_VERSION, "inventory": inventory, "qualified_snapshots": qualified,
        "qualified_session_chain": [str(item["snapshot"]["session"]) for item in qualified],
        "classification_counts": dict(sorted(Counter(row["classification"] for row in inventory).items())),
    }


def _axis_state(value: Any, *, kind: str) -> str:
    text = str(value or "").upper()
    if not text or text in {"NONE", "NOT_PROVIDED", "UNAVAILABLE", "UNKNOWN", "FIELD_NOT_RETAINED_AT_T0"}:
        return "UNAVAILABLE"
    if kind == "setup":
        if text in {"BASE_BUILDING", "BASE"}:
            return "BUILDING"
        if text in {"EARLY_REVERSAL_CANDIDATE", "APPROACHING", "WATCH"}:
            return "EARLY_TRANSITION"
        if text in {"BREAKOUT_READY", "UPTREND_CONFIRMED", "CONFIRMED"}:
            return "CONFIRMED"
        if text in {"DOWNTREND", "AVOID", "BREAKDOWN"}:
            return "FAILED_OR_INVALID"
        return "STABLE_OR_OTHER"
    if kind == "support":
        if text in {"SUPPORTIVE", "LEADING", "ALIGNED", "BULLISH"}:
            return "SUPPORTIVE"
        if text in {"ADVERSE", "LAGGING", "UNSUPPORTIVE", "BEARISH"}:
            return "UNSUPPORTIVE"
        return "MIXED_OR_NEUTRAL"
    if text in {"UPTREND", "UPTREND_CONFIRMED", "BREAKOUT_READY", "IMPROVING", "STRENGTHENING", "POSITIVE"}:
        return "IMPROVING"
    if text in {"DOWNTREND", "WEAKENING", "DETERIORATING", "NEGATIVE", "BREAKDOWN"}:
        return "WEAKENING"
    if text in {"REPAIRING", "RECOVERING", "BASE_BUILDING"}:
        return "REPAIRING"
    return "STABLE_OR_MIXED"


def _source(record: Mapping[str, Any], axis: str) -> tuple[Any, list[str]]:
    axes = record.get("evidence_axes") or {}
    if axis == "price_trend":
        return (axes.get("TACTICAL_STRUCTURE") or {}).get("state", record.get("market_structure_state")), ["evidence_axes.TACTICAL_STRUCTURE.state", "market_structure_state"]
    if axis == "participation":
        return (axes.get("PARTICIPATION_CONFIRMATION") or {}).get("state", (record.get("participation") or {}).get("status")), ["evidence_axes.PARTICIPATION_CONFIRMATION.state", "participation.status"]
    if axis == "setup_maturation":
        current = record.get("current_decision_state") or {}
        return current.get("entry_state", record.get("entry_state")), ["current_decision_state.entry_state", "entry_state"]
    if axis == "structural_repair":
        return (axes.get("FUNDAMENTAL") or {}).get("state", record.get("fundamental_state")), ["evidence_axes.FUNDAMENTAL.state", "fundamental_state"]
    market = record.get("market_sector_context") or {}
    return market.get("market_regime", market.get("sector_leadership")), ["market_sector_context.market_regime", "market_sector_context.sector_leadership"]


def _axis_observation(record: Mapping[str, Any], axis: str) -> dict[str, Any]:
    source, fields = _source(record, axis)
    kind = "setup" if axis == "setup_maturation" else "support" if axis == "market_sector_support" else "standard"
    return {"state": _axis_state(source, kind=kind), "source_state": source, "source_fields": fields}


def _evidence_quality(snapshot_record: Mapping[str, Any], axes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    completeness = snapshot_record.get("evidence_axis_snapshot") or {}
    unavailable = sorted(name for name, row in axes.items() if row["state"] == "UNAVAILABLE")
    if completeness.get("complete") is True and not unavailable:
        state = "COMPLETE_RETAINED_EVIDENCE"
    elif len(unavailable) < len(AXES):
        state = "PARTIAL_RETAINED_EVIDENCE"
    else:
        state = "INSUFFICIENT_RETAINED_EVIDENCE"
    return {
        "state": state, "unavailable_axes": unavailable,
        "t0_snapshot_evidence_status": completeness.get("status"),
        "price_observation_retained": isinstance(snapshot_record.get("t0_close_observation"), Mapping),
    }


def _transition(previous: str, current: str, axis: str) -> str:
    if previous == "UNAVAILABLE" or current == "UNAVAILABLE":
        return "NOT_COMPARABLE"
    if previous == current:
        return "UNCHANGED"
    if axis == "setup_maturation":
        if (previous, current) in {("BUILDING", "EARLY_TRANSITION"), ("EARLY_TRANSITION", "CONFIRMED"), ("BUILDING", "CONFIRMED")}:
            return "MATURING"
        if current == "FAILED_OR_INVALID":
            return "FAILED_OR_INVALIDATED"
    if axis == "market_sector_support":
        if current == "SUPPORTIVE" and previous != "SUPPORTIVE":
            return "SUPPORT_IMPROVING"
        if previous == "SUPPORTIVE" and current != "SUPPORTIVE":
            return "SUPPORT_WEAKENING"
    if current in {"IMPROVING", "REPAIRING"} and previous == "WEAKENING":
        return "IMPROVING"
    if current == "WEAKENING" and previous in {"IMPROVING", "REPAIRING"}:
        return "WEAKENING"
    return "STATE_CHANGED"


def _overall(transitions: Mapping[str, str], quality: Mapping[str, Any], *, initial: bool) -> str:
    if initial:
        return "INITIAL_OBSERVATION"
    if quality["state"] == "INSUFFICIENT_RETAINED_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE"
    positive = sum(value in {"MATURING", "IMPROVING", "SUPPORT_IMPROVING"} for value in transitions.values())
    negative = sum(value in {"FAILED_OR_INVALIDATED", "WEAKENING", "SUPPORT_WEAKENING"} for value in transitions.values())
    if positive and negative:
        return "DIVERGENT_TRANSITION"
    if positive >= 2:
        return "EARLY_TRANSITION_EMERGING"
    if positive:
        return "EARLY_TRANSITION_ADVANCING"
    if negative:
        return "EARLY_TRANSITION_STALLED"
    return "STABLE_RETAINED_STATE"


def build_artifact(*, qualified_snapshots: Sequence[Mapping[str, Any]], source_inventory: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Build a deterministic categorical projection from already-qualified snapshots."""
    ordered = sorted(qualified_snapshots, key=lambda item: str((item.get("snapshot") or {}).get("session")))
    prior_by_ticker: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for item in ordered:
        snapshot = item.get("snapshot") or {}
        inventory = item.get("inventory") or {}
        session = snapshot.get("session")
        for ticker, sealed in sorted((snapshot.get("records") or {}).items()):
            decision = (sealed or {}).get("integrated_decision_at_t0") if isinstance(sealed, Mapping) else None
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            axes = {axis: _axis_observation(decision, axis) for axis in AXES}
            quality = _evidence_quality(sealed, axes)
            prior = prior_by_ticker.get(ticker)
            transitions = ({axis: _transition(prior["axes"][axis]["state"], axes[axis]["state"], axis) for axis in AXES} if prior else {})
            row = {
                "ticker": ticker, "session": session, "source_sequence_index": len([r for r in records if r["ticker"] == ticker]) + 1,
                "source_snapshot_identity": snapshot.get("snapshot_identity"),
                "source_integrated_decision_identity": sealed.get("integrated_decision_identity"),
                "source_operation_identity": snapshot.get("daily_session_operation_identity"),
                "source_paths": {"snapshot": inventory.get("snapshot_path"), "canonical_handoff": inventory.get("canonical_handoff_path"), "operation_manifest": inventory.get("operation_manifest_path")},
                "previous_session": prior.get("session") if prior else None,
                "observations_count": (prior.get("observations_count", 0) + 1) if prior else 1,
                "axes": axes, "axis_transitions": transitions, "evidence_quality": quality,
                "overall_transition_state": _overall(transitions, quality, initial=prior is None),
                "reason_codes": (["EXACT_IMMUTABLE_T0_SNAPSHOT", "SESSION_ORDERED_RETAINED_SEQUENCE"] + (list(transitions.values()) or ["NO_PRIOR_QUALIFIED_OBSERVATION"])),
                "research_tier": RESEARCH_TIER, "is_actionable": False,
            }
            records.append(row)
            prior_by_ticker[ticker] = {"session": session, "axes": axes, "observations_count": row["observations_count"]}
    counts = Counter(row["overall_transition_state"] for row in records)
    latest_session = ordered[-1]["snapshot"].get("session") if ordered else None
    latest = [row for row in records if row["session"] == latest_session]
    validation = {
        "retained_session_count": len(ordered), "retained_sessions": [item["snapshot"].get("session") for item in ordered],
        "record_count": len(records), "latest_session": latest_session, "latest_session_cohort_counts": dict(sorted(Counter(row["overall_transition_state"] for row in latest).items())),
        "overall_transition_counts": dict(sorted(counts.items())),
        "axis_transition_counts": {axis: dict(sorted(Counter(row["axis_transitions"].get(axis, "INITIAL") for row in records).items())) for axis in AXES},
        "lead_time_diagnostic": {"status": "NOT_EVALUABLE_NO_FORWARD_OUTCOME_CONTRACT", "value": None},
        "false_transition_diagnostic": {"status": "NOT_EVALUABLE_NO_FORWARD_OUTCOME_CONTRACT", "value": None},
        "limits": ["NO_FUTURE_PRICE_OR_OUTCOME_DATA_USED", "NO_CALENDAR_OR_LATEST_FALLBACK", "CATEGORICAL_TRANSITIONS_NOT_SCORE_OR_PROBABILITY", "MISSING_T0_FIELDS_REMAIN_UNAVAILABLE"],
    }
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "research_tier": RESEARCH_TIER,
        "source_inventory": list(source_inventory or []), "records": records, "validation": validation,
        "authority_boundary": {"retained_t0_only": True, "no_provider_or_network": True, "no_historical_reconstruction": True, "no_score_probability_or_recommendation": True, "no_execution_or_sizing": True, "is_actionable": False},
    }
    return _identity(artifact)


def build_from_retained_root(root: str | Path) -> dict[str, Any]:
    discovery = discover_retained_snapshots(root)
    return build_artifact(qualified_snapshots=discovery["qualified_snapshots"], source_inventory=discovery["inventory"])


def write_immutable(path: str | Path, artifact: Mapping[str, Any]) -> Path:
    destination = Path(path)
    serialized = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if destination.exists() and destination.read_text(encoding="utf-8") != serialized:
        raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:" + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized, encoding="utf-8")
    return destination
