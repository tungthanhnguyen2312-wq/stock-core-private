from __future__ import annotations
import inspect

from official_financial_value_evidence import EXACT_MATCH, EXACT_UNIT_MATCH, SIGN_MATCH, qualify_value_evidence

SHA = "b" * 64

def official(**overrides):
    value = {"document_sha256": SHA, "issuer_identity": "TEST", "entity_type": "corporate", "reporting_period": "2024", "periodicity": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "canonical_metric": "total_assets", "raw_label": "Total assets", "raw_value_text": "1,000", "normalized_numeric_value": 1000, "source_page": 1, "statement_family": "balance_sheet", "statement_or_note_context": "balance_sheet", "extraction_method": "pdf_text/v1", "source_span": {"document_sha256": SHA, "citation_id": "c", "source_page": 1, "text": "Total assets 1,000"}}
    return {**value, **overrides}

def provider(**overrides):
    value = {"observation_id": "o", "issuer_identity": "TEST", "canonical_metric": "total_assets", "statement_family": "balance_sheet", "reporting_period": "2024-Q4", "periodicity": "quarterly", "normalized_numeric_value": 1000, "unit_scale": 1, "provider": "VCI"}
    return {**value, **overrides}

def test_exact_span_and_fy_q4_balance_alias_qualify_deterministically():
    a = qualify_value_evidence(official(), provider(), applicable_entity_types={"corporate"})
    b = qualify_value_evidence(official(), provider(), applicable_entity_types={"corporate"})
    assert a["reconciliation_status"] == EXACT_MATCH
    assert a["canonical_qualification"] == "CANONICAL_QUALIFIED"
    assert a["value_evidence_id"] == b["value_evidence_id"]
    assert a["official_value_evidence"]["source_span"]["document_sha256"] == SHA

def test_explicit_unit_and_approved_sign_policy_only():
    unit = qualify_value_evidence(official(unit_scale=1000000, raw_value_text="1" , normalized_numeric_value=1), provider(normalized_numeric_value=1000000, unit_scale=1))
    assert unit["reconciliation_status"] == EXACT_UNIT_MATCH
    sign = qualify_value_evidence(official(raw_value_text="(1,000)", normalized_numeric_value=-1000), provider(), sign_policy={"version": "v1"})
    assert sign["reconciliation_status"] == SIGN_MATCH
    assert qualify_value_evidence(official(raw_value_text="(1,000)", normalized_numeric_value=-1000), provider())["reconciliation_status"] == "VALUE_MISMATCH"

def test_identity_period_scope_ambiguity_and_missing_metric_fail_closed_independently():
    assert qualify_value_evidence(official(), provider(canonical_metric="revenue"))["reconciliation_status"] == "SEMANTIC_IDENTITY_MISMATCH"
    assert qualify_value_evidence(official(statement_family="income_statement"), provider(statement_family="income_statement"))["reconciliation_status"] == "PERIOD_MISMATCH"
    assert qualify_value_evidence(official(), provider(statement_scope="separate"))["reconciliation_status"] == "SCOPE_MISMATCH"
    assert qualify_value_evidence(official(), provider(currency="USD"))["reconciliation_status"] == "CURRENCY_SCALE_BLOCKED"
    assert qualify_value_evidence(official(raw_value_text="1.0"), provider())["canonical_qualification"] == "CANONICAL_BLOCKED"
    good = qualify_value_evidence(official(), provider())
    missing = qualify_value_evidence(official(canonical_metric="cash_and_equivalents"), None)
    assert good["canonical_qualification"] == "CANONICAL_QUALIFIED" and missing["canonical_qualification"] == "CANONICAL_BLOCKED"

def test_sector_gate_and_no_ticker_specific_branch():
    assert qualify_value_evidence(official(entity_type="bank"), provider(), applicable_entity_types={"corporate"})["reconciliation_status"] == "SECTOR_NOT_APPLICABLE"
    assert "if ticker ==" not in inspect.getsource(qualify_value_evidence)
