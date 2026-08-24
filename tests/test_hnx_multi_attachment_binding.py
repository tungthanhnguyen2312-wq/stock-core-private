from __future__ import annotations
import hashlib
from hnx_multi_attachment_binding import parse_parent_attachments, _attachment_type

def parent(detail:bytes)->dict:
 return {'detail_sha256':hashlib.sha256(detail).hexdigest(),'detail_url':'https://www.hnx.vn/p.html','published_at':'2026-08-24'}

def test_classifies_each_sibling_without_scope_propagation():
 detail=b'''<div class="Box-Noidung"></div><div class="divLstFileAttach"><p><a href="https://owa.hnx.vn/a_Consolidated.pdf">Consolidated financial statements</a></p><p><a href="https://owa.hnx.vn/b_Separate.pdf">Separate financial statements</a></p><p><a href="https://owa.hnx.vn/c_Explanations.pdf">Explanations</a></p></div></div>'''
 result=parse_parent_attachments(parent=parent(detail),detail_bytes=detail,retained_sha_by_url={'https://owa.hnx.vn/a_Consolidated.pdf':'a'})
 assert [x['attachment_type'] for x in result['attachments']]==['CONSOLIDATED_FINANCIAL_STATEMENTS','SEPARATE_FINANCIAL_STATEMENTS','EXPLANATORY_LETTER']
 assert [x['attachment_scope'] for x in result['attachments']]==['consolidated','separate','UNKNOWN']
 assert all(x['ticker'] is None for x in result['attachments'])

def test_filename_only_financial_statement_is_not_an_auditor_report():
 assert _attachment_type('AuditedFinancialStatements_6M.pdf','x.pdf')[0]=='UNKNOWN'
 assert _attachment_type('Auditor review report','x.pdf')[0]=='AUDITOR_REVIEW_REPORT'
 assert _attachment_type('GiaTrinhLienQuanDenBCTC.pdf','x.pdf')[0]=='EXPLANATORY_LETTER'
