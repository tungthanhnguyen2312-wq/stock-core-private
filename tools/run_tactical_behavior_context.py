"""Materialize the compact tactical_behavior_context product artifact to disk.

Foreground, offline, deterministic. ``--boundaries-path`` and ``--leadership-path`` are optional:
their absence degrades specific fields to UNAVAILABLE rather than blocking the whole run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tactical_behavior_context import build_artifact  # noqa: E402


def run(*, tactical_path: Path, technical_structure_path: Path, setup_tags_path: Path,
        boundaries_path: Path | None, leadership_path: Path | None, out_dir: Path, requested_at: str) -> Path:
    tactical = json.loads(tactical_path.read_text(encoding="utf-8"))
    technical_structure = json.loads(technical_structure_path.read_text(encoding="utf-8"))
    setup_tags = json.loads(setup_tags_path.read_text(encoding="utf-8"))
    boundaries = json.loads(boundaries_path.read_text(encoding="utf-8")) if boundaries_path else None
    leadership = json.loads(leadership_path.read_text(encoding="utf-8")) if leadership_path else None
    artifact = build_artifact(
        tactical=tactical, technical_structure=technical_structure, tactical_setup_tags=setup_tags,
        confirmation_invalidation_boundaries=boundaries, current_leadership=leadership, requested_at=requested_at,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "tactical_behavior_context_artifact.json"
    target.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tactical-path", required=True)
    parser.add_argument("--technical-structure-path", required=True)
    parser.add_argument("--setup-tags-path", required=True)
    parser.add_argument("--boundaries-path", default=None)
    parser.add_argument("--leadership-path", default=None)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--requested-at", default=None, help="Defaults to current UTC time if omitted; never enters canonical content identity.")
    args = parser.parse_args(argv)
    requested_at = args.requested_at
    if requested_at is None:
        from datetime import datetime, timezone
        requested_at = datetime.now(timezone.utc).isoformat()
    run(
        tactical_path=Path(args.tactical_path), technical_structure_path=Path(args.technical_structure_path),
        setup_tags_path=Path(args.setup_tags_path), boundaries_path=Path(args.boundaries_path) if args.boundaries_path else None,
        leadership_path=Path(args.leadership_path) if args.leadership_path else None,
        out_dir=Path(args.out_dir), requested_at=requested_at,
    )


if __name__ == "__main__":
    main()
