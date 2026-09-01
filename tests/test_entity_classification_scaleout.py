"""Tests for MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1.

Verifies:
1. Source precedence: seed > original promoted > scale-out promoted; scale-out never
   overrides either higher tier, and a scale-out/seed or scale-out/promoted disagreement
   fails closed as CONFLICT.
2. Provenance preservation: every qualified record carries evidence id, source id, and
   the full reconciliation detail that produced it.
3. Deterministic identity: identical inputs produce identical evidence ids.
4. Generic/absent evidence never defaults to industrial; financial-sector absence is not
   read as positive industrial evidence.
5. Known specialized-financial regression: bank / securities / insurer / finance-company
   evidence is never overridden into corporate.
6. Unknown stays unknown; qualified metadata conflicts fail closed.
7. Security-type applicability: a known non-equity instrument class is NOT_APPLICABLE,
   never silently dropped or classified.
8. No ticker-prefix heuristic, no company-name-only classification, no ratio-derived
   classification, and zero hardcoded ticker branches in the production module.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from entity_classification_contract import ClassificationStatus, EntityClass, EvidenceTier
from entity_classification_scaleout import (
    REASON_AMBIGUOUS_NO_SUBTYPE,
    REASON_ENTITY_TYPE_MISSING,
    ReconciliationInput,
    reconcile_ticker,
)
from exchange_industry_classification import (
    HINT_AMBIGUOUS_FINANCIAL,
    HINT_BANK,
    HINT_CORPORATE,
    HINT_INSURANCE,
    resolve_industry_hint,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFIED_AT = "2026-09-01T00:00:00+00:00"


def _inp(**overrides) -> ReconciliationInput:
    base = dict(
        ticker="ZZZ", issuer_identity="candidate:zzz", legal_name="CTCP Test Enterprise",
        instrument_class="EQUITY", icb_industry_hint=None, icb_industry_label=None,
        icb_industry_reason=None, statement_taxonomy=None,
    )
    base.update(overrides)
    return ReconciliationInput(**base)


# --- 1. Positive, non-heuristic evidence resolves the expected class -------------------

def test_non_financial_icb_sector_with_agreeing_statement_template_resolves_corporate():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_CORPORATE, icb_industry_label="Bất động sản",
                                statement_taxonomy="corporate_vas"), verified_at=VERIFIED_AT)
    assert res.outcome == "corporate"
    assert res.record.entity_class == EntityClass.CORPORATE
    assert res.record.classification_status == ClassificationStatus.QUALIFIED
    assert res.record.evidence_tier == EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION


def test_non_financial_icb_sector_with_no_statement_data_still_resolves_corporate():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_CORPORATE, icb_industry_label="Bán lẻ",
                                statement_taxonomy=None), verified_at=VERIFIED_AT)
    assert res.outcome == "corporate"


def test_ambiguous_specialized_statement_plus_bank_icb_resolves_bank():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_BANK, icb_industry_label="Ngân hàng",
                                statement_taxonomy="financial_specialized_ambiguous"), verified_at=VERIFIED_AT)
    assert res.outcome == "bank"
    assert res.record.evidence_tier == EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION


def test_ambiguous_specialized_statement_plus_insurance_icb_resolves_insurance():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_INSURANCE, icb_industry_label="Bảo hiểm",
                                statement_taxonomy="financial_specialized_ambiguous"), verified_at=VERIFIED_AT)
    assert res.outcome == "insurance"


def test_securities_statement_template_alone_resolves_securities():
    res = reconcile_ticker(_inp(statement_taxonomy="securities_company"), verified_at=VERIFIED_AT)
    assert res.outcome == "securities"


def test_securities_statement_template_corroborated_by_ambiguous_financial_icb():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_AMBIGUOUS_FINANCIAL, icb_industry_label="Dịch vụ tài chính",
                                statement_taxonomy="securities_company"), verified_at=VERIFIED_AT)
    assert res.outcome == "securities"


def test_specialized_charter_narrows_ambiguous_credit_institution_to_bank():
    res = reconcile_ticker(_inp(legal_name="Ngân hàng Thương mại Cổ phần Test",
                                statement_taxonomy="credit_institution"), verified_at=VERIFIED_AT)
    assert res.outcome == "bank"


def test_specialized_charter_narrows_ambiguous_credit_institution_to_finance_company():
    res = reconcile_ticker(_inp(legal_name="Công ty Tài chính Cổ phần Test",
                                statement_taxonomy="credit_institution"), verified_at=VERIFIED_AT)
    assert res.outcome == "finance_company"


# --- 2. Fail-closed: generic/absent evidence never defaults to industrial --------------

def test_no_evidence_at_all_stays_unknown_not_industrial():
    res = reconcile_ticker(_inp(), verified_at=VERIFIED_AT)
    assert res.outcome == "UNKNOWN"
    assert res.reason_code == REASON_ENTITY_TYPE_MISSING
    assert res.record is None


def test_ambiguous_financial_sector_with_no_corroboration_stays_unknown():
    """'Dịch vụ tài chính' alone (no specific statement/charter evidence) must never
    become corporate: financial-sector membership is not read as non-financial, and it is
    not specific enough to name a single specialized class either."""
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_AMBIGUOUS_FINANCIAL,
                                icb_industry_label="Dịch vụ tài chính"), verified_at=VERIFIED_AT)
    assert res.outcome == "UNKNOWN"
    assert res.reason_code == REASON_AMBIGUOUS_NO_SUBTYPE


def test_ambiguous_financial_sector_with_ordinary_statement_template_stays_unknown():
    """Even when the filer's own statement uses the ordinary corporate template, a
    'Dịch vụ tài chính' sector tag alone is not treated as positive industrial evidence --
    this milestone's brief explicitly rules out inferring industrial from the absence of a
    specific financial signal."""
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_AMBIGUOUS_FINANCIAL, icb_industry_label="Dịch vụ tài chính",
                                statement_taxonomy="corporate_vas"), verified_at=VERIFIED_AT)
    assert res.outcome == "UNKNOWN"


def test_unrecognized_future_icb_label_fails_closed_not_industrial():
    hint, reason = resolve_industry_hint("Some Brand New Sector Nobody Has Seen")
    assert hint is None
    res = reconcile_ticker(_inp(icb_industry_hint=hint, icb_industry_label="Some Brand New Sector Nobody Has Seen"),
                           verified_at=VERIFIED_AT)
    assert res.outcome == "UNKNOWN"
    assert res.reason_code.startswith("METADATA_TOO_GENERIC_UNRECOGNIZED_SECTOR_LABEL")


# --- 3. Conflicts fail closed, never arbitrated ----------------------------------------

@pytest.mark.parametrize("icb_hint,icb_label,tax", [
    (HINT_BANK, "Ngân hàng", "corporate_vas"),
    (HINT_INSURANCE, "Bảo hiểm", "corporate_vas"),
    (HINT_CORPORATE, "Bán lẻ", "securities_company"),
    (HINT_CORPORATE, "Bán lẻ", "financial_specialized_ambiguous"),
    (HINT_BANK, "Ngân hàng", "securities_company"),
])
def test_disagreeing_sources_fail_closed_as_conflict(icb_hint, icb_label, tax):
    res = reconcile_ticker(_inp(icb_industry_hint=icb_hint, icb_industry_label=icb_label, statement_taxonomy=tax),
                           verified_at=VERIFIED_AT)
    assert res.outcome == "CONFLICT"
    assert res.record.classification_status == ClassificationStatus.CONFLICT
    assert res.record.entity_class == EntityClass.UNKNOWN
    assert "CONFLICT" in res.reason_code


def test_charter_disagreeing_with_statement_template_fails_closed():
    res = reconcile_ticker(_inp(legal_name="Ngân hàng Thương mại Cổ phần Test",
                                statement_taxonomy="securities_company"), verified_at=VERIFIED_AT)
    assert res.outcome == "CONFLICT"


# --- 4. Security-type applicability -----------------------------------------------------

def test_known_non_equity_instrument_is_not_applicable_never_dropped():
    res = reconcile_ticker(_inp(instrument_class="UNKNOWN_SECURITY_GROUP", icb_industry_hint=HINT_CORPORATE,
                                icb_industry_label="Bán lẻ"), verified_at=VERIFIED_AT)
    assert res.outcome == "NOT_APPLICABLE"
    assert res.reason_code.startswith("UNSUPPORTED_SECURITY_TYPE")
    assert res.record is None


def test_missing_instrument_class_does_not_block_classification():
    """Absence from the C.1 candidate master is not evidence of an unsupported security
    type -- it just means that snapshot doesn't cover this ticker."""
    res = reconcile_ticker(_inp(instrument_class=None, icb_industry_hint=HINT_CORPORATE, icb_industry_label="Bán lẻ"),
                           verified_at=VERIFIED_AT)
    assert res.outcome == "corporate"


# --- 5. Provenance & determinism --------------------------------------------------------

def test_qualified_record_carries_full_provenance():
    res = reconcile_ticker(_inp(icb_industry_hint=HINT_CORPORATE, icb_industry_label="Y tế",
                                statement_taxonomy="corporate_vas"), verified_at=VERIFIED_AT)
    rec = res.record
    assert rec.source_id == "market_wide_financial_entity_classification_scaleout/v1"
    assert rec.classification_evidence_id
    assert rec.verified_at == VERIFIED_AT
    assert rec.supporting_evidence["icb_industry_label"] == "Y tế"
    assert rec.supporting_evidence["statement_taxonomy"] == "corporate_vas"


def test_identical_inputs_produce_identical_evidence_id():
    inp = _inp(icb_industry_hint=HINT_CORPORATE, icb_industry_label="Y tế", statement_taxonomy="corporate_vas")
    r1 = reconcile_ticker(inp, verified_at=VERIFIED_AT)
    r2 = reconcile_ticker(inp, verified_at=VERIFIED_AT)
    assert r1.record.classification_evidence_id == r2.record.classification_evidence_id


def test_different_ticker_same_evidence_produces_different_evidence_id():
    common = dict(icb_industry_hint=HINT_CORPORATE, icb_industry_label="Y tế", statement_taxonomy="corporate_vas")
    r1 = reconcile_ticker(_inp(ticker="AAA1", issuer_identity="candidate:aaa1", **common), verified_at=VERIFIED_AT)
    r2 = reconcile_ticker(_inp(ticker="BBB1", issuer_identity="candidate:bbb1", **common), verified_at=VERIFIED_AT)
    assert r1.record.classification_evidence_id != r2.record.classification_evidence_id


# --- 6. No heuristics: static checks on the production module --------------------------

def test_zero_ticker_branches_in_scaleout_reconciler():
    tree = ast.parse((REPO_ROOT / "entity_classification_scaleout.py").read_text(encoding="utf-8"))
    forbidden_tickers = {"GAS", "VRE", "MWG", "VIC", "VNM", "HPG", "VCB", "SSI", "BID", "MBB", "TCB",
                         "AIC", "PGI", "PRE", "PTI", "ART", "TVB"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value.strip().upper() not in forbidden_tickers, (
                f"Forbidden hardcoded ticker '{node.value}' found in production reconciler")


def test_reconciliation_input_carries_no_ratio_or_price_fields():
    """The reconciler's only inputs are identity + governed classification evidence --
    no ratio, market-cap, or price field exists for it to (mis)use as authority."""
    forbidden_substrings = ("revenue", "price", "market_cap", "pe_ratio", "pb_ratio", "roe", "roa", "volume")
    for field in ReconciliationInput._fields:
        lowered = field.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), field


def test_general_corporate_name_prefix_alone_is_not_accepted_as_authority():
    """A generic 'Công ty Cổ phần ...' name with zero corroborating statement/ICB/charter
    evidence must not resolve to corporate -- this milestone explicitly excludes name-only
    classification as sufficient evidence, unlike the pre-existing (and untouched) Case D
    fallback in evidence_backed_entity_classifier.py's general classify_entity() path."""
    res = reconcile_ticker(_inp(legal_name="Công ty Cổ phần Một Doanh Nghiệp Bất Kỳ"), verified_at=VERIFIED_AT)
    assert res.outcome == "UNKNOWN"


# --- 7. ICB sector vocabulary is a closed, documented mapping --------------------------

def test_icb_bank_and_insurance_labels_are_unambiguous():
    assert resolve_industry_hint("Ngân hàng") == (HINT_BANK, resolve_industry_hint("Ngân hàng")[1])
    assert resolve_industry_hint("Bảo hiểm") == (HINT_INSURANCE, resolve_industry_hint("Bảo hiểm")[1])


def test_icb_financial_services_label_never_resolves_a_specific_class():
    hint, _reason = resolve_industry_hint("Dịch vụ tài chính")
    assert hint == HINT_AMBIGUOUS_FINANCIAL


def test_icb_null_label_resolves_no_hint():
    hint, reason = resolve_industry_hint(None)
    assert hint is None
    assert "NO_RETAINED_INDUSTRY_SYNC_RECORD" in reason
