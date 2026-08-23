from current_macro_regime import build, content_identity, session_context

def row(identifier,value,previous,release=None):
 return {'indicator_id':identifier,'country_or_region':'X','category':'x','value':value,'unit':'x','observation_date':'2026-08-20','released_at':release,'source':'official','source_identity':identifier,'url':'https://official.example','retrieved_at':'2026-08-24T00:00:00Z','freshness':{'status':'CURRENT_RESEARCH_NOT_HISTORICAL_PIT'},'revision_state':'UNKNOWN','authority':'OFFICIAL_PUBLIC_SOURCE','status':'AVAILABLE','limitations':[],'previous_observation_date':'2026-08-19','previous_value':previous,'raw_payload_sha256':'a'}
def artifact():
 rows=[row('us_fed_funds',3.5,3.6),row('us_cpi',300,299),row('us_treasury_2y',4,3.9),row('us_treasury_10y',4,4),row('usd_emerging_markets',120,121),row('wti_oil',70,69),row('vn_cpi_yoy',3,3.1)]
 rows += [{**row(x,None,None),'status':'UNAVAILABLE'} for x in ('vn_policy_rate','vn_usd_vnd','vn_credit_growth','vn_system_liquidity','vn_government_bond_yield')]
 return build(observations=rows,raw_sources=[],retrieved_at='2026-08-24T00:00:00Z')
def test_deterministic_axes_and_identity():
 a=artifact(); assert content_identity(a)['artifact_sha256']==a['artifact_sha256']; assert a['state_axes']['GLOBAL_RATES']['state']=='EASING'; assert a['state_axes']['USD_PRESSURE']['state']=='EASING'
def test_release_semantics_fail_closed_for_earlier_equity_session():
 a=artifact(); assert session_context(a,'2026-08-21')['status']=='UNAVAILABLE'; a['current_research_as_of']='2026-08-20'; assert session_context(a,'2026-08-21')['status']=='AVAILABLE'
def test_missing_is_never_zero():
 a=artifact(); assert a['observations']['vn_policy_rate']['value'] is None; assert a['state_axes']['DOMESTIC_RATES']['state']=='UNKNOWN'
