"""Execute the bounded approved issuer-IR official-financial evidence cohort."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from approved_issuer_ir_financial_evidence import acquire, summarize_existing_artifact


OUTPUT = ROOT / "operations-review" / "approved-issuer-ir-official-financial-evidence-cohort-v1-20260827"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--coverage-report", type=Path)
    args = parser.parse_args()
    if args.summarize:
        coverage = json.loads(args.coverage_report.read_text(encoding="utf-8")) if args.coverage_report else None
        print(json.dumps(summarize_existing_artifact(OUTPUT / "artifact.json", coverage), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(acquire(output_root=OUTPUT), ensure_ascii=False, indent=2))
