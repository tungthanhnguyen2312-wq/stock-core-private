from p3f17_provider_analytics_terminal_resolution import run
def test_terminal_resolution_is_deterministic_and_preserves_authority():
 a,b=run(),run();assert a['artifact_identity']==b['artifact_identity'];assert a['terminal_provider_semantic_decision']=='PROVIDER_FUNDAMENTALS_DESCRIPTIVE_ONLY';assert a['authority_boundary']['official_promotions']==0
