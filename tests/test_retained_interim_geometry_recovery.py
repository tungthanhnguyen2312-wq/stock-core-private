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
    # Neither a damaged letter nor missing wrapped parent text can be guessed.
    assert 'attributable_net_income' not in facts
    assert any(b['canonical_metric']=='attributable_net_income' for b in result['blocked_candidates'])


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
