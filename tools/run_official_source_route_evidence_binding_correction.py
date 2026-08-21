"""Emit the offline evidence-binding correction without changing historical V1."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_financial_source_route_discovery import build_evidence_binding_correction, execute


PRIOR_V1 = ROOT / "operations-review/official-financial-source-route-discovery-v1-20260821/official_financial_source_route_discovery_artifact.json"
WAVE2 = ROOT / "operations-review/official-financial-evidence-scaleout-wave2-20260821/wave2_official_financial_evidence_scaleout_artifact.json"
OUT = ROOT / "operations-review/official-source-route-evidence-binding-correction-v1-20260821"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run() -> tuple[dict, dict]:
    """Replay against the retained corpus. Wave 2 proves no ownership objects exist."""
    prior_v1 = _load(PRIOR_V1)
    wave2 = _load(WAVE2)
    corrected = execute(retained_ownership_evidence=())
    return corrected, build_evidence_binding_correction(prior_v1, corrected, wave2)


def main() -> None:
    corrected, correction = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "official_financial_source_route_discovery_evidence_bound_artifact.json").write_text(
        json.dumps(corrected, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (OUT / "official_source_route_evidence_binding_correction_artifact.json").write_text(
        json.dumps(correction, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(corrected["artifact_identity"])
    print(correction["artifact_identity"])


if __name__ == "__main__":
    main()
