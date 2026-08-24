from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hnx_filing_evidence_binding import build, replay


RETAINED_ROOT = ROOT / "operations-review" / "official-financial-filings-and-canonical-history-scaleout-v1-20260824-r3"
BASELINE_PATH = ROOT / "operations-review" / "p3f13-official-financial-evidence-scaleout-20260820" / "p3f13_official_financial_evidence_scaleout_artifact.json"
OUT = ROOT / "operations-review" / "hnx-official-filing-evidence-binding-and-extraction-v1-20260824" / "hnx_official_filing_evidence_binding_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    retained = _load(RETAINED_ROOT / "official_financial_filings_scaleout_artifact.json")
    baseline = _load(BASELINE_PATH)
    artifact = build(retained_artifact=retained, raw_root=RETAINED_ROOT, baseline=baseline)
    data = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_text(encoding="utf-8") != data:
        raise ValueError("IMMUTABLE_CONTENT_CONFLICT")
    OUT.write_text(data, encoding="utf-8")
    replay(retained_artifact=retained, raw_root=RETAINED_ROOT, baseline=baseline, artifact=_load(OUT))
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
