"""Source-backed FPT discovery, auditor continuation and exact historical fields."""
import copy
import json
from pathlib import Path
import pytest
from financial_evidence_currency_refresh import parse_index_document_links
from official_financial_assurance_evidence import resolve_document_assurance_evidence
from official_financial_ocr_table_evidence import qualify_table_facts, resolve_scoped_unit_evidence, resolve_scoped_statement_scope_evidence
from tests.test_reviewed_interim_canonical_ingress import _materialization, REVIEW_PAGE
from tools.run_reviewed_interim_canonical_ingress import run
FIXTURE = Path(__file__).parent / "fixtures/fpt_official_evidence"
TITLE = "Independent Auditor's Report We have audited the accompanying consolidated financial statements"
OPINION = "Auditor's Opinion In our opinion the consolidated financial statements present fairly in all material respects in accordance with Vietnamese Accounting Standards"

def source():
    return json.loads((FIXTURE / "annual_positioned_tokens.json").read_text(encoding="utf8"))

def test_retained_index_excludes_separate_and_non_target_quarters():
    html = (FIXTURE / "retained_index_financial_chunk.html").read_text()
    links = parse_index_document_links(html, "https://fpt.com/en/ir/report")
    assert {(x["period"], x["url"].split("/")[-1]) for x in links} == {
        ("2025", "20260319_fpt_audited_consolidated_financial_statements_for_2025_f29f536732.pdf"),
        ("2026-Q2", "20260727_FPT_Consolidated_Financial_Statements_for_Q22026_1_a1e229ff76.pdf")}
    assert all(x["discovery_kind"] == "LITERAL_EMBEDDED_FINANCIAL_DOCUMENT" for x in links)
    assert parse_index_document_links(html, "https://example.com/index") == []
    assert parse_index_document_links(html.replace('financial', 'earnings'), "https://fpt.com/en/ir/report") == []

@pytest.mark.parametrize("payload", [None, {}, ["x"], ["$", "x", None, {"category":"financial", "yearDataList":None}],
    ["$", "x", None, {"category":"financial", "yearDataList":[{"year":[],"periods":[{"period":[]}]}]}]])
def test_malformed_embedded_json_has_no_locator(payload):
    html = '<script>self.__next_f.push(' + json.dumps([1,'1a:'+json.dumps(payload)]) + ')</script>'
    assert parse_index_document_links(html, "https://fpt.com/en/ir/report") == []

@pytest.mark.parametrize("texts", [(TITLE, OPINION), (TITLE + " " + OPINION,)])
def test_literal_english_auditor_and_opinion_qualify(texts):
    r = resolve_document_assurance_evidence(_materialization(*texts))
    assert r["state"] == "QUALIFIED" and r["audit_or_review_status"] == "audited"
    assert r["opinion_evidence"]["token_ids"]

@pytest.mark.parametrize("texts", [(TITLE,), (OPINION,), (TITLE, "unrelated", OPINION),
    (TITLE.replace('consolidated','separate'),OPINION),
    (TITLE,OPINION.replace('consolidated','separate')), (TITLE,OPINION.replace('present fairly','may present fairly')),
    (TITLE,OPINION.replace('Accounting Standards','company policies')),
    (TITLE,OPINION+" We do not express an audit opinion"), (TITLE,TITLE.replace("consolidated","separate")+" "+OPINION.replace("consolidated","separate"))])
def test_missing_or_unrelated_english_assurance_blocks(texts):
    assert resolve_document_assurance_evidence(_materialization(*texts))["state"] == "BLOCKED"

def test_review_conflict_and_missing_page_block():
    assert resolve_document_assurance_evidence(_materialization(TITLE, OPINION, REVIEW_PAGE))["reason"] == "ASSURANCE_STATUS_AMBIGUOUS"
    m = _materialization(TITLE, OPINION); m['pages'][1]['page_number']=3
    assert resolve_document_assurance_evidence(m)["state"] == "BLOCKED"

def test_retained_source_exact_values_and_ambiguous_parent_stays_blocked():
    m = source(); a = resolve_document_assurance_evidence(m)
    assert a["audit_or_review_status"] == "audited" and a["page_number"] == 6
    assert a["opinion_evidence"]["page_number"] == 7
    q = qualify_table_facts(m, ticker="FPT", reporting_period="2025",
        scoped_unit_evidence=resolve_scoped_unit_evidence(m), scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(m))
    values = {x['canonical_metric']:x['value'] for x in q['qualified_facts']}
    assert values == {'shareholders_equity':43748040747539, 'revenue':70112825100710}
    assert any(x['canonical_metric']=='attributable_net_income' and x['reason']=='OCR_NUMERIC_AMBIGUITY' for x in q['blocked_candidates'])
    other=copy.deepcopy(m);other['pages'][1]['source_image_evidence']['rendered_image_sha256']='changed'
    assert resolve_document_assurance_evidence(other)['evidence_id'] != a['evidence_id']

@pytest.mark.parametrize('kwargs',[{'evidence_subdir':'../outside'},{'front_matter_pages':(6,6)}, {'front_matter_pages':(9,)}, {'front_matter_pages':()}])
def test_replay_front_pages_and_landing_remain_bounded(tmp_path,kwargs):
    with pytest.raises(ValueError,match='OUTSIDE_BOUNDED'):
        run(landing_root=tmp_path,**kwargs)
