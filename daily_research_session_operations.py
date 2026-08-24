"""Foreground, retained-evidence daily research session operation.

The registry is an explicit identity selection boundary: no glob/latest discovery
is permitted.  Downstream peer, scenario, and daily-product artifacts are rebuilt
from that coherent selection rather than reusing a same-date but mismatched output.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from current_daily_decision_research_product import build as build_product, content_identity as product_identity, markdown
from current_evidence_bound_scenario import build as build_scenario, content_identity as scenario_identity
from field_temporal_contract import stable_id
from market_wide_current_corporate_intelligence import prospective_context
from polymorphic_current_strategy_classification import build as build_strategy, content_identity as strategy_identity, prospective_context as strategy_prospective_context
from current_portfolio_risk_envelope import build as build_portfolio_risk
from current_market_flow_positioning import prospective_context as flow_prospective_context
from current_macro_regime import session_context as macro_session_context
from current_opportunity_prioritization import build as build_opportunity, content_identity as opportunity_identity
from daily_opportunity_decision_queue import build as build_decision_queue, content_identity as decision_queue_identity, prospective_context as decision_queue_prospective_context
from prospective_research_learning import freeze_current_decision_surface
from sector_aware_relative_research import build as build_peer, content_identity as peer_identity
from ai_research_session_delivery import build_delivery

CONTRACT_VERSION = "daily_research_session_operation/v1"
REQUIRED = ("descriptive", "screening", "tactical", "triage", "fundamental", "valuation", "catalyst", "corporate_intelligence")
OPTIONAL = ("market_flow_positioning", "official_universe", "event_context")


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
    if not set(REQUIRED).issubset(selection) or not set(selection).issubset(set(REQUIRED) | set(OPTIONAL)):
        raise ValueError("SESSION_INPUT_REGISTRY_INCOMPLETE")
    values: dict[str, Any] = {}; metadata: dict[str, Mapping[str, Any]] = {}
    for name in tuple(REQUIRED) + tuple(name for name in OPTIONAL if name in selection):
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
    corporate = inputs["corporate_intelligence"]
    if corporate.get("contract_version") != "market_wide_current_corporate_intelligence/v1" or corporate.get("session") != session:
        raise ValueError("CORPORATE_INTELLIGENCE_SESSION_OR_CONTRACT_MISMATCH")
    if (corporate.get("source_artifact_identities") or {}).get("descriptive") != descriptive_id:
        raise ValueError("CORPORATE_INTELLIGENCE_DESCRIPTIVE_LINEAGE_MISMATCH")
    if set(corporate.get("records") or {}) != set(descriptive.get("records") or {}):
        raise ValueError("CORPORATE_INTELLIGENCE_UNIVERSE_MISMATCH")
    lineage = descriptive.get("input_lineage") or {}
    if not lineage.get("technical_history_recovery_artifact_identity"):
        raise ValueError("RECOVERED_TECHNICAL_LINEAGE_REQUIRED")
    coverage = (descriptive.get("market_breadth") or {}).get("same_session_technical_feature_available_count")
    if coverage != (tactical.get("coverage") or {}).get("classified_count"):
        raise ValueError("TECHNICAL_COVERAGE_TACTICAL_CLASSIFIED_MISMATCH")
    flow = inputs.get("market_flow_positioning")
    if flow and (flow.get("contract_version") != "current_market_flow_positioning/v1" or flow.get("session") != session):
        raise ValueError("MARKET_FLOW_POSITIONING_SESSION_OR_CONTRACT_MISMATCH")
    return {"session": session, "technical_coverage_semantics": {"same_session_technical_feature_available_count": coverage, "current_active_equity_denominator": descriptive["market_breadth"]["current_active_equity_denominator"], "observed_session_cohort": descriptive["market_breadth"]["observed_session_cohort"], "semantic_note": "956 is same-session technical feature coverage and tactical classified count after retained technical recovery; 763 is superseded pre-recovery coverage and is rejected."}, "corporate_intelligence_coverage": corporate.get("coverage"), "accepted_degraded_inputs": {"catalyst": "EARLIER_RETAINED_CATALYST_CONTEXT"}, "incompatible_inputs": []}


def build_operation(inputs: Mapping[str, Any], session: str, *, producer_head: str, consumer_head: str, generation_context: str = "RETAINED_FIXED_TIME_REPLAY", portfolio: Mapping[str, Any] | None = None, macro: Mapping[str, Any] | None = None) -> dict[str, Any]:
    coherence = validate_coherence(inputs, session)
    peer = build_peer(descriptive=inputs["descriptive"], tactical=inputs["tactical"], fundamental=inputs["fundamental"], valuation=inputs["valuation"])
    if peer_identity(peer)["artifact_sha256"] != peer["artifact_sha256"]: raise ValueError("PEER_ARTIFACT_SELF_VERIFICATION_FAILED")
    macro_context = macro_session_context(macro, session)
    flow = inputs.get("market_flow_positioning")
    scenario = build_scenario(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], triage=inputs["triage"], catalyst=inputs["catalyst"], screening=inputs["screening"], corporate_intelligence=inputs["corporate_intelligence"], macro_context=macro_context, market_flow_positioning=flow)
    if scenario_identity(scenario)["artifact_sha256"] != scenario["artifact_sha256"]: raise ValueError("SCENARIO_ARTIFACT_SELF_VERIFICATION_FAILED")
    strategy = build_strategy(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=scenario, corporate_intelligence=inputs["corporate_intelligence"], market_flow_positioning=flow)
    if strategy_identity(strategy)["artifact_sha256"] != strategy["artifact_sha256"]: raise ValueError("STRATEGY_ARTIFACT_SELF_VERIFICATION_FAILED")
    portfolio_risk = build_portfolio_risk(portfolio=portfolio, descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=scenario, strategy=strategy, corporate_intelligence=inputs["corporate_intelligence"], macro_context=macro_context, market_flow_positioning=flow) if portfolio else None
    official_universe, event_context_input = inputs.get("official_universe"), inputs.get("event_context")
    opportunity = decision_queue = opportunity_snapshot = None
    # official_universe/event_context are "current as of build" (not session-locked) inputs;
    # only attach the research-priority queue when a session explicitly registers both, so an
    # already-frozen session (e.g. 2026-08-21) is never retrofitted with knowledge it never had.
    if official_universe is not None and event_context_input is not None:
        opportunity = build_opportunity(official_universe=official_universe, screening=inputs["screening"], tactical=inputs["tactical"], strategy=strategy, scenario=scenario, fundamental=inputs["fundamental"], peer=peer, event_context=event_context_input, descriptive=inputs["descriptive"])
        if opportunity_identity(opportunity)["artifact_sha256"] != opportunity["artifact_sha256"]: raise ValueError("OPPORTUNITY_ARTIFACT_SELF_VERIFICATION_FAILED")
        decision_queue = build_decision_queue(opportunity=opportunity, triage=inputs["triage"])
        if decision_queue_identity(decision_queue)["artifact_sha256"] != decision_queue["artifact_sha256"]: raise ValueError("DECISION_QUEUE_ARTIFACT_SELF_VERIFICATION_FAILED")
        opportunity_snapshot = decision_queue_prospective_context(opportunity, decision_queue)
    product = build_product(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=peer, fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=scenario, triage=inputs["triage"], corporate_intelligence=inputs["corporate_intelligence"], strategy_classification=strategy, portfolio_risk=portfolio_risk, macro_context=macro_context, market_flow_positioning=flow, opportunity_decision_queue=decision_queue)
    if product_identity(product)["artifact_sha256"] != product["artifact_sha256"]: raise ValueError("PRODUCT_ARTIFACT_SELF_VERIFICATION_FAILED")
    snapshot = freeze_current_decision_surface(inputs["tactical"], inputs["triage"], inputs["fundamental"], inputs["valuation"])
    corporate_snapshot = prospective_context(inputs["corporate_intelligence"])
    strategy_snapshot = strategy_prospective_context(strategy)
    flow_snapshot = flow_prospective_context(flow) if flow else None
    input_manifest = {}
    for name, value in inputs.items():
        input_session = value.get("session") or value.get("source_market_session") or value.get("valuation_session") or value.get("research_session")
        freshness = "ACCEPTED_DEGRADED" if name == "catalyst" else "ACCEPTED_UNDATED_RETAINED_CONTEXT" if name == "fundamental" else "CURRENT_SESSION_COHERENT_WITH_RETAINED_EVENT_FRESHNESS" if name == "corporate_intelligence" else "ACCEPTED_CURRENT_ASOF_BUILD_NOT_SESSION_LOCKED" if name in ("official_universe", "event_context") else "CURRENT_SESSION_COHERENT"
        input_manifest[name] = {"artifact_identity": value.get("artifact_identity"), "contract_version": value.get("contract_version"), "session": input_session, "freshness_state": freshness}
    if portfolio_risk:
        input_manifest["explicit_portfolio"] = {"artifact_identity": portfolio_risk["input_identity"], "contract_version": "explicit_portfolio_input/v1", "session": portfolio_risk["session"], "freshness_state": "EXPLICIT_USER_OR_DEMONSTRATION_INPUT"}
    manifest = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "market_session": session, "generation_context": generation_context, "producer_head": producer_head, "consumer_head": consumer_head, "input_artifacts": input_manifest, "session_coherence": coherence, "outputs": {"peer_relative": peer["artifact_identity"], "scenario": scenario["artifact_identity"], "strategy_classification": strategy["artifact_identity"], "daily_product": product["artifact_identity"], "prospective_snapshot": snapshot["snapshot_id"], "corporate_intelligence_prospective_context": corporate_snapshot["snapshot_id"], "strategy_prospective_context": strategy_snapshot["snapshot_id"]}, "delivery_contract": {"ai_research_bundle": "ai_research_session_bundle/v1", "dashboard_projection": "current_decision_cockpit_projection/v2", "primary_filename": "ai_research_session_bundle.json", "full_universe_filename": "ai_research_full_universe.ndjson", "dashboard_projection_filename": "current_decision_cockpit_projection.json"}, "coverage_summary": {"technical": product["market_brief"]["coverage"]["same_session_technical_feature_available_count"], "watchlist_cards": product["watchlist"]["cards_available"], "high_priority_review": product["high_priority_full_universe_review_set"]["count"], "entry_relevant": product["aggregate_validation"]["entry_relevant_90_count"], "corporate_intelligence": inputs["corporate_intelligence"]["coverage"], "strategy": strategy["coverage"]}, "warnings": ["Catalyst context is explicitly earlier retained evidence.", "Corporate Intelligence uses retained source evidence; event freshness remains per record.", "Strategy fit is separate from entry action, scenario probability, and portfolio action.", "Fundamental context is retained/undated rather than session-stamped.", "Strict valuation and valuation peer comparison remain unavailable."], "authority_boundary": product["authority_boundary"]}
    if flow:
        manifest["outputs"]["market_flow_positioning_prospective_context"] = flow_snapshot["snapshot_id"]
        manifest["coverage_summary"]["market_flow_positioning"] = flow["coverage"]
        manifest["warnings"].append("Market flow/positioning is provider-scoped descriptive research only; no causality, institutional intent, liquidity, sizing, or execution authority.")
    manifest["operation_identity"] = _identity(manifest)
    if portfolio_risk:
        manifest["outputs"]["portfolio_risk"] = portfolio_risk["artifact_identity"]
        manifest["coverage_summary"]["portfolio_risk"] = {"portfolio_id": portfolio_risk["portfolio_id"], "positions": len(portfolio_risk["positions"]), "is_actionable": False}
        manifest["warnings"].append("Portfolio risk is an explicit-input descriptive envelope only; sizing, liquidity, correlation, volatility, VaR/CVaR, leverage, and execution remain blocked or not evaluated.")
        manifest["operation_identity"] = _identity(manifest)
    if macro:
        manifest["input_artifacts"]["macro"] = {"artifact_identity": macro.get("artifact_identity"), "contract_version": macro.get("contract_version"), "session": macro.get("current_research_as_of"), "freshness_state": macro_context["status"]}
        manifest["outputs"]["macro_context"] = macro_context
        manifest["warnings"].append("Macro evidence is accepted only when known by the retained equity session; otherwise it is preserved as unavailable context.")
        manifest["operation_identity"] = _identity(manifest)
    if decision_queue:
        manifest["outputs"]["opportunity_prioritization"] = opportunity["artifact_identity"]
        manifest["outputs"]["daily_opportunity_decision_queue"] = decision_queue["artifact_identity"]
        manifest["outputs"]["opportunity_decision_prospective_context"] = opportunity_snapshot["snapshot_id"]
        manifest["coverage_summary"]["opportunity_decision_queue"] = {"current_official_universe": opportunity["coverage"]["current_official_universe"], "priority_now": decision_queue["entry_relevant_summary"]["PRIORITY_NOW_TOTAL"], "priority_now_entry_relevant": decision_queue["entry_relevant_summary"]["PRIORITY_NOW_ENTRY_RELEVANT"], "primary_review_candidates": decision_queue["primary_review_candidates"]["count"]}
        manifest["warnings"].append("Research priority tier is a research-lane signal, not entry timing, full-position readiness, or position sizing; see entry_relevant and lane_specific_priority on each decision-queue record.")
        manifest["operation_identity"] = _identity(manifest)
    return {"inputs": dict(inputs), "peer": peer, "scenario": scenario, "strategy": strategy, "portfolio_risk": portfolio_risk, "macro_context": macro_context, "flow_snapshot": flow_snapshot, "opportunity": opportunity, "decision_queue": decision_queue, "opportunity_snapshot": opportunity_snapshot, "product": product, "snapshot": snapshot, "corporate_snapshot": corporate_snapshot, "strategy_snapshot": strategy_snapshot, "manifest": manifest}


def write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canon(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_SESSION_OPERATION_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload, encoding="utf-8")


def materialize(output_dir: Path, operation: Mapping[str, Any]) -> None:
    write_immutable(output_dir / "peer_relative_research_artifact.json", operation["peer"])
    write_immutable(output_dir / "scenario_artifact.json", operation["scenario"])
    write_immutable(output_dir / "strategy_classification_artifact.json", operation["strategy"])
    if operation.get("portfolio_risk"): write_immutable(output_dir / "portfolio_risk_envelope.json", operation["portfolio_risk"])
    write_immutable(output_dir / "current_daily_decision_research_product_artifact.json", operation["product"])
    text = markdown(operation["product"])
    markdown_path = output_dir / "current_daily_decision_research_brief.md"
    if markdown_path.exists() and markdown_path.read_text(encoding="utf-8") != text: raise ValueError("IMMUTABLE_SESSION_OPERATION_MARKDOWN_CONFLICT")
    markdown_path.write_text(text, encoding="utf-8")
    write_immutable(output_dir / "prospective_snapshot.json", operation["snapshot"])
    write_immutable(output_dir / "corporate_intelligence_prospective_context.json", operation["corporate_snapshot"])
    write_immutable(output_dir / "strategy_prospective_context.json", operation["strategy_snapshot"])
    if operation.get("flow_snapshot"): write_immutable(output_dir / "market_flow_positioning_prospective_context.json", operation["flow_snapshot"])
    if operation.get("decision_queue"):
        write_immutable(output_dir / "opportunity_prioritization_artifact.json", operation["opportunity"])
        write_immutable(output_dir / "daily_opportunity_decision_queue_artifact.json", operation["decision_queue"])
        write_immutable(output_dir / "opportunity_decision_prospective_context.json", operation["opportunity_snapshot"])
    delivery = build_delivery(operation, operation["inputs"])
    for filename, value in (("ai_research_session_bundle.json", delivery["primary"]), ("ai_research_full_universe.ndjson", delivery["full_universe"]), ("ai_research_bundle_manifest.json", delivery["manifest"]), ("ai_research_session_brief.md", delivery["brief"]), ("current_decision_cockpit_projection.json", delivery["projection"])):
        path = output_dir / filename
        if path.exists() and path.read_bytes() != value: raise ValueError("IMMUTABLE_SESSION_OPERATION_DELIVERY_CONFLICT:" + filename)
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
    write_immutable(output_dir / "run_manifest.json", operation["manifest"])


def run_session_operation(
    root: Path,
    *,
    session: str,
    producer_head: str,
    consumer_head: str,
    output_root: Path,
    registry_path: Path | None = None,
    generation_context: str = "RETAINED_FIXED_TIME_REPLAY",
    portfolio: Mapping[str, Any] | None = None,
    macro: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Build, Consumer-validate, and immutably materialize one exact operation.

    This is the reusable foreground integration seam.  Callers supply resolved
    repository heads and explicit optional inputs; it never discovers a
    ``latest`` artifact or performs acquisition.
    """
    inputs, _ = resolve_inputs(root, session, load_registry(root, registry_path))
    operation = build_operation(
        inputs,
        session,
        producer_head=producer_head,
        consumer_head=consumer_head,
        generation_context=generation_context,
        portfolio=portfolio,
        macro=macro,
    )
    consumer_root = root.parent / "ai-core-private"
    if str(consumer_root) not in sys.path:
        sys.path.insert(0, str(consumer_root))
    from builders.build_ticker_context import current_daily_decision_research_contract

    card_ticker = "ABB" if "ABB" in operation["product"]["detailed_research_cards"] else next(iter(operation["product"]["detailed_research_cards"]), None)
    if not card_ticker:
        raise ValueError("CONSUMER_E2E_REPRESENTATIVE_CARD_MISSING")
    card = operation["product"]["detailed_research_cards"][card_ticker]
    bundled = dict(card)
    bundled.update({
        "source_artifact_identity": operation["product"]["artifact_identity"],
        "source_session": session,
        "market_brief": operation["product"]["market_brief"],
        "authority_boundary": operation["product"]["authority_boundary"],
        "is_actionable": False,
    })
    if operation.get("portfolio_risk"):
        bundled["portfolio_risk"] = operation["portfolio_risk"]
    if operation.get("macro_context"):
        bundled["macro_context"] = operation["macro_context"]
    accepted = current_daily_decision_research_contract(
        {"tickers": {card_ticker: {"current_daily_decision_research": bundled}}}, card_ticker
    )
    if not accepted or accepted.get("status") == "malformed":
        raise ValueError("CONSUMER_E2E_FAIL_CLOSED")
    operation["manifest"]["consumer_e2e"] = {
        "status": "PASS",
        "representative_ticker": card_ticker,
        "consumer_contract": "current_daily_decision_research_contract",
    }
    operation["manifest"]["operation_identity"] = _identity(operation["manifest"])
    output_dir = output_root / session / operation["manifest"]["operation_identity"].split(":", 1)[1]
    materialize(output_dir, operation)
    return operation, output_dir
