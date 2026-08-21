from pathlib import Path
import json
from prospective_research_context_extension import build, write_immutable

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'operations-review/prospective-research-context-extension-v1-20260820'
SNAPSHOT = ROOT / 'operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json'

def _load(path): return json.loads(path.read_text(encoding='utf8'))

def run():
    snapshot = _load(SNAPSHOT)
    extension = build(snapshot,
        _load(ROOT / 'operations-review/research-setup-classification-v1-20260820/research_setup_classification_artifact.json'),
        _load(ROOT / 'operations-review/price-structure-breakout-context-v1-20260820/price_structure_breakout_context_artifact.json'),
        _load(ROOT / 'operations-review/market-regime-breadth-context-v1-20260820/market_regime_breadth_context_artifact.json'),
        _load(ROOT / 'operations-review/downside-uncertainty-research-context-v1-20260820/downside_uncertainty_research_context_artifact.json'),
        _load(ROOT / 'operations-review/sector-relative-research-context-v1-20260820/sector_relative_research_context_artifact.json'))
    return snapshot, extension

if __name__ == '__main__':
    snapshot, extension = run(); OUT.mkdir(parents=True, exist_ok=True)
    write_immutable(OUT / (extension['extension_content_identity'].split(':', 1)[1] + '.json'), extension)
    print(extension['extension_content_identity'])
