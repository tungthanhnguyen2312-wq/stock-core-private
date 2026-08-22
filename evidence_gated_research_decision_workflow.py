"""Deterministic, evidence-bound research decision packets.

This contract integrates retained research artifacts.  It does not calculate a
signal, recommendation, target, probability, position size, or execution
instruction.  In particular, an absent retained item is emitted as a gap and
is never interpreted as a zero, a negative event, or a no-risk conclusion.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping


METHOD = "evidence_gated_research_decision_workflow/v1"
ELIGIBILITY_VOCABULARY = ("ELIGIBLE", "PARTIAL", "BLOCKED", "NOT_APPLICABLE", "UNKNOWN")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _dimension(status: str, authority: str, reasons: list[str], source: str | None, **details: Any) -> dict[str, Any]:
    if status not in ELIGIBILITY_VOCABULARY:
        raise ValueError(f"UNKNOWN_ELIGIBILITY_STATUS:{status}")
    return {
        "eligibility": status,
        "authority_ceiling": authority,
        "reason_codes": reasons,
        "source_artifact_identity": source,
        "details": details,
    }


def _index(records: list[Mapping[str, Any]], name: str, expected: set[str]) -> dict[str, Mapping[str, Any]]:
    result = {str(row["ticker"]): row for row in records}
    if len(result) != len(records) or set(result) != expected:
        raise ValueError(f"COHORT_MEMBERSHIP_MISMATCH:{name}")
    return result


def _mapped_lens(lens: Mapping[str, Any], source: str) -> dict[str, Any]:
    status = lens["eligibility"]
    mapped = {"ELIGIBLE": "ELIGIBLE", "ELIGIBLE_LOWER_AUTHORITY": "PARTIAL", "PARTIAL": "PARTIAL",
              "BLOCKED": "BLOCKED", "UNAVAILABLE": "UNKNOWN"}.get(status)
    if mapped is None:
        raise ValueError(f"UNKNOWN_SOURCE_LENS_STATUS:{status}")
    return _dimension(mapped, lens["authority_ceiling"], list(lens["reason_codes"]), source,
                      source_eligibility=status, lens_identity=lens["lens_identity"],
                      observed_input_statuses=lens["observed_input_statuses"])


def _lane(lens: Mapping[str, Any], source: str, technical_downside: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the existing lens rather than creating a second taxonomy."""
    item = _mapped_lens(lens, source)
    item["supporting_evidence"] = ([lens["observed_input_statuses"]]
                                    if item["eligibility"] in ("ELIGIBLE", "PARTIAL") else [])
    item["conflicting_evidence"] = ([{"technical_downside_status": technical_downside["status"],
                                         "reason_codes": list(technical_downside["reason_codes"])}]
                                      if technical_downside["status"] == "OBSERVED_ADVERSE_TECHNICAL_CONTEXT" else [])
    item["missing_evidence"] = (list(item["reason_codes"])
                                if item["eligibility"] in ("BLOCKED", "UNKNOWN") else [])
    return item


def _valuation_summary(bundle: Mapping[str, Any], source: str) -> tuple[dict[str, Any], dict[str, Any]]:
    proxy = bundle.get("mva_provider_proxy_valuation", {})
    if proxy.get("status") == "MISSING":
        return (_dimension("UNKNOWN", "NON_AUTHORITATIVE_RESEARCH_PROXY", [proxy.get("reason", "NO_RETAINED_PROXY_VALUATION")], source),
                {"status": "MISSING", "reason_codes": [proxy.get("reason", "NO_RETAINED_PROXY_VALUATION")]})
    market_cap = proxy.get("market_cap_provider_issued_share_proxy", {})
    methods = proxy.get("methods", {})
    method_states = {
        name: {"status": value.get("status"), "output_status": value.get("output_status"),
               "blocker_codes": list(value.get("blockers", [])), "valuation_lane": value.get("valuation_lane"),
               "provider_share_proxy_namespace": value.get("provider_share_proxy_namespace")}
        for name, value in sorted(methods.items())
    }
    ready = [name for name, value in methods.items() if value.get("status") == "MVA_PROXY_READY"]
    not_applicable = [name for name, value in methods.items() if value.get("status") == "NOT_APPLICABLE"]
    blockers = list(market_cap.get("blockers", []))
    if ready:
        dimension = _dimension("PARTIAL", "NON_AUTHORITATIVE_RESEARCH_PROXY",
                               ["PROVIDER_ISSUED_SHARES_PROXY", "AUTHORITATIVE_CURRENT_SHARE_AUTHORITY_BLOCKED"], source,
                               proxy_namespace="PROVIDER_REPORTED_ISSUED_SHARES_PROXY", ready_methods=sorted(ready),
                               market_cap_status=market_cap.get("status"), valuation_lane=proxy.get("valuation_lane"))
    elif len(not_applicable) == len(methods) and methods:
        dimension = _dimension("NOT_APPLICABLE", "NON_AUTHORITATIVE_RESEARCH_PROXY",
                               ["SECTOR_METHOD_SEMANTICS_NOT_APPLICABLE"], source,
                               proxy_namespace="PROVIDER_REPORTED_ISSUED_SHARES_PROXY", method_states=method_states)
    else:
        dimension = _dimension("BLOCKED", "NON_AUTHORITATIVE_RESEARCH_PROXY",
                               blockers or ["PROVIDER_ISSUED_SHARES_PROXY_NOT_USABLE"], source,
                               proxy_namespace="PROVIDER_REPORTED_ISSUED_SHARES_PROXY", method_states=method_states)
    return dimension, {
        "status": proxy.get("output_status"), "authority": "NON_AUTHORITATIVE_RESEARCH_PROXY",
        "proxy_namespace": "PROVIDER_REPORTED_ISSUED_SHARES_PROXY", "valuation_lane": proxy.get("valuation_lane"),
        "market_cap_proxy_status": market_cap.get("status"), "method_states": method_states,
        "authoritative_valuation": {"status": bundle.get("authoritative_valuation", {}).get("market_cap_readiness", bundle.get("authoritative_valuation", {}).get("status")),
                                      "blocker_codes": list(bundle.get("authoritative_valuation", {}).get("blocker_codes", []))},
        "prohibited_interpretation": "NOT_AUTHORITATIVE_MARKET_CAP_OR_MULTIPLE",
    }


def _official_financial_evidence(official_panel: Mapping[str, Any], daily: Mapping[str, Mapping[str, Any]],
                                 fundamental_readiness: Mapping[str, Any], members: set[str], session: str) -> tuple[set[str], dict[str, Mapping[str, Any]]]:
    """Separate sector-neutral evidence presence from model applicability.

    P3-F13 is the authority for the 13-issuer official evidence panel.  The
    older daily product remains a source of descriptive context only and has
    its original 11 issuer snapshot; P3-F13 adds its two retained qualified
    issuers without reclassifying any provider observation.
    """
    cohort = official_panel["cohort_identity"]
    if cohort.get("as_of_session") != session:
        raise ValueError("SESSION_MISMATCH:official_financial_panel")
    readiness = official_panel["before_after_comparison"]["fundamental_readiness_status"]["after"]
    if readiness.get("PARTIAL") != 13 or readiness.get("BLOCKED") != len(members) - 13:
        raise ValueError("OFFICIAL_FINANCIAL_PANEL_COVERAGE_MISMATCH")
    retained = {ticker for ticker, row in daily.items()
                if row["research_summary"]["fundamental_authority"] == "OFFICIAL_QUALIFIED"}
    retained.update(str(ticker) for ticker in official_panel["newly_qualified_issuers"])
    if len(retained) != 13 or not retained.issubset(members):
        raise ValueError("OFFICIAL_FINANCIAL_PANEL_MEMBERSHIP_MISMATCH")
    by_ticker = {str(row["issuer_identity"]["ticker"]): row
                 for row in fundamental_readiness["issuer_research_readiness"]}
    return retained, by_ticker


def _fundamental_dimensions(ticker: str, official_tickers: set[str], readiness_by_ticker: Mapping[str, Mapping[str, Any]],
                            official_source: str, readiness_source: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return model eligibility and metric-level sector applicability.

    The P3-B status is deliberately not substituted for the P3-F13 evidence
    presence state: a sector-specific NOT_APPLICABLE metric does not erase a
    qualified fact, and a blocked metric does not make an absent fact zero.
    """
    if ticker not in official_tickers:
        return (
            _dimension("BLOCKED", "OFFICIAL_QUALIFIED", ["NO_APPROVED_OFFICIAL_SOURCE_ROUTE_IN_REGISTRY"], official_source,
                       evidence_presence="NOT_QUALIFIED"),
            _dimension("UNKNOWN", "UNKNOWN", ["SECTOR_MODEL_APPLICABILITY_NOT_ASSESSABLE_WITHOUT_QUALIFIED_FINANCIAL_PANEL"], official_source),
        )
    readiness = readiness_by_ticker.get(ticker)
    if readiness is None:
        # FPT/PNJ are evidence-qualified by P3-F13 after the retained P3-B
        # artifact snapshot; P3-F13's refreshed readiness summary is partial.
        return (
            _dimension("PARTIAL", "OFFICIAL_QUALIFIED", ["P3F13_REFRESHED_FUNDAMENTAL_READINESS_PARTIAL"], official_source,
                       evidence_presence="QUALIFIED", entity_class="corporate"),
            _dimension("PARTIAL", "OFFICIAL_QUALIFIED", ["CORPORATE_MODEL_METRICS_PARTIALLY_CHARACTERIZED"], official_source,
                       entity_class="corporate", not_applicable_metric_ids=[]),
        )
    not_applicable = [metric["metric_id"] for metric in readiness["metrics"] if metric["status"] == "NOT_APPLICABLE"]
    return (
        _dimension("PARTIAL", "OFFICIAL_QUALIFIED", ["P3B_FUNDAMENTAL_READINESS_PARTIAL"], readiness_source,
                   evidence_presence="QUALIFIED", entity_class=readiness["issuer_identity"]["entity_class"],
                   metric_family_states=readiness["metric_family_states"]),
        _dimension("PARTIAL", "OFFICIAL_QUALIFIED", ["SECTOR_SPECIFIC_METRIC_APPLICABILITY_RETAINED"], readiness_source,
                   entity_class=readiness["issuer_identity"]["entity_class"], not_applicable_metric_ids=not_applicable,
                   metric_status_counts=dict(Counter(metric["status"] for metric in readiness["metrics"])),
        ),
    )
def _evidence(kind: str, value: Any, authority: str, source: str, reasons: list[str] | None = None) -> dict[str, Any]:
    return {"classification": kind, "observed_value": value, "authority": authority,
            "source_artifact_identity": source, "reason_codes": reasons or []}


def build(product: Mapping[str, Any], eligibility: Mapping[str, Any], setups: Mapping[str, Any],
          scenarios: Mapping[str, Any], events: Mapping[str, Any], downside: Mapping[str, Any],
          market: Mapping[str, Any], mva_bundle: Mapping[str, Any], official_financial_panel: Mapping[str, Any],
          fundamental_readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Build a cohort packet only when every input is the same dated cohort."""
    session = product["daily_market_research"]["session"]
    source_artifacts = {"daily_product": product["artifact_identity"], "strategy_eligibility": eligibility["artifact_identity"],
                        "setup_classification": setups["artifact_identity"], "scenario": scenarios["artifact_identity"],
                        "event_context": events["artifact_identity"], "downside_context": downside["artifact_identity"],
                        "market_context": market["artifact_identity"], "mva_bundle": mva_bundle["artifact_identity"],
                        "official_financial_panel": official_financial_panel["artifact_identity"],
                        "fundamental_readiness": fundamental_readiness["artifact_identity"]}
    for name, artifact in (("eligibility", eligibility), ("setups", setups), ("scenarios", scenarios),
                           ("events", events), ("downside", downside), ("market", market)):
        if artifact["research_session"] != session:
            raise ValueError(f"SESSION_MISMATCH:{name}")
    daily = {str(row["ticker"]): row for row in product["stock_research"]}
    members = set(daily)
    if not members or len(daily) != len(product["stock_research"]):
        raise ValueError("INVALID_DAILY_COHORT")
    elig = _index(list(eligibility["records"]), "strategy_eligibility", members)
    setup = _index(list(setups["records"]), "setup_classification", members)
    event = _index(list(events["records"]), "event_context", members)
    risk = _index(list(downside["records"]), "downside_context", members)
    for name, indexed in (("strategy_eligibility", elig), ("setup_classification", setup),
                          ("event_context", event), ("downside_context", risk)):
        if any(row["research_session"] != session for row in indexed.values()):
            raise ValueError(f"SESSION_MISMATCH:{name}")
    scenario = {str(row["ticker"]): row for row in scenarios["scenarios"]}
    if not set(scenario).issubset(members):
        raise ValueError("COHORT_MEMBERSHIP_MISMATCH:scenario")
    bundle_members = {str(row["identity"]["canonical_ticker"]): row for row in mva_bundle["records"] if row.get("empirical_active_cohort_member")}
    if set(bundle_members) != members:
        raise ValueError("COHORT_MEMBERSHIP_MISMATCH:mva_bundle")
    if any(row.get("session") != session for row in bundle_members.values()):
        raise ValueError("SESSION_MISMATCH:mva_bundle")
    official_tickers, readiness_by_ticker = _official_financial_evidence(official_financial_panel, daily, fundamental_readiness, members, session)

    records = []
    for ticker in sorted(members):
        daily_row, lens_row, setup_row, event_row, risk_row, bundle_row = daily[ticker], elig[ticker], setup[ticker], event[ticker], risk[ticker], bundle_members[ticker]
        facts = daily_row["ai_ready_brief"]["facts"]
        fundamental_authority = daily_row["research_summary"]["fundamental_authority"]
        lenses = lens_row["lenses"]
        valuation_dimension, valuation_state = _valuation_summary(bundle_row, source_artifacts["mva_bundle"])
        scenario_row = scenario.get(ticker)
        scenario_dimension = _mapped_lens(lenses["SCENARIO_RESEARCH"], source_artifacts["strategy_eligibility"])
        event_dimension = _mapped_lens(lenses["CATALYST_RESEARCH"], source_artifacts["strategy_eligibility"])
        fundamental_quality, sector_applicability = _fundamental_dimensions(
            ticker, official_tickers, readiness_by_ticker, source_artifacts["official_financial_panel"], source_artifacts["fundamental_readiness"])
        financial_evidence = (_dimension("ELIGIBLE", "OFFICIAL_QUALIFIED", ["OFFICIAL_FINANCIAL_EVIDENCE_QUALIFIED"], source_artifacts["official_financial_panel"],
                                         panel_membership="QUALIFIED", entity_class=sector_applicability["details"].get("entity_class"))
                              if ticker in official_tickers else
                              _dimension("BLOCKED", "OFFICIAL_QUALIFIED", ["NO_APPROVED_OFFICIAL_SOURCE_ROUTE_IN_REGISTRY"], source_artifacts["official_financial_panel"],
                                         panel_membership="NOT_QUALIFIED"))
        dimensions = {
            "market_descriptive": _mapped_lens(lenses["TREND_MOMENTUM_RESEARCH"], source_artifacts["strategy_eligibility"]),
            "market_regime_context": _dimension("ELIGIBLE", "EMPIRICAL_ACTIVE_SHADOW_ONLY", ["CONTEMPORANEOUS_EMPIRICAL_COHORT_ONLY"], source_artifacts["market_context"], descriptor=market["breadth"]["trend"]["descriptor"]["descriptor"]),
            "fundamental_quality": fundamental_quality,
            "financial_evidence_depth": financial_evidence,
            "sector_model_applicability": sector_applicability,
            "valuation_research": valuation_dimension,
            "scenario_research": scenario_dimension,
            "event_catalyst_evidence": event_dimension,
            "liquidity_readiness": _mapped_lens(lenses["LIQUIDITY_SENSITIVE_RESEARCH"], source_artifacts["strategy_eligibility"]),
            "historical_pit_readiness": _mapped_lens(lenses["HISTORICAL_PIT_STRATEGY_RESEARCH"], source_artifacts["strategy_eligibility"]),
        }
        positive, negative, conflicting, missing, catalysts, risks = [], [], [], [], [], []
        trend = daily_row["research_summary"]["trend_state"]
        (positive if trend == "ABOVE_MA20" else negative).append(_evidence("OBSERVED_TECHNICAL_CONTEXT", trend, "SHADOW_ONLY", source_artifacts["daily_product"]))
        if ticker in official_tickers:
            positive.append(_evidence("OFFICIAL_FINANCIAL_EVIDENCE", "QUALIFIED", "OFFICIAL_QUALIFIED", source_artifacts["official_financial_panel"]))
        else:
            missing.append(_evidence("FUNDAMENTAL_AUTHORITY_LIMITATION", fundamental_authority, fundamental_authority, source_artifacts["daily_product"], ["PROVIDER_FUNDAMENTALS_DESCRIPTIVE_ONLY"]))
        for domain_name, domain in sorted(risk_row["domains"].items()):
            item = _evidence(domain_name, domain["status"], domain["authority_tier"], domain.get("source_identity") or source_artifacts["downside_context"], list(domain["reason_codes"]))
            if domain_name == "EVENT_VISIBILITY" and domain["status"] != "NO_RETAINED_EVENT_EVIDENCE":
                catalysts.append(item)
            elif domain_name in ("EVIDENCE_UNCERTAINTY", "EXECUTION_RISK_STATUS", "TECHNICAL_DOWNSIDE_CONTEXT", "PRICE_STRUCTURE_DOWNSIDE_CONTEXT", "SCENARIO_DOWNSIDE_CONTEXT"):
                risks.append(item)
        if event_row["event_facts"]:
            catalysts.extend(_evidence("EVENT_FACT", fact, "RESEARCH_SHADOW", event_row["event_context_identity"]) for fact in event_row["event_facts"])
        else:
            missing.append(_evidence("EVENT_EVIDENCE", "UNKNOWN", "MISSING", event_row["event_context_identity"], ["NO_RETAINED_EVENT_EVIDENCE_NOT_NO_EVENT_RISK"]))
        if scenario_row:
            for item in scenario_row["counter_thesis_reference"]["items"]:
                negative.append(_evidence("SCENARIO_COUNTER_THESIS", item["claim"], item["authority_tier"], scenario_row["scenario_content_identity"]))
            for item in scenario_row["thesis_reference"]["items"]:
                positive.append(_evidence("SCENARIO_THESIS_REFERENCE", item["claim"], item["authority_tier"], scenario_row["scenario_content_identity"]))
        else:
            missing.append(_evidence("SCENARIO_EVIDENCE", "UNKNOWN", "RESEARCH_SHADOW", source_artifacts["scenario"], ["SCENARIO_OBJECT_NOT_RETAINED"]))
        if positive and negative:
            conflicting.append(_evidence("COEXISTING_OBSERVED_EVIDENCE", "POSITIVE_AND_NEGATIVE_EVIDENCE_RETAINED", "MIXED", source_artifacts["daily_product"]))
        for name, dim in dimensions.items():
            if dim["eligibility"] in ("BLOCKED", "UNKNOWN"):
                missing.append(_evidence("ANALYTICAL_DIMENSION_GAP", name, dim["authority_ceiling"], dim["source_artifact_identity"], dim["reason_codes"]))
        # The upstream registry calls these "research lenses".  Its scenario
        # lens is retained as an input gate, but is intentionally not emitted
        # as a strategy/research lane: scenario evidence is its own axis.
        lane_states = {name: _lane(value, source_artifacts["strategy_eligibility"],
                                   risk_row["domains"]["TECHNICAL_DOWNSIDE_CONTEXT"])
                       for name, value in sorted(lenses.items()) if name != "SCENARIO_RESEARCH"}
        review_state = "RESEARCH_PARTIAL" if any(value["eligibility"] in ("PARTIAL", "BLOCKED", "UNKNOWN") for value in dimensions.values()) else "RESEARCH_READY"
        records.append({
            "ticker": ticker,
            "universe_membership": {"state": "INCLUDED", "as_of_session": session},
            "evidence_inventory": {"daily_facts": facts, "fundamental_authority": fundamental_authority,
                                   "source_artifact_identities": source_artifacts},
            "analytical_eligibility": dimensions,
            "strategy_research_lanes": lane_states,
            "source_research_lenses_excluded_from_lane_classification": {
                "SCENARIO_RESEARCH": _mapped_lens(lenses["SCENARIO_RESEARCH"], source_artifacts["strategy_eligibility"])
            },
            "setup_context": {"record_setup_state": setup_row["record_setup_state"], "active_setup_ids": setup_row["active_setup_ids"],
                              "authority": setup_row["active_setup_authorities"], "orthogonal_to_strategy_lanes": True},
            "scenario_axis": {"eligibility": scenario_dimension["eligibility"], "scenario_content_identity": scenario_row["scenario_content_identity"] if scenario_row else None,
                              "qualification_status": scenario_row["scenario_qualification_status"] if scenario_row else "NOT_RETAINED", "probability_status": scenario_row["probability_status"] if scenario_row else "UNQUALIFIED",
                              "prohibited": ["SCENARIO_PROBABILITIES", "TARGET_PRICES", "EXPECTED_RETURNS"]},
            "research_case": {"POSITIVE_EVIDENCE": positive, "NEGATIVE_EVIDENCE": negative, "CONFLICTING_EVIDENCE": conflicting,
                              "UNKNOWN_OR_MISSING": missing, "CATALYST_EVIDENCE": catalysts, "RISK_EVIDENCE": risks},
            "valuation_state": valuation_state,
            "human_review": {"workflow_state": review_state, "human_decision_required": True,
                             "evidence_reviewed": sorted(source_artifacts), "optional_analyst_notes": None,
                             "unresolved_questions": [item["reason_codes"] for item in missing if item["reason_codes"]],
                             "permissible_conclusion_types": ["EVIDENCE_BOUND_RESEARCH_SUMMARY", "OBSERVED_TECHNICAL_CONTEXT", "QUALIFIED_OR_PROVIDER_DESCRIPTIVE_FUNDAMENTAL_CONTEXT"],
                             "forbidden_authority": ["BUY_SELL_HOLD", "TARGET_PRICE", "EXPECTED_RETURN", "SCENARIO_PROBABILITY", "POSITION_SIZE", "EXECUTION"]},
        })
    coverage = {name: dict(sorted(Counter(row["analytical_eligibility"][name]["eligibility"] for row in records).items()))
                for name in records[0]["analytical_eligibility"]}
    artifact = {"schema_version": "1.0.0", "contract_version": METHOD, "as_of": {"research_session": session,
                "universe_identity": product["artifact_identity"], "universe_source": "mva_daily_investment_research_artifact.stock_research",
                "membership_count": len(records), "universe_authority": "EMPIRICAL_ACTIVE_SHADOW_ONLY",
                "shadow_universe_note": "A separate 2026-08-21 shadow snapshot is not this dated cohort."},
                "eligibility_vocabulary": list(ELIGIBILITY_VOCABULARY), "source_artifact_identities": source_artifacts, "records": records,
                "coverage": {"membership_count": len(records), "by_analytical_dimension": coverage,
                             "official_financial_evidence_presence": dict(sorted(Counter(row["analytical_eligibility"]["financial_evidence_depth"]["eligibility"] for row in records).items())),
                             "fundamental_quality_eligibility": dict(sorted(Counter(row["analytical_eligibility"]["fundamental_quality"]["eligibility"] for row in records).items())),
                             "sector_metric_not_applicable_counts": dict(sorted(Counter(
                                 row["analytical_eligibility"]["sector_model_applicability"]["details"].get("entity_class")
                                 for row in records
                                 for _ in row["analytical_eligibility"]["sector_model_applicability"]["details"].get("not_applicable_metric_ids", [])
                             ).items())),
                             "valuation_method_not_applicable_counts": dict(sorted(Counter(
                                 row["analytical_eligibility"]["sector_model_applicability"]["details"].get("entity_class")
                                 for row in records
                                 for state in row["valuation_state"].get("method_states", {}).values()
                                 if state.get("status") == "NOT_APPLICABLE"
                             ).items())),
                             "human_review_state_counts": dict(sorted(Counter(row["human_review"]["workflow_state"] for row in records).items())),
                             "scenario_packet_count": sum(row["scenario_axis"]["scenario_content_identity"] is not None for row in records),
                             "event_fact_packet_count": sum(bool(row["research_case"]["CATALYST_EVIDENCE"]) for row in records)},
                "authority_boundary": {"decision_support_only": True, "ai_may_only_consume_structured_packet": True,
                                       "ai_may_not_create_authority_or_override_eligibility": True,
                                       "recommendation_target_probability_sizing_execution": "NOT_EMITTED",
                                       "missing_is_not_zero_or_absence": True},
                "verdict": "EVIDENCE_GATED_RESEARCH_DECISION_WORKFLOW_V1_READY"}
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "evidence_gated_research_decision_workflow:" + artifact["artifact_sha256"]
    return artifact
