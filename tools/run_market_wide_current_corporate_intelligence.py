"""Materialize the current corporate-intelligence artifact from retained inputs only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_wide_current_corporate_intelligence import build, content_identity


def main() -> None:
    parser = argparse.ArgumentParser(description="Build retained-evidence current corporate intelligence.")
    parser.add_argument("--session", default="2026-08-21")
    parser.add_argument("--output", type=Path, default=ROOT / "operations-review/market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json")
    args = parser.parse_args()
    operations = ROOT / "operations-review"
    descriptive = json.loads((operations / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json").read_text(encoding="utf-8"))
    fundamental = json.loads((operations / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json").read_text(encoding="utf-8"))
    artifact = build(descriptive=descriptive, fundamental=fundamental, session=args.session, root=ROOT)
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]: raise ValueError("CORPORATE_INTELLIGENCE_SELF_VERIFICATION_FAILED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
