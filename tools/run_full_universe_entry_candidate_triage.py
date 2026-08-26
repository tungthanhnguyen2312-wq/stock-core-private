"""Materialize full_universe_entry_candidate_triage/v1 from current-session inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from full_universe_entry_candidate_triage import build, replay

OPS = ROOT / "operations-review"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Exact completed market session YYYY-MM-DD.")
    parser.add_argument("--descriptive", type=Path, required=True)
    parser.add_argument("--screening", type=Path, required=True)
    parser.add_argument("--tactical", type=Path, required=True)
    parser.add_argument("--fundamental", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = {
        "descriptive": json.loads(args.descriptive.read_text(encoding="utf-8")),
        "screening": json.loads(args.screening.read_text(encoding="utf-8")),
        "tactical": json.loads(args.tactical.read_text(encoding="utf-8")),
        "session": args.session,
    }
    if args.fundamental:
        inputs["fundamental"] = json.loads(args.fundamental.read_text(encoding="utf-8"))
    artifact = build(**inputs)
    replay(artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
