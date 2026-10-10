from __future__ import annotations

from copy import deepcopy

import stocklookup_core.decision.integrated_investment_decision_product as integrated
import operational_fundamental_context_integration as bridge


def feature(feature_id: str, *, state: str | None = None, periods: tuple[str, ...] = ("2026-Q1",),
            status: str = "READY_RESEARCH_PROXY", scope: str = "unknown") -> dict:
    balance = feature_id.endswith("pit_trajectory")
    return {
        "feature_id": feature_id, "value": None if state == "TURNAROUND_TO_PROFIT" else 1,
        "categorical_state": state, "status": status, "research_fitness": status,
        "method": "same_native_point_in_time_trajectory/v1" if balance else "same_native_latest_sign/v1",
        "compatibility_class": "POINT_IN_TIME_TRAJECTORY_COMPATIBLE" if balance else "SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE",
        "compatibility_rule_version": "same_native_series_research_compatibility/v2",
        "input_periods": list(periods),
        "duration_semantics": ["POINT_IN_TIME_BALANCE_SHEET" if balance else "STANDALONE_QUARTER"],
        "scope": [scope],
        "provider_source_lineage": [{"provider": "KBS", "source_file": "native.parquet", "source_sha256": "abc"} for _ in periods],
        "blocker_reason_codes": [], "authority_tier": "OPERATIONAL_PROVIDER_RESEARCH_ONLY",
        "authoritative_financial_eligible": False, "pit_backtest_eligible": False,
        "is_actionable": False,
    }


def record(entity: str, features: dict) -> dict:
    return {"ticker": "AAA", "entity_type": entity,
            "entity_applicability": ("GENERIC_RESEARCH_PRIMITIVES_ALLOWED" if entity == "corporate"
                                     else "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE"),
            "features": features, "authority_boundary": {"authoritative": False, "pit": False, "actionable": False}}


def evaluate(entity: str, features: dict) -> dict:
    return bridge.evaluate_ticker(ticker="AAA", entity_class=entity, feature_record=record(entity, features),
                                  session="2026-09-24")


def test_corporate_core_and_missing_specialist_ratio() -> None:
    profit = feature("profit_state", state="PROFITABLE")
    margin = feature("gross_margin")
    blocked_roe = feature("roe_eop_proxy", status="BLOCKED")
    blocked_roe["blocker_reason_codes"] = ["CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE"]
    original = deepcopy(profit)
    result = evaluate("corporate", {"profit_state": profit, "gross_margin": margin, "roe_eop_proxy": blocked_roe})
    assert result["status"] == "RESEARCH_USABLE"
    assert result["usable_features"]["profit_state"] == original
    assert result["blocked_features"]["roe_eop_proxy"]["source_feature"]["status"] == "BLOCKED"
    assert result["financial_context"]["authoritative_financial_eligible"] is False


def test_bank_requires_applicable_balance_context_not_industrial_margin() -> None:
    features = {"profit_state": feature("profit_state", state="PROFITABLE"),
                "gross_margin": feature("gross_margin")}
    assert evaluate("bank", features)["primary_reason"] == "FEATURE_APPLICABILITY_INSUFFICIENT"
    features["total_assets_pit_trajectory"] = feature("total_assets_pit_trajectory", state="IMPROVING",
                                                       periods=("2025-Q4", "2026-Q1"))
    result = evaluate("bank", features)
    assert result["status"] == "RESEARCH_USABLE"
    assert "gross_margin" in result["non_applicable_features"]
    assert result["financial_context"]["profitability_state"] == "PROFITABLE"


def test_securities_uses_profit_and_equity_without_industrial_metrics() -> None:
    result = evaluate("securities", {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "shareholders_equity_pit_trajectory": feature("shareholders_equity_pit_trajectory", state="WEAKENING",
                                                      periods=("2025-Q4", "2026-Q1")),
        "debt_to_equity": feature("debt_to_equity"),
    })
    assert result["status"] == "RESEARCH_USABLE"
    assert "debt_to_equity" in result["non_applicable_features"]


def test_insurance_and_finance_company_use_limited_existing_context() -> None:
    for entity in ("insurance", "finance_company"):
        result = evaluate(entity, {
            "profit_state": feature("profit_state", state="PROFITABLE"),
            "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                                    periods=("2025-Q4", "2026-Q1")),
        })
        assert result["status"] == "RESEARCH_USABLE"
        assert result["financial_context"]["fitness"] == "OPERATIONAL_PROVIDER_RESEARCH_ONLY"


def test_stale_or_missing_core_stays_blocked() -> None:
    stale = evaluate("securities", {
        "profit_state": feature("profit_state", state="PROFITABLE", periods=("2025-Q2",)),
        "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                                periods=("2024-Q2", "2025-Q2")),
    })
    assert stale["primary_reason"] == "FEATURE_STALE"
    missing = feature("profit_state", status="BLOCKED")
    missing["blocker_reason_codes"] = ["MISSING_STANDALONE_QUARTER_EARNINGS"]
    missing_result = evaluate("corporate", {"profit_state": missing, "cash_to_assets": feature("cash_to_assets")})
    assert missing_result["primary_reason"] == "MISSING_STANDALONE_QUARTER_EARNINGS"


def test_negative_base_transition_remains_categorical_proxy() -> None:
    turnaround = feature("net_income_same_period_yoy", state="TURNAROUND_TO_PROFIT",
                         status="PARTIAL_RESEARCH", periods=("2025-Q1", "2026-Q1"))
    result = evaluate("corporate", {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "net_income_same_period_yoy": turnaround,
    })
    assert result["status"] == "RESEARCH_USABLE"
    assert result["usable_features"]["net_income_same_period_yoy"]["value"] is None
    assert result["usable_features"]["net_income_same_period_yoy"]["categorical_state"] == "TURNAROUND_TO_PROFIT"
    assert result["financial_context"]["earnings_turnaround_state"] == "TURNAROUND"


def test_integrated_builder_consumes_proxy_without_valuation_or_execution_authority() -> None:
    result = evaluate("bank", {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                                periods=("2025-Q4", "2026-Q1")),
    })
    decision = integrated.build_ticker_integrated_decision(
        ticker="AAA", as_of_session="2026-09-24", tactical_record=None,
        financial_record={"status": "ABSENT"}, valuation_record=None,
        relative_volume_record=None, market_sector_record=None,
        operational_fundamental_context_record=result,
        producer_artifact_identities={"operational_fundamental_integration": "integration:fixture"},
    )
    assert decision["fundamental_state"] == integrated.FUNDAMENTAL_STABLE
    axis = decision["evidence_axes"]["FUNDAMENTAL"]
    assert axis["fitness"] == "RESEARCH_PROXY_CONTEXT"
    assert axis["method"] == bridge.CONTRACT_VERSION
    assert decision["valuation_context_summary"]["status"] == "UNAVAILABLE"
    assert "EXACT_EXECUTION_CAPACITY_BLOCKED" in decision["exact_capabilities_unavailable"]
    assert decision["operational_fundamental_context"]["usable_features"]["profit_state"]["authority_tier"] == "OPERATIONAL_PROVIDER_RESEARCH_ONLY"


def test_entity_conflict_fails_closed_and_cohort_identity_is_order_independent() -> None:
    source = record("bank", {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                                periods=("2025-Q4", "2026-Q1")),
    })
    assert bridge.evaluate_ticker(ticker="AAA", entity_class="corporate", feature_record=source,
                                  session="2026-09-24")["primary_reason"] == "ENTITY_CLASS_CONFLICT"
    second = deepcopy(source)
    second["ticker"] = "BBB"
    forward = bridge.build_artifact(
        session="2026-09-24", capability_map_identity="map:fixture",
        cohort={"AAA": "bank", "BBB": "bank"}, feature_records={"AAA": source, "BBB": second},
        feature_store_identity="store:fixture", financial_analysis_identity="financial:fixture")
    reverse = bridge.build_artifact(
        session="2026-09-24", capability_map_identity="map:fixture",
        cohort={"BBB": "bank", "AAA": "bank"}, feature_records={"BBB": second, "AAA": source},
        feature_store_identity="store:fixture", financial_analysis_identity="financial:fixture")
    assert forward["artifact_identity"] == reverse["artifact_identity"]
    assert forward["coverage"]["research_usable"] == 2
    assert forward["authority_boundary"]["authoritative_financial_eligible"] is False


def test_stronger_financial_conflict_prevents_proxy_integration() -> None:
    result = evaluate("bank", {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                                periods=("2025-Q4", "2026-Q1")),
    })
    decision = integrated.build_ticker_integrated_decision(
        ticker="AAA", as_of_session="2026-09-24", tactical_record=None,
        financial_record={"status": "AVAILABLE", "conflicting_evidence": ["SOURCE_CONFLICT"]},
        valuation_record=None, relative_volume_record=None, market_sector_record=None,
        operational_fundamental_context_record=result,
    )
    assert decision["fundamental_state"] == integrated.FUNDAMENTAL_INSUFFICIENT
    assert decision["evidence_axes"]["FUNDAMENTAL"]["method"] == "financial_analysis_product_integration/v1"


def test_action_authority_in_source_or_feature_fails_closed() -> None:
    features = {
        "profit_state": feature("profit_state", state="PROFITABLE"),
        "total_assets_pit_trajectory": feature("total_assets_pit_trajectory", state="IMPROVING",
                                               periods=("2025-Q4", "2026-Q1")),
    }
    source = record("bank", features)
    source["authority_boundary"]["actionable"] = True
    assert bridge.evaluate_ticker(ticker="AAA", entity_class="bank", feature_record=source,
                                  session="2026-09-24")["primary_reason"] == "AUTHORITY_CONFLICT"
    source["authority_boundary"]["actionable"] = False
    features["profit_state"]["is_actionable"] = True
    blocked = bridge.evaluate_ticker(ticker="AAA", entity_class="bank", feature_record=source,
                                     session="2026-09-24")
    assert blocked["status"] == "BLOCKED"
    assert blocked["blocked_features"]["profit_state"]["integration_fitness"] == "AUTHORITY_CONFLICT"
