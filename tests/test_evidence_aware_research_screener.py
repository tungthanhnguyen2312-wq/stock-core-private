from run_evidence_aware_research_screener import run
from evidence_aware_research_screener import query
def test_screener_is_deterministic_and_fails_closed():
 a,o=run();b,_=run();assert a['artifact_identity']==b['artifact_identity'];assert len(a['records'])==523;assert len(o['entries'])==25
 counts={p['query_name']:p['result_count'] for p in a['presets']};assert counts['RESEARCHABLE_BUT_EXECUTION_BLOCKED']==523;assert counts['HIGHER_AUTHORITY_FUNDAMENTAL_RESEARCH']==11;assert counts['RELATIVE_CONTEXT_AVAILABLE']==27;assert counts['PROVIDER_DESCRIPTIVE_RELATIVE_CONTEXT_AVAILABLE']==486;assert counts['ANY_RELATIVE_CONTEXT_AVAILABLE']==513;assert counts['EVIDENCE_BACKED_EVENT_AVAILABLE']==1;assert counts['UPCOMING_EVIDENCED_EVENT']==0;assert counts['NEGATIVE_EVENT_CONTEXT']==0;assert counts['CATALYST_RESEARCH_AVAILABLE']==1
 bad=query(a['records'],{'name':'BAD','research_session':'2026-08-20','predicate':{'type':'field','field':'invented','operator':'==','value':1}},a['source_artifact_identities']);assert bad['result_count']==0;assert bad['excluded_count']==523
