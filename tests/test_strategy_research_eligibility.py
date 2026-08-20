from run_strategy_research_eligibility import run
def test_eligibility_is_deterministic_and_isolates_blockers():
 a,o=run();b,_=run();assert a['artifact_identity']==b['artifact_identity'];assert len(a['records'])==523;assert len(o['entries'])==25
 for r in a['records']:
  assert r['lenses']['TREND_MOMENTUM_RESEARCH']['eligibility']=='ELIGIBLE';assert r['lenses']['LIQUIDITY_SENSITIVE_RESEARCH']['eligibility']=='BLOCKED';assert r['lenses']['HISTORICAL_PIT_STRATEGY_RESEARCH']['eligibility']=='BLOCKED';assert r['lenses']['CATALYST_RESEARCH']['eligibility']==('ELIGIBLE' if r['ticker']=='HPG' else 'UNAVAILABLE')
 assert a['coverage']['fully_blocked']==0;assert a['authority_boundary']['not_a_signal_or_recommendation']
