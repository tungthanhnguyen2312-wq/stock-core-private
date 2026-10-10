"""Fixed VNM/QNS/POW current-interim probe: identities, terminal states and safety."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

import market_wide_current_fundamental_research as fundamental
import stocklookup_core.evidence.official_document_acquisition as acquisition
from official_financial_ocr_table_evidence import (
    qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
    row_label_supports_metric,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "derived/financial-evidence-currency-refresh-v1"
FIXTURE = Path(__file__).parent / "fixtures/triad_current_h1/vnm_h1_positioned_tokens.json"
QNS_FIXTURE = Path(__file__).parent / "fixtures/triad_current_h1/qns_h1_positioned_tokens.json"
QNS_SHA = "5a06a40f34a6d9b30233926f9c9d909d684744de2bf2ad0956edd367d5f7b068"
QNS_EQUITY = 10647823148609
VNM_SHA = "a6155aa757b320b893a78093b0454473f4a581aead225af4eb4ef1fbd6628561"
VNM_URL = "https://d8um25gjecm9v.cloudfront.net/cms/20260730_VNM_BCTC_da_soat_xet_Q2_2026_Hop_nhat_76ef2e29c1.pdf"
VNM_CASH = 4535672366831


def tokens():
    return json.loads(FIXTURE.read_text(encoding="utf8"))


def qualify(m, period="2026-H1", ticker="VNM"):
    return qualify_table_facts(m, ticker=ticker, reporting_period=period, include_earnings_quality_components=True,
                               scoped_unit_evidence=resolve_scoped_unit_evidence(m),
                               scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(m))


def by_metric(q):
    return {f["canonical_metric"]: f for f in q["qualified_facts"]}


def blocked(q, metric):
    return next(b for b in q["blocked_candidates"] if b["canonical_metric"] == metric)


def rewrite(m, old, new, page=None):
    m = copy.deepcopy(m)
    for p in m["pages"]:
        if page is None or p["page_number"] == page:
            for t in p["ocr_derived_text_evidence"]["tokens"]:
                if t["text"] == old:
                    t["text"] = new
    return m


def overlay():
    return [json.loads(line) for line in (PUBLIC / "qualified_official_facts.jsonl").read_text(encoding="utf8").splitlines()]


def report():
    return json.loads((PUBLIC / "triad_current_h1_evidence_report.json").read_text(encoding="utf8"))


def proof():
    return json.loads((PUBLIC / "triad_current_h1_acquisition_proof.json").read_text(encoding="utf8"))


# --- source/document identity and acquisition bounds -------------------------------------------

def test_each_issuer_reaches_exactly_one_terminal_state():
    states = report()["issuer_terminal_states"]
    assert set(states) == {"VNM", "QNS", "POW"}
    assert states["VNM"]["state"] == "CURRENT_OFFICIAL_FACTS_QUALIFIED"
    assert states["VNM"]["document_sha256"] == VNM_SHA and states["VNM"]["network_requests"] == 0
    assert states["QNS"]["state"] == "CURRENT_OFFICIAL_FACTS_QUALIFIED"
    assert states["QNS"]["document_sha256"] == QNS_SHA and states["QNS"]["qualified_metrics"] == ["shareholders_equity"]
    assert states["POW"] == {**states["POW"], "state": "APPROVED_ROUTE_BLOCKED", "reason": "access_denied"}


def test_acquisition_stayed_inside_declared_budget():
    p = proof()
    assert p["actual_requests"] == 5 <= p["budget"]["actual_http_cap"] == 12
    assert p["pdf_requests"] == 1
    assert p["new_landing_bytes_total"] <= p["budget"]["storage_cap_bytes"] == 100 * 1024 * 1024
    kinds = [(s["ticker"], s["kind"]) for s in p["trace"]]
    assert sorted(kinds) == [("POW", "index"), ("QNS", "detail_page_resolver"), ("QNS", "index"), ("QNS", "pdf")]
    assert sum(s["requests_counted_incl_redirects_retries"] for s in p["trace"]) == p["actual_requests"]
    assert {s["url"].split("/")[2] for s in p["trace"]} <= {"www.qns.com.vn", "www.pvpower.vn"}
    detail = p["qns_detail_page_resolver"]
    assert detail["classification"] == "ISSUER_IR_DETAIL_PAGE_RESOLVER"
    assert detail["authority_effect"] == "DISCOVERY_ONLY_NOT_FINANCIAL_EVIDENCE"
    assert detail["parent_index"]["sha256"] == next(s["sha256"] for s in p["trace"] if s["kind"] == "index" and s["ticker"] == "QNS")
    [selected] = [a for a in detail["pdf_anchors"] if a["url"] == detail["selected_locator"]]
    assert selected["literal_anchor_text"] == "Báo cáo tài chính hợp nhất bán niên năm 2026"
    assert p["qns_pdf"]["sha256"] == QNS_SHA and p["qns_pdf"]["canonical_url"] == detail["selected_locator"]
    assert p["qns_pdf"]["final_url"] == p["qns_pdf"]["canonical_url"]
    copy_ = p["vnm_retained_copy"]
    assert copy_["network_requests"] == 0 and copy_["record"]["sha256"] == VNM_SHA
    assert copy_["record"]["canonical_url"] == VNM_URL and copy_["record"]["observed_at"] == "2026-08-02T08:25:00Z"
    assert copy_["record"]["retained_copy_provenance"]["source_manifest_reporting_period"] == "2026"
    assert copy_["duplicate_replay_state"] == "cached_valid" and copy_["duplicate_replay_manifest_bytes_equal"]


def _source(tmp_path, url=VNM_URL, data=b"%PDF-1.4 retained official bytes\n"):
    sha = hashlib.sha256(data).hexdigest()
    rel = f"documents/VNM/2026/reviewed_interim_financial_statements/{sha}.pdf"
    (tmp_path / "src" / rel).parent.mkdir(parents=True)
    (tmp_path / "src" / rel).write_bytes(data)
    record = {"acquisition_status": "retained", "canonical_url": url, "final_url": url, "ticker": "VNM",
              "document_class": "reviewed_interim_financial_statements", "reporting_period": "2026",
              "observed_at": "2026-08-02T08:25:00Z", "relative_path": rel, "sha256": sha,
              "document_id": hashlib.sha256(f"VNM|{url}|{sha}".encode()).hexdigest()}
    (tmp_path / "src" / acquisition.MANIFEST).write_text(json.dumps({"schema_version": "1.1.0", "records": [record]}), encoding="utf8")
    return tmp_path / "src", sha


def test_retained_copy_is_network_free_and_duplicate_is_a_byte_identical_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    src, sha = _source(tmp_path)
    source_bytes = (src / acquisition.MANIFEST).read_bytes()
    first = acquisition.adopt_retained_document_copy(src, sha, tmp_path / "dst", reporting_period="2026-H1", adopted_at="t1")
    manifest = (tmp_path / "dst" / acquisition.MANIFEST).read_bytes()
    second = acquisition.adopt_retained_document_copy(src, sha, tmp_path / "dst", reporting_period="2026-H1", adopted_at="t2")
    assert (first["state"], second["state"]) == ("retained", "cached_valid")
    assert first["document_id"] == second["document_id"] and first["network_requests"] == second["network_requests"] == 0
    assert (tmp_path / "dst" / acquisition.MANIFEST).read_bytes() == manifest
    assert (src / acquisition.MANIFEST).read_bytes() == source_bytes
    [record] = json.loads(manifest)["records"]
    assert record["observed_at"] == "2026-08-02T08:25:00Z" and record["reporting_period"] == "2026-H1"
    with pytest.raises(ValueError, match="RETAINED_COPY_BINDING_CONFLICT"):
        acquisition.adopt_retained_document_copy(src, sha, tmp_path / "dst", reporting_period="2026-Q2", adopted_at="t3")


def test_retained_copy_refuses_unadmitted_host_and_changed_bytes(tmp_path):
    src, sha = _source(tmp_path, url="https://cdn.example.com/vnm.pdf")
    with pytest.raises(ValueError, match="refused_by_source_registry"):
        acquisition.adopt_retained_document_copy(src, sha, tmp_path / "dst", reporting_period="2026-H1", adopted_at="t")
    src, sha = _source(tmp_path / "b")
    next((src / "documents").rglob("*.pdf")).write_bytes(b"%PDF-1.4 altered")
    with pytest.raises(ValueError, match="RETAINED_SOURCE_HASH_MISMATCH"):
        acquisition.adopt_retained_document_copy(src, sha, tmp_path / "dst", reporting_period="2026-H1", adopted_at="t")
    assert not (tmp_path / "dst").exists()


# --- assurance, period, scope, unit and the qualified fact ------------------------------------

def test_reviewed_consolidated_interim_assurance_is_proven_by_the_document():
    vnm = report()["documents"][0]
    a = vnm["assurance"]
    assert (a["state"], a["audit_or_review_status"], a["scope_of_assurance"], a["page_number"]) == (
        "QUALIFIED", "reviewed", "consolidated_interim_statements", 5)
    assert "soat xet so 2410" in a["matched_anchors"]


def test_vnm_cash_row_qualifies_with_period_scope_unit_and_citation():
    cash = by_metric(qualify(tokens()))["cash_and_equivalents"]
    lineage = cash["source_lineage"]
    assert (cash["value"], cash["currency"], cash["unit_scale"], cash["reporting_period"]) == (VNM_CASH, "VND", 1, "2026-H1")
    assert (lineage["source_page"], lineage["line_code"], lineage["row_object"]["note_reference"]) == (7, "110", "V.1")
    assert lineage["row_object"]["current_period_label"] == "30/6/2026"
    assert lineage["row_object"]["comparative_period_label"] == "1/1/2026"
    assert lineage["ocr_derived_text_evidence"]["current_raw"] == "4.535.672.366.831"
    assert lineage["statement_scope_evidence"]["statement_scope"] == "consolidated"
    assert lineage["unit_evidence"]["state"] == "QUALIFIED"


def test_overlay_row_preserves_full_identity_and_later_knowledge():
    [row] = [r for r in overlay() if r["ticker"] == "VNM"]
    assert (row["canonical_metric"], row["normalized_value"], row["currency"], row["source_unit_scale"]) == (
        "cash_and_equivalents", VNM_CASH, "VND", 1)
    assert (row["statement_family"], row["statement_scope"], row["reporting_period"], row["period_type"]) == (
        "balance_sheet", "consolidated", "2026-H1", "interim")
    assert (row["period_start"], row["period_end"], row["audit_or_review_status"]) == ("2026-01-01", "2026-06-30", "reviewed")
    assert (row["document_sha256"], row["source_page"], row["line_code"]) == (VNM_SHA, 7, "110")
    assert row["citation_id"] and row["knowledge_available_at"].startswith("2026-10-08T")
    assert row["observed_at"] == "2026-08-02T08:25:00Z"


# --- fail-closed column, note and label rules --------------------------------------------------

def test_opening_date_column_binds_only_on_the_exact_interim_period_end():
    assert "cash_and_equivalents" not in by_metric(qualify(rewrite(tokens(), "30/6/2026", "1/7/2026", page=7)))
    # An annual target cannot use two same-year dates to choose a column.
    assert "cash_and_equivalents" not in by_metric(qualify(tokens(), period="2026"))


def test_only_exact_literal_vas_note_tokens_leave_the_label_band():
    assert "cash_and_equivalents" not in by_metric(qualify(rewrite(tokens(), "V.1", "V:1", page=7)))
    assert "cash_and_equivalents" not in by_metric(qualify(rewrite(tokens(), "V.1", "V.1x", page=7)))


@pytest.mark.parametrize("metric,label,ok", [
    ("short_term_borrowings", "Vay và nợ thuê tài chính ngắn hạn", True),
    ("short_term_borrowings", "Vay va ng thué tai chinh ngan han", True),
    ("short_term_borrowings", "Phải trả ngắn hạn khác", False),
    ("short_term_borrowings", "Vay dài hạn", False),
    ("long_term_borrowings_or_finance_leases", "Vay và nợ thuê tài chính dài hạn", True),
    ("long_term_borrowings_or_finance_leases", "Phai tra dai han khac", False),
    ("long_term_borrowings_or_finance_leases", "", False),
])
def test_debt_components_require_a_literal_loan_label(metric, label, ok):
    assert row_label_supports_metric(metric, label) is ok


def test_renumbered_2026_rows_and_damaged_cells_stay_blocked():
    q = qualify(tokens())
    assert set(by_metric(q)) == {"cash_and_equivalents"}
    assert blocked(q, "total_assets")["reason"] == "ROW_LABEL_DOES_NOT_SUPPORT_METRIC"  # row 270, PR #87 rule
    assert blocked(q, "long_term_borrowings_or_finance_leases")["reason"] == "ROW_LABEL_DOES_NOT_SUPPORT_METRIC"
    assert blocked(q, "total_interest_bearing_debt")["reason"] == "DEBT_COMPONENT_INCOMPLETE"
    equity = blocked(q, "shareholders_equity")
    assert equity["reason"] == "OCR_NUMERIC_AMBIGUITY" and equity["raw_value"].startswith("—")
    for metric in ("revenue", "net_income", "attributable_net_income", "operating_cash_flow",
                   "provision_charge_or_reversal_adjustment"):
        assert blocked(q, metric)["reason"] == "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED"
    assert not any("²" in str(f["source_lineage"]["ocr_derived_text_evidence"]["current_raw"]) for f in q["qualified_facts"])


# --- knowledge cutoff, projection, packet/AI and valuation -------------------------------------

def _baseline():
    value = {"contract_version": fundamental.CONTRACT_VERSION, "records": {
        "VNM": {"authority_tier": "OFFICIAL_QUALIFIED", "authoritative_periods_available": ["2024"],
                "metrics": [{"metric_id": "net_margin", "status": "EXACT_QUALIFIED", "periods_used": ["2024"], "value": 0.1}]}}}
    value.update(fundamental.content_identity(value))
    return value


def _project(rows, session):
    return fundamental.project_session(baseline=_baseline(), official_rows=rows, session=session,
                                       cutoff=session + "T15:00:00+07:00")


def test_completed_session_excludes_and_october8_scratch_includes_vnm():
    rows = [r for r in overlay() if r["ticker"] == "VNM"]
    assert not _project(rows, "2026-10-07")["records"]["VNM"]["official_field_context"]
    later = _project(rows, "2026-10-08")["records"]["VNM"]
    assert [f["canonical_metric"] for f in later["official_field_context"]] == ["cash_and_equivalents"]
    assert later["metrics"] == _baseline()["records"]["VNM"]["metrics"]
    late = [dict(rows[0], knowledge_available_at="2026-10-08T08:00:01+00:00")]
    assert not _project(late, "2026-10-08")["records"]["VNM"]["official_field_context"]


def test_packet_and_ai_receive_the_field_without_valuation_authority():
    import current_research_decision_packet as packet
    from ai_research_session_delivery import _compact_context
    from market_wide_current_valuation_input_scaleout import _financial_input
    value = _project([r for r in overlay() if r["ticker"] == "VNM"], "2026-10-08")
    fields = value["records"]["VNM"]["official_field_context"]
    financial = _financial_input(value["records"]["VNM"], value)
    assert financial["official_field_context"] == fields
    assert financial["interim_context_does_not_supply_annual_valuation_inputs"] is True
    assert packet._valuation({"financial_input": financial})["official_field_context"] == fields
    assert _compact_context("VNM", {"product": {}}, {"fundamental": value})["fundamental_context"]["official_field_context"] == fields
    assert report()["valuation"] == {"pe_ttm_from_h1": False, "ps_ttm_from_h1": False, "pb_effect": "NONE"}
    assert value["records"]["VNM"]["earnings_quality_context"]["status"] == "UNKNOWN"


# --- QNS reviewed H1 continuation ---------------------------------------------------------------

def qns_tokens():
    return json.loads(QNS_FIXTURE.read_text(encoding="utf8"))


def test_qns_assurance_and_unusable_text_layer_fallback_are_recorded():
    qns = next(d for d in report()["documents"] if d["ticker"] == "QNS")
    a = qns["assurance"]
    assert (a["state"], a["audit_or_review_status"], a["scope_of_assurance"], a["page_number"]) == (
        "QUALIFIED", "reviewed", "consolidated_interim_statements", 5)
    assert "khong dua ra y kien kiem toan" in a["matched_anchors"]
    receipts = [p["native_failure_evidence"] for p in qns["native_fallback_pages"]]
    assert receipts and all(r["candidate_count"] == 0 and r["trigger"] == "EXPLICIT_OPT_IN_AFTER_NATIVE_ZERO_CANDIDATES" for r in receipts)


def test_qns_equity_qualifies_and_damaged_headers_stay_blocked():
    q = qualify(qns_tokens(), ticker="QNS")
    assert set(by_metric(q)) == {"shareholders_equity"}
    equity = by_metric(q)["shareholders_equity"]
    row = equity["source_lineage"]["row_object"]
    assert (equity["value"], equity["currency"], equity["unit_scale"]) == (QNS_EQUITY, "VND", 1)
    assert (equity["source_lineage"]["source_page"], row["line_code"]) == (7, "400")
    assert (row["current_period_label"], row["comparative_period_label"]) == ("30/06/2026", "01/01/2026")
    # Page 6 header reads 30/06/²0²6: never normalized, so cash and total assets stay unread.
    for metric in ("cash_and_equivalents", "total_assets", "revenue", "net_income", "attributable_net_income"):
        assert blocked(q, metric)["reason"] == "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED"
    # 338 is ``Phải trả dài hạn khác`` under the 2026 template.
    assert blocked(q, "long_term_borrowings_or_finance_leases")["reason"] == "ROW_LABEL_DOES_NOT_SUPPORT_METRIC"
    assert blocked(q, "total_interest_bearing_debt")["reason"] == "DEBT_COMPONENT_INCOMPLETE"


def test_qns_overlay_row_identity_and_cutoffs():
    [row] = [r for r in overlay() if r["ticker"] == "QNS" and r["reporting_period"] == "2026-H1"]
    assert (row["canonical_metric"], row["normalized_value"], row["statement_scope"], row["period_type"]) == (
        "shareholders_equity", QNS_EQUITY, "consolidated", "interim")
    assert (row["document_sha256"], row["source_page"], row["line_code"], row["audit_or_review_status"]) == (
        QNS_SHA, 7, "400", "reviewed")
    assert row["knowledge_available_at"] > next(r for r in overlay() if r["ticker"] == "VNM")["knowledge_available_at"]
    assert row["knowledge_available_at"].startswith("2026-10-08T")
    completed = fundamental.project_session(baseline=_baseline(), official_rows=[row], session="2026-10-07",
                                            cutoff="2026-10-07T15:00:00+07:00")
    assert "QNS" not in completed["records"] or not completed["records"]["QNS"].get("official_field_context")
