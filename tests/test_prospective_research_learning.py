from pathlib import Path
import pytest
from run_prospective_research_learning import run
from prospective_research_learning import write_immutable
def test_snapshot_replays_pending_and_preserves_tiers(tmp_path:Path):
 a,outcome=run();b,repeat_outcome=run();assert a['snapshot_id']==b['snapshot_id'];assert outcome['outcome_status']=='PENDING_FUTURE_OBSERVATION';assert repeat_outcome['outcome_status']=='PENDING_FUTURE_OBSERVATION';assert {x['fundamental_authority'] for x in a['frozen_records']}>= {'OFFICIAL_QUALIFIED','PROVIDER_RESEARCH'};p=tmp_path/'x.json';write_immutable(p,a);write_immutable(p,a);c=dict(a);c['cohort_count']=0
 with pytest.raises(ValueError):write_immutable(p,c)
