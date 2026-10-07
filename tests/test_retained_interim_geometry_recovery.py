"""Offline positioned-token regression; retained PDF/image bytes are not fixtures."""
import copy
import json
from pathlib import Path

import pytest
from official_financial_ocr_table_evidence import (
    qualify_table_facts, resolve_scoped_unit_evidence,
    resolve_scoped_statement_scope_evidence, row_label_supports_metric,
    _pages_by_statement_family,
)
from official_financial_structural_table import match_geometry_table_row

FIXTURES = Path(__file__).parent / 'fixtures' / 'retained_interim_geometry'


def test_audited_annual_split_baseline_header_requires_literal_source_line():
    from official_financial_assurance_evidence import resolve_document_assurance_evidence
    mat = materialization('HPG_FY25')
    assert resolve_document_assurance_evidence(mat['front'])['state'] == 'QUALIFIED'
    result = qualify_table_facts(mat['statements'], ticker='HPG', reporting_period='2025')
    assert {f['canonical_metric']: f['value'] for f in result['qualified_facts']} == {
        'revenue': 156116094618482, 'net_income': 15514931571606}
    # Superscript characters in parent profit remain unreadable, not repaired.
    assert any(b['canonical_metric'] == 'attributable_net_income' for b in result['blocked_candidates'])
    broken = copy.deepcopy(mat['statements'])
    for token in broken['pages'][0]['ocr_derived_text_evidence']['tokens']:
        if token['text'] == 'nay':
            token['tsv_hierarchy']['line_num'] += 1000
    assert not qualify_table_facts(broken, ticker='HPG', reporting_period='2025')['qualified_facts']
    damaged = copy.deepcopy(mat['statements'])
    for token in damaged['pages'][0]['ocr_derived_text_evidence']['tokens']:
        if token['text'] == 'nay':
            token['text'] = 'naY0'
    assert not qualify_table_facts(damaged, ticker='HPG', reporting_period='2025')['qualified_facts']


def materialization(ticker):
    return json.loads((FIXTURES / (ticker + '.json')).read_text(encoding='utf-8'))


@pytest.mark.parametrize('ticker,value', [('PNJ',728386009054), ('VRE',3214788000000)])
def test_total_profit_requires_label_and_preserves_exact_scale(ticker, value):
    mat = materialization(ticker)
    result = qualify_table_facts(mat, ticker=ticker, reporting_period='2026-H1',
        scoped_unit_evidence=resolve_scoped_unit_evidence(mat),
        scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(mat))
    facts = {f['canonical_metric']: f for f in result['qualified_facts']}
    assert facts['net_income']['value'] == value
    assert facts['net_income']['source_lineage']['line_code'] == '60'
    assert facts['net_income']['currency'] == 'VND'
    if ticker == 'PNJ':
        assert facts['attributable_net_income']['value'] == 728529788872
        row = facts['attributable_net_income']['source_lineage']['row_object']
        assert row['label_binding']['contract'] == 'tsv_code_line_label/v1'
        assert 'khongkiemsoat' not in row['reconstructed_label'].replace(' ', '').lower()
    else:
        # A damaged identity-bearing letter is never repaired.
        assert 'attributable_net_income' not in facts
        assert any(b['canonical_metric']=='attributable_net_income' for b in result['blocked_candidates'])


def test_disposal_component_requires_full_literal_label_and_preserves_scale():
    mat = materialization('VRE')
    result = qualify_table_facts(mat,ticker='VRE',reporting_period='2026-H1',
        include_earnings_quality_components=True,scoped_unit_evidence=resolve_scoped_unit_evidence(mat),
        scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(mat))
    component = next(f for f in result['qualified_facts'] if f['canonical_metric']=='investment_property_disposal_result')
    assert component['value']==184751000000 and component['unit_scale']==1000000
    row = component['source_lineage']['row_object']
    assert row['current_raw_value']=='184.751' and row['comparative_raw_value']=='143'
    assert row_label_supports_metric(component['canonical_metric'],row['reconstructed_label'])
    assert not row_label_supports_metric(component['canonical_metric'],'thanh ly bat dau')
    assert not row_label_supports_metric(component['canonical_metric'],'thanh ly bat dong san dAu tO')
    assert 'cấp dich vu' not in row['reconstructed_label']


def test_code_on_second_label_line_preserves_all_literal_usd_income_fields():
    mat = materialization('PVD')
    result = qualify_table_facts(mat,ticker='PVD',reporting_period='2026-H1',
        include_earnings_quality_components=True,scoped_unit_evidence=resolve_scoped_unit_evidence(mat),
        scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(mat))
    assert {f['canonical_metric']:(f['value'],f['currency']) for f in result['qualified_facts']} == {
        'revenue':(245730824,'USD'), 'net_income':(18272708,'USD'),
        'attributable_net_income':(17920760,'USD')}
    profit = next(f for f in result['qualified_facts'] if f['canonical_metric']=='net_income')
    assert profit['source_lineage']['row_object']['label_binding']['contract']=='physical_midpoint_label/v1'


def test_missing_parent_wrap_and_damaged_next_code_cannot_cross_map_label():
    mat = materialization('PNJ')
    for page in mat['pages']:
        tokens = page['ocr_derived_text_evidence']['tokens']
        page['ocr_derived_text_evidence']['tokens'] = [t for t in tokens if t['tsv_hierarchy']['line_num'] != 33]
        for t in page['ocr_derived_text_evidence']['tokens']:
            if t['text']=='62':
                t['text']='6Z'
    result = qualify_table_facts(mat,ticker='PNJ',reporting_period='2026-H1')
    assert not any(f['canonical_metric']=='attributable_net_income' for f in result['qualified_facts'])


def test_two_sided_labels_fail_closed():
    mat = materialization('VRE')
    page = next(p for p in _pages_by_statement_family(mat)['income_statement']
                if match_geometry_table_row(p,line_code='60',target_period='2026-H1'))
    match = match_geometry_table_row(page,line_code='60',target_period='2026-H1')
    assert 'Lợi' in match['line_text']
    changed = copy.deepcopy(page)
    token = copy.deepcopy(changed['positioned_tokens'][0])
    token.update(text='Other',x0=990,x1=1040,top=match['row_object']['current_value_bbox']['top'],
                 bottom=match['row_object']['current_value_bbox']['bottom'],raw_token_order=9999)
    changed['positioned_tokens'].append(token)
    assert match_geometry_table_row(changed,line_code='60',target_period='2026-H1') is None


def test_readable_label_cannot_repair_a_damaged_numeric_cell():
    mat = materialization('VRE')
    for page in mat['pages']:
        for token in page.get('ocr_derived_text_evidence', {}).get('tokens', []):
            if token['text'] == '3.214.788':
                token['text'] = '3.214.78O'
    result = qualify_table_facts(mat,ticker='VRE',reporting_period='2026-H1')
    assert not any(f['canonical_metric']=='net_income' for f in result['qualified_facts'])
    assert any(b['canonical_metric']=='net_income' and b['reason']=='OCR_NUMERIC_AMBIGUITY'
               for b in result['blocked_candidates'])


def test_word_spacing_does_not_repair_letter_identity_or_cross_map_profit():
    assert row_label_supports_metric('net_income','Loinhuan sau thuế TNDN')
    assert not row_label_supports_metric('net_income','Loi nhuan sau thue congtyme')
    assert not row_label_supports_metric('attributable_net_income','Céng ty me')
    assert not row_label_supports_metric('attributable_net_income','Cong ty me khongkiemsoat')
