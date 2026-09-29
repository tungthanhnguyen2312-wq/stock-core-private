from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from financial_evidence_currency_contract import (
    COHORT,
    EVF_BLOCKER,
    FINANCIAL_V2_PIN_TICKER_THRESHOLD,
    HTTP_REQUEST_CAP,
    INDEX_DOCUMENT_TYPE,
    MILESTONE_ID,
    core_metrics_for,
    entity_family,
    official_ttm_eligible,
    pin_rebuild_eligible,
)
from financial_evidence_currency_refresh import (
    BoundedHttpBudget,
    OfficialOverlayArtifactError,
    extract_from_retained_pdf,
    financial_v2_pin_decision,
    image_only_disposition,
    load_public_official_citations,
    parse_index_document_links,
    restatement_envelope,
    run_refresh,
)
from official_financial_filing_evidence import METADATA_BLOCKED, METADATA_QUALIFIED, qualify_document_metadata
from official_financial_period_identity import recognize_statement_period, recognize_unit_scale
from official_financial_value_evidence import qualify_value_evidence
from official_legacy_precedence import (
    BOTH_ABSENT,
    EXACT_MATCH,
    LEGACY_ONLY,
    NOT_COMPARABLE,
    OFFICIAL_ONLY,
    TRUE_CONFLICT,
    compare_official_and_legacy,
    official_is_value_qualified,
)
import canonical_daily_financial_v2_materialization as fin_v2_material
import canonical_fact_store as fact_store
from official_source_registry import ADMITTED, admit, load_registry
import official_document_acquisition as acquirer
import current_research_valuation_context as valuation
import financial_v2_current_input_authority as fin_v2

ROOT = Path(__file__).resolve().parents[1]
SHA = "c" * 64


def _span(name: str = "p"):
    return {"citation_id": f"c-{name}", "document_sha256": SHA, "source_page": 1,
            "text": "explicit source text", "citation_kind": "test"}


def _official_meta(**overrides):
    candidate = {
        "issuer_identity": "HPG", "entity_type": "corporate",
        "document": {"document_id": "doc", "sha256": SHA,
                     "source_locator": "https://www.hoaphat.com.vn/fy2025.pdf",
                     "observed_at": "2026-09-29T00:00:00Z", "immutable_bytes_verified": True},
        "metadata": {name: {"value": value, "evidence_span": _span(name)} for name, value in {
            "reporting_period": "2025", "periodicity": "annual", "statement_scope": "consolidated",
            "currency": "VND", "unit_scale": 1,
        }.items()},
    }
    candidate.update(overrides)
    return candidate


def _fact(ticker="HPG", metric="shareholders_equity", period="2025", value=1000, **extra):
    row = {
        "ticker": ticker, "canonical_metric": metric, "reporting_period": period,
        "statement_scope": "consolidated", "statement_family": "balance_sheet",
        "currency": "VND", "unit_scale": 1, "normalized_value": value, "value": value,
        "qualification_state": "QUALIFIED", "document_sha256": SHA,
        "source_locator": "https://www.hoaphat.com.vn/fy2025.pdf",
        "observed_at": "2026-09-29T12:00:00Z", "knowledge_available_at": "2026-09-29T12:00:00Z",
        "raw_value_text": f"{value:,}", "parsed_numeric_value": value,
        "source_span": {"document_sha256": SHA, "text": "equity", "source_page": 1},
        "extraction_mode": "native_text",
    }
    row.update(extra)
    return row


def test_cohort_is_frozen_fourteen_and_evf_has_no_admitted_route(tmp_path: Path):
    assert COHORT == (
        "HPG", "VNM", "FPT", "PNJ", "PAN", "PVD", "NVL",
        "POW", "SSI", "GAS", "VRE", "VCB", "QNS", "EVF",
    )
    assert entity_family("VCB") == "bank"
    assert entity_family("SSI") == "securities"
    assert entity_family("EVF") == "finance_company"
    assert core_metrics_for("EVF") == ()
    report = run_refresh(
        landing_root=tmp_path / "landing", public_root=tmp_path / "public",
        allow_network=False, observed_at="2026-09-29T00:00:00Z",
    )
    assert report["issuers"]["EVF"]["route"]["blocker"] == EVF_BLOCKER
    assert report["http_requests"] == 0


def test_official_metadata_qualification_requires_currency_scale_scope():
    ok = qualify_document_metadata(_official_meta())
    assert ok["qualification_status"] == METADATA_QUALIFIED
    missing = _official_meta()
    missing["metadata"].pop("currency")
    blocked = qualify_document_metadata(missing)
    assert blocked["qualification_status"] == METADATA_BLOCKED
    assert "CURRENCY_MISSING" in blocked["blockers"]


def test_official_value_qualification_digit_for_digit():
    official = {
        "document_sha256": SHA, "issuer_identity": "HPG", "entity_type": "corporate",
        "reporting_period": "2025", "periodicity": "annual", "statement_scope": "consolidated",
        "currency": "VND", "unit_scale": 1, "canonical_metric": "total_assets",
        "raw_label": "Total assets", "raw_value_text": "1,000", "normalized_numeric_value": 1000,
        "source_page": 1, "statement_family": "balance_sheet",
        "extraction_method": "pypdf_native_text",
        "source_span": {"document_sha256": SHA, "citation_id": "c", "source_page": 1, "text": "1,000"},
    }
    provider = {"observation_id": "o", "issuer_identity": "HPG", "canonical_metric": "total_assets",
                "statement_family": "balance_sheet", "reporting_period": "2025-Q4",
                "normalized_numeric_value": 1000, "unit_scale": 1, "provider": "VCI"}
    matched = qualify_value_evidence(official, provider, applicable_entity_types={"corporate"})
    assert matched["reconciliation_status"] == "EXACT_MATCH"
    conflicted = qualify_value_evidence(official, {**provider, "normalized_numeric_value": 999})
    assert conflicted["reconciliation_status"] == "VALUE_MISMATCH"


def test_h1_and_q2_period_identity_and_q3_out_of_scope():
    h1 = recognize_statement_period("Kỳ kế toán 6 tháng kết thúc ngày 30 tháng 6 năm 2026")
    assert h1["period"] == "2026-H1"
    q2 = recognize_statement_period("Báo cáo tài chính quý II năm 2026")
    assert q2["period"] == "2026-Q2"
    annual = recognize_statement_period("năm tài chính kết thúc ngày 31 tháng 12 năm 2025")
    assert annual["period"] == "2025"
    q3 = recognize_statement_period("Báo cáo tài chính quý III năm 2026")
    assert q3["status"] == "OUT_OF_SCOPE_Q3_2026"
    million = recognize_unit_scale("Đơn vị tính: triệu đồng")
    assert million["unit_scale"] == 1_000_000


def test_image_only_fail_closed_without_ocr(tmp_path: Path):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path = tmp_path / "blank.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    extracted = extract_from_retained_pdf(
        {"document_id": "blank", "ticker": "HPG", "sha256": digest,
         "official_url": "https://www.hoaphat.com.vn/blank.pdf",
         "retrieved_at": "2026-09-29T00:00:00Z", "immutable_bytes_verified": True},
        path, allow_ocr=False,
    )
    assert extracted["blocker"] == "IMAGE_ONLY_OCR_NOT_TRIGGERED"
    assert extracted["facts"] == []
    triggered = image_only_disposition(
        text_layer_status="IMAGE_ONLY_OR_SCANNED", ocr_authorized=True, needed_for_core=True,
    )
    assert triggered["status"] == "OCR_AUTHORIZED_BOUNDED"
    assert triggered["ocr_used"] is True


def test_corporate_bank_securities_metric_semantics():
    assert "revenue" in core_metrics_for("HPG")
    assert "net_profit_parent" in core_metrics_for("VCB")
    assert "brokerage_revenue" in core_metrics_for("SSI")
    assert "short_term_interest_bearing_debt" not in core_metrics_for("SSI")
    assert "short_term_interest_bearing_debt" not in core_metrics_for("VCB")


def _legacy(**overrides):
    row = {"canonical_metric": "shareholders_equity", "reporting_period": "2025-Q4",
           "statement_family": "balance_sheet", "statement_scope": "consolidated",
           "normalized_value": 1000, "already_normalized": True}
    row.update(overrides)
    return row


def test_exact_match_true_conflict_period_and_scope():
    official = _fact()
    legacy = _legacy()
    matched = compare_official_and_legacy(official, legacy)
    assert matched["status"] == EXACT_MATCH
    assert matched["official_becomes_factual_authority"] is True
    assert matched["legacy_relabelled_official"] is False
    conflicted = compare_official_and_legacy(official, {**legacy, "normalized_value": 999})
    assert conflicted["status"] == TRUE_CONFLICT
    assert conflicted["official_becomes_factual_authority"] is False
    period = compare_official_and_legacy(official, {**legacy, "reporting_period": "2024-Q4"})
    assert period["status"] == NOT_COMPARABLE
    assert period["reason"] == "PERIOD_DIFFERENCE"
    assert period["official_becomes_factual_authority"] is False
    scope = compare_official_and_legacy(official, {**legacy, "statement_scope": "standalone"})
    assert scope["status"] == NOT_COMPARABLE
    assert scope["reason"] == "SCOPE_DIFFERENCE"
    assert scope["official_becomes_factual_authority"] is False
    metric = compare_official_and_legacy(official, {**legacy, "canonical_metric": "total_equity"})
    assert metric["status"] == NOT_COMPARABLE
    assert metric["reason"] == "METRIC_DIFFERENCE"
    assert metric["official_becomes_factual_authority"] is False
    missing = compare_official_and_legacy(None, legacy)
    assert missing["status"] == LEGACY_ONLY
    assert missing["reason"] == "MISSING_OFFICIAL_NOT_NEGATIVE_EVIDENCE"
    assert missing["legacy_deleted"] is False
    assert missing["legacy_relabelled_official"] is False


def test_both_absent_is_fail_closed_and_not_legacy_proxy():
    result = compare_official_and_legacy(None, None)
    assert result["status"] == BOTH_ABSENT
    assert result["reason"] == "BOTH_ABSENT"
    assert result["allowed_uses"] == ()
    assert result["official_becomes_factual_authority"] is False
    assert result["legacy_relabelled_official"] is False
    assert result["legacy_deleted"] is False


def test_metadata_qualification_is_not_value_level_authority():
    metadata_only = _fact(qualification_state=METADATA_QUALIFIED, qualification_status=METADATA_QUALIFIED)
    assert official_is_value_qualified(metadata_only) is False
    official_only = compare_official_and_legacy(metadata_only, None)
    assert official_only["status"] == OFFICIAL_ONLY
    assert official_only["official_becomes_factual_authority"] is False
    assert official_only["allowed_uses"] == ()
    matched = compare_official_and_legacy(metadata_only, _legacy())
    assert matched["status"] == EXACT_MATCH
    assert matched["official_becomes_factual_authority"] is False
    assert matched["legacy_relabelled_official"] is False
    assert matched["allowed_uses"] == ("CURRENT_RESEARCH_PROXY_ONLY",)


def test_value_qualified_official_only_and_exact_match_promote_authority():
    official = _fact()
    assert official_is_value_qualified(official) is True
    official_only = compare_official_and_legacy(official, None)
    assert official_only["status"] == OFFICIAL_ONLY
    assert official_only["official_becomes_factual_authority"] is True
    assert official_only["allowed_uses"] == (
        "CURRENT_RESEARCH_FACTUAL_AUTHORITY",
        "VALUATION_INPUT_WHERE_METRIC_PERMITS",
    )
    matched = compare_official_and_legacy(official, _legacy())
    assert matched["status"] == EXACT_MATCH
    assert matched["official_becomes_factual_authority"] is True
    assert matched["legacy_relabelled_official"] is False
    assert matched["legacy_deleted"] is False


def test_restatement_append_only_forbids_backdating():
    original = {"document_sha256": "a" * 64, "observed_at": "2026-03-31T00:00:00Z",
                "knowledge_available_at": "2026-03-31T00:00:00Z"}
    amendment = {"document_sha256": "b" * 64, "observed_at": "2026-09-01T00:00:00Z",
                 "knowledge_available_at": "2026-09-01T00:00:00Z"}
    ok = restatement_envelope(original=original, amendment=amendment)
    assert ok["accepted"] is True
    assert ok["append_only"] is True
    backdated = restatement_envelope(
        original=original,
        amendment={**amendment, "observed_at": "2026-01-01T00:00:00Z",
                   "knowledge_available_at": "2026-01-01T00:00:00Z"},
    )
    assert backdated["accepted"] is False
    assert backdated["blocker"] == "AMENDMENT_BACKDATING_FORBIDDEN"


def test_financial_v2_pin_threshold_does_not_bump_current_pin():
    assert pin_rebuild_eligible(tickers_with_new_qualified_core=4, unresolved_schema_ambiguity=False) is False
    assert pin_rebuild_eligible(tickers_with_new_qualified_core=5, unresolved_schema_ambiguity=True) is False
    eligible = pin_rebuild_eligible(tickers_with_new_qualified_core=5, unresolved_schema_ambiguity=False)
    assert eligible is True
    decision = financial_v2_pin_decision(tickers_with_new_qualified_core=5, unresolved_schema_ambiguity=False)
    assert decision["rebuild_performed"] is False
    assert decision["current_authority_version"] == fin_v2.AUTHORITY_VERSION == "2026-09-05.1"
    assert decision["new_authority_version"] is None
    assert FINANCIAL_V2_PIN_TICKER_THRESHOLD == 5


def test_ttm_not_promoted_from_fy_plus_h1():
    assert official_ttm_eligible(["2025", "2026-H1"]) is False
    assert official_ttm_eligible(["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]) is True
    assert official_ttm_eligible(["2026-Q1", "2026-Q2"]) is False


def test_run_refresh_integrates_injected_facts_and_writes_public_overlay(tmp_path: Path):
    facts = [
        _fact("HPG", "shareholders_equity", "2025", 10),
        _fact("VNM", "net_income", "2025", 20, statement_family="income_statement"),
        _fact("FPT", "total_assets", "2025", 30),
        _fact("PNJ", "revenue", "2026-H1", 40, statement_family="income_statement"),
        _fact("QNS", "operating_cash_flow", "2025", 50, statement_family="cash_flow"),
    ]
    legacy = {
        ("HPG", "shareholders_equity", "2025", "consolidated"): {
            "canonical_metric": "shareholders_equity", "reporting_period": "2025-Q4",
            "statement_family": "balance_sheet", "statement_scope": "consolidated",
            "normalized_value": 10, "already_normalized": True,
        }
    }
    report = run_refresh(
        landing_root=tmp_path / "landing", public_root=tmp_path / "derived/financial-evidence-currency-refresh-v1",
        allow_network=False, extracted_facts=facts, legacy_facts=legacy,
        observed_at="2026-09-29T00:00:00Z",
    )
    assert report["new_qualified_core_fact_count"] == 5
    assert report["tickers_with_ge1_new_qualified_core_fact"] == ["FPT", "HPG", "PNJ", "QNS", "VNM"]
    assert report["official_pe_ttm_gain"] == []
    assert report["official_ps_ttm_gain"] == []
    assert report["official_ttm_eligible"] is False
    assert report["financial_v2_pin"]["rebuild_performed"] is False
    assert report["vnstock_runtime"] is False
    assert report["raw_filings_committed"] is False
    assert report["conflicts"]["EXACT_MATCH"] == 1
    written = (tmp_path / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl").read_text(
        encoding="utf-8",
    )
    assert "HPG" in written
    assert report["implementation_success_gate"] == "A_FIVE_TICKERS_QUALIFIED"


def test_http_budget_stops_at_cap():
    budget = BoundedHttpBudget(cap=2, storage_budget=100)
    assert budget.can_request()
    budget.record_request()
    budget.record_request()
    assert budget.can_request() is False
    assert budget.stopped_reason == "HTTP_REQUEST_CAP_REACHED"
    assert HTTP_REQUEST_CAP == 40


def test_index_parser_keeps_target_periods_and_drops_q3():
    html = """
    <a href="/files/BCTC-hop-nhat-nam-2025-kiem-toan.pdf">FY2025</a>
    <a href="/files/BCTC-6-thang-2026-soat-xet.pdf">H1</a>
    <a href="/files/BCTC-quy-3-2026.pdf">Q3</a>
    <a href="/files/unrelated.html">no</a>
    """
    links = parse_index_document_links(html, "https://www.hoaphat.com.vn/")
    periods = {row["period"] for row in links}
    assert "2025" in periods
    assert "2026-H1" in periods
    assert "2026-Q3" not in periods


def test_issuer_ir_index_page_is_admitted_on_existing_host():
    registry = load_registry()
    decision = admit(
        "issuer_ir", "https://www.hoaphat.com.vn/quan-he-co-dong/bao-cao-tai-chinh",
        INDEX_DOCUMENT_TYPE, registry=registry, seconds_since_last_request=30,
    )
    assert decision["decision"] == ADMITTED
    gas = admit(
        "issuer_ir", "https://www.pvgas.com.vn/quan-he-co-dong",
        "reviewed_interim_financial_statements", registry=registry, seconds_since_last_request=30,
    )
    assert gas["decision"] == ADMITTED
    assert "2026-H1" in acquirer.PERIODS
    assert "2026-Q2" in acquirer.PERIODS
    assert "EVF" not in acquirer.TICKERS


def _pb_official(official_facts, *, period="2025-Q4", value=1_000_000):
    from tests.test_current_research_book_value_valuation import _cap, _equity
    verdict = __import__("provider_financial_monetary_basis_verdict").resolve(ROOT)
    return valuation._book_value_method(
        ticker="AAA", entity="corporate", share_class="CURRENT_SHARE_RESEARCH_PROXY",
        market_cap=_cap(), equity_rows=[_equity(period=period, value=value)],
        decision_session="2026-09-24", verdict=verdict, official_equity_facts=official_facts,
    )


def test_official_equity_supersedes_matching_vci_and_conflicts_fail_closed():
    matched = _pb_official([_fact("AAA", "shareholders_equity", "2025", 1_000_000)])
    assert matched["status"] == "RESEARCH_USABLE"
    assert matched["formula"] == "research_usable_market_cap / official_total_owners_equity"
    assert matched["official_becomes_factual_authority"] is True
    conflicted = _pb_official([_fact("AAA", "shareholders_equity", "2025", 2_000_000)])
    assert conflicted["status"] == "INPUT_BLOCKED"
    assert "OFFICIAL_LEGACY_TRUE_CONFLICT" in conflicted["blocker_reason_codes"]


def test_pb_same_period_does_not_authorize_official_on_scope_or_metric_difference():
    baseline = _pb_official([])
    different_scope = _pb_official([
        _fact("AAA", "shareholders_equity", "2025", 9_000_000, statement_scope="standalone"),
    ])
    assert different_scope["status"] == "RESEARCH_USABLE"
    assert different_scope["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    assert abs(different_scope["value"] - baseline["value"]) < 1e-12
    different_metric = _pb_official([
        _fact("AAA", "total_equity", "2025", 9_000_000),
    ])
    assert different_metric["status"] == "RESEARCH_USABLE"
    assert different_metric["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    assert different_metric["official_legacy_precedence"] == NOT_COMPARABLE
    assert different_metric["official_becomes_factual_authority"] is False
    assert abs(different_metric["value"] - baseline["value"]) < 1e-12
    different_period = _pb_official([
        _fact("AAA", "shareholders_equity", "2024", 9_000_000),
    ])
    assert different_period["status"] == "RESEARCH_USABLE"
    assert different_period["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    assert different_period["official_legacy_precedence"] == NOT_COMPARABLE
    exact = _pb_official([_fact("AAA", "shareholders_equity", "2025", 1_000_000)])
    assert exact["formula"] == "research_usable_market_cap / official_total_owners_equity"
    conflicted = _pb_official([_fact("AAA", "shareholders_equity", "2025", 2_000_000)])
    assert conflicted["status"] == "INPUT_BLOCKED"


def test_official_equity_missing_scope_is_not_treated_as_consolidated():
    missing_scope = _fact("AAA", "shareholders_equity", "2025", 9_000_000, statement_scope=None)
    assert official_is_value_qualified(missing_scope) is False
    assert valuation._official_equity_row([missing_scope], "AAA") is None
    method = _pb_official([missing_scope])
    assert method["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    assert "official_legacy_precedence" not in method


def test_missing_official_does_not_change_legacy_pb():
    from tests.test_current_research_book_value_valuation import _pb
    baseline = _pb()
    unchanged = valuation._book_value_method(
        ticker="AAA", entity="corporate", share_class="CURRENT_SHARE_RESEARCH_PROXY",
        market_cap=baseline["market_cap"] if False else __import__(
            "tests.test_current_research_book_value_valuation", fromlist=["_cap"]
        )._cap(),
        equity_rows=[__import__("tests.test_current_research_book_value_valuation", fromlist=["_equity"])._equity()],
        decision_session="2026-09-24",
        verdict=__import__("provider_financial_monetary_basis_verdict").resolve(ROOT),
        official_equity_facts=[],
    )
    assert unchanged["status"] == baseline["status"]
    assert abs(unchanged["value"] - baseline["value"]) < 1e-12


def test_no_vnstock_vnai_in_refresh_modules():
    for module in (
        "financial_evidence_currency_refresh",
        "official_legacy_precedence",
        "official_financial_period_identity",
        "financial_evidence_currency_contract",
    ):
        source = inspect.getsource(__import__(module))
        assert "import vnstock" not in source
        assert "import vnai" not in source


def test_roadmap_current_milestone_is_the_authorized_ocr_continuation():
    state = json.loads((ROOT / "docs" / "ROADMAP_STATE.json").read_text(encoding="utf-8"))
    assert state["current"]["milestone"] == "FINANCIAL_EVIDENCE_COHORT1_TRIGGERED_OCR_V1"
    assert state["current"]["state"] == "PARTIAL"
    assert state["queued_next"] == []
    ids = [row["milestone_id"] for row in state["milestones"]]
    assert MILESTONE_ID in ids
    assert "FINANCIAL_EVIDENCE_COHORT1_TRIGGERED_OCR_V1" in ids
    assert "FINANCIAL_EVIDENCE_ZERO_ACTIVE_VNSTOCK_V1" in ids


def test_no_raw_pdf_is_tracked_in_public_artifact_dir():
    public = ROOT / "derived" / "financial-evidence-currency-refresh-v1"
    if not public.exists():
        return
    for path in public.rglob("*"):
        assert path.suffix.lower() not in {".pdf", ".xlsx", ".xls", ".png", ".jpg"}


def test_malformed_present_overlay_fails_closed_and_missing_overlay_is_empty(tmp_path: Path):
    overlay_dir = tmp_path / "derived" / "financial-evidence-currency-refresh-v1"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "qualified_official_facts.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(OfficialOverlayArtifactError, match="OFFICIAL_OVERLAY_MALFORMED_JSON"):
        load_public_official_citations(tmp_path)
    with pytest.raises(OfficialOverlayArtifactError, match="OFFICIAL_OVERLAY_MALFORMED_JSON"):
        fact_store.load_official_citations(tmp_path)
    with pytest.raises(fin_v2_material.CanonicalFinancialV2MaterializationError, match="OFFICIAL_OVERLAY_MALFORMED"):
        fin_v2_material._official_equity_overlay(tmp_path)
    identity = overlay_dir / "qualified_official_facts.jsonl"
    identity.write_text(
        json.dumps({"qualification_state": "QUALIFIED", "value": 1}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(OfficialOverlayArtifactError, match="OFFICIAL_OVERLAY_IDENTITY_CORRUPT"):
        load_public_official_citations(tmp_path)
    missing = load_public_official_citations(tmp_path / "absent-root")
    assert missing == {}
    empty_root = tmp_path / "empty-overlay"
    (empty_root / "derived" / "financial-evidence-currency-refresh-v1").mkdir(parents=True)
    (empty_root / "derived" / "financial-evidence-currency-refresh-v1" / "qualified_official_facts.jsonl").write_text(
        "", encoding="utf-8",
    )
    assert load_public_official_citations(empty_root) == {}
    assert fact_store.load_official_citations(empty_root) == {}


def test_evaluated_valuation_keeps_daily_with_explicit_malformed_overlay_state(monkeypatch):
    def boom(_root):
        raise fin_v2_material.CanonicalFinancialV2MaterializationError("OFFICIAL_OVERLAY_MALFORMED:test")
    monkeypatch.setattr(fin_v2_material, "_official_equity_overlay", boom)
    engine = {"artifact_identity": "financial_analysis_context/v2:test", "records": {"AAA": {}}}
    valuation_artifact = fin_v2_material.build_evaluated_valuation_artifact(
        engine_artifact=engine, raw_valuation_artifact=None,
        product_tickers=["AAA"], requested_at="2026-09-29T15:00:00+07:00",
    )
    assert valuation_artifact["official_overlay_eligibility"] == "OFFICIAL_OVERLAY_MALFORMED_INELIGIBLE"
    assert "AAA" in valuation_artifact["records"]
