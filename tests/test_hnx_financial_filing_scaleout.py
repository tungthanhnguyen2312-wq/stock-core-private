from hnx_financial_filing_scaleout import _pdf_metadata, data_gap_matrix, discover

def test_discovery_uses_only_financial_titles_and_preserves_separate_scope():
    feed=b'''<rss><channel><item><title>B\xc3\xa1o c\xc3\xa1o t\xc3\xa0i ch\xc3\xadnh b\xc3\xa1n ni\xc3\xaan n\xc4\x83m 2026 (c\xc3\xb4ng ty m\xe1\xba\xb9)</title><link>https://www.hnx.vn/a.html</link><pubDate>Mon, 24 Aug 2026 09:38:44 +0700</pubDate></item></channel></rss>'''
    registry={'sources':[{'source_id':'hnx','authority':'HNX','allowed_hosts':['www.hnx.vn'],'document_types':['reviewed_interim_financial_statements']}]}
    row=discover(feed,registry)[0]
    assert row['reporting_period']=='2026-H1' and row['title_scope']=='separate'

def test_pdf_extracts_only_single_line_exact_value_with_explicit_unit_and_scope():
    metadata,facts=_pdf_metadata(b'not a PDF','2026-H1','UNKNOWN')
    assert metadata['parser_status']=='NEEDS_OCR' and facts==[]

def test_gap_matrix_is_deterministic_and_never_turns_missing_into_zero():
    artifact={'artifact_identity':'a','documents':[{'ticker':None}],'facts':[],'coverage':{'resolved_tickers':[]}}
    assert data_gap_matrix(artifact)==data_gap_matrix(artifact)
    assert data_gap_matrix(artifact)['missing_is_zero'] is False
