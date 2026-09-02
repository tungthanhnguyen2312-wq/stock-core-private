"""Offline replay of retained DNSE OHLC observations for relative-volume research."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_wide_relative_volume_research import build_artifact, content_identity


def replay(snapshot_path: Path, output_dir: Path) -> Path:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = snapshot.get("records")
    session = snapshot.get("resolved_completed_session")
    if not isinstance(records, dict) or not isinstance(session, str):
        raise ValueError("RETAINED_SNAPSHOT_SHAPE_INVALID")
    artifact = build_artifact(
        candidates=sorted(records), records=records, session=session,
        requested_at=f"RETAINED_SESSION_BOUND:{session}",
    )
    artifact["universe"]["source_snapshot_identity"] = snapshot.get("canonical_identity")
    artifact.update(content_identity(artifact))
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "market_wide_relative_volume_research_artifact.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    print(replay(Path(args.snapshot), Path(args.out_dir)))


if __name__ == "__main__":
    main()
