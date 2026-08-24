from __future__ import annotations
from hnx_enumerable_universe_kllh_event_disclosure_scaleout import _content, _last_page, _total, parse_disclosures, parse_events, parse_list

CAPTURE = {'official_url': 'https://hnx.vn/x', 'sha256': 'a' * 64}
LIST = '''<tbody><tr><td>1</td><td>AAA</td><td>Issuer</td><td>Industry</td><td>01/02/2026</td><td>120.000</td><td>100.000</td></tr></tbody><div>Tổng số 1 bản ghi</div>'''
UPCOM_LIST = '''<tbody><tr><td>1</td><td>AAA</td><td>Issuer</td><td>01/02/2026</td><td>120.000</td><td>100.000</td></tr></tbody><div>Tổng số 1 bản ghi</div>'''
EVENT = '''<tbody><tr><td>1</td><td>AAA</td><td>01/02/2026</td><td>02/02/2026</td><td>03/02/2026</td><td>Trả cổ tức bằng tiền</td></tr></tbody><div>Tổng số 1 bản ghi</div>'''
DISCLOSURE = '''<tbody><tr><td>1</td><td>01/02/2026 10:00</td><td>AAA</td><td><a onclick="return funcViewDetailArticlesByID(123,1)">Báo cáo tài chính</a></td><td>x</td></tr></tbody><div>Tổng số 1 bản ghi</div>'''

def test_list_keeps_kllh_and_list_quantity_separate():
    row = parse_list(LIST, market='HNX_LISTED', capture=CAPTURE)[0]
    assert row['hnx_kllh_shares'] == 100000 and row['source_listing_or_registration_quantity'] == 120000
    assert row['instrument_class'] == 'EXCHANGE_STOCK_LIST_CANDIDATE'

def test_upcom_registered_quantity_is_not_misparsed_as_sector_or_klny():
    row = parse_list(UPCOM_LIST, market='UPCOM', capture=CAPTURE)[0]
    assert row['source_quantity_label'] == 'KLĐKGD (Cổ phiếu)' and row['sector_label'] is None

def test_event_requires_explicit_ex_date_and_never_uses_record_date():
    row = parse_events(EVENT, market='UPCOM', capture=CAPTURE)[0]
    assert row['ex_date'] == '2026-02-01' and row['record_date'] == '2026-02-02'
    assert row['event_type'] == 'CASH_DIVIDEND' and row['qualification'] == 'EX_DATE_OFFICIAL_QUALIFIED'

def test_disclosure_keeps_exact_index_identity():
    row = parse_disclosures(DISCLOSURE, market='HNX_LISTED', capture=CAPTURE)[0]
    assert (row['article_id'], row['ticker'], row['published_at']) == ('123', 'AAA', '2026-02-01')
    assert row['financial_statement_candidate'] is True

def test_total_and_terminal_page_contracts_fail_closed():
    assert _total(LIST) == 1
    assert _last_page('<span id="end">>></span> pageNextTin(7)', 70, 10) == 7
    assert _content(b'{"Content":"<tbody></tbody>"}') == '<tbody></tbody>'
