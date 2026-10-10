"""Build the Current Research coverage / decision-fitness read model from a retained Integrated Decision JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stocklookup_core.decision.current_research_decision_input as decision_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to integrated_investment_decision_product/v1 JSON")
    parser.add_argument("--output", required=True, help="Output path for decision-fitness JSON")
    parser.add_argument("--requested-at", default=None)
    args = parser.parse_args()

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    artifact = decision_input.build_decision_fitness_artifact(
        integrated_decision_artifact=source,
        requested_at=args.requested_at,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(output)

    coverage = artifact["coverage"]
    print(f"SESSION={artifact['session']}")
    print(f"DENOMINATOR={coverage['denominator_count']}")
    print(f"RESEARCH_USABLE={coverage['research_usable_count']}")
    print(f"BLOCKED_CURRENT_RESEARCH={coverage['blocked_current_research_count']}")
    print(f"OUTSIDE_SCOPE={coverage['outside_scope_count']}")
    print(f"ARTIFACT_IDENTITY={artifact['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
