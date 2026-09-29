"""Hermetic contract tests for historical net-income semantic correction overlay V1."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from canonical_fact_store import load_official_citations
from canonical_financial_facts import METRIC_REGISTRY
from financial_statement_template_recognizer import (
    CANONICAL_ATTRIBUTABLE_NET_INCOME_SEMANTIC,
    CANONICAL_NET_INCOME_SEMANTIC,
    GENERIC_METRIC_RULES,
    attributable_net_income_line_codes_for_scope,
    net_income_line_codes_for_scope,
)
from historical_net_income_semantic_correction import (
    CLASS_A,
    CLASS_D_UNRESOLVED,
    COMPATIBILITY_ALIAS,
    CONTRACT_VERSION,
    CORRECTION_KIND,
    CURRENT_AUTHORITATIVE,
    FINANCIAL_V2_PIN,
    MILESTONE_ID,
    PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
    SEMANTIC_IDENTITY_UNRESOLVED,
    SEMANTIC_INTENT_UNRESOLVED,
    SUPERSEDED,
    TOTAL_NET_INCOME_REQUIRED,
    UNAVAILABLE,
    apply_to_citation_mapping,
    apply_to_facts,
    apply_to_verified_identities,
    build_all_correction_records,
    build_public_report,
    canonicalize_metric_name,
    class_a_outcome,
    classify_consumers,
    correction_id_for,
    current_authority_fact_rows,
    is_wrong_class_a_net_income,
    precedence_official_attributable_vs_provider_net_income,
    unresolved_consumer_fail_closed,
)
from official_financial_ocr_table_evidence import STANDARD_FACT_RULES, row_label_supports_metric
from official_legacy_precedence import NOT_COMPARABLE
from financial_evidence_currency_refresh import financial_v2_pin_decision


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_registry_keeps_total_and_attributable_distinct():
    assert "net_income" in METRIC_REGISTRY and "attributable_net_income" in METRIC_REGISTRY
    assert METRIC_REGISTRY["net_income"] is not METRIC_REGISTRY["attributable_net_income"]
    assert CANONICAL_NET_INCOME_SEMANTIC == "net_income"
    assert CANONICAL_ATTRIBUTABLE_NET_INCOME_SEMANTIC == "attributable_net_income"
    rules = {code: metric for metric, family, code in STANDARD_FACT_RULES if code in {"60", "61"}}
    assert rules == {"60": "net_income", "61": "attributable_net_income"}
    assert GENERIC_METRIC_RULES["net_income"]["standard_line_code"] == "60"
    assert GENERIC_METRIC_RULES["attributable_net_income"]["standard_line_code"] == "61"
    assert net_income_line_codes_for_scope("consolidated") == ("60",)
    assert net_income_line_codes_for_scope(None) == ("60",)
    assert attributable_net_income_line_codes_for_scope("consolidated") == ("61",)


def test_line60_qualifies_net_income_only_with_identity_evidence():
    assert row_label_supports_metric("net_income", "Lợi nhuận sau thuế thu nhập doanh nghiệp")
    assert row_label_supports_metric("net_income", "Net profit after tax")
    assert not row_label_supports_metric("net_income", "Shareholders of the parent company")
    assert not row_label_supports_metric("net_income", "")
    assert CLASS_A[0]["line60"]["label_qualifies"] is True
    assert CLASS_A[2]["line60"]["label_qualifies"] is True
    assert CLASS_A[3]["line60"]["label_qualifies"] is True


def test_line61_qualifies_attributable_only_with_identity_evidence():
    assert row_label_supports_metric("attributable_net_income", "Shareholders of the parent company")
    assert row_label_supports_metric("attributable_net_income", "Lợi nhuận sau thuế của cổ đông Công ty mẹ")
    assert not row_label_supports_metric("attributable_net_income", "Lợi nhuận sau thuế thu nhập doanh nghiệp")
    assert not row_label_supports_metric("attributable_net_income", "Phan b6é cho: cong Cô déng cua ty me")
    assert CLASS_A[0]["line61"]["label_qualifies"] is True
    assert CLASS_A[2]["line61"]["label_qualifies"] is False
    assert CLASS_A[3]["line61"]["label_qualifies"] is True


def test_append_only_correction_and_old_evidence_immutable():
    original = {
        "ticker": "HPG", "canonical_metric": "net_income", "reporting_period": "2022",
        "statement_scope": "consolidated", "value": 8_483_510_554_031, "currency": "VND",
        "unit_scale": 1, "qualification_state": "QUALIFIED",
        "source_lineage": {
            "document_sha256": CLASS_A[0]["document_sha256"], "citation_id": CLASS_A[0]["wrong"]["citation_id"],
            "line_code": "61", "source_page": 107,
        },
    }
    frozen = json.dumps(original, sort_keys=True)
    applied = apply_to_facts([original])
    assert json.dumps(original, sort_keys=True) == frozen
    assert applied["superseded_facts"][0]["qualification_state"] == SUPERSEDED
    assert applied["superseded_facts"][0]["value"] == 8_483_510_554_031
    assert all(row["canonical_metric"] != "net_income" or row.get("current_authority_state") != SUPERSEDED
               or row["value"] == 8_483_510_554_031 for row in applied["superseded_facts"])


def test_old_wrong_fact_superseded_and_corrected_fact_current_only_when_qualified():
    outcomes = { (row["ticker"], row["reporting_period"]): row for row in (class_a_outcome(entry) for entry in CLASS_A) }
    assert outcomes[("HPG", "2022")]["net_income"]["available"] is True
    assert outcomes[("HPG", "2022")]["attributable_net_income"]["available"] is True
    assert outcomes[("HPG", "2023")]["net_income"]["value"] == 6_800_388_315_081
    assert outcomes[("FPT", "2025")]["attributable_net_income"]["available"] is False
    assert outcomes[("FPT", "2025")]["net_income"]["value"] == 11_232_339_450_734
    assert outcomes[("GAS", "2025")]["net_income"]["value"] == 11_571_631_226_008
    assert outcomes[("GAS", "2025")]["attributable_net_income"]["value"] == 11_414_339_911_686
    current = { (row["ticker"], row["canonical_metric"], row["reporting_period"], row["value"])
                for row in current_authority_fact_rows() }
    assert ("FPT", "attributable_net_income", "2025", 9_376_127_629_501) not in current
    assert ("FPT", "net_income", "2025", 9_376_127_629_501) not in current
    assert ("FPT", "net_income", "2025", 11_232_339_450_734) in current


def test_deterministic_correction_id_and_no_wall_clock():
    records = build_all_correction_records()
    again = build_all_correction_records()
    assert [row["correction_id"] for row in records] == [row["correction_id"] for row in again]
    payload = {
        "document_sha256": "a" * 64, "citation_id": "b" * 64, "ticker": "HPG",
        "reporting_period": "2022", "statement_scope": "consolidated", "old_metric": "net_income",
        "new_metric": "attributable_net_income", "source_page": 107, "line_code": "61",
        "evidence_identity": {"document_sha256": "a" * 64},
    }
    assert correction_id_for(payload) == correction_id_for(dict(payload))
    source = inspect.getsource(correction_id_for)
    assert "datetime" not in source and "time.time" not in source


def test_exact_key_dedup_and_no_numeric_copying():
    line60 = {
        "ticker": "HPG", "canonical_metric": "net_income", "reporting_period": "2022",
        "statement_scope": "consolidated", "value": 8_444_429_054_516,
        "source_lineage": {"document_sha256": CLASS_A[0]["document_sha256"], "line_code": "60", "citation_id": "x"},
    }
    applied = apply_to_facts([line60])
    net = [row for row in applied["current_facts"] if row["canonical_metric"] == "net_income" and row["reporting_period"] == "2022"]
    attr = [row for row in applied["current_facts"] if row["canonical_metric"] == "attributable_net_income" and row["reporting_period"] == "2022"]
    assert len(net) == 1 and net[0]["value"] == 8_444_429_054_516
    assert len(attr) == 1 and attr[0]["value"] == 8_483_510_554_031
    assert net[0]["value"] != attr[0]["value"]
    conflict = dict(line60)
    conflict["value"] = 1
    with pytest.raises(ValueError, match="EXACT_KEY_DUPLICATE"):
        apply_to_facts([line60, conflict])


def test_missing_line60_stays_missing_when_label_fails():
    entry = dict(CLASS_A[2])
    assert entry["ticker"] == "FPT"
    assert entry["line61"]["label_qualifies"] is False
    applied = apply_to_facts([{
        "ticker": "FPT", "canonical_metric": "net_income", "reporting_period": "2025",
        "statement_scope": "consolidated", "value": 9_376_127_629_501,
        "source_lineage": {"document_sha256": entry["document_sha256"], "citation_id": entry["wrong"]["citation_id"],
                           "line_code": "61"},
    }])
    attr = [row for row in applied["current_facts"] if row["canonical_metric"] == "attributable_net_income"]
    assert attr == []
    net = [row for row in applied["current_facts"] if row["canonical_metric"] == "net_income" and row["reporting_period"] == "2025"]
    assert len(net) == 1 and net[0]["value"] == 11_232_339_450_734


def test_hpg_fpt_gas_frozen_identities():
    by_key = {(row["ticker"], row["reporting_period"]): row for row in CLASS_A}
    assert by_key[("HPG", "2022")]["wrong"]["value"] == 8_483_510_554_031
    assert by_key[("HPG", "2023")]["wrong"]["value"] == 6_835_064_334_356
    assert by_key[("FPT", "2025")]["wrong"]["value"] == 9_376_127_629_501
    assert by_key[("GAS", "2025")]["wrong"]["value"] == 11_414_339_911_686
    assert {row["ticker"] + row["reporting_period"] for row in CLASS_D_UNRESOLVED} == {
        "PVD2022", "PVD2023", "VNM2024", "AAA2024", "VRE2025"}


def test_class_d_facts_are_not_relabelled():
    facts = [
        {"ticker": "VRE", "canonical_metric": "net_income", "reporting_period": "2025",
         "statement_scope": "consolidated", "value": 6_445_924, "source_lineage": {"line_code": "61"}},
        {"ticker": "PVD", "canonical_metric": "net_income", "reporting_period": "2022",
         "statement_scope": "consolidated", "value": -6_653_052},
    ]
    applied = apply_to_facts(facts)
    assert applied["superseded_facts"] == []
    current = {(row["ticker"], row["reporting_period"], row["canonical_metric"], row["value"]) for row in applied["current_facts"]
               if row["ticker"] in {"VRE", "PVD"}}
    assert ("VRE", "2025", "net_income", 6_445_924) in current
    assert ("PVD", "2022", "net_income", -6_653_052) in current
    assert all(row["reason"] == SEMANTIC_IDENTITY_UNRESOLVED for row in CLASS_D_UNRESOLVED)


def test_metric_difference_precedence_and_no_value_similarity_shortcut():
    result = precedence_official_attributable_vs_provider_net_income()
    assert result["status"] == NOT_COMPARABLE
    assert result["reason"] == "METRIC_DIFFERENCE"
    assert result["official_becomes_factual_authority"] is False


def test_consumer_semantic_classification_and_unresolved_fail_closed():
    by_key = {(row["consumer"], row["key"]): row["classification"] for row in classify_consumers()}
    assert by_key[("fundamental_research_readiness.py", "corporate.net_margin")] == TOTAL_NET_INCOME_REQUIRED
    assert by_key[("fundamental_research_readiness.py", "bank.earnings")] == PARENT_ATTRIBUTABLE_INCOME_REQUIRED
    assert by_key[("market_wide_current_valuation_input_scaleout.py", "corporate.P/E")] == TOTAL_NET_INCOME_REQUIRED
    assert by_key[("market_wide_current_valuation_input_scaleout.py", "bank.P/E")] == PARENT_ATTRIBUTABLE_INCOME_REQUIRED
    blocked = unresolved_consumer_fail_closed(SEMANTIC_INTENT_UNRESOLVED, metric="mystery_multiple")
    assert blocked["status"] == "BLOCKED" and blocked["value"] is None
    with pytest.raises(ValueError):
        unresolved_consumer_fail_closed(TOTAL_NET_INCOME_REQUIRED, metric="net_income")


def test_stale_vocabulary_compatibility_alias():
    assert canonicalize_metric_name(COMPATIBILITY_ALIAS) == "attributable_net_income"
    assert canonicalize_metric_name("net_income") == "net_income"
    verified = apply_to_verified_identities({
        ("ZZZ", COMPATIBILITY_ALIAS, "2024"): {
            "ticker": "ZZZ", "metric": COMPATIBILITY_ALIAS, "value": 1, "reporting_period": "2024",
        }
    })
    assert ("ZZZ", "attributable_net_income", "2024") in verified
    assert verified[("ZZZ", "attributable_net_income", "2024")]["compatibility_alias_from"] == COMPATIBILITY_ALIAS


def test_financial_v2_pin_unchanged():
    decision = financial_v2_pin_decision(tickers_with_new_qualified_core=2, unresolved_schema_ambiguity=False)
    assert decision["current_authority_version"] == FINANCIAL_V2_PIN
    assert decision["rebuild_performed"] is False
    assert decision["decision"] == "KEEP_CURRENT_PIN"


def test_zero_active_vnstock_in_correction_modules():
    for module in (
        "historical_net_income_semantic_correction",
        "canonical_fact_store",
        "p3f13_official_financial_evidence_scaleout",
        "semantic_evidence_bridge",
    ):
        source = inspect.getsource(__import__(module))
        assert "import vnstock" not in source
        assert "import vnai" not in source


def test_deterministic_rebuild_identity():
    first = build_public_report(unexplained_drift_count=0)
    second = build_public_report(unexplained_drift_count=0)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["historical_rows_rewritten"] is False
    assert first["v1_covers"] == "exactly four confirmed Class-A facts"


def test_loader_applies_current_authority_overlay(tmp_path: Path):
    loaded = apply_to_citation_mapping({})
    assert loaded[("HPG", "net_income", "2022")]["value"] == 8_444_429_054_516
    assert loaded[("HPG", "attributable_net_income", "2022")]["value"] == 8_483_510_554_031
    assert loaded[("FPT", "net_income", "2025")]["value"] == 11_232_339_450_734
    assert ("FPT", "attributable_net_income", "2025") not in loaded
    assert loaded[("GAS", "attributable_net_income", "2025")]["value"] == 11_414_339_911_686
    wrong_kept_out = apply_to_citation_mapping({
        ("FPT", "net_income", "2025"): {"value": 9_376_127_629_501, "citation_id": "x"},
    })
    assert wrong_kept_out[("FPT", "net_income", "2025")]["value"] == 11_232_339_450_734
    citations = load_official_citations(tmp_path)
    assert citations[("GAS", "net_income", "2025")]["value"] == 11_571_631_226_008


def test_no_line61_remains_current_net_income_for_class_a():
    applied = apply_to_facts([
        {
            "ticker": entry["ticker"], "canonical_metric": "net_income",
            "reporting_period": entry["reporting_period"], "statement_scope": "consolidated",
            "value": entry["wrong"]["value"],
            "source_lineage": {
                "document_sha256": entry["document_sha256"], "citation_id": entry["wrong"]["citation_id"],
                "line_code": "61", "source_page": entry["wrong"]["source_page"],
            },
        }
        for entry in CLASS_A
    ])
    current_net = [
        row for row in applied["current_facts"]
        if row["canonical_metric"] == "net_income" and (row["ticker"], row["reporting_period"]) in {(e["ticker"], e["reporting_period"]) for e in CLASS_A}
    ]
    assert {row["value"] for row in current_net} == {
        8_444_429_054_516, 6_800_388_315_081, 11_232_339_450_734, 11_571_631_226_008,
    }
    assert all(str((row.get("source_lineage") or {}).get("line_code") or row.get("line_code")) != "61" for row in current_net)


def test_governed_fact_corrections_no_longer_replace_line60_with_line61_as_net_income():
    source = __import__("p3f13_official_financial_evidence_scaleout")
    text = inspect.getsource(source.apply_canonical_identity_corrections)
    assert "fact[\"value\"] = correction[\"correct_value\"]" not in text
    assert "SUPERSEDED_BY_SEMANTIC_METRIC_RELABEL" in text
    assert CORRECTION_KIND == "SEMANTIC_METRIC_RELABEL"
    assert MILESTONE_ID.endswith("OVERLAY_V1")
    assert CONTRACT_VERSION.startswith("historical_net_income_semantic_correction/")
