"""Synthetic source-to-sink regressions; no network or production refresh.

The release baseline is 498b02dd8471078a9cd627eb75241a4ed2da0de5.
Malformed fixture failures against that baseline are reproduced defects, not
evidence that a production record was contaminated.
"""
from copy import deepcopy
import json
import hashlib
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
    from official_financial_filing_evidence import admit_official_financial_fact
    results=[admit_official_financial_fact(row) for row in rows]
    # Exact pinned v2 rows: proof-bound and byte-verified offline, original semantics NOT re-verified.
    assert all(r["state"]=="ADMITTED" and r["admission_basis"]=="PINNED_LEGACY_GOVERNED_INGRESS_V2" for r in results)
    assert all(r["evidence_classification"]["original_document_semantics_independently_verified"] is False for r in results)
    # Committed LF bytes; a Windows autocrlf checkout differs only in line endings.
    committed=hashlib.sha256(before.replace(b"\r\n",b"\n")).hexdigest()
    assert committed=="bd83de2ddb80a56e8a1fdfccb131418c55979a0799836da36538496a7283d653"
    pin=json.loads((Path(__file__).resolve().parents[1]/"config/official_financial_legacy_row_admission_v1.json").read_text(encoding="utf8"))
    assert pin["overlay_sha256_lf"]==committed and len(pin["rows"])==27
    assert path.read_bytes()==before


def _retained_rows():
    path=Path(__file__).resolve().parents[1]/refresh.PUBLIC_ARTIFACT_DIR/refresh.PUBLIC_FACTS
    return [json.loads(line) for line in path.read_bytes().splitlines()]


@pytest.mark.parametrize("mutation",["value","status","assurance","citation","contract","metadata","period","new_row"])
def test_pinned_legacy_rows_cannot_be_reused_or_edited(mutation):
    from official_financial_filing_evidence import admit_official_financial_fact
    row=deepcopy(next(r for r in _retained_rows() if r["ticker"]=="VNM"))
    if mutation=="value": row["normalized_value"]+=1; row["value"]=row["normalized_value"]
    if mutation=="status": row["audit_or_review_status"]="audited"
    if mutation=="assurance": row["assurance_evidence"]["document_sha256"]="f"*64
    if mutation=="citation": row["citation_id"]="cross-document-reuse"
    if mutation=="contract": row["ingress_contract"]="reviewed_interim_canonical_ingress/v3"
    if mutation=="metadata": row["document_metadata"]={"qualification_status":"DOCUMENT_METADATA_QUALIFIED"}
    if mutation=="period": row["reporting_period"]="2026-Q3"
    if mutation=="new_row": row["ticker"]="PNJ"
    result=admit_official_financial_fact(row)
    assert result["state"]!="ADMITTED" and "admission_basis" not in result


def test_pinned_legacy_rows_still_respect_cutoff_and_intended_use():
    from official_financial_filing_evidence import admit_official_financial_fact
    rows=_retained_rows()
    early=[admit_official_financial_fact(r,cutoff="2026-09-01T00:00:00+07:00") for r in rows]
    assert all(r["state"]=="BLOCKED" and "AFTER_KNOWLEDGE_CUTOFF" in r["reason_codes"] for r in early)
    annual=[r for r in rows if r.get("context_kind") in {"AUDITED_ANNUAL_FIELD","EARNINGS_QUALITY_COMPONENT"}]
    assert annual and all(admit_official_financial_fact(r,intended_use="VALUATION_INPUT_WHERE_METRIC_PERMITS")["state"]=="BLOCKED" for r in annual)


def proved_fixture(period="2026-H1", *, ticker="PNJ", metric="revenue", value=123,
                   currency="VND", scale=1, observed="2026-10-07T00:00:00Z", native_pdf=False):
    """Entirely synthetic document/source; no real issuer disclosure is fabricated."""
    from official_source_registry import load_registry
    from official_financial_filing_evidence import qualify_document_metadata
    from official_financial_period_identity import period_bounds
    from financial_statement_template_recognizer import GENERIC_METRIC_RULES
    from financial_evidence_currency_contract import ISSUER_IR_INDEX_SEEDS
    annual=period=="2025"
    status="audited" if annual else "reviewed"
    title=("BAO CAO KIEM TOAN DOC LAP chung toi da kiem toan hop nhat" if annual else
           "BAO CAO SOAT XET hop dong dich vu soat xet so 2410 hop nhat giua nien do")
    period_text={"2025":"financial year ended 31 December 2025",
          "2026-H1":"six months ended 30 June 2026","2026-Q2":"second quarter 2026"}[period]
    spec=GENERIC_METRIC_RULES.get(metric)
    label=spec["source_label"] if spec else {"provision_charge_or_reversal_adjustment":"Provisions",
        "investment_property_disposal_result":"thanh ly bat dong san dau tu"}.get(metric,"synthetic unknown metric")
    raw=str(value//scale) if value>=0 else '('+str(abs(value)//scale)+')'
    unit="Unit: "+({1:"",1000:"thousand ",1_000_000:"million "}[scale])+currency
    if native_pdf:
        import unicodedata
        label=''.join(c for c in unicodedata.normalize('NFD',label.replace('đ','d').replace('Đ','D')) if not unicodedata.combining(c))
    text_payload=(ticker+" synthetic fixture\n"+period_text+"\n"+title+"\nconsolidated\n"+unit+"\n"+label+" "+raw)
    payload=text_payload.encode("utf8")
    if native_pdf:
        payload=_synthetic_pdf(text_payload)
    sha=hashlib.sha256(payload).hexdigest()
    materialization={"document_sha256":sha,"materialization_id":"b"*64,"pages":[{
        "page_number":1,"source_image_evidence":{"rendered_image_sha256":"c"*64},
        "ocr_derived_text_evidence":{"tokens":[{"text":word,"token_id":str(i),"raw_token_order":i}
                                               for i,word in enumerate(title.split())]}}]}
    proof=assurance.resolve_document_assurance_evidence(materialization)
    if native_pdf:
        proof=assurance.resolve_native_document_assurance(sha,{1:text_payload})
    text={"2025":"financial year ended 31 December 2025",
          "2026-H1":"six months ended 30 June 2026","2026-Q2":"second quarter 2026"}[period]
    seed=ISSUER_IR_INDEX_SEEDS[ticker]
    from urllib.parse import urlsplit
    url="https://"+str(urlsplit(seed).hostname)+"/test-only-synthetic-fixture.pdf"
    source={"ticker":ticker,"document_id":"synthetic-doc","sha256":sha,"source_id":"issuer_ir",
        "canonical_url":url,"final_url":url,
        "document_class":"audited_annual_financial_statements" if annual else "reviewed_interim_financial_statements",
        "acquisition_status":"retained","observed_at":observed,"reporting_period":period,
        "relative_path":"fixture.pdf"}
    document={"document_id":source["document_id"],"sha256":sha,"source_locator":source["canonical_url"],
        "source_id":"issuer_ir","observed_at":source["observed_at"],"immutable_bytes_verified":True}
    claims={k:{"value":v,"evidence_span":{"citation_id":"synthetic-metadata","document_sha256":sha,
        "source_page":1,"text":text if k in {"reporting_period","periodicity"} else unit if k=="unit_scale" else str(v)}}
        for k,v in {"reporting_period":period,"periodicity":"annual" if annual else "interim",
            "statement_scope":"consolidated","currency":currency,"unit_scale":scale}.items()}
    metadata=qualify_document_metadata({"issuer_identity":ticker,"entity_type":"corporate","document":document,"metadata":claims})
    start,end=period_bounds(period)
    row={"ticker":ticker,"canonical_metric":metric,"reporting_period":period,"period_start":start,"period_end":end,
        "period_type":"annual" if annual else "interim","statement_family":str(spec["statement_type"]) if spec else "income_statement" if metric=="investment_property_disposal_result" else "cash_flow","statement_scope":"consolidated",
        "currency":currency,"unit_scale":1,"source_unit_scale":scale,"raw_value_text":raw,"normalized_value":value,
        "raw_row_label":label, "source_span":{"text":label+" "+raw,
            "document_sha256":sha,"citation_id":"synthetic-value:"+sha,"source_page":1},
        "document_sha256":sha,"citation_id":"synthetic-value:"+sha,"document_metadata":metadata,
        "qualification_state":"QUALIFIED","audit_or_review_status":status,"assurance_evidence":proof,
        "observed_at":source["observed_at"],"knowledge_available_at":source["observed_at"]}
    registry=load_registry()
    synthetic_source=next(s for s in registry["sources"] if s["source_id"]=="issuer_ir")
    synthetic_source["allowed_hosts"].append("synthetic.invalid")
    synthetic_source.get("host_document_types",{}).pop("synthetic.invalid",None)
    return row,{"source_record":source,"retained_bytes":payload,"registry":registry,"document_pages":{1:text_payload}}


def _synthetic_pdf(text):
    """Minimal owned ASCII PDF fixture; no external document or PDF generator dependency."""
    lines=[line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)') for line in text.splitlines()]
    stream=('BT /F1 10 Tf 40 760 Td '+ ' 0 -14 Td '.join('('+line+') Tj' for line in lines)+' ET').encode('ascii')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    output=b'%PDF-1.4\n'; offsets=[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(output));output+=str(number).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    xref=len(output)
    output+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return output+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'


@pytest.mark.parametrize('period',['2025','2026-H1','2026-Q2'])
def test_native_retained_pdf_reader_replays_owned_source_and_fails_closed_without_parser(tmp_path,period):
    from stocklookup_core.evidence.official_document_qualification import admit_retained_financial_fact
    row,context=proved_fixture(period,native_pdf=True)
    (tmp_path/'fixture.pdf').write_bytes(context['retained_bytes'])
    (tmp_path/'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[context['source_record']]}),encoding='utf8')
    result=admit_retained_financial_fact(row,evidence_root=tmp_path,registry=context['registry'])
    try:
        import pypdf
    except ImportError:
        assert result['state']=='UNKNOWN' and 'RETAINED_DOCUMENT_TEXT_PROOF_UNAVAILABLE' in result['reason_codes']
    else:
        assert result['state']=='ADMITTED',result
        from stocklookup_core.evidence.official_document_qualification import qualify_retained_document, QUALIFICATION_SUCCESS_STATUS
        qualification=qualify_retained_document(context['source_record'],evidence_root=tmp_path,registry=context['registry'])
        assert qualification.qualification_status==QUALIFICATION_SUCCESS_STATUS
        bad=deepcopy(row);bad['normalized_value']+=1
        assert admit_retained_financial_fact(bad,evidence_root=tmp_path,registry=context['registry'])['state']=='BLOCKED'
    (tmp_path/'fixture.pdf').write_bytes(context['retained_bytes']+b'changed')
    assert admit_retained_financial_fact(row,evidence_root=tmp_path,registry=context['registry'])['state']=='BLOCKED'


@pytest.mark.parametrize("period",["2025","2026-H1","2026-Q2"])
def test_shared_admission_positive_controls(period):
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture(period)
    result=admit_official_financial_fact(row,**context)
    assert result["state"]=="ADMITTED",result
    assert result==admit_official_financial_fact(deepcopy(row),**context)


@pytest.mark.parametrize('body',[
    'PNJ\nQ3 2026 financial statements\nnotes: financial year ended 31 December 2025\nUnit: VND\nconsolidated\nBAO CAO KIEM TOAN DOC LAP chung toi da kiem toan hop nhat',
    'PNJ\nfinancial year ended 31 December 2025\nUnit: VND\nconsolidated\naudit engagement notice BAO CAO KIEM TOAN DOC LAP',
    'PNJ\nfinancial year ended 31 December 2025\nUnit: VND\nconsolidated\nnot audited BAO CAO KIEM TOAN DOC LAP chung toi da kiem toan hop nhat'])
def test_document_class_hint_cannot_qualify_actual_retained_document(tmp_path,body):
    from stocklookup_core.evidence.official_document_qualification import qualify_retained_document
    _,context=proved_fixture('2025',native_pdf=True)
    payload=_synthetic_pdf(body)
    record={**context['source_record'],'sha256':hashlib.sha256(payload).hexdigest()}
    (tmp_path/'fixture.pdf').write_bytes(payload)
    result=qualify_retained_document(record,evidence_root=tmp_path,registry=context['registry'])
    assert result.qualification_status=='DISQUALIFIED_RETAINED_DOCUMENT'
    assert result.audit_status=='unknown' and result.statement_scope=='unknown'


def test_actual_extracted_fact_owner_requires_whole_bound_source():
    row,context=proved_fixture()
    candidate={**row,'qualification_status':'OFFICIAL_FACT_QUALIFIED',
        'page_number':1,'unit_scale':row['source_unit_scale']}
    document={**context['source_record'],'document_metadata':row['document_metadata'],
        'assurance_evidence':row['assurance_evidence'],'audit_or_review_status':row['audit_or_review_status'],
        '_source_record':context['source_record'],'_retained_bytes':context['retained_bytes'],
        '_source_registry':context['registry'],'_document_pages':context['document_pages']}
    assert refresh._qualify_extracted_fact(candidate,document)['qualification_state']=='QUALIFIED'
    bad=deepcopy(document);bad['_retained_bytes']+=b'changed'
    assert refresh._qualify_extracted_fact(candidate,bad)['qualification_state']=='BLOCKED'


def test_unregistered_intended_use_has_no_authority():
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture()
    result=admit_official_financial_fact(row,**context,intended_use='Q3_VALUE_AUTHORITY')
    assert result['state']=='INAPPLICABLE' and result['reason_codes']==['INTENDED_USE_OUTSIDE_CONTRACT']


def test_refresh_shaped_row_cannot_bypass_through_legacy_citation_filename(tmp_path):
    from canonical_fact_store import load_official_citations
    row,_=proved_fixture()
    row.pop('document_metadata')
    row.update(metric='revenue',value=row['normalized_value'])
    folder=tmp_path/'data/official-evidence';folder.mkdir(parents=True)
    (folder/'financial_identity_citations.jsonl').write_text(json.dumps(row)+'\n',encoding='utf8')
    assert ('PNJ','revenue','2026-H1') not in load_official_citations(tmp_path)


def test_legacy_citation_files_never_resolve_conflicts_by_line_order(tmp_path):
    from canonical_fact_store import load_official_citations
    folder=tmp_path/'data/official-evidence';folder.mkdir(parents=True)
    path=folder/'financial_identity_citations.jsonl'
    base={'ticker':'AAA','metric':'revenue','reporting_period':'2024','currency':'VND','scale':'units'}
    rows=[{**base,'value':10,'citation_id':'c-1','evidence_id':'e-1'},
          {**base,'value':11,'citation_id':'c-2','evidence_id':'e-2'},
          {**base,'metric':'net_income','value':5,'citation_id':'n-2','evidence_id':'e-n2'},
          {**base,'metric':'net_income','value':5,'citation_id':'n-1','evidence_id':'e-n1'}]
    answers=[]
    for ordered in (rows,list(reversed(rows))):
        path.write_text(''.join(json.dumps(row)+'\n' for row in ordered),encoding='utf8')
        answers.append(load_official_citations(tmp_path))
    assert answers[0]==answers[1]
    assert ('AAA','revenue','2024') not in answers[0]
    assert answers[0][('AAA','net_income','2024')]['citation_id']=='n-1'


@pytest.mark.parametrize('change',[
    {'document_metadata':{'document':'bad'}},{'assurance_evidence':'bad'},
    {'value':999},{'source_locator':'https://unrelated.invalid/fixture.pdf'}])
def test_malformed_or_contradictory_proof_cannot_promote(change):
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture()
    row.update(change)
    assert admit_official_financial_fact(row,**context)['state']=='BLOCKED'


@pytest.mark.parametrize('manifest_present',[True,False])
def test_native_panel_adapter_cannot_promote_unadmitted_current_source(tmp_path,monkeypatch,manifest_present):
    import official_financial_pdf_page_evidence as pdf
    row,context=proved_fixture('2025',native_pdf=True)
    path=tmp_path/'fixture.pdf';path.write_bytes(context['retained_bytes'])
    source=context['source_record']
    if manifest_present:
        (tmp_path/'official_document_acquisition_manifest.json').write_text(json.dumps({'records':[source]}),encoding='utf8')
    # Isolate table extraction; exercise the actual current-panel admission against the owned bytes/pages.
    pages=[{'page_number':1,'page_text':context['document_pages'][1],'status':'TEXT_AVAILABLE','positioned_tokens':[]}]
    monkeypatch.setattr(pdf,'page_evidence',lambda **_:pages)
    candidate={**row,'fiscal_period':'2025','qualification_status':'OFFICIAL_FACT_QUALIFIED',
        'table_id':row['citation_id'],'page_number':1,'table_heading':'synthetic table',
        'period_column_label':'2025','extraction_method':'synthetic fixture','unit_scale':1,
        'source_span':row['source_span']}
    monkeypatch.setattr(pdf,'extract_candidates',lambda **_:([candidate],[]))
    artifact=pdf.build_artifact(document={**source,'official_url':source['canonical_url'],'retrieved_at':source['observed_at']},path=path)
    fact=artifact['p3f13_panel_facts'][0]
    assert fact['is_positive_authority'] is manifest_present
    assert fact['qualification_state']==('QUALIFIED' if manifest_present else 'UNQUALIFIED')


@pytest.mark.parametrize('negative',['not been reviewed','not yet independently reviewed','chua duoc soat xet'])
def test_expanded_negation_blocks_both_actual_recognizers(negative):
    text='BAO CAO SOAT XET hop nhat giua nien do hop dong dich vu soat xet so 2410 '+negative
    assert recognize_audit_or_review(text)['audit_or_review_status'] is None
    from tests.test_reviewed_interim_canonical_ingress import _materialization
    assert assurance.resolve_document_assurance_evidence(_materialization(text))['state']=='BLOCKED'


def test_registry_admitted_cross_issuer_redirect_does_not_bind_issuer():
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture()
    context['source_record']['final_url']='https://www.hoaphat.com.vn/test-only-synthetic-fixture.pdf'
    result=admit_official_financial_fact(row,**context)
    assert result['state']=='BLOCKED' and 'ISSUER_SOURCE_DOMAIN_MISMATCH' in result['reason_codes']


def _attachment_fixture(*, ticker="HPG", period="2026-H1", origin="file.hoaphat.com.vn", final=None):
    """Owned proof on explicit hosts; this is never a real HPG financial fact."""
    row, context = proved_fixture(period, ticker=ticker)
    url = "https://" + origin + "/test-only-synthetic-fixture.pdf"
    context["source_record"].update(canonical_url=url,
        final_url="https://" + (final or origin) + "/test-only-synthetic-fixture.pdf")
    row["source_locator"] = url
    row["document_metadata"]["document"]["source_locator"] = url
    return row, context


@pytest.mark.parametrize("period", ["2025", "2026-H1", "2026-Q2"])
@pytest.mark.parametrize("origin,final", [
    ("www.hoaphat.com.vn", "www.hoaphat.com.vn"),
    ("file.hoaphat.com.vn", "file.hoaphat.com.vn"),
    ("www.hoaphat.com.vn", "file.hoaphat.com.vn"),
    ("file.hoaphat.com.vn", "www.hoaphat.com.vn"),
])
def test_existing_hpg_attachment_binding_runs_whole_common_admission(period, origin, final):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture(period=period, origin=origin, final=final)
    before = deepcopy((row, context))
    result = admit_official_financial_fact(row, **context)
    assert result["state"] == "ADMITTED", result
    assert result["admission_basis"] == "RETAINED_SOURCE_REPLAY"
    assert (row, context) == before
    assert result == admit_official_financial_fact(deepcopy(row), **deepcopy(context))


@pytest.mark.parametrize("ticker", ["PNJ", "FPT", "VNM"])
def test_registered_hpg_attachment_host_cannot_bind_another_issuer(ticker):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture(ticker=ticker)
    result = admit_official_financial_fact(row, **context)
    assert result["state"] == "BLOCKED"
    assert "ISSUER_SOURCE_DOMAIN_MISMATCH" in result["reason_codes"]


@pytest.mark.parametrize("host", [
    "files.hoaphat.com.vn", "cdn.hoaphat.com.vn", "file-hoaphat.com.vn",
    "file.hoaphat.com.vn.evil.invalid",
])
def test_registry_host_alone_cannot_create_an_hpg_attachment_binding(host):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture(origin=host)
    issuer_source = next(s for s in context["registry"]["sources"] if s["source_id"] == "issuer_ir")
    issuer_source["allowed_hosts"].append(host)  # Synthetic approval cannot supply issuer linkage.
    result = admit_official_financial_fact(row, **context)
    assert result["state"] == "BLOCKED"
    assert "ISSUER_SOURCE_DOMAIN_MISMATCH" in result["reason_codes"]


@pytest.mark.parametrize("origin,final", [
    ("file.hoaphat.com.vn", "www.pnj.com.vn"),
    ("www.pnj.com.vn", "file.hoaphat.com.vn"),
])
def test_hpg_attachment_binding_rejects_cross_issuer_redirect_in_both_directions(origin, final):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture(origin=origin, final=final)
    result = admit_official_financial_fact(row, **context)
    assert result["state"] == "BLOCKED"
    assert "ISSUER_SOURCE_DOMAIN_MISMATCH" in result["reason_codes"]


@pytest.mark.parametrize("final", ["file.hoaphat.com.vn", "www.hoaphat.com.vn"])
@pytest.mark.parametrize("restriction", ["host_removed", "class_removed", "activation_removed"])
def test_existing_hpg_attachment_relationship_cannot_bypass_current_registry(final, restriction):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture(final=final)
    issuer_source = next(s for s in context["registry"]["sources"] if s["source_id"] == "issuer_ir")
    if restriction == "host_removed":
        issuer_source["allowed_hosts"].remove("file.hoaphat.com.vn")
    elif restriction == "class_removed":
        issuer_source.setdefault("host_document_types", {})["file.hoaphat.com.vn"] = ["audited_annual_financial_statements"]
    else:
        issuer_source["activation"] = "declared"
    result = admit_official_financial_fact(row, **context)
    assert result["state"] == "BLOCKED"
    assert "OFFICIAL_SOURCE_NOT_ADMITTED" in result["reason_codes"]


@pytest.mark.parametrize("mutation,reason", [
    ("source_ticker", "RETAINED_SOURCE_IDENTITY_MISMATCH"),
    ("metadata_issuer", "DOCUMENT_ISSUER_IDENTITY_MISMATCH"),
    ("literal_issuer", "RETAINED_ISSUER_LITERAL_PROOF_UNAVAILABLE"),
    ("bytes", "RETAINED_DOCUMENT_HASH_MISMATCH"),
    ("assurance", "DOCUMENT_ASSURANCE_PROOF_NOT_BOUND"),
    ("period", "SOURCE_PERIOD_NOT_ADMITTED"),
    ("cutoff", "AFTER_KNOWLEDGE_CUTOFF"),
])
def test_hpg_attachment_host_does_not_replace_independent_document_proofs(mutation, reason):
    from official_financial_filing_evidence import admit_official_financial_fact
    row, context = _attachment_fixture()
    if mutation == "source_ticker":
        context["source_record"]["ticker"] = "PNJ"
    elif mutation == "metadata_issuer":
        row["document_metadata"]["issuer_identity"] = "PNJ"
    elif mutation == "literal_issuer":
        context["document_pages"][1] = context["document_pages"][1].replace("HPG", "PNJ")
    elif mutation == "bytes":
        context["retained_bytes"] += b"changed"
    elif mutation == "assurance":
        row["assurance_evidence"]["document_sha256"] = "f" * 64
    elif mutation == "period":
        row["reporting_period"] = "2026-Q3"
    else:
        context["cutoff"] = "2026-10-06T00:00:00Z"
    result = admit_official_financial_fact(row, **context)
    assert result["state"] != "ADMITTED"
    assert reason in result["reason_codes"]


def test_common_rule_rejects_crossed_line_identity_without_relying_on_adapter():
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture(metric='net_income')
    row['line_code']='61'
    result=admit_official_financial_fact(row,**context)
    assert result['state']=='BLOCKED' and 'METRIC_LINE_CODE_IDENTITY_CONFLICT' in result['reason_codes']


@pytest.mark.parametrize("mutation",["bytes","source","ticker","assurance","metadata","period","units","cutoff"])
def test_shared_admission_refuses_broken_bindings(mutation):
    from official_financial_filing_evidence import admit_official_financial_fact
    row,context=proved_fixture()
    if mutation=="bytes": context["retained_bytes"]=b"wrong original bytes"
    if mutation=="source": context["source_record"]["final_url"]="https://unregistered.invalid/wrong.pdf"
    if mutation=="ticker": row["ticker"]="FAKE"
    if mutation=="assurance": row["assurance_evidence"]["document_sha256"]="f"*64
    if mutation=="metadata": row["document_metadata"]["qualification_status"]="DOCUMENT_METADATA_BLOCKED"
    if mutation=="period": row["reporting_period"]="2026-Q3"
    if mutation=="units": row["unit_scale"]=1_000_000
    if mutation=="cutoff": context["cutoff"]="2026-10-06T00:00:00Z"
    assert admit_official_financial_fact(row,**context)["state"]=="BLOCKED"


def test_publication_validates_whole_batch_and_retains_history():
    from official_financial_filing_evidence import admit_official_financial_fact, prepare_official_overlay_publication
    row,context=proved_fixture()
    admission=lambda r:admit_official_financial_fact(r,**context)
    history='{"historical_marker":true}\n'
    result=prepare_official_overlay_publication([row],retained_text=history,admission=admission)
    assert result.startswith(history)
    bad=deepcopy(row);bad["normalized_value"]=124
    with pytest.raises(ValueError):
        prepare_official_overlay_publication([row,bad],retained_text=history,admission=admission)
    with pytest.raises(ValueError,match="CONFLICT"):
        prepare_official_overlay_publication([row],retained_text=json.dumps(bad)+"\n",admission=admission)


@pytest.mark.parametrize("href",["2026-q3-interim-audited-2025.pdf","2025-audit-engagement.pdf"])
def test_ir_discovery_does_not_reclassify_excluded_documents(href):
    assert refresh.parse_index_document_links('<a href="'+href+'">financial statement</a>',"https://synthetic.invalid/")==[]


@pytest.mark.parametrize("title",["Thông báo ký hợp đồng kiểm toán báo cáo tài chính năm 2026",
    "Báo cáo tài chính quý III năm 2026"])
def test_hnx_discovery_does_not_call_engagement_or_q3_an_annual_statement(title):
    from stocklookup_core.evidence.hnx_financial_filing_scaleout import discover
    feed=('<rss><channel><item><title>'+title+'</title><link>https://www.hnx.vn/fixture.html</link></item></channel></rss>').encode("utf8")
    registry={"sources":[{"source_id":"hnx","authority":"HNX","allowed_hosts":["www.hnx.vn"],
        "document_types":["audited_annual_financial_statements","reviewed_interim_financial_statements"]}]}
    assert discover(feed,registry)==[]


def test_negated_retained_assurance_cannot_qualify_at_resolver():
    row,_=proved_fixture()
    text="BAO CAO SOAT XET hop nhat giua nien do hop dong dich vu soat xet so 2410 khong duoc soat xet"
    page={"page_number":1,"ocr_derived_text_evidence":{"tokens":[{"text":word,"token_id":str(i),"raw_token_order":i}
          for i,word in enumerate(text.split())]}}
    result=assurance.resolve_document_assurance_evidence({"document_sha256":row["document_sha256"],"pages":[page]})
    assert result["state"]=="BLOCKED"


def test_canonical_policy_does_not_admit_direct_citation_labels():
    from canonical_financial_qualification_policy import evaluate_fact
    from tests.test_canonical_financial_qualification_policy import _fact
    fact=_fact(status="qualified");fact.update(citation_id="fake-citation",evidence_id="fake-evidence")
    assert evaluate_fact(fact)["status"]!="qualified"


def test_metadata_blocked_row_cannot_reach_fundamental_or_valuation():
    from tests.test_current_official_evidence_projection import baseline
    from market_wide_current_fundamental_research import project_session
    from official_legacy_precedence import official_is_value_qualified
    row,_=proved_fixture()
    row["document_metadata"]["qualification_status"]="DOCUMENT_METADATA_BLOCKED"
    result=project_session(baseline=baseline(),official_rows=[row],session="2026-10-08",cutoff="2026-10-08T15:00:00+07:00")
    assert not any(r["official_field_context"] for r in result["records"].values())
    assert not official_is_value_qualified(row)


@pytest.mark.parametrize("fail_at",[2,3])
def test_publication_promotion_failure_restores_all_original_artifacts(tmp_path,fail_at):
    from atomic_io import atomic_write_file
    from official_financial_filing_evidence import admit_official_financial_fact, prepare_official_overlay_publication
    from stocklookup_core.evidence.official_document_qualification import _publish_official_artifacts
    row,context=proved_fixture()
    facts=tmp_path/refresh.PUBLIC_FACTS
    paths=[facts,tmp_path/"precedence.jsonl",tmp_path/"report.json"]
    originals={path:b'{"original":true}\n' for path in paths}
    for path,content in originals.items(): path.write_bytes(content)
    prepared=prepare_official_overlay_publication([row],retained_text=facts.read_text(),
        admission=lambda r:admit_official_financial_fact(r,**context))
    calls=[]
    def writer(path,content):
        calls.append(path)
        atomic_write_file(path,content)
        if len(calls)==fail_at: raise OSError("synthetic promotion failure")
    with pytest.raises(OSError,match="synthetic"):
        _publish_official_artifacts({facts:prepared,paths[1]:'{"new":true}\n',paths[2]:'{"new":true}\n'},commit_path=facts,writer=writer)
    assert all(path.read_bytes()==content for path,content in originals.items())
    if fail_at==3: assert calls[-1]==facts


def test_financial_v2_official_equity_respects_cutoff_and_never_follows_input_order():
    from stocklookup_core.valuation.current_research_valuation_context import _official_equity_row
    rows=_retained_rows()
    qns=next(r for r in rows if r["ticker"]=="QNS")
    assert _official_equity_row(rows,"QNS")==qns
    assert _official_equity_row(rows,"QNS",cutoff="2026-10-07T15:00:00+07:00") is None
    assert _official_equity_row(rows,"QNS",cutoff="2026-10-08T15:00:00+07:00")==qns
    # Annual audited context rows are research context only; V2 valuation cannot widen that verdict.
    assert _official_equity_row(rows,"PVD") is None and _official_equity_row(rows,"FPT") is None
    assert _official_equity_row(list(reversed(rows)),"QNS")==_official_equity_row(rows,"QNS")


def test_financial_v2_equal_time_conflicting_official_equity_fails_closed(monkeypatch):
    from tests.financial_source_fixture import bind_fixture_source, install_synthetic_admission
    from stocklookup_core.valuation.current_research_valuation_context import _official_equity_row
    install_synthetic_admission(monkeypatch)
    template={"ticker":"PNJ","canonical_metric":"shareholders_equity","reporting_period":"2026-H1",
        "period_start":"2026-01-01","period_end":"2026-06-30","period_type":"interim","statement_scope":"consolidated",
        "currency":"VND","qualification_state":"QUALIFIED","observed_at":"2026-10-07T00:00:00Z",
        "knowledge_available_at":"2026-10-07T00:00:00Z"}
    first=bind_fixture_source({**template,"normalized_value":100})[0]
    second=bind_fixture_source({**template,"normalized_value":101})[0]
    assert _official_equity_row([first],"PNJ")==first
    assert _official_equity_row([first,second],"PNJ") is None
    assert _official_equity_row([second,first],"PNJ") is None


def test_stale_projected_copy_of_a_qualified_row_cannot_requalify():
    from tests.test_current_official_evidence_projection import baseline
    from market_wide_current_fundamental_research import project_session
    rows=_retained_rows()
    session=dict(session="2026-10-08",cutoff="2026-10-08T15:00:00+07:00")
    first=project_session(baseline=baseline(),official_rows=rows,**session)
    cached=[deepcopy(f) for r in first["records"].values() for f in r["official_field_context"]]
    assert cached and all(f.get("factual_status") for f in cached)
    replay=project_session(baseline=baseline(),official_rows=cached,**session)
    assert not any(r["official_field_context"] for r in replay["records"].values())
