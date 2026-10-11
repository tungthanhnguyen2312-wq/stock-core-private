"""Synthetic source-to-sink regressions; no network or production refresh.

The release baseline is 498b02dd8471078a9cd627eb75241a4ed2da0de5.
Malformed fixture failures against that baseline are reproduced defects, not
evidence that a production record was contaminated.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import financial_evidence_currency_refresh as refresh
import official_financial_assurance_evidence as assurance
from official_financial_period_identity import recognize_audit_or_review, recognize_statement_period
from tools.run_reviewed_interim_canonical_ingress import write_outputs


@pytest.mark.parametrize("text", [
    "Q3 2026 consolidated financial statements; notes: year ended 31 December 2025",
    "Quarter 3 2026 financial statements; comparative financial year ended 31 December 2025",
])
def test_interim_header_cannot_become_annual_note(text):
    result = recognize_statement_period(text)
    assert result["period"] is None
    assert result["status"] in {"UNKNOWN", "CONFLICT", "OUT_OF_SCOPE_Q3_2026"}


@pytest.mark.parametrize("text", ["unaudited", "not reviewed", "not audited",
    "chưa được soát xét", "không được kiểm toán", "Công ty kiểm toán độc lập XYZ"])
def test_incidental_or_negative_assurance_is_not_proof(text):
    assert recognize_audit_or_review(text)["audit_or_review_status"] is None


@pytest.mark.parametrize("text,period", [
    ("Consolidated financial statements for the year ended 31 December 2025", "2025"),
    ("Interim consolidated financial statements for six months ended 30 June 2026", "2026-H1"),
    ("Consolidated financial statements second quarter 2026", "2026-Q2"),
])
def test_positive_period_controls_preserve_native_identity(text, period):
    assert recognize_statement_period(text)["period"] == period


@pytest.mark.parametrize("status", ["audited", "reviewed"])
def test_assurance_word_alone_never_admits(status):
    with pytest.raises(ValueError, match="REQUIRES_RETAINED_DOCUMENT_EVIDENCE"):
        assurance.validate_assurance_claim(status, None, document_sha256="a"*64)


def unverified_fact():
    return {"ticker":"PNJ", "canonical_metric":"revenue", "reporting_period":"2025",
        "currency":"VND", "unit_scale":1, "statement_scope":"consolidated",
        "source_span":{"text":"synthetic revenue 123", "source_page":1},
        "raw_value_text":"123", "qualification_status":"OFFICIAL_FACT_CANDIDATE_BLOCKED"}


def test_blocked_extraction_does_not_qualify_from_labels():
    row=refresh._qualify_extracted_fact(unverified_fact(),
        {"ticker":"PNJ", "sha256":"a"*64, "observed_at":"2026-10-07T00:00:00Z"})
    assert row["qualification_state"] == "BLOCKED"
    assert row["blockers"]


def write_fixture(root, rows):
    path=root/refresh.PUBLIC_ARTIFACT_DIR/refresh.PUBLIC_FACTS
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("".join(json.dumps(row)+"\n" for row in rows),encoding="utf8")
    return path


def test_refresh_shaped_claim_cannot_enter_canonical_citations(tmp_path):
    row=refresh._qualify_extracted_fact(unverified_fact(), {"ticker":"PNJ", "sha256":"a"*64})
    row["qualification_state"]="QUALIFIED"  # Adversarial caller; never documentary proof.
    write_fixture(tmp_path,[row])
    assert refresh.load_public_official_citations(tmp_path)=={}


def test_conflicting_citations_never_have_an_order_selected_winner(tmp_path):
    row={**unverified_fact(),"qualification_state":"QUALIFIED", "normalized_value":10,
         "document_sha256":"a"*64, "citation_id":"synthetic"}
    other={**deepcopy(row),"normalized_value":11}
    answers=[]
    for rows in ([row,other],[other,row]):
        write_fixture(tmp_path,rows)
        answers.append(refresh.load_public_official_citations(tmp_path))
    assert answers[0]==answers[1]=={}


def test_empty_ingress_preserves_original_overlay(tmp_path):
    path=tmp_path/refresh.PUBLIC_FACTS
    original=b'{"historical_retained_marker":true}\n'
    path.write_bytes(original)
    result={"overlay_rows":[],"precedence_rows":[],"report":{"documents":[]}}
    write_outputs(result,tmp_path)
    assert path.read_bytes()==original


def test_invalid_ingress_refuses_before_any_overlay_replacement(tmp_path):
    path=tmp_path/refresh.PUBLIC_FACTS
    original=b'{"historical_retained_marker":true}\n'
    path.write_bytes(original)
    result={"overlay_rows":[{**unverified_fact(),"qualification_state":"QUALIFIED"}],
            "precedence_rows":[],"report":{"documents":[]}}
    with pytest.raises(ValueError):
        write_outputs(result,tmp_path)
    assert path.read_bytes()==original


def test_retained_overlay_inventory_is_read_only():
    path=Path(__file__).resolve().parents[1]/refresh.PUBLIC_ARTIFACT_DIR/refresh.PUBLIC_FACTS
    before=path.read_bytes()
    rows=[json.loads(line) for line in before.splitlines()]
    assert len(rows)==27 and len({r['document_sha256'] for r in rows})==9
    assert all(r['assurance_evidence']['document_sha256']==r['document_sha256'] for r in rows)
    assert path.read_bytes()==before
