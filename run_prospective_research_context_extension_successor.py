from pathlib import Path
import json
from prospective_research_context_extension import build_successor, write_immutable
from run_prospective_research_context_extension import ROOT, SNAPSHOT

OUT = ROOT / 'operations-review/prospective-research-context-extension-v1-successor-20260820'
PREDECESSOR = ROOT / 'operations-review/prospective-research-context-extension-v1-20260820/1248d909c9ffd204d9bbcfbf3c886a4621e690c6739b5c8736fcab3bf7f58339.json'
def _load(path): return json.loads(path.read_text(encoding='utf8'))
def run():
 return _load(SNAPSHOT), build_successor(_load(SNAPSHOT), _load(PREDECESSOR), _load(ROOT/'operations-review/research-setup-classification-v1-20260820/research_setup_classification_artifact.json'), _load(ROOT/'operations-review/price-structure-breakout-context-v1-20260820/price_structure_breakout_context_artifact.json'), _load(ROOT/'operations-review/market-regime-breadth-context-v1-20260820/market_regime_breadth_context_artifact.json'), _load(ROOT/'operations-review/downside-uncertainty-research-context-v1-restored-20260820/e8561c8eb191442be89e320847f3583214e9fb5cac9c393591b7d34d0c0e041d.json'), _load(ROOT/'operations-review/downside-uncertainty-research-context-v2-20260820/0c5baa1b37907c730930e923f7317e85aecb43a77de333784c2aef0f38c78ca4.json'), _load(ROOT/'operations-review/sector-relative-research-context-v1-20260820/sector_relative_research_context_artifact.json'))
if __name__=='__main__':
 snapshot, extension=run();OUT.mkdir(parents=True,exist_ok=True);write_immutable(OUT/(extension['extension_content_identity'].split(':',1)[1]+'.json'),extension);print(extension['extension_content_identity'])
