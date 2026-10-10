"""Auditor-page continuation and subset refresh preserve authority boundaries."""
import copy
import json
from pathlib import Path
import pytest
from tests.test_reviewed_interim_canonical_ingress import _materialization, REVIEW_PAGE
from official_financial_assurance_evidence import resolve_document_assurance_evidence, validate_assurance_claim
from tools.run_reviewed_interim_canonical_ingress import write_outputs
from financial_evidence_currency_refresh import PUBLIC_FACTS, PUBLIC_PRECEDENCE

TITLE = "BÁO CÁO KIỂM TOÁN ĐỘC LẬP báo cáo tài chính hợp nhất"
OPINION = "Ý kiến của Kiểm toán viên báo cáo tài chính hợp nhất đã phản ánh trung thực trên các khía cạnh trọng yếu theo chuẩn mực Việt Nam"

@pytest.mark.parametrize("texts,opinion_page", [((TITLE + " " + OPINION,), 1), ((TITLE, OPINION), 2)])
def test_literal_opinion_same_or_immediately_next_page(texts, opinion_page):
    result = resolve_document_assurance_evidence(_materialization(*texts))
    assert result["state"] == "QUALIFIED"
    assert result["audit_or_review_status"] == "audited"
    assert result["opinion_evidence"]["page_number"] == opinion_page
    assert result["opinion_evidence"]["rendered_image_sha256"] == f"img{opinion_page}"
    assert result["opinion_evidence"]["token_ids"]

@pytest.mark.parametrize("texts", [
    (TITLE,), (OPINION,), (TITLE, "unrelated", OPINION),
    (TITLE.replace("ĐỘC", "BỘC"), OPINION),
    (TITLE.replace("hợp nhất", "riêng"), OPINION),
    (TITLE, OPINION.replace("hợp nhất", "riêng")),
    (TITLE, OPINION.replace("Kiểm toán viên", "Ban điều hành")),
    (TITLE, OPINION.replace("đã phản ánh", "sẽ phản ánh")),
    (TITLE, OPINION + " Chúng tôi không đưa ra ý kiến kiểm toán"),
    (TITLE, "BÁO CÁO KIỂM TOÁN ĐỘC LẬP " + OPINION.replace("hợp nhất", "riêng")),
])
def test_report_or_scope_missing_or_unrelated_page_blocks(texts):
    assert resolve_document_assurance_evidence(_materialization(*texts))["state"] == "BLOCKED"


def test_missing_page_does_not_bridge_and_review_conflict_blocks():
    m = _materialization(TITLE, OPINION)
    m["pages"][1]["page_number"] = 3
    assert resolve_document_assurance_evidence(m)["state"] == "BLOCKED"
    assert resolve_document_assurance_evidence(_materialization(TITLE, OPINION, REVIEW_PAGE))["reason"] == "ASSURANCE_STATUS_AMBIGUOUS"


def test_opinion_page_hash_changes_evidence_and_other_source_claim_rejected():
    m = _materialization(TITLE, OPINION)
    first = resolve_document_assurance_evidence(m)
    m["pages"][1]["source_image_evidence"]["rendered_image_sha256"] = "different-image"
    assert resolve_document_assurance_evidence(m)["evidence_id"] != first["evidence_id"]
    with pytest.raises(ValueError, match="ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS"):
        validate_assurance_claim("audited", first, document_sha256="b" * 64)


def test_subset_refresh_preserves_other_issuers_same_year_and_all_other_periods(tmp_path):
    old = [{"ticker": t, "reporting_period": p, "canonical_metric": "revenue", "value": n}
           for n, (t, p) in enumerate((("HPG", "2025"), ("PNJ", "2025"), ("PVD", "2025"), ("PNJ", "2026-H1")))]
    prior = [{"key": {"ticker": r["ticker"], "period": r["reporting_period"]}, "status": "NOT_COMPARABLE"} for r in old]
    for name, rows in ((PUBLIC_FACTS, old), (PUBLIC_PRECEDENCE, prior)):
        (tmp_path / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf8")
    refreshed = {**old[1], "value": 42}
    result = {"report": {"documents": [{"ticker": "PNJ", "reporting_period": "2025"}]},
              "overlay_rows": [refreshed], "precedence_rows": [prior[1]]}
    untouched = copy.deepcopy(result)
    write_outputs(result, tmp_path, preserve_other_documents=True)
    rows = [json.loads(line) for line in (tmp_path / PUBLIC_FACTS).read_text().splitlines()]
    assert len(rows) == 4
    assert refreshed in rows
    assert all(r in rows for i, r in enumerate(old) if i != 1)
    assert len((tmp_path / PUBLIC_PRECEDENCE).read_text().splitlines()) == 4
    assert result == untouched


def test_retained_source_anchor_spans_and_new_facts_stay_historical_context():
    from tests.test_current_official_evidence_projection import baseline
    import market_wide_current_fundamental_research as fundamental
    from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _financial_input
    from stocklookup_core.decision.current_research_decision_packet import _valuation
    from ai_research_session_delivery import _compact_context
    root = Path(__file__).resolve().parents[1] / "derived/financial-evidence-currency-refresh-v1"
    sources = json.loads((root / "retained_annual_assurance_source_tokens.json").read_text(encoding="utf8"))
    for source in sources:
        materialization = {"document_sha256": source["document_sha256"],
            "materialization_id": source["materialization_id"], "pages": source["selected_pages"]}
        result = resolve_document_assurance_evidence(materialization)
        assert result["state"] == "QUALIFIED"
        assert result["page_number"] == source["assurance"]["page_number"]
        assert result["opinion_evidence"]["page_number"] == source["assurance"]["opinion_evidence"]["page_number"]
    rows = [json.loads(line) for line in (root / PUBLIC_FACTS).read_text(encoding="utf8").splitlines()]
    new = [r for r in rows if r["period_type"] == "annual" and r["ticker"] in {"PNJ", "PVD"}]
    assert len(new) == 6
    original = baseline()
    early = fundamental.project_session(baseline=original, official_rows=new,
        session="2026-10-07", cutoff="2026-10-07T15:00:00+07:00")
    assert all(not r["official_field_context"] for r in early["records"].values())
    later = fundamental.project_session(baseline=original, official_rows=new,
        session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    assert sum(len(r["official_field_context"]) for r in later["records"].values()) == 6
    for ticker, record in later["records"].items():
        assert record["metrics"] == original["records"][ticker]["metrics"]
        for field in record["official_field_context"]:
            assert field["temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
            assert field["valuation_use"] == "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT"
        if ticker in {"PNJ", "PVD"}:
            financial = _financial_input(record, later)
            assert _valuation({"financial_input": financial})["official_field_context"] == record["official_field_context"]
            assert _compact_context(ticker, {"product": {}}, {"fundamental": later})["fundamental_context"]["official_field_context"] == record["official_field_context"]
