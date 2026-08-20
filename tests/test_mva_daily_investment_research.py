from run_mva_daily_investment_research import run
def test_product_is_deterministic_and_non_actionable():
 a,b=run(),run();assert a['artifact_identity']==b['artifact_identity'];assert len(a['stock_research'])==523;assert all(not x['research_summary']['attention_is_recommendation'] for x in a['research_attention'])
