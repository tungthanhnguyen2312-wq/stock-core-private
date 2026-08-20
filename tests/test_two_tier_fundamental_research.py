import inspect
from two_tier_fundamental_research import provider_fact,PROVIDER,FORBIDDEN
def test_provider_never_claims_official():
 r=provider_fact({'raw_value':1,'provider':'VCI','raw_item_id':'assets','warnings':['unknown']},'total_assets');assert r['authority_state']==PROVIDER and not r['official_citation_claim'] and 'official_label' in FORBIDDEN
def test_no_ticker_branch():assert 'if ticker ==' not in inspect.getsource(provider_fact)
