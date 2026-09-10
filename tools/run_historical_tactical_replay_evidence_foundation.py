"""Build the local historical tactical-replay evidence foundation without provider calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import historical_tactical_replay_evidence_foundation as foundation  # noqa: E402


def write_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True, help="Explicit local runtime root containing vn_stock.db.")
    parser.add_argument("--retained-evidence-root", type=Path, required=True, help="Read-only root holding exact PAN control snapshots.")
    parser.add_argument("--out", type=Path, required=True, help="Tracked artifact path in this checkout.")
    args = parser.parse_args(argv)
    artifact = foundation.build_from_runtime(
        runtime_root=args.runtime_root,
        retained_evidence_root=args.retained_evidence_root,
    )
    write_artifact(args.out, artifact)
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "historical_sessions": artifact["coverage"]["historical_sessions"],
        "qualifications": artifact["coverage"]["representative_qualification_counts"],
        "pan_transition": artifact["pan_control"].get("transition"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
