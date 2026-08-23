"""Foreground, retained-evidence daily research session operation.

The registry is an explicit identity selection boundary: no glob/latest discovery
is permitted.  Downstream peer, scenario, and daily-product artifacts are rebuilt
from that coherent selection rather than reusing a same-date but mismatched output.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from current_daily_decision_research_product import build as build_product, content_identity as product_identity, markdown
from current_evidence_bound_scenario import build as build_scenario, content_identity as scenario_identity
from field_temporal_contract import stable_id
from prospective_research_learning import freeze_current_decision_surface
from sector_aware_relative_research import build as build_peer, content_identity as peer_identity

CONTRACT_VERSION = "daily_research_session_operation/v1"
REQUIRED = ("descriptive", "screening", "tactical", "triage", "fundamental", "valuation", "catalyst")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identity(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value)); payload.pop("operation_identity", None)
    return "daily_research_session_operation:" + stable_id(payload)


def load_registry(root: Path, registry_path: Path | None = None) -> Mapping[str, Any]:
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("contract_version") != "daily_research_session_input_registry/v1":
        raise ValueError("SESSION_INPUT_REGISTRY_CONTRACT_INVALID")
    return registry


def resolve_inputs(root: Path, session: str, registry: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    selection = (registry.get("sessions") or {}).get(session)
    if not isinstance(selection, Mapping):
        raise ValueError("SESSION_NOT_REGISTERED_EXPLICIT_INPUT_MANIFEST_REQUIRED")
    if set(selection) != set(REQUIRED):
        raise ValueError("SESSION_INPUT_REGISTRY_INCOMPLETE")
    values: dict[str, Any] = {}; metadata: dict[str, Mapping[str, Any]] = {}
    for name in REQUIRED:
        entry = selection[name]
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("artifact_identity"), str):
            raise ValueError("SESSION_INPUT_REGISTRY_ENTRY_INVALID:" + name)
        path = root / entry["path"]
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("artifact_identity") != entry["artifact_identity"]:
            raise ValueError("SESSION_INPUT_IDENTITY_MISMATCH:" + name)
        values[name], metadata[name] = value, entry
    return values, metadata


def validate_coherence(inputs: Mapping[str, Any], session: str) -> dict[str, Any]:
    descriptive, screening, tactical, triage = (inputs[key] for key in ("descriptive", "screening", "tactical", "triage"))
    if descriptive.get("session") != session or screening.get("session") != session or tactical.get("session") != session or triage.get("source_market_session") != session:
        raise ValueError("SESSION_COHERENCE_MISMATCH")
    descriptive_id, screening_id = descriptive.get("artifact_identity"), screening.get("artifact_identity")
    if (screening.get("input_lineage") or {}).get("current_descriptive_artifact_identity") != descriptive_id:
        raise ValueError("SCREENING_DESCRIPTIVE_LINEAGE_MISMATCH")
    tactical_sources = tactical.get("source_artifacts") or {}
    if tactical_sources.get("descriptive") != descriptive_id or tactical_sources.get("screening") != screening_id:
        raise ValueError("TACTICAL_UPSTREAM_LINEAGE_MISMATCH")
    if inputs["valuation"].get("valuation_session") != session:
        raise ValueError("VALUATION_SESSION_MISMATCH")
    lineage = descriptive.get("input_lineage") or {}
    if not lineage.get("technical_history_recovery_artifact_identity"):
        raise ValueError("RECOVERED_TECHNICAL_LINEAGE_REQUIRED")
    coverage = (descriptive.get("market_breadth") or {}).get("same_session_technical_feature_available_count")
    if coverage != (tactical.get("coverage") or {}).get("classified_count"):
        raise ValueError("TECHNICAL_COVERAGE_TACTICAL_CLASSIFIED_MISMATCH")
    return {"session": session, "technical_coverage_semantics": {"same_session_technical_feature_available_count": coverage, "current_active_equity_denominator": descriptive["market_breadth"]["current_active_equity_denominator"], "observed_session_cohort": descriptive["market_breadth"]["observed_session_cohort"], "semantic_note": "956 is same-session technical feature coverage and tactical classified count after retained technical recovery; 763 is superseded pre-recovery coverage and is rejected."}, "accepted_degraded_inputs": {"catalyst": "EARLIER_RETAINED_CATALYST_CONTEXT"}, "incompatible_inputs": []}


def build_operation(inputs: Mapping[str, Any], session: str, *, producer_head: str, consumer_head: str, generation_context: str = "RETAINED_FIXED_TIME_REPLAY") -> dict[str, Any]:
    coherence = validate_coherence(inputs, session)
    peer = build_peer(descriptive=inputs["descriptive"], tactical=inputs["tactical"], fundamental=inputs["fundamental"], valuation=inputs["valuation"])
    if peer_identity(peer)["artifact_sha256"] != peer["artifact_sha256"]: raise ValueError("PEER_ARTIFACT_SELF_VERIFICATION_FAILED")
    scenario = build_scenario(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], triage=inputs["triage"], catalyst=inputs["catalyst"], screening=inputs["screening"])
    if scenario_identity(scenario)["artifact_sha256"] != scenario["artifact_sha256"]: raise ValueError("SCENARIO_ARTIFACT_SELF_VERIFICATION_FAILED")
    product = build_product(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=scenario, triage=inputs["triage"])
    if product_identity(product)["artifact_sha256"] != product["artifact_sha256"]: raise ValueError("PRODUCT_ARTIFACT_SELF_VERIFICATION_FAILED")
    snapshot = freeze_current_decision_surface(inputs["tactical"], inputs["triage"], inputs["fundamental"], inputs["valuation"])
    input_manifest = {}
    for name, value in inputs.items():
        input_session = value.get("session") or value.get("source_market_session") or value.get("valuation_session") or value.get("research_session")
        freshness = "ACCEPTED_DEGRADED" if name == "catalyst" else "ACCEPTED_UNDATED_RETAINED_CONTEXT" if name == "fundamental" else "CURRENT_SESSION_COHERENT"
        input_manifest[name] = {"artifact_identity": value.get("artifact_identity"), "contract_version": value.get("contract_version"), "session": input_session, "freshness_state": freshness}
    manifest = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "market_session": session, "generation_context": generation_context, "producer_head": producer_head, "consumer_head": consumer_head, "input_artifacts": input_manifest, "session_coherence": coherence, "outputs": {"peer_relative": peer["artifact_identity"], "scenario": scenario["artifact_identity"], "daily_product": product["artifact_identity"], "prospective_snapshot": snapshot["snapshot_id"]}, "coverage_summary": {"technical": product["market_brief"]["coverage"]["same_session_technical_feature_available_count"], "watchlist_cards": product["watchlist"]["cards_available"], "high_priority_review": product["high_priority_full_universe_review_set"]["count"], "entry_relevant": product["aggregate_validation"]["entry_relevant_90_count"]}, "warnings": ["Catalyst context is explicitly earlier retained evidence.", "Fundamental context is retained/undated rather than session-stamped.", "Strict valuation and valuation peer comparison remain unavailable."], "authority_boundary": product["authority_boundary"]}
    manifest["operation_identity"] = _identity(manifest)
    return {"peer": peer, "scenario": scenario, "product": product, "snapshot": snapshot, "manifest": manifest}


def write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canon(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_SESSION_OPERATION_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload, encoding="utf-8")


def materialize(output_dir: Path, operation: Mapping[str, Any]) -> None:
    write_immutable(output_dir / "peer_relative_research_artifact.json", operation["peer"])
    write_immutable(output_dir / "scenario_artifact.json", operation["scenario"])
    write_immutable(output_dir / "current_daily_decision_research_product_artifact.json", operation["product"])
    text = markdown(operation["product"])
    markdown_path = output_dir / "current_daily_decision_research_brief.md"
    if markdown_path.exists() and markdown_path.read_text(encoding="utf-8") != text: raise ValueError("IMMUTABLE_SESSION_OPERATION_MARKDOWN_CONFLICT")
    markdown_path.write_text(text, encoding="utf-8")
    write_immutable(output_dir / "prospective_snapshot.json", operation["snapshot"])
    write_immutable(output_dir / "run_manifest.json", operation["manifest"])
