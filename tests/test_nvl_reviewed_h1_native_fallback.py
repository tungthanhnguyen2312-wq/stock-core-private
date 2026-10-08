"""Retained reviewed source stays distinct from native text and financial values."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import official_financial_ocr_table_evidence as ocr
import official_financial_pdf_page_evidence as native
from official_financial_assurance_evidence import resolve_document_assurance_evidence
FIXTURE=Path(__file__).parent / "fixtures/nvl_reviewed_h1/positioned_source_tokens.json"

def test_actual_reviewed_source_has_no_qualified_financial_values():
    m=json.loads(FIXTURE.read_text(encoding="utf8"))
    assurance=resolve_document_assurance_evidence(m)
    assert assurance['state']=='QUALIFIED' and assurance['audit_or_review_status']=='reviewed'
    assert assurance['page_number']==6
    q=ocr.qualify_table_facts(m,ticker='NVL',reporting_period='2026-H1',
        scoped_unit_evidence=ocr.resolve_scoped_unit_evidence(m),
        scoped_statement_scope_evidence=ocr.resolve_scoped_statement_scope_evidence(m))
    assert q['qualified_facts']==[]
    assert all(p['route']=='UNQUALIFIED_NATIVE_TSV_OCR' for p in m['pages'])
    assert all(p['native_failure_evidence']['candidate_count']==0 for p in m['pages'])
    assert any('²' in t['text'] for p in m['pages'] for t in p['ocr_derived_text_evidence']['tokens'])

@pytest.fixture
def setup_native(tmp_path,monkeypatch):
    content=b'fixed native source';(tmp_path/'source.pdf').write_bytes(content)
    record={'document_id':'doc','sha256':hashlib.sha256(content).hexdigest(), 'relative_path':'source.pdf',
            'ticker':'NVL','canonical_url':'https://www.novaland.com.vn/source.pdf','observed_at':'2026-10-08T00:00:00Z'}
    class Document:
        page_count=1
        def __getitem__(self,index):return SimpleNamespace(get_text=lambda *args:'broken native labels')
        def close(self):pass
    monkeypatch.setitem(sys.modules,'fitz',SimpleNamespace(open=lambda *args:Document()))
    tsv=b'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t95\tRaw\n'
    monkeypatch.setattr(ocr.subprocess,'run',lambda args,**kwargs: SimpleNamespace(stdout='test engine\n' if '--version' in args else tsv))
    monkeypatch.setattr(ocr,'_render_image_bytes',lambda *args: (b'fixed image',{'rendered_image_sha256':'img'}))
    monkeypatch.setattr(native,'build_artifact',lambda **kwargs:{'artifact_identity':'native-proof', 'fact_candidates':[],
        'p3f13_panel_facts':[],'page_evidence':[{'page_number':1,'page_text':'broken native labels'}]})
    return tmp_path,record

def test_default_does_not_ocr_a_text_layer(setup_native,monkeypatch):
    root,record=setup_native
    monkeypatch.setattr(ocr,'_render_image_bytes',lambda *args:pytest.fail('default re-read native page'))
    result=ocr.materialize_tsv_pages(record,evidence_root=root,pages=(1,))
    assert result['pages'][0]['route']=='NATIVE_TEXT_AVAILABLE_USE_NATIVE_PATH'

def test_explicit_zero_candidate_fallback_preserves_both_proofs(setup_native):
    root,record=setup_native
    page=ocr.materialize_tsv_pages(record,evidence_root=root,pages=(1,),allow_unqualified_native_fallback=True)['pages'][0]
    assert page['route']=='UNQUALIFIED_NATIVE_TSV_OCR'
    assert page['ocr_derived_text_evidence']['tokens'][0]['text']=='Raw'
    assert page['source_image_evidence']['document_sha256']==record['sha256']
    assert page['native_failure_evidence']['native_artifact_identity']=='native-proof'
    assert page['native_failure_evidence']['native_page_text_sha256']['1']

@pytest.mark.parametrize('key',['fact_candidates','p3f13_panel_facts'])
def test_native_candidates_refuse_supplement_or_replacement(setup_native,monkeypatch,key):
    root,record=setup_native
    monkeypatch.setattr(native,'build_artifact',lambda **kwargs:{key:[{'value':123}]})
    monkeypatch.setattr(ocr,'_render_image_bytes',lambda *args:pytest.fail('re-read qualified native source'))
    with pytest.raises(ValueError,match='NATIVE_FINANCIAL_CANDIDATES_PRESENT'):
        ocr.materialize_tsv_pages(record,evidence_root=root,pages=(1,),allow_unqualified_native_fallback=True)

def test_hash_and_page_guards_precede_native_fallback(setup_native):
    root,record=setup_native
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        ocr.materialize_tsv_pages({**record,'sha256':'0'*64},evidence_root=root,pages=(1,),allow_unqualified_native_fallback=True)
    with pytest.raises(ValueError,match='PAGE_OUT_OF_RANGE'):
        ocr.materialize_tsv_pages(record,evidence_root=root,pages=(2,),allow_unqualified_native_fallback=True)

@pytest.mark.parametrize('ticker',['VCB','SSI','EVF','UNKNOWN'])
def test_specialist_or_unknown_entity_cannot_enter_corporate_fallback(setup_native,monkeypatch,ticker):
    root,record=setup_native
    monkeypatch.setattr(native,'build_artifact',lambda **kwargs:pytest.fail('specialist forced through corporate extractor'))
    with pytest.raises(ValueError,match='REQUIRES_DECLARED_CORPORATE_ISSUER'):
        ocr.materialize_tsv_pages({**record,'ticker':ticker},evidence_root=root,pages=(1,),allow_unqualified_native_fallback=True)
