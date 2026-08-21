"""Materialize the first retained strictly-future descriptive attribution."""
from __future__ import annotations
import json
from pathlib import Path
from prospective_research_learning import first_real_observation, write_immutable

ROOT = Path(__file__).resolve().parent

def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))

def run() -> dict:
    return first_real_observation(
        _load('operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json'),
        _load('operations-review/prospective-research-context-extension-v1-successor-20260820/6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807.json'),
        _load('operations-review/p3f9b-market-wide-exact-session-scaleout-20260820/p3f9b_mva_exact_session_snapshot.json'),
        _load('operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_market_wide_exact_session_scaleout_artifact.json'),
        _load('operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json'),
        _load('operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f7_mva_daily_research_bundle_exact_session.json'),
    )

if __name__ == '__main__':
    artifact = run()
    path = ROOT / 'operations-review/first-real-prospective-attribution-v1-20260821' / 'first_real_prospective_attribution_artifact.json'
    write_immutable(path, artifact)
    print(artifact['artifact_identity'])
