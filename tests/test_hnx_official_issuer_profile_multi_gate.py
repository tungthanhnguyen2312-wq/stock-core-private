from __future__ import annotations
from hnx_official_issuer_profile_multi_gate import _date,_number,parse_profile

def test_profile_keeps_kllh_and_klny_distinct_and_parses_explicit_ex_date():
 raw='''<div class="dktimkiem_row row_inline"><div class="dktimkiem_cell_title"><label>KLLH (Cổ phiếu)</label></div><div class="dktimkiem_cell_content">100.000</div></div><div class="dktimkiem_row row_inline"><div class="dktimkiem_cell_title"><label>KLNY (Cổ phiếu)</label></div><div class="dktimkiem_cell_content">90.000</div></div><div id="divGiaoDichGLDT"><tr><td>1</td><td>01/02/2026</td><td>02/02/2026</td><td>03/02/2026</td><td>Trả cổ tức bằng tiền</td></tr></div><div id="divBaoCaoDK">'''.encode()
 out=parse_profile(raw,identity={'STOCK_CODE':'ABC','NAME':'Issuer','MARKETCODE':'NY','CARBOND_TYPE':0},retention={'official_url':'u','retrieved_at':'t','sha256':'h'})
 assert out['hnx_kllh_shares']==100000 and out['hnx_klny_shares']==90000
 assert out['events'][0]['ex_date']=='2026-02-01' and out['events'][0]['record_date']=='2026-02-02'
 assert out['common_shares_outstanding_result'].startswith('UNPROVEN')

def test_date_and_number_never_default_missing_to_zero():
 assert _date('') is None and _number('') is None

def test_upcom_registered_trading_volume_is_not_aliased_to_klny():
 raw='''<div class="dktimkiem_row row_inline"><div class="dktimkiem_cell_title"><label>KLLH (Cổ phiếu)</label></div><div class="dktimkiem_cell_content">100</div></div><div class="dktimkiem_row row_inline"><div class="dktimkiem_cell_title"><label>KLĐKGD (Cổ phiếu)</label></div><div class="dktimkiem_cell_content">90</div></div>'''.encode()
 out=parse_profile(raw,identity={'STOCK_CODE':'ABC','NAME':'Issuer','MARKETCODE':'UC','CARBOND_TYPE':0},retention={'official_url':'u','retrieved_at':'t','sha256':'h'})
 assert out['hnx_klny_shares'] is None and out['hnx_kldkgd_shares']==90

def test_rights_issue_is_distinct_from_cash_dividend_and_agm():
 raw='''<div id="divGiaoDichGLDT"><tr><td>1</td><td>01/02/2026</td><td>02/02/2026</td><td></td><td>Phát hành CP cho cổ đông hiện hữu</td></tr></div><div id="divBaoCaoDK">'''.encode()
 out=parse_profile(raw,identity={'STOCK_CODE':'ABC','NAME':'Issuer','MARKETCODE':'NY','CARBOND_TYPE':0},retention={'official_url':'u','retrieved_at':'t','sha256':'h'})
 assert out['events'][0]['event_type']=='RIGHTS_ISSUE' and out['events'][0]['price_adjustment_candidate'] is True

def test_non_equity_identity_fails_common_equity_filter():
 out=parse_profile(b'',identity={'STOCK_CODE':'BOND','NAME':'Issuer','MARKETCODE':'NY','CARBOND_TYPE':1},retention={'official_url':'u','retrieved_at':'t','sha256':'h'})
 assert out['common_equity_eligible'] is False and out['instrument_class']=='INELIGIBLE_OR_UNKNOWN'
