"""One foreground, fail-closed Producer workflow for a completed session.

This module intentionally orchestrates existing retained-evidence contracts.  It
does not crawl providers, infer a market calendar, or create analytical truth.
New-session acquisition remains limited to already governed upstream routes; a
session is eligible here only after its exact evidence has been registered.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from daily_research_session_operations import load_registry, resolve_inputs, run_session_operation, validate_coherence
from field_temporal_contract import stable_id
from vn_time import VN_TZ, vn_now


CONTRACT_VERSION = "daily_producer_run/v1"
IMPLEMENTATION_REVISION = "1.0.1"
OWNER_FILENAMES = (
    "ai_research_session_bundle.json",
    "ai_research_full_universe.ndjson",
    "ai_research_bundle_manifest.json",
    "ai_research_session_brief.md",
)


class DailyProducerError(ValueError):
    """A deliberately concise operational refusal."""


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iso_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError as exc:
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:INVALID_SESSION_FORMAT") from exc


def resolve_latest_registered_completed_session(registry: Mapping[str, Any]) -> str:
    """Resolve only explicit completed-session ledger entries, never civil time."""
    ledger = registry.get("completed_sessions")
    if not isinstance(ledger, Mapping):
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:NO_GOVERNED_COMPLETED_SESSION_LEDGER")
    eligible = [session for session, row in ledger.items() if isinstance(row, Mapping) and row.get("status") == "COMPLETED_RETAINED_EVIDENCE"]
    if not eligible:
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:NO_GOVERNED_COMPLETED_SESSION")
    return sorted(eligible)[-1]


def completed_session_gate(registry: Mapping[str, Any], session: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Require a governed completed-session record and exact source compatibility."""
    session = _iso_date(session)
    now = now or vn_now()
    local_now = now.astimezone(VN_TZ)
    ledger = registry.get("completed_sessions")
    if not isinstance(ledger, Mapping):
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:NO_GOVERNED_COMPLETED_SESSION_LEDGER")
    record = ledger.get(session)
    if not isinstance(record, Mapping):
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:SESSION_NOT_GOVERNED_COMPLETED")
    if record.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:SESSION_COMPLETION_NOT_PROVED")
    if record.get("trading_day_valid") is not True:
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:TRADING_DAY_NOT_VALIDATED")
    if session >= local_now.date().isoformat():
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:TARGET_NOT_STRICTLY_BEFORE_LOCAL_DATE")
    return {
        "status": "PASS",
        "target_session": session,
        "trading_day_valid": True,
        "completion_status": record["status"],
        "completion_evidence": copy.deepcopy(record.get("completion_evidence") or {}),
        "current_local_time_context": {"timezone": "Asia/Ho_Chi_Minh", "observed_at": local_now.isoformat(timespec="seconds"), "policy": "LOCAL_TIME_NEVER_INFERRED_SESSION_COMPLETION"},
        "source_session_compatibility": "PENDING_EXACT_REGISTRY_RESOLUTION",
    }


def _disposition(name: str) -> tuple[str, bool, str]:
    policy = {
        "descriptive": ("REUSE_CURRENT_VALID_RETAINED", True, "DNSE/current-market retained exact-session research"),
        "screening": ("REUSE_CURRENT_VALID_RETAINED", True, "existing deterministic screening"),
        "tactical": ("REUSE_CURRENT_VALID_RETAINED", True, "existing tactical classifier"),
        "triage": ("REUSE_CURRENT_VALID_RETAINED", True, "existing entry-candidate triage"),
        "fundamental": ("REUSE_HISTORICAL_CONTEXT", True, "retained evidence; explicitly undated context"),
        "valuation": ("BLOCKED", False, "strict valuation remains blocked; shadow semantics are unchanged"),
        "catalyst": ("REUSE_HISTORICAL_CONTEXT", False, "retained earlier catalyst context"),
        "corporate_intelligence": ("REUSE_CURRENT_VALID_RETAINED", False, "retained source-linked corporate intelligence"),
        "market_flow_positioning": ("REUSE_CURRENT_VALID_RETAINED", False, "qualified DNSE value-flow projection; provider-limited"),
    }
    return policy.get(name, ("NOT_APPLICABLE", False, "no current producer dependency"))


def build_acquisition_plan(
    inputs: Mapping[str, Any],
    entries: Mapping[str, Mapping[str, Any]],
    session: str,
    *,
    macro: Mapping[str, Any] | None = None,
    portfolio: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe exact reuse/acquisition policy without pretending to acquire data."""
    rows = []
    for name in sorted(inputs):
        value, entry = inputs[name], entries[name]
        disposition, required, reason = _disposition(name)
        source_session = value.get("session") or value.get("source_market_session") or value.get("valuation_session") or value.get("research_session")
        rows.append({
            "input_class": name,
            "execution_disposition": disposition,
            "required_for_core_operation": required,
            "source_contract": value.get("contract_version"),
            "target_session": session,
            "source_session": source_session,
            "retrieval_time": value.get("retrieved_at") or value.get("generated_at") or "RETAINED_ARTIFACT_TIMESTAMP_PRESERVED_IN_SOURCE",
            "freshness": "ACCEPTED_DEGRADED" if name == "catalyst" else "ACCEPTED_UNDATED_RETAINED_CONTEXT" if name == "fundamental" else "EXACT_SESSION" if source_session == session else "CONTRACT_DEFINED_CONTEXT",
            "artifact_identity": entry["artifact_identity"],
            "artifact_path": entry["path"],
            "reason": reason,
        })
    rows.extend([
        {"input_class": "macro", "execution_disposition": "REUSE_HISTORICAL_CONTEXT" if macro else "OPTIONAL_UNAVAILABLE", "required_for_core_operation": False, "target_session": session, "source_session": (macro or {}).get("current_research_as_of"), "artifact_identity": (macro or {}).get("artifact_identity"), "reason": "Explicit retained macro context is passed through with its own session compatibility" if macro else "No retained macro artifact was explicitly supplied; Vietnam unavailable remains unavailable."},
        {"input_class": "explicit_portfolio", "execution_disposition": "REUSE_CURRENT_VALID_RETAINED" if portfolio else "NOT_APPLICABLE", "required_for_core_operation": False, "target_session": session, "source_session": session if portfolio else None, "artifact_identity": "portfolio_input:" + stable_id(portfolio) if portfolio else None, "reason": "Explicit portfolio is passed only to the optional portfolio-risk branch" if portfolio else "No explicit portfolio input supplied; watchlist is never treated as holdings."},
    ])
    return {"schema_version": "daily_producer_acquisition_plan/v1", "mode": "RETAINED_EVIDENCE_REUSE_ONLY", "target_session": session, "policy": "Existing governed acquisition routes may create retained inputs upstream; this orchestration stage never invents a provider or requalifies one.", "items": rows}


def _dependency_graph(plan: Mapping[str, Any]) -> dict[str, Any]:
    upstream = [row["input_class"] for row in plan["items"] if row["input_class"] not in {"macro", "explicit_portfolio"}]
    return {
        "schema_version": "daily_producer_dependency_graph/v1",
        "required_retained_inputs": [row["input_class"] for row in plan["items"] if row.get("required_for_core_operation")],
        "optional_local_failures": [row["input_class"] for row in plan["items"] if not row.get("required_for_core_operation")],
        "topology": [
            {"stage": "retained_source_evidence", "depends_on": upstream},
            {"stage": "daily_session_operation", "depends_on": ["retained_source_evidence"]},
            {"stage": "peer_scenario_strategy_product", "depends_on": ["daily_session_operation"]},
            {"stage": "ai_delivery_and_dashboard_projection", "depends_on": ["peer_scenario_strategy_product"]},
            {"stage": "daily_producer_manifest_and_parity", "depends_on": ["ai_delivery_and_dashboard_projection"]},
        ],
        "failure_policy": "Required exact-session lineage failures stop the operation. Optional macro, flow, corporate-intelligence, catalyst, strict-valuation, and portfolio states remain localized and explicitly labelled.",
    }


def _write_immutable(path: Path, value: bytes) -> None:
    if path.exists() and path.read_bytes() != value:
        raise DailyProducerError("IMMUTABLE_DAILY_PRODUCER_CONTENT_CONFLICT:" + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _verify_delivery(operation: Mapping[str, Any], operation_dir: Path) -> dict[str, Any]:
    bundle = json.loads((operation_dir / "ai_research_session_bundle.json").read_text(encoding="utf-8"))
    projection = json.loads((operation_dir / "current_decision_cockpit_projection.json").read_text(encoding="utf-8"))
    manifest = json.loads((operation_dir / "ai_research_bundle_manifest.json").read_text(encoding="utf-8"))
    expected_operation = operation["manifest"]["operation_identity"]
    expected_product = operation["product"]["artifact_identity"]
    if bundle.get("session") != operation["manifest"]["market_session"] or projection.get("session") != bundle.get("session"):
        raise DailyProducerError("AI_DASHBOARD_PARITY_SESSION_MISMATCH")
    if bundle.get("operation_identity") != expected_operation or projection.get("source", {}).get("operation_identity") != expected_operation:
        raise DailyProducerError("AI_DASHBOARD_PARITY_OPERATION_MISMATCH")
    if bundle.get("product_identity") != expected_product or projection.get("source", {}).get("product_identity") != expected_product:
        raise DailyProducerError("AI_DASHBOARD_PARITY_PRODUCT_MISMATCH")
    if bundle.get("lineage", {}).get("input_artifacts") != projection.get("source", {}).get("input_artifacts"):
        raise DailyProducerError("AI_DASHBOARD_PARITY_UPSTREAM_IDENTITY_MISMATCH")
    for filename, record in manifest.get("files", {}).items():
        path = operation_dir / filename
        if not path.is_file() or _sha(path.read_bytes()) != record.get("sha256"):
            raise DailyProducerError("AI_DELIVERY_SELF_VERIFICATION_FAILED:" + filename)
    return {"status": "PASS", "session": bundle["session"], "operation_identity": expected_operation, "product_identity": expected_product, "input_identity_parity": "PASS", "files_verified": sorted(manifest["files"])}


def _run_identity(session: str, producer_head: str, consumer_head: str, plan: Mapping[str, Any], operation_identity: str) -> str:
    return "daily_producer_run:" + stable_id({"contract_version": CONTRACT_VERSION, "implementation_revision": IMPLEMENTATION_REVISION, "session": session, "producer_head": producer_head, "consumer_head": consumer_head, "plan": plan, "operation_identity": operation_identity})


def run_daily_producer(
    root: Path,
    *,
    session: str | None,
    latest_completed_session: bool,
    producer_head: str,
    consumer_head: str,
    registry_path: Path | None = None,
    output_root: Path | None = None,
    operation_output_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    macro: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the one-command retained completed-session producer pipeline."""
    if bool(session) == bool(latest_completed_session):
        raise DailyProducerError("REFUSE_COMPLETED_SESSION_RUN:SELECT_EXACTLY_ONE_SESSION_MODE")
    registry = load_registry(root, registry_path)
    selected = resolve_latest_registered_completed_session(registry) if latest_completed_session else _iso_date(str(session))
    gate = completed_session_gate(registry, selected, now=now)
    inputs, entries = resolve_inputs(root, selected, registry)
    coherence = validate_coherence(inputs, selected)
    gate["source_session_compatibility"] = "PASS"
    plan = build_acquisition_plan(inputs, entries, selected, macro=macro, portfolio=portfolio)
    graph = _dependency_graph(plan)
    output_root = output_root or root / "operations-review" / "daily-producer-runs-v1"
    operation_output_root = operation_output_root or root / "operations-review" / "daily-research-session-operations-v1"
    operation, operation_dir = run_session_operation(
        root,
        session=selected,
        producer_head=producer_head,
        consumer_head=consumer_head,
        output_root=operation_output_root,
        registry_path=registry_path,
        generation_context="DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
        portfolio=portfolio,
        macro=macro,
    )
    parity = _verify_delivery(operation, operation_dir)
    run_identity = _run_identity(selected, producer_head, consumer_head, plan, operation["manifest"]["operation_identity"])
    run_dir = output_root / selected / run_identity.split(":", 1)[1]
    existing_run = (run_dir / "run_manifest.json").exists()
    copied: dict[str, dict[str, Any]] = {}
    for filename in OWNER_FILENAMES:
        data = (operation_dir / filename).read_bytes()
        _write_immutable(run_dir / filename, data)
        copied[filename] = {"sha256": _sha(data), "bytes": len(data)}
    projection = (operation_dir / "current_decision_cockpit_projection.json").read_bytes()
    _write_immutable(run_dir / "dashboard" / "current_decision_cockpit_projection.json", projection)
    copied["dashboard/current_decision_cockpit_projection.json"] = {"sha256": _sha(projection), "bytes": len(projection)}
    generated_at = f"{selected}T00:00:00+00:00"
    blocked_dimensions = ["STRICT_VALUATION", "NO_LIQUIDITY_SIZING_EXECUTION_AUTHORITY"]
    if not macro:
        blocked_dimensions.append("MACRO_OPTIONAL_UNAVAILABLE")
    if not portfolio:
        blocked_dimensions.append("NO_EXPLICIT_PORTFOLIO")
    manifest = {
        "schema_version": CONTRACT_VERSION,
        "implementation_revision": IMPLEMENTATION_REVISION,
        "run_identity": run_identity,
        "target_market_session": selected,
        "started_at": generated_at,
        "generated_at": generated_at,
        "timestamp_basis": "SESSION_DERIVED_DETERMINISTIC_REPLAY",
        "producer_head": producer_head,
        "consumer_head": consumer_head,
        "completed_session_gate": {**{key: value for key, value in gate.items() if key != "current_local_time_context"}, "current_local_time_context": {"timezone": "Asia/Ho_Chi_Minh", "policy": "EVALUATED_AT_RUNTIME_NOT_RETAINED_TO_KEEP_REPLAY_IMMUTABLE"}},
        "source_plan": plan,
        "dependency_graph": graph,
        "source_acquisition_result": {"status": "REUSED_RETAINED_EVIDENCE", "acquired": [], "reused": [row["input_class"] for row in plan["items"] if row["input_class"] not in {"macro", "explicit_portfolio"}], "blocked_or_unavailable": [row["input_class"] for row in plan["items"] if row["execution_disposition"] in {"BLOCKED", "OPTIONAL_UNAVAILABLE", "NOT_APPLICABLE"}]},
        "upstream_artifact_identities": copy.deepcopy(operation["manifest"]["input_artifacts"]),
        "daily_session_operation": {"identity": operation["manifest"]["operation_identity"], "directory": str(operation_dir.relative_to(root)).replace("\\", "/")},
        "daily_product_identity": operation["product"]["artifact_identity"],
        "ai_delivery": copied,
        "dashboard_projection": {"identity": json.loads(projection)["projection_identity"], **copied["dashboard/current_decision_cockpit_projection.json"]},
        "coverage_summary": copy.deepcopy(operation["manifest"]["coverage_summary"]),
        "warnings": copy.deepcopy(operation["manifest"]["warnings"]),
        "blocked_dimensions": blocked_dimensions,
        "coherence": coherence,
        "ai_dashboard_parity": parity,
        "self_verification": {"status": "PASS", "consumer_e2e": operation["manifest"].get("consumer_e2e"), "delivery_file_hashes": "PASS"},
        "authority_boundary": copy.deepcopy(operation["manifest"]["authority_boundary"]),
    }
    _write_immutable(run_dir / "run_manifest.json", _canon(manifest))
    pointer = {"schema_version": "daily_producer_latest_completed_navigation/v1", "navigation_only": True, "session": selected, "run_identity": run_identity, "daily_session_operation_identity": operation["manifest"]["operation_identity"], "relative_directory": str(run_dir.relative_to(output_root)).replace("\\", "/")}
    (output_root / "LATEST_COMPLETED_RUN.json").parent.mkdir(parents=True, exist_ok=True)
    (output_root / "LATEST_COMPLETED_RUN.json").write_bytes(_canon(pointer))
    return {"status": "COMPLETED", "session": selected, "run_identity": run_identity, "run_dir": run_dir, "operation": operation, "operation_dir": operation_dir, "manifest": manifest, "gate": gate, "reused_existing_run": existing_run}
