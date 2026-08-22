"""Deterministic, retained-evidence reconciliation of current-share capabilities.

This is an evidence map, not an authority promotion.  In particular, it
preserves the distinction between the retained VCI issued-share field and an
effective-dated common-shares-outstanding denominator.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_share_basis_capability_reconciliation/v1"
ARTIFACT_TYPE = "CURRENT_SHARE_BASIS_CAPABILITY_RECONCILIATION"

EXACT_RECONCILED = "EXACT_RECONCILED"
PROVIDER_REPORTED_CURRENT = "PROVIDER_REPORTED_CURRENT"
COVERAGE_RESTRICTED = "COVERAGE_RESTRICTED"
STALE_AFTER_CORPORATE_ACTION = "STALE_AFTER_CORPORATE_ACTION"
SEMANTICALLY_AMBIGUOUS = "SEMANTICALLY_AMBIGUOUS"
UNAVAILABLE = "UNAVAILABLE"

VALUATION_USES = ("current_market_cap_denominator", "current_p_e", "current_p_b", "current_p_s", "current_ev_inputs")


def _use_decision(*, eligible: bool, reason: str) -> dict[str, dict[str, Any]]:
    return {name: {"eligible": eligible, "reason": reason} for name in VALUATION_USES}


def derive_common_shares_from_components(issued_shares: int | None, treasury_shares: int | None) -> dict[str, Any]:
    """Perform only the explicit issued-minus-treasury formula; never imply zero."""
    valid = lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if not valid(issued_shares) or not valid(treasury_shares):
        return {"value": None, "identity": "UNKNOWN", "status": UNAVAILABLE,
                "reason": "ISSUED_MINUS_TREASURY_REQUIRES_BOTH_EXPLICIT_COMPONENTS"}
    if treasury_shares > issued_shares:
        return {"value": None, "identity": "UNKNOWN", "status": SEMANTICALLY_AMBIGUOUS,
                "reason": "TREASURY_SHARES_EXCEED_ISSUED_SHARES"}
    return {"value": issued_shares - treasury_shares, "identity": "common_shares_outstanding",
            "status": EXACT_RECONCILED, "reason": "EXPLICIT_ISSUED_MINUS_TREASURY_COMPONENTS"}


def _record(*, capability: str, semantic_identity: str, source: str, unit: str,
            observation_date: str | None, effective_date: str | None, freshness: str,
            verdict: str, lineage: Sequence[str], corporate_action_state: str,
            allowed_uses: Mapping[str, Mapping[str, Any]], value: int | None = None,
            notes: Sequence[str] = ()) -> dict[str, Any]:
    return {"capability": capability, "semantic_identity": semantic_identity, "source": source,
            "unit": unit, "observation_date": observation_date, "effective_date": effective_date,
            "value": value, "freshness_state": freshness, "verdict": verdict,
            "evidence_lineage": list(lineage), "corporate_action_state": corporate_action_state,
            "allowed_downstream_uses": dict(allowed_uses), "notes": list(notes)}


def build_reconciliation(p3f4: Mapping[str, Any], p3f5: Mapping[str, Any], p3f6: Mapping[str, Any]) -> dict[str, Any]:
    """Build a stable artifact solely from already-retained review artifacts."""
    valuation_date = p3f6["provider_proxy_coverage"]["valuation_date"]
    p4_identity = p3f4.get("artifact_identity")
    p5_identity = p3f5.get("artifact_identity")
    p6_identity = p3f6.get("artifact_identity")
    proofs = p3f4["representative_proofs"]
    executed = proofs["executed_transition"]["bridge_result"]
    hpg = executed["latest_qualified_identity"]
    comparisons = list(p3f5["official_comparison_matrix"])
    provider_rows = list(p3f6["proxy_valuation_rows"])
    provider_observations = [row["provider_share_proxy"] for row in provider_rows]
    provider_dates = sorted({row.get("provider_observation_date") for row in provider_observations if row.get("provider_observation_date")})
    provider_values = [row.get("value") for row in provider_observations if isinstance(row.get("value"), int)]
    corporate_blocks = p3f6["corporate_action_blocks"]

    blocked = _use_decision(eligible=False, reason="CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN")
    mva_only = _use_decision(eligible=False, reason="ISSUED_SHARES_PROXY_IS_NOT_CURRENT_COMMON_OUTSTANDING_AUTHORITY")
    records = [
        _record(capability="official_executed_common_share_anchor", semantic_identity="common_shares_outstanding",
                source="official_corporate_action_result", unit="shares", observation_date=None,
                effective_date=hpg["effective_date"], freshness="COVERAGE_THROUGH_2026_07_30_ONLY",
                verdict=COVERAGE_RESTRICTED, lineage=[p4_identity, *hpg["citation_ids"]],
                corporate_action_state="EXECUTED_RESULT_RETAINED_BUT_CONTINUITY_TO_VALUATION_DATE_NOT_PROVEN",
                allowed_uses=blocked, value=hpg["value"],
                notes=["Exact historical common-outstanding anchor; not forward-filled to valuation date."]),
        _record(capability="official_period_end_shares", semantic_identity="period_end_shares",
                source="official_retained_evidence", unit="shares", observation_date="2024-12-31",
                effective_date="2024-12-31", freshness="HISTORICAL_PERIOD_END_ONLY", verdict=COVERAGE_RESTRICTED,
                lineage=[p4_identity, p5_identity, *[row["official"]["citation_id"] for row in comparisons if row.get("official")]],
                corporate_action_state="NO_EFFECTIVE_DATE_BRIDGE_TO_VALUATION_DATE", allowed_uses=blocked,
                notes=["Period-end identity remains distinct from current shares."]),
        _record(capability="provider_reported_issued_shares", semantic_identity="issued_shares",
                source=p3f5["candidate"]["source"], unit="shares", observation_date=(provider_dates[0] if len(provider_dates) == 1 else None),
                effective_date=None, freshness="STALE_DEGRADED", verdict=SEMANTICALLY_AMBIGUOUS,
                lineage=[p5_identity, p6_identity, p3f5["candidate"]["field_path"]],
                corporate_action_state="TWO_RETAINED_ROWS_BLOCKED_FOR_UNRESOLVED_CORPORATE_ACTION_TIMING",
                allowed_uses=mva_only, value=(provider_values[0] if len(set(provider_values)) == 1 else None),
                notes=["Provider observation is issued shares, not common outstanding.",
                       "May remain visible only in the existing non-authoritative MVA shadow namespace."]),
        _record(capability="listed_shares", semantic_identity="listed_shares", source="retained_contract_inventory",
                unit="shares", observation_date=None, effective_date=None, freshness="UNKNOWN", verdict=UNAVAILABLE,
                lineage=[p4_identity], corporate_action_state="UNKNOWN", allowed_uses=blocked,
                notes=["No retained numeric listed-share capability in the reviewed artifacts."]),
        _record(capability="treasury_shares", semantic_identity="treasury_shares", source="retained_contract_inventory",
                unit="shares", observation_date=None, effective_date=None, freshness="UNKNOWN", verdict=UNAVAILABLE,
                lineage=[p4_identity], corporate_action_state="UNKNOWN", allowed_uses=blocked,
                notes=["Missing treasury shares are UNKNOWN, never assumed zero."]),
        _record(capability="weighted_average_basic_shares", semantic_identity="weighted_average_basic_shares",
                source="official_retained_evidence_inventory", unit="shares", observation_date=None, effective_date=None,
                freshness="PERIOD_WEIGHTED_NOT_CURRENT", verdict=SEMANTICALLY_AMBIGUOUS, lineage=[p4_identity],
                corporate_action_state="NOT_A_CURRENT_STOCK_MEASURE", allowed_uses=blocked,
                notes=["Weighted-average basic shares are not a current market-cap denominator."]),
        _record(capability="diluted_shares", semantic_identity="diluted_shares", source="retained_contract_inventory",
                unit="shares", observation_date=None, effective_date=None, freshness="UNKNOWN", verdict=UNAVAILABLE,
                lineage=[p4_identity], corporate_action_state="UNKNOWN", allowed_uses=blocked,
                notes=["No retained numeric diluted-share capability in the reviewed artifacts."]),
    ]
    provider_by_ticker = {row["ticker"]: row["provider_share_proxy"] for row in provider_rows}
    for block in sorted(corporate_blocks, key=lambda row: row["ticker"]):
        proxy_row = provider_by_ticker.get(block["ticker"], {})
        records.append(_record(
            capability=f"provider_issued_shares_{block['ticker']}_corporate_action_case",
            semantic_identity="issued_shares", source=p3f5["candidate"]["source"], unit="shares",
            observation_date=proxy_row.get("provider_observation_date"), effective_date=None,
            freshness=str(proxy_row.get("freshness_state") or "UNKNOWN"), verdict=STALE_AFTER_CORPORATE_ACTION,
            lineage=[p5_identity, p6_identity, *list(block.get("blockers") or [])],
            corporate_action_state="CORPORATE_ACTION_TIMING_OR_RESULT_UNRESOLVED", allowed_uses=blocked,
            value=proxy_row.get("value") if isinstance(proxy_row.get("value"), int) else None,
            notes=["Provider observation is withheld from current use because retained corporate-action timing or resulting count is unresolved."],
        ))
    component_formula = derive_common_shares_from_components(
        issued_shares=None, treasury_shares=None,
    )
    value_difference = [row for row in comparisons if row["classification"] == "VALUE_DIFFERENCE"]
    equality_different_scope = [row for row in comparisons if row["classification"] == "SEMANTICALLY_COMPATIBLE_DIFFERENT_SCOPE"]
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "valuation_date": valuation_date, "source_artifacts": {"p3f4": p4_identity, "p3f5": p5_identity, "p3f6": p6_identity},
        "capability_records": records,
        "formula_tests": {"issued_minus_treasury": component_formula},
        "corpus": {"provider_metadata_universe": p3f6["provider_proxy_coverage"]["available_metadata_universe"],
                   "provider_proxy_share_eligible": p3f6["provider_proxy_coverage"]["proxy_share_eligible"],
                   "valuation_cohort": len(provider_rows), "official_comparison_count": len(comparisons),
                   "issued_vs_period_end_value_difference_count": len(value_difference),
                   "numeric_equality_different_semantic_scope_count": len(equality_different_scope),
                   "corporate_action_block_count": len(corporate_blocks)},
        "representative_reconciliation": {"issued_vs_period_end_difference": value_difference,
                                            "equal_value_not_identity_proof": equality_different_scope,
                                            "corporate_action_blocks": corporate_blocks},
        "authoritative_current_market_cap_coverage": {"eligible": 0, "denominator": len(provider_rows),
                                                        "reason": "NO_EXPLICIT_COMMON_OUTSTANDING_COVERAGE_THROUGH_VALUATION_DATE"},
        "valuation_authority": {name: {"eligible": 0, "denominator": len(provider_rows),
                                        "reason": "CURRENT_MARKET_CAP_DENOMINATOR_REMAINS_BLOCKED"} for name in VALUATION_USES},
        "boundaries": {"official_current_share_authority_promoted": False, "provider_source_promoted": False,
                       "historical_pit_promoted": False, "raw_as_traded_promoted": False,
                       "ranking_recommendation_sizing_portfolio_promoted": False,
                       "mva_shadow_lane_preexisting_and_unchanged": True},
        "verdict": "CURRENT_SHARE_BASIS_RECONCILIATION_COMPLETE_AUTHORITY_REMAINS_FAIL_CLOSED",
    }
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"current_share_basis_capability_reconciliation:{artifact['artifact_sha256']}"
    return artifact
