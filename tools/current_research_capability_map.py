"""Project retained Current Research products into a deterministic ticker capability map.

This is a read-only projection. It does not acquire data or change source fitness.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re


CONTRACT = "current_research_capability_map/v1"
OPERATION = "25ac1ea3044b88c2a9f272a471b7fadc13f6b21e158fd0abb5e171344a975f22"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_paths(root: Path, session: str) -> dict[str, Path]:
    op = root / "daily-research-session-operations-v1" / session / OPERATION
    return {
        "integrated": root / "canonical-post-close-v1" / session / "enrichment" / "integrated_investment_decision_product.json",
        "technical_disposition": root / "same-session-technical-coverage-recovery-v1-20260924" / "same_session_technical_coverage_disposition_artifact.json",
        "valuation": root / "market-wide-current-valuation-v1-20260924-session20260924" / "market_wide_current_valuation_artifact.json",
        "screener": op / "screener_master_projection.json",
        "fundamental_store": op / "market_wide_fundamental_feature_store_artifact.json",
    }


def _reason_codes(*groups: object) -> list[str]:
    result = set()
    for group in groups:
        for reason in group or []:
            if isinstance(reason, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", reason):
                result.add(reason)
    return sorted(result)


def decision_fitness(*, technical: bool, fundamental: bool, valuation: bool,
                     participation: bool) -> str:
    if technical and fundamental and valuation and participation:
        return "CURRENT_RESEARCH_READY"
    if technical and not fundamental and not valuation:
        return "TECHNICAL_RESEARCH_ONLY"
    if technical or fundamental or valuation:
        return "PARTIAL_RESEARCH_READY"
    return "INSUFFICIENT_CURRENT_EVIDENCE"


def integrated_fundamental_available(record: dict) -> bool:
    """Qualified fundamental evidence, as the Producer-owned decision input states it.

    An insufficient current direction alone is not absent evidence (FUNDAMENTAL_SIGNAL_POLICY_
    HARDENING_V1). A record produced before the decision input keeps the directional reading.
    """
    decision_fundamental = ((record.get("current_research_decision_input") or {}).get("dimensions") or {}).get("FUNDAMENTAL")
    if isinstance(decision_fundamental, dict):
        return decision_fundamental.get("state") == "AVAILABLE"
    return record["evidence_axes"]["FUNDAMENTAL"]["state"] != "INSUFFICIENT"


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 2) if d else 0.0


def build(root: Path, session: str, overrides: dict[str, Path] | None = None) -> dict:
    paths = source_paths(root, session) | (overrides or {})
    inputs = {name: _load(path) for name, path in paths.items()}
    integrated, technical, valuation, screener, store = (inputs[k] for k in paths)
    for name, artifact in inputs.items():
        artifact_session = artifact.get("session") or artifact.get("valuation_session") or artifact.get("as_of_session")
        if artifact_session and artifact_session != session:
            raise ValueError(f"{name}: wrong session {artifact_session}")
    candidate = set(integrated["records"])
    if candidate != set(technical["records"]) or candidate != set(screener["cards"]):
        raise ValueError("attempted ticker sets do not reconcile")
    if not set(valuation["records"]) <= candidate:
        raise ValueError("valuation rows outside attempted cohort")
    payload_path = paths["fundamental_store"].parent / store["records_payload"]["path"]
    fundamental_rows = {}
    with gzip.open(payload_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            ticker = item["ticker"]
            if ticker in fundamental_rows:
                raise ValueError(f"duplicate fundamental row: {ticker}")
            fundamental_rows[ticker] = item
    if len(fundamental_rows) != store["records_payload"]["record_count"]:
        raise ValueError("fundamental payload count mismatch")
    sources = {name: {"artifact_identity": inputs[name]["artifact_identity"],
                      "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for name, path in paths.items()}
    sources["fundamental_payload"] = {
        "canonical_jsonl_sha256": store["records_payload"]["canonical_jsonl_sha256"],
        "compressed_file_sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
    }
    rows = {}
    for ticker in sorted(candidate):
        src, tech, screen = integrated["records"][ticker], technical["records"][ticker], screener["cards"][ticker]
        val = valuation["records"].get(ticker, {})
        features = fundamental_rows.get(ticker, {})
        fcontext = features.get("fundamental_feature_context", {})
        axes = src["evidence_axes"]
        sector = screen.get("sector") or {}
        official = bool(tech["in_official_research_universe"])
        exact_price = bool(tech["has_exact_session_bar"])
        current_technical = exact_price and tech["is_current_session"] and axes["TACTICAL_STRUCTURE"]["fitness"] == "AVAILABLE"
        participation = (current_technical and src["participation"]["status"] == "AVAILABLE"
                         and axes["PARTICIPATION_CONFIRMATION"]["state"] != "INSUFFICIENT_EVIDENCE")
        fundamental = integrated_fundamental_available(src)
        valuation_context = axes["VALUATION"]["fitness"] == "AVAILABLE"
        corporate = official and axes["CORPORATE_INTELLIGENCE"]["fitness"] not in {"ABSENT", "UNAVAILABLE"}
        liquidity = screen["liquidity"]["status"] == "AVAILABLE"
        methods = {key: {"status": item["status"], "applicability": item.get("applicability"),
                         "first_blocker": item.get("first_blocker"),
                         "reason_codes": _reason_codes(item.get("blocked_reasons"))}
                   for key, item in sorted(val.get("metrics", {}).items())}
        integrated_methods = {key: {"status": item["status"], "applicability": item.get("applicability"),
                                    "reason_codes": _reason_codes(item.get("blocker_reason_codes"))}
                              for key, item in sorted(src["valuation_methods"].items())
                              if key in {"P/E", "P/B", "P/B_CURRENT_RESEARCH", "P/S", "EV/Sales", "EV/EBITDA", "EV/EBITDA_CALC_READY",
                                         "market_cap", "P/E_TTM", "P/S_TTM"}}
        # The Producer-owned Current Research decision input (absent on records produced before
        # CURRENT_RESEARCH_DECISION_CONVERGENCE_V1); projected, never re-derived here.
        dinput = src.get("current_research_decision_input") or {}
        ddims = dinput.get("dimensions") or {}
        dentity = (ddims.get("FUNDAMENTAL") or {}).get("entity_applicability") or {}
        fsummary = {
            "availability": fcontext.get("availability", "NOT_IN_FEATURE_STORE"),
            "ready_feature_count": fcontext.get("ready_feature_count", 0),
            "health_axes": fcontext.get("health_axes", {}),
            "periods": sorted({p for feature in features.get("features", {}).values() for p in feature.get("input_periods", [])}),
            "blocked_reason_codes": _reason_codes(*(feature.get("blocker_reason_codes") for feature in features.get("features", {}).values())),
            "entity_applicability": features.get("entity_applicability"),
            "features": {key: {"status": feature.get("status"), "input_periods": feature.get("input_periods", []),
                               "reason_codes": _reason_codes(feature.get("blocker_reason_codes"))}
                         for key, feature in sorted(features.get("features", {}).items())},
        }
        blocked = {}
        if not official:
            blocked["CURRENT_RESEARCH_SCOPE"] = _reason_codes([tech["reason_code"]])
        technical_reason = ([tech["disposition"]] if tech["disposition"] == "PROVIDER_REJECTED_OR_INVALID_SYMBOL" else
                            [tech["reason_code"]])
        if not exact_price:
            blocked["EXACT_SESSION_PRICE"] = _reason_codes(technical_reason, val.get("price_input", {}).get("blocked_reasons"))
        if not current_technical:
            blocked["CURRENT_TECHNICAL"] = _reason_codes(technical_reason, axes["TACTICAL_STRUCTURE"].get("blocker_reason_codes"))
        if not participation:
            blocked["PARTICIPATION_RESEARCH"] = _reason_codes(technical_reason if not current_technical else [], axes["PARTICIPATION_CONFIRMATION"].get("blocker_reason_codes"))
        if not fundamental:
            blocked["INTEGRATED_FUNDAMENTAL"] = _reason_codes(axes["FUNDAMENTAL"].get("blocker_reason_codes"))
        if not valuation_context:
            blocked["VALUATION_CONTEXT"] = _reason_codes(axes["VALUATION"].get("blocker_reason_codes"))
        if not corporate:
            blocked["CORPORATE_CONTEXT"] = _reason_codes(axes["CORPORATE_INTELLIGENCE"].get("blocker_reason_codes"))
        if not liquidity:
            blocked["RESEARCH_LIQUIDITY_PROXY"] = _reason_codes([screen["liquidity"].get("reason")])
        blocked["EXECUTION_LIQUIDITY"] = _reason_codes([screen["liquidity"].get("research_value_reason")])
        blocked["PORTFOLIO_FIT"] = _reason_codes(axes["PORTFOLIO_FIT"].get("blocker_reason_codes"))
        if val and val["metrics"]["market_cap"]["status"] != "READY":
            blocked["EXACT_MARKET_CAP"] = _reason_codes(val["metrics"]["market_cap"].get("blocked_reasons"), val.get("share_basis_input", {}).get("blocked_reasons"))
        for method, detail in methods.items():
            if detail["status"] == "BLOCKED":
                blocked[f"VALUATION_METRIC:{method}"] = detail["reason_codes"]
        for feature, detail in fsummary["features"].items():
            if detail["status"] == "BLOCKED":
                blocked[f"FUNDAMENTAL_FEATURE:{feature}"] = detail["reason_codes"]
        feature_ready = fcontext.get("availability") == "PRODUCT_READY_RESEARCH_CONTEXT"
        integration_gap = official and feature_ready and not fundamental
        available = [name for name, flag in {
            "EXACT_SESSION_PRICE": exact_price, "CURRENT_TECHNICAL": current_technical,
            "PARTICIPATION_RESEARCH": participation, "INTEGRATED_FUNDAMENTAL": fundamental,
            "OPERATIONAL_FUNDAMENTAL_FEATURES": feature_ready, "VALUATION_CONTEXT": valuation_context,
            "CORPORATE_CONTEXT": corporate, "RESEARCH_LIQUIDITY_PROXY": liquidity,
        }.items() if flag]
        rank = ["CURRENT_RESEARCH_SCOPE", "CURRENT_TECHNICAL", "INTEGRATED_FUNDAMENTAL", "VALUATION_CONTEXT", "EXACT_SESSION_PRICE",
                "PARTICIPATION_RESEARCH", "CORPORATE_CONTEXT", "RESEARCH_LIQUIDITY_PROXY", "EXACT_MARKET_CAP", "PORTFOLIO_FIT", "EXECUTION_LIQUIDITY"]
        primary = next((name for name in rank if name in blocked), None)
        all_reasons = sorted({code for codes in blocked.values() for code in codes})
        rows[ticker] = {
            "ticker": ticker, "universe_status": "OFFICIAL_RESEARCH_SCOPE" if official else "ATTEMPTED_OUTSIDE_OFFICIAL_SCOPE",
            "scope_reason": tech["official_qualification"], "exchange": screen.get("listing_exchange"),
            "sector": sector.get("label") or "UNKNOWN", "sector_namespace": sector.get("namespace"),
            "sector_fitness": sector.get("status"),
            "entity_class": screen.get("entity_type", {}).get("value") or val.get("entity_class"),
            "price_fitness": "EXACT_SESSION_DESCRIPTIVE" if exact_price else "NO_EXACT_SESSION_PRICE",
            "technical_fitness": "CURRENT_RESEARCH_USABLE" if current_technical else tech["disposition"],
            "participation_fitness": "RESEARCH_PROXY_USABLE" if participation else "UNAVAILABLE",
            "fundamental_fitness": "INTEGRATED_RESEARCH_USABLE" if fundamental else "INTEGRATED_INSUFFICIENT",
            # What fundamental evidence is known (five states), as the decision input states it.
            "fundamental_evidence_availability": ((dinput.get("dimensions") or {}).get("FUNDAMENTAL") or {}).get(
                "fundamental_evidence_availability"),
            "valuation_fitness": "RESEARCH_CONTEXT_USABLE" if valuation_context else "UNAVAILABLE",
            "corporate_context_fitness": "CONTEXT_EVALUATED" if corporate else "UNAVAILABLE",
            "liquidity_research_fitness": "DESCRIPTIVE_PROXY_USABLE" if liquidity else "UNAVAILABLE",
            "decision_fitness": (decision_fitness(technical=current_technical, fundamental=fundamental,
                                                  valuation=valuation_context, participation=participation)
                                 if official else "INSUFFICIENT_CURRENT_EVIDENCE"),
            "research_posture": src["research_action_posture"], "evidence_currency": src["evidence_currency"],
            "fundamental_feature_store": fsummary,
            "fundamental_integration_gap": integration_gap,
            "technical_detail": {"feature_as_of_session": tech["feature_as_of_session"], "disposition": tech["disposition"],
                                 "reason_code": tech["reason_code"], "momentum": axes["MOMENTUM"]["fitness"],
                                 "exact_session_bar": exact_price,
                                 "complete_technical_window": tech["disposition"] == "SAME_SESSION_TECHNICAL_COVERED",
                                 "close_history_depth": src.get("momentum_context", {}).get("close_history_depth"),
                                 "moving_average_status": src.get("momentum_context", {}).get("moving_average_ordering", {}).get("status"),
                                 "rsi_status": src.get("momentum_context", {}).get("rsi", {}).get("status"),
                                 "macd_status": src.get("momentum_context", {}).get("macd", {}).get("status"),
                                 "tactical_phase": src["tactical_phase"], "breakout_state_v3": src.get("breakout_state_v3"),
                                 "technical_support": src.get("technical_support", []),
                                 "trigger_available": src.get("trigger", {}).get("trigger_state") is not None,
                                 "invalidation_available": src.get("invalidation", {}).get("invalidation_level") is not None,
                                 "relative_strength": (((ddims.get("TECHNICAL") or {}).get("components") or {}).get("relative_strength")
                                                       or "NOT_EXPOSED_IN_INTEGRATED_RECORD")},
            "valuation_detail": {"entity_class": val.get("entity_class"),
                                 "share_basis_status": val.get("share_basis_input", {}).get("status"),
                                 "exact_market_cap_status": methods.get("market_cap", {}).get("status", "NOT_IN_VALUATION_SCOPE"),
                                 "peer_relative_state": src.get("valuation_context_summary", {}).get("peer_relative_state"),
                                 "own_history_state": src.get("valuation_context_summary", {}).get("own_history_state"),
                                 "current_research_state": (ddims.get("VALUATION") or {}).get("state", "NOT_AVAILABLE_IN_SOURCE"),
                                 "current_research_evidence_class": (ddims.get("VALUATION") or {}).get("evidence_class", "NOT_AVAILABLE_IN_SOURCE"),
                                 "current_research_reason_codes": (ddims.get("VALUATION") or {}).get("reason_codes", []),
                                 "current_research_methods": integrated_methods, "exact_metric_methods": methods},
            "entity_applicability": {"entity_class": dentity.get("entity_class"),
                                     "status": dentity.get("applicability_status", "NOT_AVAILABLE_IN_SOURCE"),
                                     "authority_tier": dentity.get("authority_tier"),
                                     "authority_scope": dentity.get("authority_scope")},
            "research_market_cap_usable": (src["valuation_methods"].get("market_cap") or {}).get("status") in {"RESEARCH_USABLE", "READY"},
            "decision_input": {"evidence_class": dinput.get("evidence_class", "NOT_AVAILABLE_IN_SOURCE"),
                               "dimension_states": {name: item.get("state") for name, item in sorted(ddims.items())},
                               "fundamental_as_of_period": (ddims.get("FUNDAMENTAL") or {}).get("as_of_financial_period"),
                               "fundamental_freshness": ((ddims.get("FUNDAMENTAL") or {}).get("freshness") or {}).get(
                                   "freshness_status", "NOT_AVAILABLE_IN_SOURCE"),
                               "fundamental_method": (ddims.get("FUNDAMENTAL") or {}).get("method"),
                               "fundamental_authority": (ddims.get("FUNDAMENTAL") or {}).get("authority"),
                               "operational_bridge": ((ddims.get("FUNDAMENTAL") or {}).get("operational_bridge") or {}).get("state"),
                               "missing_primary_factors": (dinput.get("synthesis") or {}).get("missing_primary_factors", {}),
                               "action_posture_gated_by_current_evidence": (dinput.get("synthesis") or {}).get(
                                   "action_posture_gated_by_current_evidence")},
            "corporate_detail": {"axis_state": axes["CORPORATE_INTELLIGENCE"]["state"],
                                 "evidence_session": src["corporate_intelligence_context"].get("evidence_session"),
                                 "evidence_session_stale": src["corporate_intelligence_context"].get("evidence_session_stale"),
                                 "material_event_count": src["corporate_intelligence_context"].get("material_event_count")},
            "liquidity_detail": {"descriptive_state": screen["liquidity"].get("descriptive_state"),
                                 "numeric_adv20_available": screen["liquidity"].get("research_value") is not None,
                                 "execution_capacity_qualified": False,
                                 "decision_input_research_state": ((ddims.get("LIQUIDITY") or {}).get("research") or {}).get("state"),
                                 "decision_input_execution_state": ((ddims.get("LIQUIDITY") or {}).get("execution") or {}).get("state")},
            "available_capabilities": available, "blocked_capabilities": blocked,
            "primary_blocker": primary, "secondary_blockers": [name for name in rank if name in blocked and name != primary],
            "reason_codes": all_reasons,
            "evidence": {"session": session, "decision_identity": src["decision_identity"],
                         "technical_disposition_identity": technical["artifact_identity"],
                         "integrated_product_identity": integrated["artifact_identity"]},
        }
    total = len(rows)
    official_rows = [row for row in rows.values() if row["universe_status"] == "OFFICIAL_RESEARCH_SCOPE"]
    if len(official_rows) != technical["official_research_universe"]["count"]:
        raise ValueError("official scope denominator mismatch")
    priced_rows = [row for row in official_rows if row["research_market_cap_usable"]]
    denominators = {
        "ATTEMPTED_COHORT": total, "OFFICIAL_RESEARCH_SCOPE": len(official_rows), "PRICED_OFFICIAL_SCOPE": len(priced_rows),
        "definitions": {
            "ATTEMPTED_COHORT": "Every Integrated Decision record of the session",
            "OFFICIAL_RESEARCH_SCOPE": "Attempted records inside the official research universe",
            "PRICED_OFFICIAL_SCOPE": "Official-scope records with a research-usable market capitalisation (every price-based multiple's size input)",
        },
        # Which population each market-wide count below is over; no count is published without one.
        "count_denominators": {
            "coverage.*.count": "ATTEMPTED_COHORT", "coverage.*.official_scope_count": "OFFICIAL_RESEARCH_SCOPE",
            "decision_readiness": "ATTEMPTED_COHORT", "current_research_decision_input": "OFFICIAL_RESEARCH_SCOPE",
            "current_research_decision_input.priced_official_scope": "PRICED_OFFICIAL_SCOPE",
            "breakdown": "ATTEMPTED_COHORT_AND_OFFICIAL_RESEARCH_SCOPE_PER_GROUP", "blocker_impact": "ATTEMPTED_COHORT",
        },
    }
    metrics = {
        "official_research_scope": len(official_rows), "attempted": total,
        "exact_session_price": sum(r["price_fitness"] == "EXACT_SESSION_DESCRIPTIVE" for r in rows.values()),
        "current_technical": sum(r["technical_fitness"] == "CURRENT_RESEARCH_USABLE" for r in rows.values()),
        "participation_research": sum(r["participation_fitness"] == "RESEARCH_PROXY_USABLE" for r in rows.values()),
        "integrated_fundamental": sum(r["fundamental_fitness"] == "INTEGRATED_RESEARCH_USABLE" for r in rows.values()),
        "operational_fundamental_features": sum("OPERATIONAL_FUNDAMENTAL_FEATURES" in r["available_capabilities"] for r in rows.values()),
        "valuation_context": sum(r["valuation_fitness"] == "RESEARCH_CONTEXT_USABLE" for r in rows.values()),
        "corporate_context": sum(r["corporate_context_fitness"] == "CONTEXT_EVALUATED" for r in rows.values()),
        "liquidity_research_proxy": sum(r["liquidity_research_fitness"] == "DESCRIPTIVE_PROXY_USABLE" for r in rows.values()),
        "fundamental_integration_gap": sum(r["fundamental_integration_gap"] for r in rows.values()),
        "exact_market_cap_ready": sum(r["valuation_detail"]["exact_market_cap_status"] == "READY" for r in rows.values()),
        "numeric_adv20": sum(r["liquidity_detail"]["numeric_adv20_available"] for r in rows.values()),
    }
    metric_tests = {
        "exact_session_price": lambda r: r["price_fitness"] == "EXACT_SESSION_DESCRIPTIVE",
        "current_technical": lambda r: r["technical_fitness"] == "CURRENT_RESEARCH_USABLE",
        "participation_research": lambda r: r["participation_fitness"] == "RESEARCH_PROXY_USABLE",
        "integrated_fundamental": lambda r: r["fundamental_fitness"] == "INTEGRATED_RESEARCH_USABLE",
        "operational_fundamental_features": lambda r: "OPERATIONAL_FUNDAMENTAL_FEATURES" in r["available_capabilities"],
        "valuation_context": lambda r: r["valuation_fitness"] == "RESEARCH_CONTEXT_USABLE",
        "corporate_context": lambda r: r["corporate_context_fitness"] == "CONTEXT_EVALUATED",
        "liquidity_research_proxy": lambda r: r["liquidity_research_fitness"] == "DESCRIPTIVE_PROXY_USABLE",
        "fundamental_integration_gap": lambda r: r["fundamental_integration_gap"],
        "exact_market_cap_ready": lambda r: r["valuation_detail"]["exact_market_cap_status"] == "READY",
        "numeric_adv20": lambda r: r["liquidity_detail"]["numeric_adv20_available"],
    }
    metrics = {k: {"count": v, "pct_attempted": _pct(v, total),
                   "official_scope_count": sum(test(r) for r in official_rows),
                   "pct_official_scope": _pct(sum(test(r) for r in official_rows), len(official_rows))}
               for k, v in metrics.items() if k in metric_tests for test in [metric_tests[k]]} | {
                   "attempted": total, "official_research_scope": len(official_rows)}
    readiness = dict(sorted(Counter(r["decision_fitness"] for r in rows.values()).items()))
    groups = {}
    for field in ("exchange", "entity_class", "sector"):
        grouped = defaultdict(list)
        for row in rows.values():
            grouped[str(row.get(field) or "UNKNOWN")].append(row)
        groups[field] = {key: {"attempted": len(items), "official_research_scope": sum(r["universe_status"] == "OFFICIAL_RESEARCH_SCOPE" for r in items),
                               "decision_fitness": dict(sorted(Counter(r["decision_fitness"] for r in items).items())),
                               "current_research_ready_pct_official_scope": _pct(
                                   sum(r["decision_fitness"] == "CURRENT_RESEARCH_READY" for r in items),
                                   sum(r["universe_status"] == "OFFICIAL_RESEARCH_SCOPE" for r in items))}
                         for key, items in sorted(grouped.items())}
    blockers = defaultdict(lambda: {"tickers": set(), "surfaces": Counter(), "fallback": 0,
                                   "sole_surface_reason": Counter()})
    for row in rows.values():
        has_fallback = row["decision_fitness"] != "INSUFFICIENT_CURRENT_EVIDENCE"
        for surface, codes in row["blocked_capabilities"].items():
            for code in codes:
                b = blockers[code]
                b["tickers"].add(row["ticker"])
                b["surfaces"][surface] += 1
                if len(codes) == 1:
                    b["sole_surface_reason"][surface] += 1
                if has_fallback:
                    b["fallback"] += 1
    blocker_impact = {key: {"tickers_affected": len(v["tickers"]), "surfaces_blocked": dict(sorted(v["surfaces"].items())),
                            "tickers_with_valid_alternative": sum(rows[t]["decision_fitness"] != "INSUFFICIENT_CURRENT_EVIDENCE" for t in v["tickers"]),
                            "conditional_single_reason_surface_unlock_upper_bound": dict(sorted(v["sole_surface_reason"].items()))}
                      for key, v in sorted(blockers.items())}
    gap_tickers = [r for r in rows.values() if r["fundamental_integration_gap"]]
    entity_mapping_candidates = sum(r["valuation_detail"]["entity_class"] == "unknown"
                                    and r["entity_class"] not in {"unknown", None}
                                    for r in rows.values())
    exact_lane_only_unresolved = sum(r["valuation_detail"]["entity_class"] == "unknown"
                                     and r["entity_applicability"]["status"] == "RESOLVED" for r in official_rows)
    governed_unresolved = sum(r["entity_applicability"]["status"] in {"UNRESOLVED", "CONFLICT"} for r in official_rows)
    governed_resolved = sum(r["entity_applicability"]["status"] == "RESOLVED" for r in official_rows)
    size_only = sum(r["valuation_detail"]["current_research_evidence_class"] == "SIZE_CONTEXT_ONLY" for r in official_rows)
    relative_valuation = sum(r["valuation_detail"]["current_research_evidence_class"] in {
        "RELATIVE_MULTIPLE_WITH_PEER_CONTEXT", "RELATIVE_MULTIPLE_WITHOUT_PEER_CONTEXT"} for r in official_rows)

    def affected(code: str) -> int:
        return (blocker_impact.get(code) or {}).get("tickers_affected", 0)

    def official_count(test) -> int:
        return sum(bool(test(r)) for r in official_rows)

    def relative_strength_available(row: dict) -> bool:
        detail = row["technical_detail"]["relative_strength"]
        return isinstance(detail, dict) and detail.get("state") == "AVAILABLE"

    valuation_blocker_causes = Counter(code for r in official_rows
                                       if r["valuation_detail"]["current_research_state"] != "AVAILABLE"
                                       for code in r["valuation_detail"]["current_research_reason_codes"])
    dimension_names = ("MARKET", "TECHNICAL", "FUNDAMENTAL", "VALUATION", "CORPORATE", "LIQUIDITY")
    decision_input_section = {
        "contract_version": "current_research_decision_input/v1",
        "denominator": "OFFICIAL_RESEARCH_SCOPE",
        "evidence_class_distribution": dict(sorted(Counter(r["decision_input"]["evidence_class"] for r in official_rows).items())),
        "dimension_state_distribution": {
            name: dict(sorted(Counter(str(r["decision_input"]["dimension_states"].get(name)) for r in official_rows).items()))
            for name in dimension_names},
        "valuation_evidence_class_distribution": dict(sorted(Counter(
            r["valuation_detail"]["current_research_evidence_class"] for r in official_rows).items())),
        "valuation_blocker_cause_ticker_counts": dict(sorted(valuation_blocker_causes.items())),
        "fundamental_method_distribution": dict(sorted(Counter(
            "{}|{}".format(r["decision_input"]["fundamental_method"], r["decision_input"]["fundamental_authority"])
            for r in official_rows).items())),
        "operational_bridge_distribution": dict(sorted(Counter(
            str(r["decision_input"]["operational_bridge"]) for r in official_rows).items())),
        "entity_applicability": {
            "status": dict(sorted(Counter(r["entity_applicability"]["status"] for r in official_rows).items())),
            "authority_tier": dict(sorted(Counter(str(r["entity_applicability"]["authority_tier"]) for r in official_rows).items())),
            "upstream_exact_lane_unknown_but_governed_resolved": exact_lane_only_unresolved,
            "authority_scope": "CURRENT_STATE_ONLY_NOT_HISTORICAL_PIT"},
        "fundamental_freshness_distribution": dict(sorted(Counter(
            str(r["decision_input"]["fundamental_freshness"]) for r in official_rows).items())),
        "fundamental_as_of_period_distribution": dict(sorted(Counter(
            str(r["decision_input"]["fundamental_as_of_period"]) for r in official_rows
            if r["decision_input"]["dimension_states"].get("FUNDAMENTAL") == "AVAILABLE").items())),
        "priced_official_scope": {
            "denominator": "PRICED_OFFICIAL_SCOPE", "count": len(priced_rows),
            "evidence_class_distribution": dict(sorted(Counter(r["decision_input"]["evidence_class"] for r in priced_rows).items())),
            "valuation_state_distribution": dict(sorted(Counter(
                str(r["decision_input"]["dimension_states"].get("VALUATION")) for r in priced_rows).items())),
            "valuation_evidence_class_distribution": dict(sorted(Counter(
                r["valuation_detail"]["current_research_evidence_class"] for r in priced_rows).items())),
        },
        "action_posture_gated_by_current_evidence": official_count(
            lambda r: r["decision_input"]["action_posture_gated_by_current_evidence"] is True),
        "relative_strength_available": official_count(relative_strength_available),
        "liquidity_research_available": official_count(
            lambda r: r["liquidity_detail"]["decision_input_research_state"] == "AVAILABLE"),
        "liquidity_execution_available": official_count(
            lambda r: r["liquidity_detail"]["decision_input_execution_state"] == "AVAILABLE"),
    }
    overblocking = {"fundamental_feature_ready_but_integrated_insufficient": {
        "ticker_count": len(gap_tickers),
        "potential_multifactor_uplift": sum(r["universe_status"] == "OFFICIAL_RESEARCH_SCOPE"
                                            and r["technical_fitness"] == "CURRENT_RESEARCH_USABLE"
                                            and r["participation_fitness"] == "RESEARCH_PROXY_USABLE"
                                            and r["valuation_fitness"] == "RESEARCH_CONTEXT_USABLE"
                                            for r in gap_tickers),
        "entity_classes": dict(sorted(Counter(r["entity_class"] or "UNKNOWN" for r in gap_tickers).items())),
        "tickers": [r["ticker"] for r in gap_tickers],
        "effect": "Retained operational proxy features are usable for their own research methods; integrated fundamental axis remains insufficient. This is an integration candidate, not automatic authority promotion."},
        "valuation_entity_identity_gap": {
            "valuation_unknown_with_screener_entity_candidate": entity_mapping_candidates,
            "upstream_exact_lane_unknown_but_governed_resolved": exact_lane_only_unresolved,
            "effect": ("The upstream exact-valuation lane derives entity class from its own narrower issuer panel. "
                       "Current Research method applicability reads the governed current-state authority; the exact "
                       "lane's own ENTITY_CLASS_UNRESOLVED stays its own verdict.")},
        "valuation_size_context_only": {
            "official_scope_count": size_only,
            "effect": "Market capitalisation is size context, never a valuation multiple; these rows carry no usable price-to-fundamental method."}}
    decision_matrix = [
        {"blocker": "FUNDAMENTAL_CONTEXT_ABSENT", "tickers_affected": affected("FUNDAMENTAL_CONTEXT_ABSENT"),
         "product_capability_blocked": "Integrated fundamental decision context",
         "existing_fallback": "Technical, valuation, and corporate context remain separately usable",
         "actionable_now": len(gap_tickers) > 0,
         "likely_implementation_class": "INTEGRATION" if gap_tickers else "EVIDENCE_WAIT",
         "expected_unlock": (f"{len(gap_tickers)} rows still retain product-ready operational features without integrated "
                             "fundamental context; the remainder lack retained or current fundamental evidence")},
        {"blocker": "ENTITY_CLASS_UNRESOLVED", "tickers_affected": affected("ENTITY_CLASS_UNRESOLVED"),
         "product_capability_blocked": ("Upstream exact-valuation lane method evaluation and, where the governed tier is "
                                        "also unresolved, entity-specific Current Research applicability"),
         "existing_fallback": (f"Governed current-state entity applicability resolves {governed_resolved} official-scope "
                               f"issuers ({exact_lane_only_unresolved} unresolved only on the upstream exact lane)"),
         "actionable_now": False, "likely_implementation_class": "EVIDENCE_WAIT",
         "expected_unlock": (f"{governed_unresolved} official-scope issuers have no qualified classification at any governed "
                             "tier; the exact lane additionally needs official qualified financial facts")},
        {"blocker": "VALUATION_NO_USABLE_RELATIVE_METHOD", "tickers_affected": affected("VALUATION_NO_USABLE_RELATIVE_METHOD"),
         "product_capability_blocked": "Current Research valuation multiples and peer-relative valuation",
         "existing_fallback": (f"{relative_valuation} official-scope rows carry a usable relative multiple; "
                               f"{size_only} carry size context only"),
         "actionable_now": False, "likely_implementation_class": "SEMANTIC_QUALIFICATION",
         "expected_unlock": "Requires an exact-session price plus a monetary-basis-compatible financial denominator; neither is manufactured"},
        {"blocker": "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION",
         "tickers_affected": affected("STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"),
         "product_capability_blocked": "Exact-session price, technical, and participation research",
         "existing_fallback": "Fundamental, valuation, and corporate context can support partial research where qualified",
         "actionable_now": False, "likely_implementation_class": "EVIDENCE_WAIT",
         "expected_unlock": (f"Up to {affected('STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION')} affected tickers only if "
                             "exact-session observations are obtained; no substitute bar is authorized")},
        {"blocker": "CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION",
         "tickers_affected": affected("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"),
         "product_capability_blocked": "Exact market cap and share-dependent authoritative valuation",
         "existing_fallback": "Current-share research proxy is explicitly labeled where qualified; technical and fundamentals remain",
         "actionable_now": False, "likely_implementation_class": "EXTERNAL_OWNER_GATE",
         "expected_unlock": (f"Up to {metrics['exact_session_price']['count']} exact-session priced tickers need qualified "
                             "current common outstanding evidence and continuity; no authority is inferred from lagged proxy")},
        {"blocker": "NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20", "tickers_affected": affected("NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20"),
         "product_capability_blocked": "Execution sizing/capacity, not Current Research decisions",
         "existing_fallback": f"{metrics['liquidity_research_proxy']['count']} descriptive research liquidity proxies remain valid",
         "actionable_now": False, "likely_implementation_class": "DATA_ACQUISITION",
         "expected_unlock": "Execution capacity only after qualified numeric history and contract; no decision-readiness uplift assumed"},
    ]
    result = {"schema_version": "1.0.0", "contract_version": CONTRACT, "session": session,
              "authority_boundary": {"current_research_only": True, "historical_pit_qualified": False,
                                     "execution_qualified": False, "is_actionable": False,
                                     "decision_fitness_is_buy_sell": False},
              "sources": sources, "denominators": denominators, "coverage": metrics, "decision_readiness": readiness,
              "current_research_decision_input": decision_input_section,
              "breakdown": groups, "blocker_impact": blocker_impact, "next_milestone_decision_matrix": decision_matrix,
              "overblocking": overblocking,
              "records": rows}
    result["artifact_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    result["artifact_identity"] = f"{CONTRACT}:{result['artifact_sha256']}"
    return result


def summary(artifact: dict) -> str:
    c = artifact["coverage"]
    lines = ["# Current Research capability coverage", "", f"Session: {artifact['session']}",
             f"Identity: `{artifact['artifact_identity']}`", "",
             f"Attempted: {c['attempted']}; official research scope: {c['official_research_scope']}.", ""]
    denominators = artifact.get("denominators") or {}
    if denominators:
        lines += ["Denominators: " + "; ".join(f"{name} = {denominators[name]}" for name in
                                             ("ATTEMPTED_COHORT", "OFFICIAL_RESEARCH_SCOPE", "PRICED_OFFICIAL_SCOPE")) + ".", ""]
    lines += ["## Capability coverage", ""]
    for key, value in c.items():
        if isinstance(value, dict):
            lines.append(f"- {key}: {value['count']} ({value['pct_attempted']}% attempted; {value['pct_official_scope']}% official-scope denominator)")
    decision_input = artifact.get("current_research_decision_input") or {}
    if decision_input:
        official = c["official_research_scope"]
        lines += ["", "## Current Research decision input (official-scope denominator)", "",
                  "Producer-owned `current_research_decision_input/v1` evidence classes; a coverage class, never an action posture.", ""]
        for key, count in decision_input.get("evidence_class_distribution", {}).items():
            lines.append(f"- {key}: {count} ({_pct(count, official)}%)")
        lines += ["", "Dimension states:", ""]
        for name, states in decision_input.get("dimension_state_distribution", {}).items():
            lines.append(f"- {name}: {states}")
        lines += ["", f"Valuation evidence classes: {decision_input.get('valuation_evidence_class_distribution')}",
                  f"Entity applicability (governed, current-state only): {decision_input.get('entity_applicability', {}).get('status')}; "
                  f"tiers {decision_input.get('entity_applicability', {}).get('authority_tier')}",
                  f"Fundamental method|authority: {decision_input.get('fundamental_method_distribution')}",
                  f"Relative strength exposed: {decision_input.get('relative_strength_available')}; research liquidity: "
                  f"{decision_input.get('liquidity_research_available')}; execution liquidity: {decision_input.get('liquidity_execution_available')}",
                  f"Action posture gated by current technical evidence while research evidence remains: "
                  f"{decision_input.get('action_posture_gated_by_current_evidence')}",
                  f"Fundamental freshness (official scope): {decision_input.get('fundamental_freshness_distribution')}"]
        priced = decision_input.get("priced_official_scope") or {}
        if priced:
            lines += [f"Priced official scope ({priced['count']}): evidence classes {priced['evidence_class_distribution']}; "
                      f"valuation {priced['valuation_state_distribution']}"]
    lines += ["", "## Decision fitness (v1 rule, attempted-cohort denominator)", ""]
    for key, count in artifact["decision_readiness"].items():
        lines.append(f"- {key}: {count} ({_pct(count, c['attempted'])}% attempted)")
    lines += ["", "## Material integration gap", "",
              f"- Product-ready operational financial features but integrated fundamental insufficient: {artifact['overblocking']['fundamental_feature_ready_but_integrated_insufficient']['ticker_count']} tickers.",
              f"- Of those, {artifact['overblocking']['fundamental_feature_ready_but_integrated_insufficient']['potential_multifactor_uplift']} have current technical, participation, and valuation context. Any readiness uplift is conditional on entity-specific, method-level integration.", "",
              "## Breakdown", ""]
    for field in ("exchange", "entity_class", "sector"):
        lines.append(f"### {field}")
        lines.append("")
        for key, data in artifact["breakdown"][field].items():
            lines.append(f"- {key}: {data['attempted']} attempted, {data['official_research_scope']} official-scope; ready {data['current_research_ready_pct_official_scope']}% of official scope; decision {data['decision_fitness']}")
        lines.append("")
    lines += ["## Top feature blockers", ""]
    for code in ("CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE", "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS", "MISSING_SAME_QUARTER_PRIOR_YEAR"):
        if code in artifact["blocker_impact"]:
            lines.append(f"- {code}: {artifact['blocker_impact'][code]['tickers_affected']} tickers; dependent feature surfaces only.")
    lines += ["",
              "## Next-milestone decision matrix", ""]
    for item in artifact["next_milestone_decision_matrix"]:
        lines.append(f"- {item['blocker']}: {item['tickers_affected']} tickers; {item['product_capability_blocked']}; fallback: {item['existing_fallback']}; actionable now: {'YES' if item['actionable_now'] else 'NO'}; {item['likely_implementation_class']}; expected unlock: {item['expected_unlock']}.")
    lines += ["", "## Boundary", "", "The map is descriptive Current Research coverage, not historical PIT, execution capacity, or investment advice. Source reason codes and per-ticker methods are in the JSON artifact.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--session", default="2026-09-24")
    parser.add_argument("--output-dir", type=Path, required=True)
    for name in source_paths(Path("."), "2026-09-24"):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path,
                            help=f"Override the retained {name} artifact path for another operation/session")
    args = parser.parse_args()
    overrides = {name: getattr(args, name) for name in source_paths(Path("."), "2026-09-24")
                 if getattr(args, name) is not None}
    artifact = build(args.source_root, args.session, overrides)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "current_research_capability_map.json").write_bytes(canonical(artifact) + b"\n")
    (args.output_dir / "current_research_capability_summary.md").write_text(summary(artifact), encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
