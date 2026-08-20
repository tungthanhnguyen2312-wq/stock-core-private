from p3f18_mva_research_synthesis import run
def test_replay_and_safety():
 a,b=run(),run();assert a['artifact_identity']==b['artifact_identity'];assert a['coverage']['generated']==523;assert not a['safety_envelope']['is_actionable_for_execution']
