"""Focused regression coverage for owner-focus evidence priority V1."""
from __future__ import annotations

from owner_focus_core_financial_panel_coverage import (
    CONTRACT_VERSION,
    _compatible_consecutive_annual,
    _opportunity,
    core_panel_contract,
    execute,
)
from owner_research_focus import owner_focus_tickers


def _artifact():
    if not hasattr(_artifact, "value"):
        _artifact.value = execute()  # type: ignore[attr-defined]
    return _artifact.value  # type: ignore[attr-defined]


def _record(ticker: str):
    return next(row for row in _artifact()["records"] if row["ticker"] == ticker)


def _metric(ticker: str, name: str):
    return next(row for row in _record(ticker)["core_metric_statuses"] if row["canonical_metric"] == name)


def test_exact_owner_focus_cohort_is_complete_ordered_and_not_acquisition_fixtures():
    artifact = _artifact()
    assert artifact["contract_version"] == CONTRACT_VERSION
    assert artifact["owner_focus_tickers"] == list(owner_focus_tickers())
    assert [row["ticker"] for row in artifact["watchlist_coverage_matrix"]] == list(owner_focus_tickers())
    assert artifact["residual_checks"] == {
        "required_ticker_count": 10, "actual_ticker_count": 10, "residual": 0,
        "residual_zero": True, "exact_owner_focus_order": True,
        "no_acquisition_route_substitution": True,
    }
    assert not {"AAA", "ABS", "ABW"} & set(artifact["owner_focus_tickers"])


def test_sector_panels_never_force_industrial_metrics_on_ssi_or_evf():
    ssi, evf = _record("SSI"), _record("EVF")
    assert ssi["entity_type"] == "securities"
    assert ssi["core_panel_contract"]["contract_state"] == "COMPLETE"
    assert "revenue" not in {row["canonical_metric"] for row in ssi["core_metric_statuses"]}
    assert evf["entity_type"] == "finance_company"
    assert evf["core_panel_contract"]["contract_state"] == "SECTOR_CORE_PANEL_CONTRACT_INCOMPLETE"
    assert all(row["status"] == "SECTOR_CONTRACT_INCOMPLETE" for row in evf["core_metric_statuses"])
    assert core_panel_contract("corporate")["metrics"] != core_panel_contract("securities")["metrics"]
    assert core_panel_contract("finance_company")["no_new_canonical_identities"] is True


def test_official_provider_temporal_and_hpg_closed_lane_boundaries_are_preserved():
    artifact, hpg, evf = _artifact(), _record("HPG"), _record("EVF")
    assert hpg["provider_research_facts"] == []
    assert len(evf["provider_research_facts"]) == 2
    assert all(row["status"] == "PROVIDER_RESEARCH_ONLY" for row in evf["provider_research_facts"])
    assert _metric("HPG", "net_income")["official_fact_periods"] == ["2022", "2023", "2024"]
    assert _metric("HPG", "net_income")["temporal_sufficiency"] == {
        "CURRENT_LEVEL": True, "YOY_2_PERIOD": True, "TREND_3_PERIOD": True,
        "compatible_annual_periods": ["2022", "2023", "2024"], "annual_and_interim_remain_distinct": True,
    }
    hpg_income = [row for row in hpg["official_qualified_facts"] if row["canonical_metric"] == "net_income"]
    assert {row["reporting_period"]: row["value"] for row in hpg_income}["2022"] == 8_483_510_554_031
    assert {row["reporting_period"]: row["value"] for row in hpg_income}["2023"] == 6_835_064_334_356
    assert artifact["authority_boundary"]["provider_promoted"] is False
    assert artifact["authority_boundary"]["valuation_or_value_authority_promoted"] is False


def test_temporal_sufficiency_requires_matching_annual_scope_currency_and_unit():
    compatible = [
        {"reporting_period": "2023", "period_type": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1},
        {"reporting_period": "2024", "period_type": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1},
        {"reporting_period": "2025", "period_type": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1},
    ]
    assert _compatible_consecutive_annual(compatible) == (True, True, ["2023", "2024", "2025"])
    incompatible = compatible[:2] + [{"reporting_period": "2025-Q1", "period_type": "quarterly", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1}]
    assert _compatible_consecutive_annual(incompatible) == (True, False, ["2023", "2024"])
    mismatched_scope = [compatible[0], {**compatible[1], "statement_scope": "separate"}]
    assert _compatible_consecutive_annual(mismatched_scope) == (False, False, ["2023", "2024"])


def test_retained_document_opportunity_classification_is_precise_and_no_ocr_is_run():
    image = [{"document_class": "audited_annual_financial_statements", "image_only": True, "native_text": False}]
    native = [{"document_class": "annual_report", "image_only": False, "native_text": True}]
    metadata = [{"document_class": "annual_report", "image_only": False, "native_text": False}]
    assert _opportunity("corporate", image) == ("IMAGE_ONLY_OCR_GAP", "OFFICIAL_DOCUMENT_IMAGE_ONLY")
    assert _opportunity("corporate", native) == ("STRUCTURAL_NATIVE_TEXT_GAP", "OFFICIAL_DOCUMENT_RETAINED_PARSER_BLOCKED")
    assert _opportunity("securities", native) == ("SECTOR_LAYOUT_GAP", "OFFICIAL_DOCUMENT_RETAINED_PARSER_BLOCKED")
    assert _opportunity("corporate", metadata) == ("METADATA_GAP", "OFFICIAL_DOCUMENT_METADATA_BLOCKED")
    assert _opportunity("corporate", []) == ("NO_RETAINED_OFFICIAL_DOCUMENT", "OFFICIAL_DOCUMENT_MISSING")
    assert _artifact()["authority_boundary"] == {
        "network_called": False, "ocr_called": False, "database_mutated": False,
        "dashboard_mutated": False, "provider_promoted": False,
        "valuation_or_value_authority_promoted": False,
    }


def test_evidence_priority_is_deterministic_not_investment_ranking_and_hpg_is_not_first():
    artifact = _artifact()
    first = artifact["evidence_priority_order"]
    second = execute()["evidence_priority_order"]
    assert first == second
    assert artifact["is_investment_ranking"] is False
    assert artifact["prohibited_outputs"] == ["buy_sell_recommendation", "investment_ranking", "target", "probability", "position_size"]
    assert first[0]["priority_code"] == "P0_CURRENT_CORE_METRIC_MISSING"
    assert first[0]["ticker"] != "HPG"
    assert _record("HPG")["evidence_priorities"][0]["priority_code"] == "P4_SECONDARY_CORE_METRIC"
    assert artifact["next_milestone_recommendation"] == {
        "ticker": "FPT", "canonical_metric": "net_income", "period": "2025",
        "existing_retained_document_sha256": "630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4",
        "blocker_type": "IMAGE_ONLY_OCR_GAP", "recommended_capability_action": "IMAGE_ONLY_TABLE_OCR",
        "not_automatically_executed": True,
    }
