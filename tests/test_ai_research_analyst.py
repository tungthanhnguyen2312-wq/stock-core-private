from ai_research_analyst import FORBIDDEN,markdown
from run_ai_research_analyst import run
def test_briefs_are_cited_non_recommendations_and_deterministic():
 a,b=run(),run();assert a['artifact_identity']==b['artifact_identity'];assert all(x['counter_thesis'] for x in a['stock_briefs']);assert all(x['ai_instruction'] for x in a['stock_briefs']);assert not any(x in markdown(a).upper() for x in FORBIDDEN)
