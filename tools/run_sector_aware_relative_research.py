from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sector_aware_relative_research import build,content_identity
O=ROOT/'operations-review';P={'descriptive':O/'market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json','tactical':O/'watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json','fundamental':O/'market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json','valuation':O/'market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json'};OUT=O/'sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json'
if __name__=='__main__':
 a=build(**{k:json.loads(v.read_text(encoding='utf8')) for k,v in P.items()});assert content_identity(a)['artifact_sha256']==a['artifact_sha256'];OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(a,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8');print(a['artifact_identity'])
