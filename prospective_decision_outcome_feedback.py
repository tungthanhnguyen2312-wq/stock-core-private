"""Retained-only prospective decision feedback and policy diagnostics.

This is a downstream observer over the existing integrated-decision artifact
and P3F9B exact-session close snapshots.  It deliberately does not rebuild a
decision, choose a later artifact for an older session, or write into any
decision-producing path.  ``integrated_decision_prospective_feedback`` remains
the sole forward-close calculator; this module supplies the missing corpus and
temporal qualification contracts plus descriptive diagnostics.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import daily_session_level2_package as level2
import integrated_decision_prospective_feedback as forward_bridge
import prospective_decision_retention as retention


CONTRACT_VERSION = "prospective_decision_outcome_feedback/v2"
TEMPORAL_CONTRACT_VERSION = "retained_integrated_decision_temporal_qualification/v1"
OUTCOME_POLICY_VERSION = "prospective_outcome_diagnostic_policy/v1"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"
GENUINE = "GENUINE_PROSPECTIVE_DECISION"
REPLAY_ONLY = "REPLAY_ONLY"
RETROSPECTIVELY_REBUILT = "RETROSPECTIVELY_REBUILT"
CURRENT_VIEW_OF_OLD_SESSION = "CURRENT_VIEW_OF_OLD_SESSION"
UNKNOWN_TEMPORAL_STATUS = "UNKNOWN_TEMPORAL_STATUS"
EXCLUDED = "EXCLUDE_TEMPORAL_PROVENANCE_UNQUALIFIED"

# These are analytical labels only.  They neither change an existing posture
# nor claim calibrated success probabilities.
OUTCOME_POLICY_CONSTANTS = {
    "positive_return_strictly_greater_than": 0.0,
    "adverse_return_strictly_less_than": 0.0,
    "material_upside_return_greater_than_or_equal_to": 0.03,
    "large_close_adverse_excursion_less_than_or_equal_to": -0.05,
    "basis_horizon_for_outcome_label": "forward_close_return_5",
    "version": OUTCOME_POLICY_VERSION,
}
REQUIRED_TICKERS = ("FPT", "HPG", "SSI", "QNS", "PVD", "PNJ", "VNM")
_GENUINE_CONTEXT = "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"


class ProspectiveFeedbackError(ValueError):
    """Raised only for malformed retained-contract input or immutable conflicts."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(payload: dict[str, Any], prefix: str, field: str = "artifact_identity") -> dict[str, Any]:
    payload[field] = prefix + hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return payload


def _load_json(path: Path) -> dict[str, Any] | None:
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


def _operation_manifests(root: Path) -> dict[str, dict[str, Any]]:
    base = root / "operations-review" / "daily-research-session-operations-v1"
    result: dict[str, dict[str, Any]] = {}
    if not base.is_dir():
        return result
    for path in sorted(base.glob("*/*/run_manifest.json")):
        manifest = _load_json(path)
        if not manifest:
            continue
        identity = manifest.get("operation_identity")
        if isinstance(identity, str) and identity:
            result[identity] = {"path": _relative(root, path), "manifest": manifest}
    return result


def _handoff_bundles(root: Path, operations: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only complete canonical handoffs with an identity-bound decision artifact."""
    base = root / "operations-review" / "canonical-post-close-v1"
    rows: list[dict[str, Any]] = []
    if not base.is_dir():
        return rows
    for path in sorted(base.glob("*/**/session_handoff_bundle.json")):
        bundle = _load_json(path)
        if not bundle:
            continue
        session = bundle.get("session")
        op_identity = bundle.get("daily_session_operation_identity")
        artifact_identity = bundle.get("integrated_investment_decision_product_identity")
        artifact_ref = (bundle.get("deeper_bundles") or {}).get("integrated_investment_decision_product")
        producer = bundle.get("daily_producer") or {}
        proof = bundle.get("market_session_proof") or {}
        if not all(isinstance(value, str) and value for value in (session, op_identity, artifact_identity, artifact_ref)):
            continue
        artifact_path = (root / artifact_ref).resolve()
        rows.append({
            "path": _relative(root, path), "bundle": bundle, "session": session,
            "operation_identity": op_identity, "operation": operations.get(op_identity),
            "artifact_identity": artifact_identity, "artifact_path": artifact_path,
            "producer_completed": producer.get("status") == "COMPLETED",
            "resolved_completed_session": proof.get("resolved_completed_session"),
            "prospective_snapshot_identity": ((bundle.get("prospective_decision_snapshot") or {}).get("identity")),
        })
    return rows


def _artifact_paths(root: Path) -> list[Path]:
    operations = root / "operations-review"
    found = set(operations.glob("**/integrated_investment_decision_product_artifact.json"))
    found.update((operations / "canonical-post-close-v1").glob("**/enrichment/integrated_investment_decision_product.json"))
    return sorted(found)


def _observed_time_matches_session(artifact: Mapping[str, Any], session: str) -> bool:
    observed = artifact.get("requested_at")
    # The modern contract is ISO.  Older retained artifacts have a legacy
    # month/day/year timestamp and are intentionally not admitted by this new
    # temporal gate rather than being parsed with locale-dependent semantics.
    return isinstance(observed, str) and observed.startswith(session + "T")


def _qualify_linked_artifact(link: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    session = link["session"]
    operation = link.get("operation") or {}
    manifest = operation.get("manifest") if isinstance(operation, Mapping) else None
    reasons: list[str] = []
    if artifact.get("contract_version") != "integrated_investment_decision_product/v1":
        reasons.append("INTEGRATED_DECISION_CONTRACT_INVALID")
    if artifact.get("artifact_identity") != link["artifact_identity"]:
        reasons.append("HANDOFF_ARTIFACT_IDENTITY_MISMATCH")
    if artifact.get("session") != session:
        reasons.append("ARTIFACT_SESSION_MISMATCH")
    if not _observed_time_matches_session(artifact, session):
        reasons.append("ARTIFACT_OBSERVED_TIME_NOT_SESSION_BOUND")
    if not link.get("producer_completed"):
        reasons.append("DAILY_PRODUCER_NOT_COMPLETED")
    if link.get("resolved_completed_session") != session:
        reasons.append("COMPLETED_SESSION_PROOF_MISMATCH")
    if not isinstance(manifest, Mapping):
        reasons.append("DAILY_OPERATION_MANIFEST_NOT_RETAINED")
    else:
        if manifest.get("market_session") != session:
            reasons.append("DAILY_OPERATION_SESSION_MISMATCH")
        if manifest.get("generation_context") != _GENUINE_CONTEXT:
            reasons.append("DAILY_OPERATION_REPLAY_OR_UNQUALIFIED")
    status = GENUINE if not reasons else EXCLUDED
    return {
        "contract_version": TEMPORAL_CONTRACT_VERSION, "status": status,
        "decision_session": session, "artifact_observed_at": artifact.get("requested_at"),
        "decision_artifact_identity": artifact.get("artifact_identity"),
        "daily_session_operation_identity": link["operation_identity"],
        "canonical_handoff_path": link["path"],
        "operation_manifest_path": operation.get("path") if isinstance(operation, Mapping) else None,
        "proof_reason_codes": reasons or [
            "CANONICAL_HANDOFF_BINDS_ARTIFACT_IDENTITY",
            "RETAINED_DAILY_OPERATION_BINDS_SAME_COMPLETED_SESSION",
            "ARTIFACT_OBSERVED_TIME_IS_SAME_SESSION",
        ],
    }


def discover_prospective_corpus(root: str | Path) -> dict[str, Any]:
    """Inventory every retained integrated-decision artifact without promoting copies or replays."""
    repository = Path(root)
    operations = _operation_manifests(repository)
    handoffs = _handoff_bundles(repository, operations)
    links = {item["artifact_path"]: item for item in handoffs}
    linked_identities = {item["artifact_identity"] for item in handoffs}
    inventory: list[dict[str, Any]] = []
    genuine: list[dict[str, Any]] = []
    for path in _artifact_paths(repository):
        artifact = _load_json(path)
        if not artifact:
            continue
        rel = _relative(repository, path)
        link = links.get(path.resolve())
        if link is not None:
            if link.get("prospective_snapshot_identity"):
                classification = CURRENT_VIEW_OF_OLD_SESSION
                temporal = {
                    "contract_version": TEMPORAL_CONTRACT_VERSION, "status": classification,
                    "decision_session": artifact.get("session"), "artifact_observed_at": artifact.get("requested_at"),
                    "decision_artifact_identity": artifact.get("artifact_identity"),
                    "proof_reason_codes": ["IMMUTABLE_PROSPECTIVE_SNAPSHOT_IS_CANONICAL_T0_SOURCE"],
                }
            else:
                temporal = _qualify_linked_artifact(link, artifact)
                classification = temporal["status"]
        else:
            lowered = rel.lower()
            if "replay" in lowered:
                classification, reason = REPLAY_ONLY, "REPLAY_PATH_NOT_ELIGIBLE"
            elif artifact.get("artifact_identity") in linked_identities:
                classification, reason = CURRENT_VIEW_OF_OLD_SESSION, "NONCANONICAL_COPY_OF_BOUND_ARTIFACT"
            elif "canonical-post-close-v1" in lowered:
                classification, reason = CURRENT_VIEW_OF_OLD_SESSION, "CANONICAL_HANDOFF_BINDING_MISSING"
            elif "integrated-investment-decision-product-v1-" in lowered:
                classification, reason = UNKNOWN_TEMPORAL_STATUS, "NO_CANONICAL_HANDOFF_BINDING"
            else:
                classification, reason = RETROSPECTIVELY_REBUILT, "NONCANONICAL_ARTIFACT_PROVENANCE"
            temporal = {
                "contract_version": TEMPORAL_CONTRACT_VERSION, "status": classification,
                "decision_session": artifact.get("session"), "artifact_observed_at": artifact.get("requested_at"),
                "decision_artifact_identity": artifact.get("artifact_identity"), "proof_reason_codes": [reason],
            }
        row = {
            "artifact_path": rel, "artifact_identity": artifact.get("artifact_identity"),
            "contract_version": artifact.get("contract_version"), "decision_session": artifact.get("session"),
            "artifact_observed_at": artifact.get("requested_at"), "record_count": len(artifact.get("records") or {}),
            "classification": classification, "temporal_qualification": temporal,
        }
        inventory.append(row)
        if classification == GENUINE:
            genuine.append({"artifact": artifact, "artifact_path": rel, "temporal": temporal})
    return {
        "contract_version": TEMPORAL_CONTRACT_VERSION,
        "inventory": sorted(inventory, key=lambda row: (str(row["decision_session"]), row["artifact_path"])),
        "genuine_artifacts": sorted(genuine, key=lambda row: (str(row["artifact"].get("session")), row["artifact_path"])),
        "qualified_session_chain": sorted({row["artifact"].get("session") for row in genuine if isinstance(row["artifact"].get("session"), str)}),
        "classification_counts": dict(sorted(Counter(row["classification"] for row in inventory).items())),
    }


def retained_session_snapshots(root: str | Path, sessions: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Load exact completed-session snapshots only when their own session identity matches."""
    repository = Path(root)
    snapshots: dict[str, dict[str, Any]] = {}
    for session in sorted(set(sessions)):
        path = level2.session_artifact_paths(repository, session)["exact_session_snapshot"]
        snapshot = _load_json(path)
        if snapshot and snapshot.get("resolved_completed_session") == session and isinstance(snapshot.get("snapshot_identity"), str):
            snapshots[session] = snapshot
    return snapshots


def _snapshot_t0_price_observations(candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Expose only the T0 close copies sealed inside immutable snapshots.

    Each row was copied from its exact-session P3F9B source at T0.  This is
    not a history rebuild; it simply lets later feedback use the same sealed
    T0 price fact even when the original session-shaped working path moved.
    """
    snapshots: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        snapshot = candidate.get("snapshot") or {}
        session = snapshot.get("session")
        if not isinstance(session, str) or session in snapshots:
            continue
        records: dict[str, Any] = {}
        for ticker, entry in (snapshot.get("records") or {}).items():
            row = (entry or {}).get("t0_close_observation") if isinstance(entry, Mapping) else None
            if isinstance(row, Mapping) and row.get("session") == session:
                records[ticker] = {"observations": [dict(row)]}
        snapshots[session] = {
            "resolved_completed_session": session,
            "snapshot_identity": ((snapshot.get("t0_price_snapshot") or {}).get("snapshot_identity")),
            "records": records,
        }
    return snapshots


def _modern_snapshot_candidates(root: str | Path) -> dict[str, Any]:
    discovery = retention.discover_snapshots(root)
    genuine = discovery["genuine_snapshots"]
    chain = sorted({row["snapshot"].get("session") for row in genuine if isinstance(row["snapshot"].get("session"), str)})
    # Prefer the immutable T0 price copy for each prospective session.  A
    # later session can only mature when its own canonical T0 snapshot exists.
    snapshots = _snapshot_t0_price_observations(genuine)
    return {"discovery": discovery, "genuine": genuine, "chain": chain, "snapshots": snapshots}


def _compact_axes(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = record.get("evidence_axes")
    if not isinstance(axes, Mapping):
        return {"status": FIELD_NOT_RETAINED, "axis_states": {}}
    return {
        "status": "RETAINED", "axis_states": {
            str(name): {"state": value.get("state"), "fitness": value.get("fitness"), "lineage": value.get("lineage")}
            for name, value in sorted(axes.items()) if isinstance(value, Mapping)
        },
    }


def _state(record: Mapping[str, Any], key: str, nested_key: str | None = None) -> Any:
    value = record.get(key)
    if nested_key and isinstance(value, Mapping):
        return value.get(nested_key, FIELD_NOT_RETAINED)
    return value if value is not None else FIELD_NOT_RETAINED


def _outcome_label(record: Mapping[str, Any], outcome: Mapping[str, Any]) -> dict[str, Any]:
    h5 = (outcome.get("horizons") or {}).get("forward_close_return_5") or {}
    if h5.get("status") != forward_bridge.MATURE:
        return {"label": "INSUFFICIENT_FORWARD_DEPTH", "reason_codes": [str(h5.get("status"))], "basis_horizon": "forward_close_return_5"}
    value = h5.get("return")
    close5 = (outcome.get("close_path_by_horizon") or {}).get("close_excursion_5") or {}
    adverse = close5.get("CLOSE_MAE")
    posture = record.get("research_action_posture", FIELD_NOT_RETAINED)
    positive = isinstance(value, (int, float)) and value > OUTCOME_POLICY_CONSTANTS["positive_return_strictly_greater_than"]
    negative = isinstance(value, (int, float)) and value < OUTCOME_POLICY_CONSTANTS["adverse_return_strictly_less_than"]
    volatile = isinstance(adverse, (int, float)) and adverse <= OUTCOME_POLICY_CONSTANTS["large_close_adverse_excursion_less_than_or_equal_to"]
    if posture == "INITIATE_ON_BREAKOUT":
        label = "POSITIVE_BUT_VOLATILE" if positive and volatile else "FOLLOW_THROUGH" if positive else "FALSE_BREAKOUT_OUTCOME" if negative else "OUTCOME_UNQUALIFIED"
    elif posture == "ACCUMULATE_ON_RETEST":
        label = "ACCUMULATION_SETUP_WORKED" if positive else "ACCUMULATION_SETUP_FAILED" if negative else "OUTCOME_UNQUALIFIED"
    elif posture == "EARLY_WATCH":
        label = "EARLY_WATCH_WORKED" if positive else "EARLY_WATCH_FAILED" if negative else "OUTCOME_UNQUALIFIED"
    elif posture in {"WAIT_FOR_CONFIRMATION", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH"}:
        label = "WAIT_MISSED_UPSIDE" if positive else "WAIT_AVOIDED_DRAWDOWN" if negative else "OUTCOME_UNQUALIFIED"
    else:
        label = "FOLLOW_THROUGH" if positive else "FAILED_FOLLOW_THROUGH" if negative else "OUTCOME_UNQUALIFIED"
    return {"label": label, "reason_codes": ["DESCRIPTIVE_CLOSE_RETURN_ONLY"], "basis_horizon": "forward_close_return_5"}


def _trigger_invalidation(
    record: Mapping[str, Any], *, snapshots: Mapping[str, Mapping[str, Any]], chain: Sequence[str],
) -> dict[str, Any]:
    trigger_condition = (record.get("trigger") or {}).get("condition")
    invalidation_condition = (record.get("invalidation") or {}).get("condition")
    if isinstance(trigger_condition, Mapping) or isinstance(invalidation_condition, Mapping):
        return {
            "trigger": retention.evaluate_serialized_close_condition(
                trigger_condition, ticker=str(record.get("ticker")), chain=chain,
                start_session=str(record.get("as_of_session")), snapshots=snapshots,
            ),
            "invalidation": retention.evaluate_serialized_close_condition(
                invalidation_condition, ticker=str(record.get("ticker")), chain=chain,
                start_session=str(record.get("as_of_session")), snapshots=snapshots,
            ),
            "authority_boundary": "SERIALIZED_EXISTING_STRATEGY_CONDITIONS_NOT_TRADE_EXECUTION",
        }
    # Legacy Integrated records preserve levels/states, not a serializable
    # forward-evaluable operator.  Do not guess that a level implies >= or <=.
    return {
        "trigger": {"status": "T0_TRIGGER_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED", "snapshot": record.get("trigger")},
        "invalidation": {"status": "T0_INVALIDATION_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED", "snapshot": record.get("invalidation")},
        "authority_boundary": "RESEARCH_INSTRUMENTATION_NOT_TRADE_EXECUTION",
    }


def _feedback_record(*, artifact: Mapping[str, Any], source_path: str, temporal: Mapping[str, Any], record: Mapping[str, Any],
                     snapshots: Mapping[str, Mapping[str, Any]], chain: Sequence[str],
                     t0_snapshot: Mapping[str, Any] | None = None, t0_snapshot_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    outcome = forward_bridge.evaluate_decision_forward_outcome(
        decision_record=record, p3f9b_snapshot=None, governed_chain=chain, retained_session_snapshots=snapshots,
    )
    if record.get("as_of_session") in chain:
        later_sessions = len(chain) - chain.index(record["as_of_session"]) - 1
    else:
        later_sessions = 0
    for horizon in (outcome.get("horizons") or {}).values():
        if isinstance(horizon, dict):
            horizon["maturation_state"] = retention.maturity_state(
                horizon_status=str(horizon.get("status")), later_completed_sessions=later_sessions,
                required_sessions=int(horizon.get("required_completed_future_sessions") or 0),
            )
    axes = _compact_axes(record)
    coherence = _state(record, "evidence_axis_coherence", "state")
    priority = _state(record, "priority_posture_reconciliation", "research_priority_tier")
    feedback = {
        "decision_identity": record.get("decision_identity"), "ticker": record.get("ticker"),
        "decision_session": artifact.get("session"), "research_action_posture": record.get("research_action_posture", FIELD_NOT_RETAINED),
        "opportunity_priority": priority, "coherence_state": coherence,
        "fundamental_state": _state(record, "fundamental_state"),
        "valuation_state": _state(record, "valuation_context_summary", "status"),
        "tactical_structure_state": _state(record, "market_structure_state"),
        "momentum_state": _state(record, "momentum_context", "status"),
        "participation_state": _state(record, "participation", "status"),
        "market_sector_state": _state(record, "market_sector_context", "market_regime"),
        "trigger": record.get("trigger"), "invalidation": record.get("invalidation"),
        "evidence_axes": axes, "source_artifact": {"path": source_path, "identity": artifact.get("artifact_identity"), "observed_at": artifact.get("requested_at")},
        "t0_snapshot_identity": (t0_snapshot or {}).get("snapshot_identity"),
        "t0_snapshot_record_identity": (t0_snapshot_record or {}).get("prospective_snapshot_record_identity"),
        "temporal_qualification": dict(temporal), "forward_outcomes": outcome,
        "trigger_invalidation_outcome": _trigger_invalidation(record, snapshots=snapshots, chain=chain),
    }
    feedback["outcome_classification"] = _outcome_label(record, outcome)
    return _identity(feedback, "prospective_decision_feedback_record:", "feedback_identity")


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _summary(groups: Mapping[str, Sequence[Mapping[str, Any]]], *, dimension: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for value, members in sorted(groups.items()):
        mature = [
            item for item in members
            if (item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}).get("status") == forward_bridge.MATURE
        ]
        row = {"dimension": dimension, "value": value, "sample_size": len(members), "mature_T5_sample_size": len(mature)}
        if mature:
            returns = [item["forward_outcomes"]["horizons"]["forward_close_return_5"]["return"] for item in mature]
            excursions = [item["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"] for item in mature]
            row.update({
                "median_forward_return_T5": _median(returns),
                "observed_positive_rate_T5": {"value": sum(value > 0 for value in returns) / len(returns), "N": len(returns)},
                "median_CLOSE_MFE_T5": _median([item["CLOSE_MFE"] for item in excursions if item.get("status") == forward_bridge.MATURE]),
                "median_CLOSE_MAE_T5": _median([item["CLOSE_MAE"] for item in excursions if item.get("status") == forward_bridge.MATURE]),
            })
        rows.append(row)
    return {"groups": rows, "authority_boundary": "DESCRIPTIVE_SAMPLE_STATISTICS_NOT_CALIBRATION_OR_CAUSAL_RANKING"}


def _false_negatives(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    conservative = {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH", "INSUFFICIENT_CURRENT_RESEARCH", "AVOID"}
    for item in records:
        h5 = item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}
        if item["research_action_posture"] not in conservative or h5.get("status") != forward_bridge.MATURE:
            continue
        if h5.get("return", 0.0) < OUTCOME_POLICY_CONSTANTS["material_upside_return_greater_than_or_equal_to"]:
            continue
        axes = item["evidence_axes"]
        explanation = "FEATURE_FITNESS_MISSING" if axes["status"] == FIELD_NOT_RETAINED else "POLICY_TOO_CONSERVATIVE_CANDIDATE"
        findings.append({"feedback_identity": item["feedback_identity"], "ticker": item["ticker"], "decision_identity": item["decision_identity"], "posture": item["research_action_posture"], "T5_return": h5["return"], "evidence_at_T0": axes, "trigger": item["trigger"], "coherence_state": item["coherence_state"], "likely_explanation": explanation})
    return findings


def _failed_setups(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    entry_postures = {"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"}
    for item in records:
        h5 = item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}
        if item["research_action_posture"] not in entry_postures or h5.get("status") != forward_bridge.MATURE:
            continue
        if h5.get("return", 0.0) >= OUTCOME_POLICY_CONSTANTS["adverse_return_strictly_less_than"]:
            continue
        findings.append({"feedback_identity": item["feedback_identity"], "ticker": item["ticker"], "decision_identity": item["decision_identity"], "posture": item["research_action_posture"], "T5_return": h5["return"], "classification": "NORMAL_MARKET_UNCERTAINTY", "reason": "NO_FORWARD_EVALUABLE_T0_INVALIDATION_CONDITION_RETAINED"})
    return findings


def build_feedback_artifact(root: str | Path) -> dict[str, Any]:
    """Build a deterministic retained-only feedback artifact for the local corpus."""
    corpus = discover_prospective_corpus(root)
    modern = _modern_snapshot_candidates(root)
    legacy_chain = corpus["qualified_session_chain"]
    legacy_snapshots = retained_session_snapshots(root, legacy_chain)
    records: list[dict[str, Any]] = []
    # Modern snapshots are the sole T0 source for future runs.  Their full
    # decision content, condition serialization and T0 close facts were sealed
    # before the canonical handoff; a later mutable integrated-artifact path is
    # therefore never consulted here.
    for candidate in modern["genuine"]:
        snapshot = candidate["snapshot"]
        inventory = candidate["inventory"]
        source = snapshot.get("source_integrated_decision_artifact") or {}
        artifact = {
            "session": snapshot.get("session"), "artifact_identity": source.get("artifact_identity"),
            "requested_at": None,
        }
        temporal = {
            "contract_version": TEMPORAL_CONTRACT_VERSION, "status": GENUINE,
            "decision_session": snapshot.get("session"),
            "decision_artifact_identity": source.get("artifact_identity"),
            "daily_session_operation_identity": snapshot.get("daily_session_operation_identity"),
            "canonical_handoff_path": inventory.get("canonical_handoff_path"),
            "operation_manifest_path": inventory.get("operation_manifest_path"),
            "proof_reason_codes": inventory.get("proof_reason_codes"),
        }
        for ticker, retained in sorted((snapshot.get("records") or {}).items()):
            if not isinstance(retained, Mapping):
                continue
            decision = retained.get("integrated_decision_at_t0")
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            records.append(_feedback_record(
                artifact=artifact, source_path=inventory["snapshot_path"], temporal=temporal,
                record=decision, snapshots=modern["snapshots"], chain=modern["chain"],
                t0_snapshot=snapshot, t0_snapshot_record=retained,
            ))
    # Legacy candidates retain their prior conservative qualification.  They
    # remain useful only for the fields they actually captured at T0.
    for candidate in corpus["genuine_artifacts"]:
        artifact = candidate["artifact"]
        for ticker, decision in sorted((artifact.get("records") or {}).items()):
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            records.append(_feedback_record(artifact=artifact, source_path=candidate["artifact_path"], temporal=candidate["temporal"], record=decision, snapshots=legacy_snapshots, chain=legacy_chain))
    records.sort(key=lambda row: (str(row["decision_session"]), str(row["ticker"]), str(row["decision_identity"])))
    by_posture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_coherence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_posture[str(row["research_action_posture"])].append(row)
        by_coherence[str(row["coherence_state"])].append(row)
        axes = row["evidence_axes"]
        if axes["status"] == FIELD_NOT_RETAINED:
            by_axis[FIELD_NOT_RETAINED].append(row)
        else:
            for name, axis in axes["axis_states"].items():
                by_axis[name + ":" + str(axis.get("state"))].append(row)
    false_negatives = _false_negatives(records)
    failed_setups = _failed_setups(records)
    horizon_coverage = {
        name: dict(sorted(Counter(row["forward_outcomes"]["horizons"][name]["status"] for row in records).items()))
        for name in forward_bridge.FORWARD_HORIZONS
    }
    required = {
        ticker: [row for row in records if row["ticker"] == ticker] or [{"ticker": ticker, "status": "NO_PROSPECTIVE_CASE"}]
        for ticker in REQUIRED_TICKERS
    }
    policy_candidates = [{
        "disposition": "MORE_PROSPECTIVE_EVIDENCE_REQUIRED", "current_rule": "Outcome feedback never mutates current daily posture policy.",
        "observed_prospective_counterexamples": len(false_negatives) + len(failed_setups), "sample_size": sum(1 for row in records if row["forward_outcomes"]["horizons"]["forward_close_return_5"]["status"] == forward_bridge.MATURE),
        "why_current_rule_may_be_too_restrictive_or_loose": "No mature T5 close-return sample exists in the temporally qualified corpus.",
        "possible_bounded_change": None, "expected_affected_cohort": None, "risk_of_change": "LOOK_AHEAD_OR_THIN_SAMPLE_OVERFIT", "evidence_strength": "INSUFFICIENT", "policy_mutated": False,
    }]
    corpus_health = retention.build_corpus_health(
        snapshot_inventory=modern["discovery"], feedback_artifact={"feedback_records": records},
    )
    artifact = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "outcome_policy_constants": OUTCOME_POLICY_CONSTANTS,
        "prospective_corpus": {"candidate_artifact_count": len(corpus["inventory"]), "genuine_artifact_count": len(corpus["genuine_artifacts"]), "immutable_snapshot_count": len(modern["discovery"]["inventory"]), "genuine_immutable_snapshot_count": len(modern["genuine"]), "genuine_decision_count": len(records), "unique_sessions": sorted(set(legacy_chain) | set(modern["chain"])), "unique_tickers": len({row["ticker"] for row in records}), "classification_counts": corpus["classification_counts"], "snapshot_classification_counts": modern["discovery"]["classification_counts"]},
        "temporal_qualification": {"artifact_inventory": corpus["inventory"], "immutable_snapshot_inventory": modern["discovery"]["inventory"], "handoff_snapshot_inventory": modern["discovery"]["handoff_snapshot_inventory"], "qualified_session_chain": sorted(set(legacy_chain) | set(modern["chain"])), "retained_snapshot_sessions": sorted(set(legacy_snapshots) | set(modern["snapshots"])), "temporal_gate": "LEGACY_CANONICAL_HANDOFF_OR_IMMUTABLE_T0_SNAPSHOT_PLUS_RETAINED_DAILY_OPERATION"},
        "feedback_records": records, "forward_outcome_coverage": {"horizons": horizon_coverage, "close_excursions": {"CLOSE_MFE_CLOSE_MAE_ONLY": True, "intraday_mfe_mae": "NOT_CLAIMED"}},
        "posture_outcome_summary": _summary(by_posture, dimension="research_action_posture"),
        "coherence_outcome_summary": _summary(by_coherence, dimension="evidence_axis_coherence"),
        "evidence_axis_outcome_summary": _summary(by_axis, dimension="evidence_axis_state"),
        "false_negative_cases": false_negatives, "failed_setup_cases": failed_setups,
        "trigger_invalidation_outcomes": [row["trigger_invalidation_outcome"] | {"feedback_identity": row["feedback_identity"], "ticker": row["ticker"]} for row in records],
        "prospective_corpus_health": corpus_health,
        "policy_diagnostic_candidates": policy_candidates, "required_ticker_cases": required,
        "authority_boundary": {"downstream_observation_only": True, "no_retroactive_recommendation_reconstruction": True, "no_policy_mutation": True, "no_probability_or_calibration": True, "no_raw_as_traded_or_pit_authority": True, "no_daily_decision_feedback_loop": True},
    }
    return _identity(artifact, "prospective_decision_outcome_feedback:")


def evidence_views(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Small, non-duplicative views used by the milestone evidence package."""
    return {
        "prospective_corpus_inventory.json": {"prospective_corpus": artifact["prospective_corpus"], "artifact_inventory": artifact["temporal_qualification"]["artifact_inventory"], "required_ticker_cases": artifact["required_ticker_cases"]},
        "temporal_qualification.json": artifact["temporal_qualification"],
        "forward_outcome_coverage.json": artifact["forward_outcome_coverage"],
        "posture_outcome_summary.json": artifact["posture_outcome_summary"],
        "coherence_outcome_summary.json": artifact["coherence_outcome_summary"],
        "evidence_axis_outcome_summary.json": artifact["evidence_axis_outcome_summary"],
        "false_negative_cases.json": {"cases": artifact["false_negative_cases"], "sample_note": "Only temporally-qualified, mature T5 cases may appear."},
        "failed_setup_cases.json": {"cases": artifact["failed_setup_cases"], "sample_note": "Only temporally-qualified, mature T5 entry-relevant cases may appear."},
        "trigger_invalidation_outcomes.json": {"outcomes": artifact["trigger_invalidation_outcomes"], "authority_boundary": "NO_TRADE_EXECUTION_OR_INFERRED_BOUNDARY_OPERATOR"},
        "prospective_corpus_health.json": artifact["prospective_corpus_health"],
        "policy_diagnostic_candidates.json": {"candidates": artifact["policy_diagnostic_candidates"], "policy_mutated": False},
        "product_feedback_gap_matrix.json": {
            "gaps": [
                {"area": "forward_close_depth", "state": "PARTIAL_BY_EVIDENCE", "detail": "Only retained canonical sessions and exact close snapshots are used."},
                {"area": "evidence_axis_snapshot", "state": "FIELD_NOT_RETAINED_AT_T0", "detail": "Qualified legacy artifacts predate additive axis snapshots; no backfill is allowed."},
                {"area": "trigger_invalidation", "state": "BOUNDARY_OPERATOR_NOT_RETAINED_AT_T0", "detail": "Levels/states are retained but not a forward-evaluable condition."},
                {"area": "intraday_excursion", "state": "UNAVAILABLE_HIGH_LOW_BASIS", "detail": "Only CLOSE_MFE/CLOSE_MAE are emitted."},
            ],
            "authority_boundary": artifact["authority_boundary"],
        },
    }
