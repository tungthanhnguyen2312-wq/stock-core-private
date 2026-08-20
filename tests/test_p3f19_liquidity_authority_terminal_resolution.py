from p3f19_liquidity_authority_terminal_resolution import run
def test_terminal_decision_replays_and_preserves_sizing_block():
 a,b=run(),run();assert a['artifact_identity']==b['artifact_identity'];assert a['terminal_liquidity_decision']=='LIQUIDITY_SEMANTICS_UNRESOLVED';assert not a['authority_boundary']['position_sizing_safe']
