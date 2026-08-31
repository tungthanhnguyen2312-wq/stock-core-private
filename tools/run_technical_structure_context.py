"""Materialize the technical_structure_context artifact to disk.

Foreground, offline, deterministic given two already-retained inputs: no network call, no new
technical acquisition. Paths are required (not defaulted) because the retained
market_wide_current_descriptive_research and P3F9B exact-session snapshot for a given real session
live in that session's own operations-review evidence folder, not in a fixed repo-relative location.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from technical_structure_context import build_artifact  # noqa: E402


def run(*, descriptive_path: Path, p3f9b_snapshot_path: Path, out_dir: Path, requested_at: str) -> Path:
    descriptive = json.loads(descriptive_path.read_text(encoding="utf-8"))
    p3f9b_snapshot = json.loads(p3f9b_snapshot_path.read_text(encoding="utf-8"))
    artifact = build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b_snapshot, requested_at=requested_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "technical_structure_context_artifact.json"
    target.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptive-path", required=True)
    parser.add_argument("--p3f9b-snapshot-path", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--requested-at", default=None, help="Defaults to current UTC time if omitted; never enters canonical content identity.")
    args = parser.parse_args(argv)
    requested_at = args.requested_at
    if requested_at is None:
        from datetime import datetime, timezone
        requested_at = datetime.now(timezone.utc).isoformat()
    run(descriptive_path=Path(args.descriptive_path), p3f9b_snapshot_path=Path(args.p3f9b_snapshot_path), out_dir=Path(args.out_dir), requested_at=requested_at)


if __name__ == "__main__":
    main()
