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
from current_daily_decision_research_product import ABSENT_OWNER_FOCUS_STATUS, is_present_research_card
from owner_research_focus import load_owner_research_focus, owner_focus_tickers
from financial_analysis_product_projection import context_for_ticker, validate_product_context


AI_CONTRACT = "ai_research_session_bundle/v1"
COCKPIT_CONTRACT = "current_decision_cockpit_projection/v2"
PRIMARY_HUMAN_REVIEW_FILENAME = "ai_research_session_bundle.json"
FULL_UNIVERSE_LOOKUP_FILENAME = "ai_research_full_universe.ndjson"
FULL_UNIVERSE_COMPANION_ROLE = "FULL_UNIVERSE_LOOKUP_ONLY"
PRIMARY_HUMAN_REVIEW_ROLE = "PRIMARY_NORMAL_HUMAN_REVIEW_INPUT"


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


def _delivery_financial_context(context: Mapping[str, Any] | None, ticker: str) -> dict[str, Any] | None:
    compact = context_for_ticker(context, ticker)
    if compact is None:
        return None
    # Deep lineage remains local/extractor-only.  Normal delivery retains the
    # logical reference and engine identity, never filesystem paths or raw rows.
    compact.pop("lineage", None)
    return compact


def _compact_context(ticker: str, operation: Mapping[str, Any], inputs: Mapping[str, Any],
                     financial_analysis_product_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One source-preserving compact context for an arbitrary universe ticker."""
    boundary = copy.deepcopy((operation.get("product") or {}).get("authority_boundary") or {})
    boundary["is_actionable"] = False
    boundary["entry_action_is_research_label_not_execution_instruction"] = True
    result = {
        "ticker": ticker,
        "companion_role": FULL_UNIVERSE_COMPANION_ROLE,
        "not_primary_human_review_input": True,
        "no_alphabetical_sampling": True,
        "entry_action_is_research_label_not_execution_instruction": True,
        "is_actionable": False,
        "current_decision_state": _slim(_records(inputs.get("tactical")).get(ticker)),
        "strategy_fit": _slim(_records(operation.get("strategy")).get(ticker)),
        "scenario": _slim(_records(operation.get("scenario")).get(ticker)),
        "peer_context": _slim(_records(operation.get("peer")).get(ticker)),
        "fundamental_context": _slim(_records(inputs.get("fundamental")).get(ticker)),
        "valuation_context": _valuation_handoff(_records(inputs.get("valuation")).get(ticker)),
        "market_flow_positioning": _slim(_records(inputs.get("market_flow_positioning")).get(ticker)),
        "corporate_intelligence_context": _slim(_records(inputs.get("corporate_intelligence")).get(ticker)),
        "authority_boundary": boundary,
    }
    # This happens after _slim by construction, so the versioned compact
    # contract cannot collapse to an empty nested map.
    financial = _delivery_financial_context(financial_analysis_product_context, ticker)
    if financial is not None:
        result["financial_analysis"] = financial
    return result


def recommended_ai_inputs() -> dict[str, str]:
    return {
        "normal_human_review": PRIMARY_HUMAN_REVIEW_FILENAME,
        "arbitrary_ticker_lookup": FULL_UNIVERSE_LOOKUP_FILENAME,
    }


def _authority_boundary(product: Mapping[str, Any]) -> dict[str, Any]:
    boundary = copy.deepcopy(product.get("authority_boundary") or {})
    boundary["is_actionable"] = False
    boundary["entry_action_is_research_label_not_execution_instruction"] = True
    boundary["owner_focus_is_not_portfolio_holdings"] = True
    boundary["recommendation"] = boundary.get("recommendation") or "NOT_EMITTED"
    return boundary


def _analysis_scope(product: Mapping[str, Any], *, full_universe_record_count: int) -> dict[str, Any]:
    focus_config = load_owner_research_focus()
    owner_focus = list(product.get("owner_focus", {}).get("tickers") or focus_config["owner_focus_tickers"])
    watchlist = list(product.get("watchlist", {}).get("tickers") or focus_config["broader_watchlist"])
    cards = product.get("detailed_research_cards") or {}
    present = [ticker for ticker in owner_focus if is_present_research_card(cards.get(ticker))]
    missing = [ticker for ticker in owner_focus if ticker not in present]
    cohorts = product.get("research_cohorts") or {}
    high_priority = product.get("high_priority_full_universe_review_set") or {}
    return {
        "role": "PRESENTATION_ANALYSIS_SCOPE_ONLY",
        "grants_investment_authority": False,
        "is_portfolio_holdings": False,
        "is_actionable": False,
        "review_order": "OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY",
        "owner_focus_tickers": owner_focus,
        "broader_watchlist": watchlist,
        "mandatory_owner_focus_coverage_count": len(owner_focus),
        "deterministic_discovery_cohorts": {
            name: {"count": (value or {}).get("count"), "tickers": list((value or {}).get("tickers") or []), "ordering": (value or {}).get("ordering") or "TICKER_ASCENDING_NOT_RANKING"}
            for name, value in cohorts.items() if isinstance(value, Mapping)
        },
        "high_priority_review": {
            "count": high_priority.get("count"),
            "tickers": list(high_priority.get("tickers") or []),
            "meaning": high_priority.get("meaning") or "Candidates for human research, not portfolio/watchlist inclusion.",
        },
        "full_universe_record_count": full_universe_record_count,
        "full_universe_companion_role": FULL_UNIVERSE_COMPANION_ROLE,
        "no_alphabetical_sampling": True,
        "entry_action_is_research_label_not_execution_instruction": True,
        "coverage": {
            "owner_focus_requested": owner_focus,
            "owner_focus_present": present,
            "owner_focus_missing": missing,
            "owner_focus_context_count": len(present),
            "discovery_cohort_counts": {name: (value or {}).get("count") for name, value in cohorts.items() if isinstance(value, Mapping)},
            "high_priority_review_count": high_priority.get("count"),
            "broader_watchlist_count": len(watchlist),
        },
    }


def _owner_focus_contexts(product: Mapping[str, Any]) -> list[dict[str, Any]]:
    cards = product.get("detailed_research_cards") or {}
    rows = []
    for ticker in owner_focus_tickers():
        card = cards.get(ticker)
        if is_present_research_card(card):
            rows.append(copy.deepcopy(card))
        elif isinstance(card, Mapping):
            rows.append(copy.deepcopy(card))
        else:
            rows.append({
                "ticker": ticker,
                "status": ABSENT_OWNER_FOCUS_STATUS,
                "is_actionable": False,
                "entry_action_is_research_label_not_execution_instruction": True,
            })
    return rows


def _session_brief(session: str, operation_identity: str, product_identity: str, warnings: list[Any], scope: Mapping[str, Any]) -> str:
    owner_focus = ", ".join(scope.get("owner_focus_tickers") or [])
    missing = ", ".join((scope.get("coverage") or {}).get("owner_focus_missing") or []) or "none"
    present_count = (scope.get("coverage") or {}).get("owner_focus_context_count")
    required = scope.get("mandatory_owner_focus_coverage_count")
    lines = [
        f"# AI Research Session Bundle — {session}",
        "",
        f"Operation: `{operation_identity}`",
        f"Product: `{product_identity}`",
        "",
        "## UPLOAD THIS",
        PRIMARY_HUMAN_REVIEW_FILENAME,
        "",
        "This is the primary normal human-review AI input.",
        "",
        "## DO NOT USE AS PRIMARY",
        FULL_UNIVERSE_LOOKUP_FILENAME,
        "",
        f"Role: `{FULL_UNIVERSE_COMPANION_ROLE}`",
        "Status: `NOT_PRIMARY_HUMAN_REVIEW_INPUT`",
        "Use it only for on-demand arbitrary ticker lookup, never as the normal review file.",
        "JSON object key order and NDJSON line order are canonical-sorted for identity; they are not a sampling queue.",
        "",
        "## External-AI analysis contract",
        "1. Market / session context first.",
        f"2. Complete owner-focus coverage before market discovery (`OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY`). Required names ({required}): {owner_focus}.",
        "3. Discovery second: use deterministic_discovery_cohorts and high_priority_review only after owner-focus coverage.",
        "4. Report coverage explicitly from analysis_scope.coverage: owner_focus_requested, owner_focus_present, owner_focus_missing, owner_focus_context_count, and discovery cohort counts. Do not infer coverage by scanning the NDJSON file.",
        "5. No alphabetical sampling. Do not take the first N tickers of the bundle or NDJSON.",
        "6. No invention. Preserve UNKNOWN/MISSING/UNAVAILABLE. Do not fabricate facts, targets, probabilities, or trades.",
        "7. `entry_action` values such as BUY_ON_CONFIRMATION, EARLY_ENTRY, and ACCUMULATE_IN_BASE are tactical research-state labels, not recommendations or suggested trades.",
        "8. `is_actionable = false`. No ranking, recommendation, target, probability, sizing, portfolio, or execution authority.",
        "",
        f"entry_action_is_research_label_not_execution_instruction = true",
        "is_actionable = false",
        "no_alphabetical_sampling = true",
        f"owner_focus_present_count = {present_count}",
        f"owner_focus_missing = {missing}",
        "",
        "Bounded on-demand extractor:",
        "`python tools/extract_ai_research_tickers.py --session YYYY-MM-DD --tickers HPG,PAN,SSI`",
        "",
        "## Warnings",
        *[f"- {item}" for item in warnings],
        "",
    ]
    return "\n".join(lines)


def build_dashboard_projection(operation: Mapping[str, Any]) -> dict[str, Any]:
    """The released cockpit's deterministic, Product V2-shaped data payload."""
    product, manifest = operation["product"], operation["manifest"]
    projection: dict[str, Any] = {
        "schema_version": COCKPIT_CONTRACT,
        "projection_kind": "RELEASED_HUMAN_DECISION_COCKPIT",
        "session": manifest["market_session"],
        "authority_boundary": _authority_boundary(product),
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
        "owner_focus": copy.deepcopy(product.get("owner_focus") or {"tickers": list(owner_focus_tickers()), "is_portfolio_holdings": False, "is_actionable": False}),
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
    universe = sorted(_records(inputs.get("descriptive")))
    scope = _analysis_scope(product, full_universe_record_count=len(universe))
    routing = recommended_ai_inputs()
    boundary = _authority_boundary(product)
    financial_context = validate_product_context(inputs.get("financial_analysis_product_context"))
    financial_summary = None
    financial_index = None
    if financial_context is not None:
        financial_summary = copy.deepcopy(financial_context.get("financial_analysis_market_summary"))
        financial_index = copy.deepcopy(financial_context.get("financial_analysis_ticker_index"))
    primary: dict[str, Any] = {
        "schema_version": AI_CONTRACT,
        "artifact_role": PRIMARY_HUMAN_REVIEW_ROLE,
        "session": session,
        "operation_identity": manifest["operation_identity"],
        "product_identity": product["artifact_identity"],
        "producer_head": manifest["producer_head"],
        "consumer_compatible_contract_version": "current_daily_decision_research_contract/v1",
        "authority_boundary": boundary,
        "recommended_ai_inputs": routing,
        "analysis_scope": scope,
        "entry_action_is_research_label_not_execution_instruction": True,
        "is_actionable": False,
        "no_alphabetical_sampling": True,
        "market": {"summary": copy.deepcopy(product["market_brief"]), "macro": copy.deepcopy(product.get("macro_context")), "flow_coverage": copy.deepcopy((manifest.get("coverage_summary") or {}).get("market_flow_positioning")), "limitations": copy.deepcopy(manifest["warnings"])},
        "financial_analysis": {"market_summary": financial_summary, "ticker_index": financial_index,
                               "source_context_identity": (financial_context or {}).get("source_context_identity")},
        "owner_focus_research_contexts": _owner_focus_contexts(product),
        "research_cohorts": {"watchlist": copy.deepcopy(product["watchlist"]), "owner_focus": copy.deepcopy(product.get("owner_focus") or {"tickers": list(owner_focus_tickers()), "is_portfolio_holdings": False}), "high_priority_review": copy.deepcopy(product["high_priority_full_universe_review_set"]), "deterministic_cohorts": copy.deepcopy(product["research_cohorts"]), "entry_relevant_90_count": product["aggregate_validation"]["entry_relevant_90_count"]},
        "ticker_research_contexts": {
            ticker: {**copy.deepcopy(cards[ticker]), **({"financial_analysis": _delivery_financial_context(financial_context, ticker)} if financial_context is not None else {})}
            for ticker in useful_tickers
        },
        "portfolio_risk": copy.deepcopy(operation.get("portfolio_risk") or {"status": "NO_EXPLICIT_PORTFOLIO_SUPPLIED", "is_actionable": False}),
        "lineage": {"input_artifacts": copy.deepcopy(manifest["input_artifacts"]), "output_artifacts": copy.deepcopy(manifest["outputs"]), "session_coherence": copy.deepcopy(manifest["session_coherence"])},
        "what_to_verify_next": copy.deepcopy(product["what_to_verify_next"]),
    }
    primary_bytes = (_canon(primary) + "\n").encode("utf-8")
    rows = [_canon(_compact_context(ticker, operation, inputs, financial_context)) for ticker in universe]
    full_bytes = (("\n".join(rows) + "\n") if rows else "").encode("utf-8")
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
        "primary_bundle_filename": PRIMARY_HUMAN_REVIEW_FILENAME,
        "full_universe_companion_filename": FULL_UNIVERSE_LOOKUP_FILENAME,
        "dashboard_projection_filename": "current_decision_cockpit_projection.json",
        "recommended_ai_inputs": routing,
        "artifact_roles": {
            PRIMARY_HUMAN_REVIEW_FILENAME: PRIMARY_HUMAN_REVIEW_ROLE,
            FULL_UNIVERSE_LOOKUP_FILENAME: FULL_UNIVERSE_COMPANION_ROLE,
        },
        "files": {
            PRIMARY_HUMAN_REVIEW_FILENAME: {"bytes": len(primary_bytes), "sha256": _hash_bytes(primary_bytes), "role": PRIMARY_HUMAN_REVIEW_ROLE},
            FULL_UNIVERSE_LOOKUP_FILENAME: {
                "bytes": len(full_bytes),
                "sha256": _hash_bytes(full_bytes),
                "record_count": len(universe),
                "role": FULL_UNIVERSE_COMPANION_ROLE,
                "not_primary_human_review_input": True,
                "ordering": "TICKER_ASCENDING_DETERMINISTIC_LOOKUP_NOT_SAMPLING",
            },
            "current_decision_cockpit_projection.json": {"bytes": len(projection_bytes), "sha256": _hash_bytes(projection_bytes), "projection_identity": projection["projection_identity"]},
        },
        "source_artifact_identities": copy.deepcopy(product["source_artifact_identities"]),
        "financial_analysis_source_context_identity": (financial_context or {}).get("source_context_identity"),
        "authority_boundary": boundary,
        "warnings": copy.deepcopy(manifest["warnings"]),
        "created_at": created_at,
        "creation_timestamp_basis": "SESSION_DERIVED_DETERMINISTIC_REPLAY",
        "entry_action_is_research_label_not_execution_instruction": True,
        "is_actionable": False,
        "no_alphabetical_sampling": True,
    }
    manifest_bytes = (_canon(manifest_payload) + "\n").encode("utf-8")
    brief = _session_brief(session, manifest["operation_identity"], product["artifact_identity"], list(manifest["warnings"]), scope)
    return {"primary": primary_bytes, "full_universe": full_bytes, "manifest": manifest_bytes, "brief": brief.encode("utf-8"), "projection": projection_bytes}
