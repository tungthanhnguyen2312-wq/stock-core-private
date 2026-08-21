from pathlib import Path
import json
from prospective_research_context_extension import write_immutable

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'operations-review/prospective-research-context-extension-v1-20260820'
SNAPSHOT = ROOT / 'operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json'
SEALED_PREDECESSOR = OUT / '1248d909c9ffd204d9bbcfbf3c886a4621e690c6739b5c8736fcab3bf7f58339.json'

def _load(path): return json.loads(path.read_text(encoding='utf8'))

def run():
    # The legacy extension is sealed evidence only.  It must never be rebuilt
    # against later versioned context inputs or selected for attribution.
    return _load(SNAPSHOT), _load(SEALED_PREDECESSOR)

if __name__ == '__main__':
    snapshot, extension = run(); OUT.mkdir(parents=True, exist_ok=True)
    write_immutable(OUT / (extension['extension_content_identity'].split(':', 1)[1] + '.json'), extension)
    print(extension['extension_content_identity'])
