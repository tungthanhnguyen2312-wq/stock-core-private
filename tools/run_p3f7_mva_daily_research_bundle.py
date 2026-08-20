"""Emit the deterministic, read-only P3-F7 MVA daily research bundle."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from mva_daily_research_bundle import build_mva_daily_research_bundle
from runtime_paths import runtime_root
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f7-mva-daily-research-bundle-20260820"
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--runtime-root", default=None); parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR)); args = parser.parse_args(argv)
    artifact = build_mva_daily_research_bundle(runtime_root(args.runtime_root), root=ROOT)
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "p3f7_mva_daily_research_bundle_artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"]); return 0
if __name__ == "__main__": raise SystemExit(main())
