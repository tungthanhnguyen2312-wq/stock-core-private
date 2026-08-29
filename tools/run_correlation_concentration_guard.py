"""Materialize a C2 correlation/concentration research artifact from retained C1 evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from correlation_concentration_guard import build_artifact


DEFAULT_RISK = ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json"
DEFAULT_RECOMMENDATIONS = ROOT / "operations-review/shadow-security-recommendation-v1-20260829/artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/correlation-concentration-guard-v1-20260829/artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(*, lookback: int, output: Path = DEFAULT_OUTPUT) -> dict:
    risk = _load(DEFAULT_RISK)
    artifact = build_artifact(risk_research=risk, securities=risk["cohort_summary"]["tickers"], lookback=lookback,
                              shadow_recommendations=_load(DEFAULT_RECOMMENDATIONS))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback", required=True, type=int, choices=(20, 60, 120, 250))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    artifact = run(lookback=args.lookback, output=Path(args.output))
    print(artifact["artifact_identity"])
    print(f"guard_status = {artifact['guard_context']['status']}")
    print(f"triggered_group_count = {artifact['validation']['triggered_group_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
