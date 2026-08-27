import pytest

from financial_statement_template_recognizer import normalize_monetary_display_value
import p3f13_official_financial_evidence_scaleout as p3f13


def test_explicit_monetary_scale_applies_once_and_preserves_sign():
    assert normalize_monetary_display_value(52_576_991, "VND", 1_000_000) == 52_576_991_000_000
    assert normalize_monetary_display_value(-3_262_205, "VND", 1_000_000) == -3_262_205_000_000
    assert normalize_monetary_display_value(9, "VND", 1) == 9


def test_missing_currency_or_scale_fails_closed_without_magnitude_inference():
    with pytest.raises(ValueError): normalize_monetary_display_value(1, None, 1_000_000)
    with pytest.raises(ValueError): normalize_monetary_display_value(1, "VND", None)


def test_exact_evidence_keyed_active_corrections_have_no_remaining_mismatch():
    artifact = p3f13.execute()
    corrections = artifact["normalization_corrections"]
    assert artifact["normalization_reconciliation"] == {
        "denominator": 138,
        "existing_exact": 128,
        "corrected": 10,
        "mismatch": 0,
        "residual": 0,
    }
    assert len(corrections) == 10
    assert {(r["ticker"], r["canonical_metric"]): r["new_value"] for r in corrections} == {
        ("VNM", "revenue"): 52_576_991_000_000,
        ("VNM", "total_assets"): 56_993_245_000_000,
        ("VRE", "cash_and_equivalents"): 4_434_617_000_000,
        ("VRE", "current_liabilities"): 5_173_857_000_000,
        ("VRE", "net_income"): 6_445_924_000_000,
        ("VRE", "operating_cash_flow"): -3_262_205_000_000,
        ("VRE", "revenue"): 8_837_380_000_000,
        ("VRE", "shareholders_equity"): 48_368_203_000_000,
        ("VRE", "total_assets"): 61_279_149_000_000,
        ("VRE", "total_interest_bearing_debt"): 6_401_081_000_000,
    }
    assert all(r["new_value"] == r["old_value"] * 1_000_000 for r in corrections)
    assert p3f13.execute()["normalization_corrections"] == corrections


def test_refreshed_derived_metrics_use_corrected_base_currency_values():
    readiness = p3f13.execute()["refreshed_fundamental_readiness"]
    metrics_by_ticker = {
        issuer["issuer_identity"]["ticker"]: {metric["metric_id"]: metric["value"] for metric in issuer["metrics"]}
        for issuer in readiness["issuer_research_readiness"]
        if issuer["issuer_identity"]["ticker"] in {"VNM", "VRE"}
    }
    assert metrics_by_ticker["VNM"]["net_margin"] == 0.16521001
    assert metrics_by_ticker["VNM"]["return_on_assets"] == 0.15240832
    assert metrics_by_ticker["VRE"]["net_margin"] == 0.7293931
    assert metrics_by_ticker["VRE"]["debt_to_equity"] == 0.13234068
