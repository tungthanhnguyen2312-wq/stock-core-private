"""Hermetic contract tests for reviewed-interim official fact ingress (synthetic fixtures only)."""
from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import pytest

import official_financial_assurance_evidence as assurance_module
import reviewed_interim_canonical_ingress as ingress_module
from canonical_fact_store import load_official_citations
from financial_evidence_currency_contract import PUBLIC_ARTIFACT_DIR, official_ttm_eligible
from financial_evidence_currency_refresh import (
    PUBLIC_FACTS, financial_v2_pin_decision, load_public_official_citations, load_public_official_fact_rows,
)
from official_financial_assurance_evidence import (
    resolve_document_assurance_evidence, validate_assurance_claim,
)
from official_financial_ocr_table_evidence import panel_facts_from_qualified_ocr
from official_legacy_precedence import (
    EXACT_MATCH, NOT_COMPARABLE, TRUE_CONFLICT, official_is_value_qualified,
)
from reviewed_interim_canonical_ingress import authority_projection, overlay_rows_from_panel_facts, precedence_row

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
OBSERVED = "2026-09-29T11:31:14.408633Z"
REVIEW_PAGE = (
    "BÁO CÁO SOÁT XÉT THÔNG TIN TÀI CHÍNH HỢP NHẤT GIỮA NIÊN ĐỘ Chúng tôi đã soát xét báo cáo tài chính hợp nhất "
    "giữa niên độ kèm theo. Chuẩn mực Việt Nam về hợp đồng dịch vụ soát xét số 2410. Chúng tôi không đưa ra ý kiến kiểm toán."
)
AUDIT_PAGE = ("BÁO CÁO KIỂM TOÁN ĐỘC LẬP Chúng tôi đã kiểm toán báo cáo tài chính hợp nhất kèm theo. "
              "Ý kiến kiểm toán của chúng tôi là ngoại trừ.")


def _materialization(*page_texts: str, sha: str = SHA) -> dict:
    pages = []
    for number, text in enumerate(page_texts, start=1):
        tokens = [{"text": word, "token_id": f"t{number}-{index}", "raw_token_order": index, "top": 1.0, "bottom": 2.0}
                  for index, word in enumerate(text.split())]
        pages.append({"page_number": number, "source_image_evidence": {"rendered_image_sha256": f"img{number}"},
                      "ocr_derived_text_evidence": {"tokens": tokens}})
    return {"document_sha256": sha, "materialization_id": "m1", "pages": pages}


def _qualification(period: str = "2026-H1", *, currency: str = "VND", metric: str = "revenue", value: int = 1_000_000_000) -> dict:
    lineage = {"line_code": "10", "source_page": 8, "row_object": {"row": 1},
               "source_image_evidence": {"document_sha256": SHA, "rendered_image_sha256": "img"},
               "ocr_derived_text_evidence": {"materialization_id": "m1"}, "unit_evidence": {"unit_scale": 1_000_000}}
    return {"ticker": "PNJ", "document_sha256": SHA, "reporting_period": period, "qualified_facts": [{
        "canonical_metric": metric, "value": value, "currency": currency, "unit_scale": 1_000_000,
        "statement_family": "income_statement", "qualification_state": "QUALIFIED",
        "reason_codes": ["OFFICIAL_EVIDENCE_QUALIFIED"], "source_lineage": lineage}]}


def _reviewed_evidence() -> dict:
    return resolve_document_assurance_evidence(_materialization(REVIEW_PAGE))


def _facts(period: str = "2026-H1", status: str = "reviewed", evidence=None, **kwargs) -> list[dict]:
    return panel_facts_from_qualified_ocr(
        _qualification(period, **{k: v for k, v in kwargs.items() if k in {"currency", "metric", "value"}}),
        entity_type="corporate", statement_scope=kwargs.get("scope", "consolidated"),
        audit_or_review_status=status, assurance_evidence=evidence,
        knowledge_available_at=kwargs.get("knowledge", OBSERVED), observed_at=OBSERVED)


def _rows() -> list[dict]:
    rows, blocked = overlay_rows_from_panel_facts(_facts(evidence=_reviewed_evidence()))
    assert not blocked
    return rows


@pytest.mark.parametrize('change', [{}, {'currency':'USD'}, {'source_lineage':{'line_code':'31'}}])
def test_disposal_component_ingress_requires_exact_identity(change):
    fact = _facts(metric='investment_property_disposal_result',evidence=_reviewed_evidence())[0]
    fact['source_lineage']['line_code']='21'
    fact['source_lineage']['row_object']['reconstructed_label']='thanh ly bat dong san dau tu'
    fact.update(change)
    rows,blocked = overlay_rows_from_panel_facts([fact])
    if change:
        assert not rows and 'EARNINGS_COMPONENT_IDENTITY_NOT_QUALIFIED' in blocked[0]['reasons']
    else:
        assert ingress_module.earnings_component_is_admitted(rows[0])
        assert precedence_row(rows[0],None)['status']=='NOT_COMPARABLE'


def test_audited_annual_still_accepted():
    facts = _facts("2025", "audited", knowledge="2026-08-09T00:00:00Z")
    assert facts[0]["period_type"] == "annual" and facts[0]["audit_or_review_status"] == "audited"
    assert (facts[0]["period_start"], facts[0]["period_end"]) == ("2025-01-01", "2025-12-31")


def test_reviewed_interim_accepted_when_explicitly_evidenced():
    evidence = _reviewed_evidence()
    assert evidence["state"] == "QUALIFIED" and evidence["audit_or_review_status"] == "reviewed"
    fact = _facts(evidence=evidence)[0]
    assert fact["audit_or_review_status"] == "reviewed"
    assert fact["source_lineage"]["assurance_evidence"]["evidence_id"] == evidence["evidence_id"]


@pytest.mark.parametrize("status", ["unknown", "unaudited", "management-prepared", "", None, "Reviewed"])
def test_unsupported_assurance_status_blocked(status):
    with pytest.raises(ValueError, match="OCR_DOCUMENT_METADATA_NOT_QUALIFIED"):
        _facts(status=status, evidence=_reviewed_evidence())


def test_caller_supplied_reviewed_without_evidence_or_with_wrong_evidence_blocked():
    with pytest.raises(ValueError, match="REVIEWED_STATUS_REQUIRES_RETAINED_DOCUMENT_EVIDENCE"):
        _facts()
    other = resolve_document_assurance_evidence(_materialization(REVIEW_PAGE, sha="b" * 64))
    with pytest.raises(ValueError, match="ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS"):
        _facts(evidence=other)
    with pytest.raises(ValueError, match="ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS"):
        validate_assurance_claim("audited", _reviewed_evidence(), document_sha256=SHA)
    with pytest.raises(ValueError, match="ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS"):
        validate_assurance_claim("reviewed", {"state": "QUALIFIED", "audit_or_review_status": "reviewed",
                                              "document_sha256": SHA}, document_sha256=SHA)


def test_reviewed_annual_period_and_standalone_scope_blocked():
    with pytest.raises(ValueError, match="OCR_DOCUMENT_METADATA_NOT_QUALIFIED"):
        _facts(evidence=_reviewed_evidence(), scope="standalone")
    with pytest.raises(ValueError, match="REVIEWED_STATUS_REQUIRES_INTERIM_PERIOD"):
        _facts("2025", evidence=_reviewed_evidence())


def test_assurance_recognizer_needs_report_title_engagement_scope_and_interim_wording():
    assert resolve_document_assurance_evidence(_materialization("Báo cáo tài chính hợp nhất giữa niên độ đã được soát xét"))["state"] == "BLOCKED"
    assert resolve_document_assurance_evidence(_materialization("BÁO CÁO SOÁT XÉT hợp nhất giữa niên độ"))["state"] == "BLOCKED"
    assert resolve_document_assurance_evidence(_materialization("BÁO CÁO SOÁT XÉT hợp đồng dịch vụ soát xét giữa niên độ"))["state"] == "BLOCKED"
    audited = resolve_document_assurance_evidence(_materialization(AUDIT_PAGE))
    assert audited["audit_or_review_status"] == "audited"
    ambiguous = resolve_document_assurance_evidence(_materialization(REVIEW_PAGE, AUDIT_PAGE))
    assert ambiguous["state"] == "BLOCKED" and ambiguous["reason"] == "ASSURANCE_STATUS_AMBIGUOUS"


def test_reviewed_is_never_relabelled_audited():
    fact = _facts(evidence=_reviewed_evidence())[0]
    assert fact["audit_or_review_status"] == "reviewed"
    assert all(row["audit_or_review_status"] == "reviewed" for row in _rows())


def test_h1_period_preserved_and_duration():
    fact = _facts(evidence=_reviewed_evidence())[0]
    assert (fact["reporting_period"], fact["period_type"], fact["temporal_nature"]) == ("2026-H1", "interim", "duration")
    assert (fact["period_start"], fact["period_end"]) == ("2026-01-01", "2026-06-30")


def test_h1_revenue_has_no_q2_or_annual_alias(tmp_path):
    directory = tmp_path / PUBLIC_ARTIFACT_DIR
    directory.mkdir(parents=True)
    (directory / PUBLIC_FACTS).write_text("".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8")
    for citations in (load_public_official_citations(tmp_path), load_official_citations(tmp_path)):
        assert {key for key in citations if key[1] == "revenue"} == {("PNJ", "revenue", "2026-H1")}
    citation = load_public_official_citations(tmp_path)[("PNJ", "revenue", "2026-H1")]
    assert citation["value"] == 1_000_000_000 and citation["scale"] == 1  # no second rescale of VRE-style scaled values


def test_overlay_row_is_value_qualified_and_reviewed_factual_authority():
    row = _rows()[0]
    assert official_is_value_qualified(row) and row["qualification_state"] == "QUALIFIED"
    assert authority_projection(row)["factual_status"] == "qualified"


def test_reviewed_h1_fact_remains_research_partial_not_annual():
    projection = authority_projection(_rows()[0])
    assert projection["factual_status"] == "qualified" and projection["research_status"] == "partial"
    assert projection["research_reason_codes"] == ["RESEARCH_PERIOD_NOT_ANNUAL"]
    assert projection["factual_reason_codes"] == []


def test_usd_is_context_only_and_excluded_from_vnd_citations(tmp_path):
    rows, blocked = overlay_rows_from_panel_facts(_facts(evidence=_reviewed_evidence(), currency="USD"))
    assert not blocked and rows[0]['currency'] == 'USD'
    assert rows[0]['projection_currency_policy'] == 'SOURCE_CURRENCY_CONTEXT_ONLY'
    assert authority_projection(rows[0])['factual_status'] == 'qualified'
    precedence = precedence_row(rows[0],{'currency':'VND','normalized_value':rows[0]['normalized_value']})
    assert precedence['status']=='NOT_COMPARABLE' and precedence['official_factual_status']=='qualified'
    assert precedence['legacy_modified'] is False
    assert precedence['allowed_uses']==['EXACT_FIELD_CURRENT_RESEARCH_CONTEXT']
    directory = tmp_path / PUBLIC_ARTIFACT_DIR
    directory.mkdir(parents=True)
    (directory / PUBLIC_FACTS).write_text(json.dumps(rows[0])+'\n',encoding='utf-8')
    assert load_public_official_fact_rows(tmp_path) == rows
    assert load_public_official_citations(tmp_path) == {}
    assert load_official_citations(tmp_path) == {}


def test_unknown_currency_and_foreign_stock_metrics_stay_blocked():
    rows, blocked = overlay_rows_from_panel_facts(_facts(evidence=_reviewed_evidence(), currency="EUR"))
    assert not rows and 'CURRENCY_NOT_ADMITTED_FOR_CONTEXT' in blocked[0]['reasons']
    rows, blocked = overlay_rows_from_panel_facts(_facts(evidence=_reviewed_evidence(), currency="USD",metric='total_assets'))
    assert not rows and 'FOREIGN_CURRENCY_METRIC_NOT_ADMITTED' in blocked[0]['reasons']


def test_financial_v2_pin_is_not_bumped_by_three_or_four_tickers():
    for count in (2, 3, 4):
        decision = financial_v2_pin_decision(tickers_with_new_qualified_core=count, unresolved_schema_ambiguity=False)
        assert decision["decision"] == "KEEP_CURRENT_PIN" and decision["current_authority_version"] == "2026-09-05.1"
        assert decision["rebuild_performed"] is False and decision["new_authority_version"] is None


def test_no_ttm_from_h1_only_for_pe_or_ps():
    assert official_ttm_eligible(["2026-H1"]) is False
    assert official_ttm_eligible(["2025", "2026-H1"]) is False
    assert official_ttm_eligible(["2026-Q1", "2026-Q2"]) is False


def _legacy(period="2026-H1", value=1_000_000_000, scale=1):
    return {"canonical_metric": "revenue", "reporting_period": period, "statement_scope": "consolidated",
            "statement_family": "income_statement", "value": value, "unit_scale": scale}


def test_precedence_exact_match_true_conflict_and_period_mismatch():
    row = _rows()[0]
    assert precedence_row(row, _legacy())["status"] == EXACT_MATCH
    conflict = precedence_row(row, _legacy(value=999))
    assert conflict["status"] == TRUE_CONFLICT and conflict["official_becomes_factual_authority"] is False
    mismatch = precedence_row(row, _legacy(period="2026-Q2"))
    assert mismatch["status"] == NOT_COMPARABLE and mismatch["reason"] == "PERIOD_DIFFERENCE"
    assert precedence_row(row, None)["status"] == "OFFICIAL_ONLY"


def test_knowledge_time_cannot_be_backdated_to_period_end():
    for stamp in ("2026-06-30T00:00:00Z", "2026-05-01T00:00:00Z", ""):
        with pytest.raises(ValueError, match="KNOWLEDGE_TIME_NOT_AFTER_PERIOD_END"):
            _facts(evidence=_reviewed_evidence(), knowledge=stamp)
    assert _rows()[0]["knowledge_available_at"] == OBSERVED


def test_raw_documents_are_not_tracked_and_overlay_is_public_safe():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for sha in ("db877169e7c19b4b81d60b37d5aab8f9938129a66b582c2229ffffebdca2a43d",
                "a7360d2fc9a8a67a1535820813cda2bb8ef288466cd36c949e050c2f2a1b290a",
                "7e9b9e39901a028972fff80bc1a4f9f5cab4c1526ce4029f9b853ccff6aeaac0",
                "9a2881a88ac8ca4cc5cd948b0fafa031ff30fd0332a372f362477a8a6b0c9968"):
        assert sha not in tracked
    row = _rows()[0]
    assert "tokens" not in json.dumps(row) and "page_text" not in row["assurance_evidence"]


def test_new_modules_stay_zero_active_vnstock():
    for module in (assurance_module, ingress_module):
        source = inspect.getsource(module).lower()
        assert "import vnstock" not in source and "from vnstock" not in source


def test_overlay_loader_accepts_rows_and_keeps_missing_overlay_empty(tmp_path):
    assert load_public_official_fact_rows(tmp_path) == []
    directory = tmp_path / PUBLIC_ARTIFACT_DIR
    directory.mkdir(parents=True)
    (directory / PUBLIC_FACTS).write_text("".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8")
    loaded = load_public_official_fact_rows(tmp_path)
    assert [row["audit_or_review_status"] for row in loaded] == ["reviewed"]


# ---- net_income vs attributable_net_income identity corrective --------------------------------
from canonical_financial_facts import METRIC_REGISTRY  # noqa: E402
import financial_evidence_currency_contract as currency_contract  # noqa: E402
from official_financial_ocr_table_evidence import STANDARD_FACT_RULES, row_label_supports_metric  # noqa: E402

LINE60_LABEL = "Lợi nhuận sau thuế thu nhập doanh nghiệp"
LINE61_LABEL = "Lợi nhuận sau thuế của công ty mẹ"


def test_line_60_maps_to_total_net_income_and_line_61_to_attributable():
    rules = {code: metric for metric, family, code in STANDARD_FACT_RULES if family == "income_statement" and code in {"60", "61"}}
    assert rules == {"60": "net_income", "61": "attributable_net_income"}
    assert "net_income" in METRIC_REGISTRY and "attributable_net_income" in METRIC_REGISTRY
    assert METRIC_REGISTRY["net_income"] is not METRIC_REGISTRY["attributable_net_income"]


def test_explicit_row_label_is_required_for_each_identity():
    assert row_label_supports_metric("net_income", LINE60_LABEL)
    assert not row_label_supports_metric("net_income", LINE61_LABEL)
    assert row_label_supports_metric("attributable_net_income", LINE61_LABEL)
    assert not row_label_supports_metric("attributable_net_income", LINE60_LABEL)
    assert not row_label_supports_metric("attributable_net_income", "")
    assert not row_label_supports_metric("attributable_net_income", "Lợi nhuận sau thuế của cổ đông không kiểm soát")
    assert not row_label_supports_metric("net_income", "")


def _line_fact(metric: str, code: str) -> list[dict]:
    qualification = _qualification(metric=metric)
    qualification["qualified_facts"][0]["source_lineage"]["line_code"] = code
    return panel_facts_from_qualified_ocr(
        qualification, entity_type="corporate", statement_scope="consolidated", audit_or_review_status="reviewed",
        assurance_evidence=_reviewed_evidence(), knowledge_available_at=OBSERVED, observed_at=OBSERVED)


def test_line_61_can_never_emit_net_income_into_the_overlay():
    rows, blocked = overlay_rows_from_panel_facts(_line_fact("net_income", "61"))
    assert rows == [] and blocked[0]["reasons"] == ["METRIC_LINE_CODE_IDENTITY_CONFLICT"]
    rows, blocked = overlay_rows_from_panel_facts(_line_fact("attributable_net_income", "60"))
    assert rows == [] and blocked[0]["reasons"] == ["METRIC_LINE_CODE_IDENTITY_CONFLICT"]
    for metric, code in (("net_income", "60"), ("attributable_net_income", "61")):
        rows, blocked = overlay_rows_from_panel_facts(_line_fact(metric, code))
        assert len(rows) == 1 and not blocked


def test_net_income_and_attributable_are_distinct_keys_and_metric_difference_in_precedence():
    rows, _ = overlay_rows_from_panel_facts(_line_fact("attributable_net_income", "61"))
    legacy = {"canonical_metric": "net_income", "reporting_period": "2026-H1", "statement_scope": "consolidated",
              "statement_family": "income_statement", "value": rows[0]["normalized_value"], "unit_scale": 1}
    result = precedence_row(rows[0], legacy)
    assert result["status"] == NOT_COMPARABLE and result["reason"] == "METRIC_DIFFERENCE"
    assert result["official_becomes_factual_authority"] is False
    assert authority_projection(rows[0])["research_reason_codes"] == ["RESEARCH_PERIOD_NOT_ANNUAL"]


def test_current_overlay_has_no_net_income_sourced_from_line_61():
    path = ROOT / PUBLIC_ARTIFACT_DIR / PUBLIC_FACTS
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all((row["canonical_metric"], str(row.get("line_code"))) not in ingress_module.LINE_CODE_IDENTITY_CONFLICTS for row in rows)
    assert all(row["period_type"] == "interim" and row["audit_or_review_status"] == "reviewed" for row in rows)


def test_core_metric_vocabulary_has_no_orphans():
    assert set(currency_contract.CORPORATE_CORE_METRICS) <= set(METRIC_REGISTRY)
    # Specialist (bank/securities) ids are a separate, explicitly enumerated vocabulary, not corporate aliases.
    specialist = {"net_profit_parent", "total_equity", "customer_loans_net", "customer_deposits", "provision_for_credit_losses",
                  "brokerage_revenue", "total_operating_revenue"}
    orphans = (set(currency_contract.BANK_CORE_METRICS) | set(currency_contract.SECURITIES_CORE_METRICS)) - set(METRIC_REGISTRY)
    assert orphans == specialist
