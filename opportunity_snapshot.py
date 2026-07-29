"""Deterministic VNM point-in-time opportunity snapshots; never a backtest or recommendation."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from opportunity_contract_validation import validate_no_prohibited_capabilities
from opportunity_ranking import DIMENSIONS, VERSION as RANKING_CONTRACT_VERSION, evaluate_opportunity
from scenario_analysis import VERSION as SCENARIO_CONTRACT_VERSION, evaluate_scenario_analysis

VERSION = "1.0.0"
IDENTITY_VERSION = "1.0.0"
_REQUIRED_VINTAGE = ("identity", "price_observation_cutoff", "financial_statement_publication_cutoff", "corporate_action_evidence_cutoff", "market_risk_calculation_cutoff")

class SnapshotInputError(ValueError):
    pass

def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()

def _instant(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise SnapshotInputError("timestamp_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotInputError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise SnapshotInputError("timestamp_timezone_missing")
    return parsed.astimezone(timezone.utc)

def _assert_not_later(value: Any, cutoff: datetime, field: str) -> None:
    if value is not None and _instant(value) > cutoff:
        raise SnapshotInputError("future_data_leakage:" + field)

def _validate_metadata(metadata: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    cutoff_text = metadata.get("knowledge_cutoff")
    cutoff = _instant(cutoff_text)
    _instant(metadata.get("calculation_timestamp"))
    vintage = metadata.get("input_vintage")
    if not isinstance(vintage, Mapping):
        raise SnapshotInputError("input_vintage_missing")
    for name in _REQUIRED_VINTAGE:
        if not vintage.get(name):
            raise SnapshotInputError("input_vintage_" + name + "_missing")
    for name in _REQUIRED_VINTAGE[1:]:
        _assert_not_later(vintage[name], cutoff, name)
    return cutoff_text, dict(vintage)

def _validate_lineage(lineage: Any, cutoff: datetime) -> list[dict[str, Any]]:
    if not isinstance(lineage, list) or not lineage:
        raise SnapshotInputError("input_lineage_missing")
    accepted: list[dict[str, Any]] = []
    for item in lineage:
        if not isinstance(item, Mapping):
            raise SnapshotInputError("input_lineage_invalid")
        if not item.get("lineage_id") or not item.get("source_hash") or not item.get("citation_id"):
            raise SnapshotInputError("citation_or_source_hash_missing")
        if item.get("derived") and (not item.get("derived_fact_lineage_complete") or not item.get("derived_fact_lineage")):
            raise SnapshotInputError("derived_lineage_incomplete")
        for field in ("observed_date", "published_date", "effective_date", "calculation_date"):
            _assert_not_later(item.get(field), cutoff, field)
        accepted.append(dict(item))
    return sorted(accepted, key=lambda item: str(item["lineage_id"]))

def _dimension_summary(opportunity: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    dimensions = opportunity.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise SnapshotInputError("opportunity_dimensions_missing")
    out: dict[str, Any] = {}
    available: list[str] = []
    incomplete: list[str] = []
    for name in DIMENSIONS:
        row = dimensions.get(name)
        if not isinstance(row, Mapping) or row.get("state") not in {"available", "unavailable", "partial", "incomparable", "inapplicable", "unknown", "limited", "blocked"}:
            raise SnapshotInputError("ranking_dimension_unreconstructable:" + name)
        state = str(row["state"])
        out[name] = {"state": state, "facts": row.get("facts", []), "data_warnings": row.get("data_warnings", []), "reason": row.get("reason"), "is_actionable": row.get("is_actionable") is True}
        (available if state == "available" else incomplete).append(name)
    return out, available, incomplete

def _market_risk_summary(market_risk: Mapping[str, Any] | None) -> dict[str, Any]:
    source = market_risk if isinstance(market_risk, Mapping) else {}
    keep = ("point_in_time_beta", "point_in_time_correlation", "return_risk", "portfolio_concentration", "position_sizing")
    return {name: dict(source[name]) if isinstance(source.get(name), Mapping) else {"state": "unavailable", "reason": "market_risk_fact_missing"} for name in keep}

def _identity(ticker: str, cutoff: str | None, vintage: Mapping[str, Any]) -> dict[str, Any]:
    return {"identity_version": IDENTITY_VERSION, "ticker": ticker, "knowledge_cutoff": cutoff, "calculation_contract_version": VERSION, "ranking_contract_version": RANKING_CONTRACT_VERSION, "scenario_contract_version": SCENARIO_CONTRACT_VERSION, "input_vintage_identity": vintage["identity"]}

def _safe_invalid_identity(ticker: str, metadata: Mapping[str, Any]) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    cutoff = metadata.get("knowledge_cutoff") if isinstance(metadata.get("knowledge_cutoff"), str) else None
    try:
        if cutoff is not None:
            _instant(cutoff)
    except SnapshotInputError:
        cutoff = None
    raw_vintage = metadata.get("input_vintage")
    vintage = dict(raw_vintage) if isinstance(raw_vintage, Mapping) else {}
    identity_value = vintage.get("identity")
    vintage["identity"] = identity_value if isinstance(identity_value, str) and identity_value else "unavailable_input_vintage"
    return _identity(ticker, cutoff, vintage), cutoff, vintage

def build_snapshot(*, ticker: str, opportunity: Mapping[str, Any], scenario: Mapping[str, Any], market_risk: Mapping[str, Any] | None, metadata: Mapping[str, Any], input_lineage: list[Mapping[str, Any]]) -> dict[str, Any]:
    if ticker != "VNM":
        raise SnapshotInputError("ticker_not_authorized")
    try:
        cutoff, vintage = _validate_metadata(metadata)
        identity = _identity(ticker, cutoff, vintage)
        snapshot_id = "vnm-pit-" + _digest(identity)
        lineage = _validate_lineage(input_lineage, _instant(cutoff))
        dimensions, available, incomplete = _dimension_summary(opportunity)
        if not isinstance(scenario, Mapping) or not isinstance(scenario.get("scenarios"), Mapping):
            raise SnapshotInputError("scenario_inputs_unavailable")
        snapshot = {"schema_version": VERSION, "snapshot_id": snapshot_id, "snapshot_identity": identity, "ticker": ticker, "knowledge_cutoff": cutoff, "calculation_timestamp": metadata["calculation_timestamp"], "input_vintage": vintage, "state": "available" if not incomplete else "partial", "ranking": {"state": opportunity.get("state", "unknown"), "dimensions": dimensions, "facts": opportunity.get("facts", []), "data_warnings": opportunity.get("data_warnings", []), "inferences": opportunity.get("inferences", []), "hypotheses": opportunity.get("hypotheses", []), "interpretation_limits": opportunity.get("interpretation_limits", [])}, "scenarios": {"state": scenario.get("state", "unknown"), "records": scenario["scenarios"], "facts": (scenario.get("evidence_inventory") or {}).get("facts", []), "data_warnings": scenario.get("data_warnings", []), "unknowns": scenario.get("unknowns", []), "inferences": (scenario.get("evidence_inventory") or {}).get("inferences", []), "hypotheses": (scenario.get("evidence_inventory") or {}).get("hypotheses", [])}, "market_risk": _market_risk_summary(market_risk), "input_lineage": lineage, "available_ranking_dimensions": available, "unavailable_or_partial_dimensions": incomplete, "gate_failures": [], "backtest_outputs": []}
    except SnapshotInputError as exc:
        identity, safe_cutoff, safe_vintage = _safe_invalid_identity(ticker, metadata)
        snapshot_id = "vnm-pit-" + _digest(identity)
        snapshot = {"schema_version": VERSION, "snapshot_id": snapshot_id, "snapshot_identity": identity, "ticker": ticker, "knowledge_cutoff": safe_cutoff, "calculation_timestamp": None, "input_vintage": safe_vintage, "state": "unavailable", "ranking": {"state": "unavailable", "dimensions": {}, "facts": [], "data_warnings": [str(exc)], "inferences": [], "hypotheses": []}, "scenarios": {"state": "unavailable", "records": {}, "facts": [], "data_warnings": [str(exc)], "unknowns": [], "inferences": [], "hypotheses": []}, "market_risk": _market_risk_summary(None), "input_lineage": [], "available_ranking_dimensions": [], "unavailable_or_partial_dimensions": list(DIMENSIONS), "gate_failures": [str(exc)], "backtest_outputs": []}
    validate_no_prohibited_capabilities(snapshot)
    return snapshot

def serialize_snapshot(snapshot: Mapping[str, Any]) -> bytes:
    return _canonical(snapshot).encode("utf-8")

def _pilot_entry() -> dict[str, Any]:
    fact = {"value": 1, "period_identity": {"period": "2024", "period_type": "annual"}, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "pilot", "observation_ids": ["obs-vnm"], "citation_id": "cit-vnm", "evidence_id": "evi-vnm"}
    return {"fundamental_quality": {"models": {"financial_strength": {"result_state": "available", "used_input_facts": {"net_income": fact}}}}, "relative_valuation": {"methods": {"pb": {"state": "available", "is_actionable": True, "provenance": {"citation_id": "pb-vnm"}}}}, "freshness": {"daily_prices": {"is_actionable": True}, "technical_signals": {"is_actionable": True}}, "analysis_readiness": {"domains": {"market_technical": {"state": "ready"}}}, "ta_signal": {"above_sma50": True}, "corporate_intelligence": {}}

def run_frozen_pilot() -> list[dict[str, Any]]:
    entry = _pilot_entry(); opportunity = evaluate_opportunity(entry, ticker="VNM", entity_type="corporate")
    scenario = evaluate_scenario_analysis({"freshness": entry["freshness"], "readiness": entry["analysis_readiness"]["domains"], "technical": entry["ta_signal"], "opportunity": opportunity}, "2026-06-30T00:00:00Z")
    lineage = [{"lineage_id": "vnm-financial-2024", "citation_id": "cit-vnm", "source_hash": "a" * 64, "observed_date": "2026-01-01T00:00:00Z", "published_date": "2026-01-02T00:00:00Z", "effective_date": "2026-01-02T00:00:00Z", "calculation_date": "2026-01-03T00:00:00Z", "derived": False}]
    result=[]
    for cutoff, vintage in (("2026-02-01T00:00:00Z", "vnm-20260201"), ("2026-06-30T00:00:00Z", "vnm-20260630")):
        metadata={"knowledge_cutoff": cutoff, "calculation_timestamp": "2026-07-29T00:00:00Z", "input_vintage": {"identity": vintage, "price_observation_cutoff": "2026-01-03T00:00:00Z", "financial_statement_publication_cutoff": "2026-01-02T00:00:00Z", "corporate_action_evidence_cutoff": "2026-01-02T00:00:00Z", "market_risk_calculation_cutoff": "2026-01-03T00:00:00Z"}}
        risk={"point_in_time_beta": {"state": "available" if cutoff > "2026-03" else "unavailable"}, "point_in_time_correlation": {"state": "available" if cutoff > "2026-03" else "unavailable"}}
        snap=build_snapshot(ticker="VNM", opportunity=opportunity, scenario=scenario, market_risk=risk, metadata=metadata, input_lineage=lineage)
        if serialize_snapshot(snap) != serialize_snapshot(build_snapshot(ticker="VNM", opportunity=opportunity, scenario=scenario, market_risk=risk, metadata=metadata, input_lineage=lineage)):
            raise RuntimeError("non_deterministic_snapshot")
        result.append({"knowledge_cutoff": cutoff, "snapshot_id": snap["snapshot_id"], "input_vintage_id": vintage, "available_ranking_dimensions": snap["available_ranking_dimensions"], "unavailable_or_partial_dimensions": snap["unavailable_or_partial_dimensions"], "scenario_availability": snap["scenarios"]["state"], "market_risk": snap["market_risk"], "lineage_status": "pass", "deterministic_output_hash": _digest(serialize_snapshot(snap).decode("utf-8"))})
    return result

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--frozen-pilot", action="store_true"); args=parser.parse_args()
    if args.frozen_pilot: print(json.dumps(run_frozen_pilot(), ensure_ascii=False, sort_keys=True))
