"""Emit the deterministic P3-F current-market valuation research artifact."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from p3f_current_market_valuation import build_p3f_valuation_artifact

P3E = repo_root / "operations-review/p3e-fundamental-coverage-closeout-20260820/p3e_fundamental_coverage_closeout_artifact.json"
OUTPUT = repo_root / "operations-review/p3f-current-market-valuation-20260820"


def run_p3f_current_market_valuation(output_dir: Path = OUTPUT, runtime_root: Path | None = None) -> dict:
    resolved_runtime = runtime_root or (Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"]) if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT") else None)
    if resolved_runtime is None:
        raise ValueError("STOCK_LOOKUP_RUNTIME_ROOT_REQUIRED")
    p3e = json.loads(P3E.read_text(encoding="utf-8"))
    artifact = build_p3f_valuation_artifact(p3e_artifact=p3e, runtime_root=resolved_runtime)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "p3f_current_market_valuation_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(run_p3f_current_market_valuation()["artifact_identity"])
