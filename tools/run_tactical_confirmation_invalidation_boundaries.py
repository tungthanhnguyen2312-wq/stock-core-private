"""Materialize the tactical_confirmation_invalidation_boundaries artifact to disk.

Foreground, offline, deterministic. ``--technical-structure-path`` is optional: boundaries fall back
to MA20/momentum-only anchors for tickers (or entire runs) without a structure context.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tactical_confirmation_invalidation_boundaries import build_artifact  # noqa: E402


def run(*, tactical_path: Path, descriptive_path: Path, technical_structure_path: Path | None, out_dir: Path, requested_at: str) -> Path:
    tactical = json.loads(tactical_path.read_text(encoding="utf-8"))
    descriptive = json.loads(descriptive_path.read_text(encoding="utf-8"))
    technical_structure = json.loads(technical_structure_path.read_text(encoding="utf-8")) if technical_structure_path else None
    artifact = build_artifact(tactical=tactical, current_descriptive=descriptive, technical_structure=technical_structure, requested_at=requested_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "tactical_confirmation_invalidation_boundaries_artifact.json"
    target.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tactical-path", required=True)
    parser.add_argument("--descriptive-path", required=True)
    parser.add_argument("--technical-structure-path", default=None)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--requested-at", default=None, help="Defaults to current UTC time if omitted; never enters canonical content identity.")
    args = parser.parse_args(argv)
    requested_at = args.requested_at
    if requested_at is None:
        from datetime import datetime, timezone
        requested_at = datetime.now(timezone.utc).isoformat()
    run(
        tactical_path=Path(args.tactical_path), descriptive_path=Path(args.descriptive_path),
        technical_structure_path=Path(args.technical_structure_path) if args.technical_structure_path else None,
        out_dir=Path(args.out_dir), requested_at=requested_at,
    )


if __name__ == "__main__":
    main()
