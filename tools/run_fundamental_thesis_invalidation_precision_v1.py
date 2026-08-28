"""Materialize fundamental boundary precision, then replay shadow readiness and instrumentation."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import action_instrumentation
import fundamental_thesis_invalidation_precision as precision
import shadow_action_readiness


CASE_INPUT = ROOT / "operations-review" / "thesis-catalyst-downside-and-dual-invalidation-v1-20260828" / "artifact.json"
TACTICAL_INPUT = ROOT / "operations-review" / "watchlist-tactical-entry-decision-v1-20260825" / "watchlist_tactical_entry_classifier_artifact.json"
DESCRIPTIVE_INPUT = ROOT / "operations-review" / "market-wide-current-descriptive-research-v1-20260825" / "market_wide_current_descriptive_research_artifact.json"
PRECISION_OUTPUT = ROOT / "operations-review" / "fundamental-thesis-invalidation-precision-v1-20260828" / "artifact.json"
SHADOW_OUTPUT = ROOT / "operations-review" / "shadow-action-readiness-v1-20260828" / "artifact.json"
ACTION_OUTPUT = ROOT / "operations-review" / "action-instrumentation-and-invalidation-precision-v1-20260828" / "artifact.json"


def _write(path: Path, artifact: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run() -> dict:
    cases = json.loads(CASE_INPUT.read_text(encoding="utf-8"))
    base_shadow = shadow_action_readiness.build_artifact(research_cases=cases)
    boundaries = precision.build_artifact(shadow=base_shadow)
    _write(PRECISION_OUTPUT, boundaries)
    preliminary_action = action_instrumentation.build_artifact(
        shadow=base_shadow, tactical=json.loads(TACTICAL_INPUT.read_text(encoding="utf-8")),
        descriptive=json.loads(DESCRIPTIVE_INPUT.read_text(encoding="utf-8")),
        fundamental_boundaries_by_ticker=boundaries["records"])
    final_shadow = shadow_action_readiness.build_artifact(
        research_cases=cases, fundamental_boundaries_by_ticker=boundaries["records"],
        technical_boundaries_by_ticker=preliminary_action["records"])
    _write(SHADOW_OUTPUT, final_shadow)
    action = action_instrumentation.build_artifact(
        shadow=final_shadow, tactical=json.loads(TACTICAL_INPUT.read_text(encoding="utf-8")),
        descriptive=json.loads(DESCRIPTIVE_INPUT.read_text(encoding="utf-8")),
        fundamental_boundaries_by_ticker=boundaries["records"])
    _write(ACTION_OUTPUT, action)
    return {"fundamental_precision": boundaries, "shadow": final_shadow, "action_instrumentation": action}


if __name__ == "__main__":
    run()
