"""Deterministic delivery projections for one Daily Research Session Operation.

This module is deliberately downstream-only: it reshapes the already validated
operation, Product V2, and selected source artifacts.  It never derives a score,
recommendation, target, probability, or execution instruction.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from field_temporal_contract import stable_id


AI_CONTRACT = "ai_research_session_bundle/v1"
COCKPIT_CONTRACT = "current_decision_cockpit_projection/v2"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _records(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    for key in ("records", "ticker_contexts", "per_ticker"):
        found = value.get(key)
        if isinstance(found, Mapping):
            return found
    return {}


def _slim(value: Any, *, depth: int = 0) -> Any:
    """Bound the optional 1,683-row companion without hiding missingness.

    Full upstream records can repeat whole peer cohorts and source lineage trees.
    This retains named, deterministic research fields while limiting nested
    structural duplication; it is not a semantic transformation.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:600] + "…[TRUNCATED_FOR_COMPACT_DELIVERY]" if len(value) > 600 else value
    if isinstance(value, list):
        kept = [_slim(item, depth=depth + 1) for item in value[:12]]
        if len(value) > 12:
            kept.append(f"…[{len(value) - 12}_MORE_ITEMS_OMITTED_FOR_COMPACT_DELIVERY]")
        return kept
    if isinstance(value, Mapping):
        if depth >= 1:
            return {"status": value.get("status", "COMPACT_NESTED_CONTEXT_OMITTED"), "compact_delivery_state": "NESTED_CONTEXT_OMITTED"}
        return {str(key): _slim(item, depth=depth + 1) for key, item in value.items() if str(key) not in {"raw_payload", "raw_observation", "source_payload"}}
    return str(value)


def _valuation_handoff(row: Any) -> dict[str, Any]:
    """Pass through existing valuation authority labels without ranking or cheap/expensive claims."""
    if not isinstance(row, Mapping):
        return {"status": "UNAVAILABLE", "research_usable_is_not_authoritative": True, "is_actionable": False}
    metrics: dict[str, Any] = {}
    for name, metric in sorted((row.get("metrics") or {}).items()):
        if not isinstance(metric, Mapping):
            continue
        status = metric.get("status")
        if status == "READY":
            note = "AUTHORITATIVE_VALUATION_AVAILABLE"
        elif status == "RESEARCH_USABLE":
            note = "RESEARCH_PROXY_VALUATION_AVAILABLE_NOT_AUTHORITATIVE"
        elif status == "NOT_APPLICABLE":
            note = "NOT_APPLICABLE"
        else:
            note = "AUTHORITATIVE_VALUATION_UNAVAILABLE"
        metrics[str(name)] = {
            "status": status,
            "labels": list(metric.get("labels") or []),
            "blocked_reasons": list(metric.get("blocked_reasons") or []),
            "first_blocker": metric.get("first_blocker"),
            "authority_note": note,
        }
    shadow = row.get("shadow_proxy_valuation") if isinstance(row.get("shadow_proxy_valuation"), Mapping) else {}
    shadow_metrics = {}
    for name, metric in sorted((shadow.get("metrics") or {}).items()):
        if isinstance(metric, Mapping):
            shadow_metrics[str(name)] = {"status": metric.get("status"), "labels": list(metric.get("labels") or [])}
    price = row.get("price_input") if isinstance(row.get("price_input"), Mapping) else {}
    share = row.get("share_basis_input") if isinstance(row.get("share_basis_input"), Mapping) else {}
    financial = row.get("financial_input") if isinstance(row.get("financial_input"), Mapping) else {}
    strategy = row.get("value_strategy") if isinstance(row.get("value_strategy"), Mapping) else {}
    return {
        "valuation_session": price.get("session"),
        "price_status": price.get("status"),
        "share_basis_status": share.get("status"),
        "financial_authority": financial.get("authority"),
        "metrics": metrics,
        "shadow_proxy": {
            "authority_tier": shadow.get("authority_tier"),
            "share_basis_type": shadow.get("share_basis_type"),
            "metrics": shadow_metrics,
        },
        "value_strategy_status": strategy.get("status"),
        "research_usable_is_not_authoritative": True,
        "research_proxy_is_not_a_value_judgment": True,
        "is_actionable": False,
    }


def _compact_context(ticker: str, operation: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    """One source-preserving compact context for an arbitrary universe ticker."""
    return {
        "ticker": ticker,
        "current_decision_state": _slim(_records(inputs.get("tactical")).get(ticker)),
        "strategy_fit": _slim(_records(operation.get("strategy")).get(ticker)),
        "scenario": _slim(_records(operation.get("scenario")).get(ticker)),
        "peer_context": _slim(_records(operation.get("peer")).get(ticker)),
        "fundamental_context": _slim(_records(inputs.get("fundamental")).get(ticker)),
        "valuation_context": _valuation_handoff(_records(inputs.get("valuation")).get(ticker)),
        "market_flow_positioning": _slim(_records(inputs.get("market_flow_positioning")).get(ticker)),
        "corporate_intelligence_context": _slim(_records(inputs.get("corporate_intelligence")).get(ticker)),
        "authority_boundary": copy.deepcopy((operation.get("product") or {}).get("authority_boundary") or {}),
    }


def build_dashboard_projection(operation: Mapping[str, Any]) -> dict[str, Any]:
    """The released cockpit's deterministic, Product V2-shaped data payload."""
    product, manifest = operation["product"], operation["manifest"]
    projection: dict[str, Any] = {
        "schema_version": COCKPIT_CONTRACT,
        "projection_kind": "RELEASED_HUMAN_DECISION_COCKPIT",
        "session": manifest["market_session"],
        "authority_boundary": copy.deepcopy(product["authority_boundary"]),
        "source": {
            "operation_identity": manifest["operation_identity"],
            "product_identity": product["artifact_identity"],
            "producer_head": manifest["producer_head"],
            "consumer_head": manifest["consumer_head"],
            "input_artifacts": copy.deepcopy(manifest["input_artifacts"]),
            "output_artifacts": copy.deepcopy(manifest["outputs"]),
            "warnings": copy.deepcopy(manifest["warnings"]),
            "session_coherence": copy.deepcopy(manifest["session_coherence"]),
        },
        "market_overview": copy.deepcopy(product["market_brief"]),
        "research_discovery": {"cohorts": copy.deepcopy(product["research_cohorts"]), "high_priority_review": copy.deepcopy(product["high_priority_full_universe_review_set"])},
        "watchlist": copy.deepcopy(product["watchlist"]),
        "ticker_cards": copy.deepcopy(product["detailed_research_cards"]),
        "risk_data_gaps": copy.deepcopy(product["risk_data_gap_panel"]),
        "macro_context": copy.deepcopy(product["macro_context"]),
        "portfolio_risk": copy.deepcopy(operation.get("portfolio_risk") or {"status": "NO_EXPLICIT_PORTFOLIO_SUPPLIED", "is_actionable": False, "message": "No explicit portfolio-risk envelope was supplied for this operation."}),
        "what_to_verify_next": copy.deepcopy(product["what_to_verify_next"]),
    }
    projection["projection_identity"] = "dashboard_decision_cockpit_projection:" + stable_id(projection)
    return projection


def build_delivery(operation: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Return primary JSON, NDJSON companion, manifest, brief, and cockpit projection bytes."""
    product, manifest = operation["product"], operation["manifest"]
    session = manifest["market_session"]
    cards = product["detailed_research_cards"]
    useful_tickers = sorted(cards)
    primary: dict[str, Any] = {
        "schema_version": AI_CONTRACT,
        "session": session,
        "operation_identity": manifest["operation_identity"],
        "product_identity": product["artifact_identity"],
        "producer_head": manifest["producer_head"],
        "consumer_compatible_contract_version": "current_daily_decision_research_contract/v1",
        "authority_boundary": copy.deepcopy(product["authority_boundary"]),
        "market": {"summary": copy.deepcopy(product["market_brief"]), "macro": copy.deepcopy(product["macro_context"]), "flow_coverage": copy.deepcopy((manifest.get("coverage_summary") or {}).get("market_flow_positioning")), "limitations": copy.deepcopy(manifest["warnings"])},
        "research_cohorts": {"watchlist": copy.deepcopy(product["watchlist"]), "high_priority_review": copy.deepcopy(product["high_priority_full_universe_review_set"]), "deterministic_cohorts": copy.deepcopy(product["research_cohorts"]), "entry_relevant_90_count": product["aggregate_validation"]["entry_relevant_90_count"]},
        "ticker_research_contexts": {ticker: copy.deepcopy(cards[ticker]) for ticker in useful_tickers},
        "portfolio_risk": copy.deepcopy(operation.get("portfolio_risk") or {"status": "NO_EXPLICIT_PORTFOLIO_SUPPLIED", "is_actionable": False}),
        "lineage": {"input_artifacts": copy.deepcopy(manifest["input_artifacts"]), "output_artifacts": copy.deepcopy(manifest["outputs"]), "session_coherence": copy.deepcopy(manifest["session_coherence"])},
        "what_to_verify_next": copy.deepcopy(product["what_to_verify_next"]),
    }
    primary_bytes = (_canon(primary) + "\n").encode("utf-8")
    universe = sorted(_records(inputs.get("descriptive")))
    rows = [_canon(_compact_context(ticker, operation, inputs)) for ticker in universe]
    full_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    projection = build_dashboard_projection(operation)
    projection_bytes = (_canon(projection) + "\n").encode("utf-8")
    # Session operations are immutable/replayable.  A wall-clock timestamp would
    # change their bytes, so the manifest carries a transparent session-derived
    # creation marker rather than pretending a replay time is research evidence.
    created_at = f"{session}T00:00:00+00:00"
    manifest_payload = {
        "schema_version": "ai_research_bundle_manifest/v1",
        "session": session,
        "operation_identity": manifest["operation_identity"],
        "producer_head": manifest["producer_head"],
        "consumer_compatible_contract_version": "current_daily_decision_research_contract/v1",
        "primary_bundle_filename": "ai_research_session_bundle.json",
        "full_universe_companion_filename": "ai_research_full_universe.ndjson",
        "dashboard_projection_filename": "current_decision_cockpit_projection.json",
        "files": {
            "ai_research_session_bundle.json": {"bytes": len(primary_bytes), "sha256": _hash_bytes(primary_bytes)},
            "ai_research_full_universe.ndjson": {"bytes": len(full_bytes), "sha256": _hash_bytes(full_bytes), "record_count": len(universe)},
            "current_decision_cockpit_projection.json": {"bytes": len(projection_bytes), "sha256": _hash_bytes(projection_bytes), "projection_identity": projection["projection_identity"]},
        },
        "source_artifact_identities": copy.deepcopy(product["source_artifact_identities"]),
        "authority_boundary": copy.deepcopy(product["authority_boundary"]),
        "warnings": copy.deepcopy(manifest["warnings"]),
        "created_at": created_at,
        "creation_timestamp_basis": "SESSION_DERIVED_DETERMINISTIC_REPLAY",
    }
    manifest_bytes = (_canon(manifest_payload) + "\n").encode("utf-8")
    brief = "\n".join([f"# AI Research Session Bundle — {session}", "", f"Operation: `{manifest['operation_identity']}`", f"Product: `{product['artifact_identity']}`", "", "Upload `ai_research_session_bundle.json` for normal human-review research. It is not a recommendation, target, probability, sizing, or execution instruction.", "", "For an arbitrary ticker outside the useful research set, use `ai_research_full_universe.ndjson` or the deterministic ticker extractor.", "", "## Warnings", *[f"- {item}" for item in manifest["warnings"]], ""])
    return {"primary": primary_bytes, "full_universe": full_bytes, "manifest": manifest_bytes, "brief": brief.encode("utf-8"), "projection": projection_bytes}
