import inspect
from official_financial_source_discovery import discover_routes
REG={'sources':[{'activation':'approved','allowed_hosts':['issuer.example']}]}
def test_discovery_is_not_approval_without_registry_host():
 r=discover_routes([{'ticker':'AAA'}],{'AAA':{'candidate_url':'https://mirror.example/x','issuer_domain_evidence':'claim'}},REG)
 assert r['route_candidates'][0]['disposition']=='CANDIDATE_ROUTE_NEEDS_MORE_EVIDENCE'
def test_identity_requirement_and_determinism():
 a=discover_routes([{'ticker':'BBB'}],{'BBB':{'candidate_url':'https://issuer.example/x'}},REG);b=discover_routes([{'ticker':'BBB'}],{'BBB':{'candidate_url':'https://issuer.example/x'}},REG)
 assert a['route_candidates'][0]['disposition']=='IDENTITY_AMBIGUOUS' and a['identity']==b['identity']
def test_approved_route_needs_explicit_evidence_and_no_ticker_branch():
 r=discover_routes([{'ticker':'CCC'}],{'CCC':{'candidate_url':'https://issuer.example/x','issuer_domain_evidence':'official exchange profile'}},REG)
 assert r['route_candidates'][0]['disposition']=='APPROVABLE_OFFICIAL_ROUTE_DISCOVERED'
 assert 'if ticker ==' not in inspect.getsource(discover_routes)
