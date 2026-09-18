"""Materialize the retained-only multi-session signal velocity projection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import multi_session_signal_velocity as velocity


def run(*, root: str | Path = ROOT, output: str | Path | None = None) -> dict:
    artifact = velocity.build_from_retained_root(root)
    if output is not None:
        velocity.write_immutable(output, artifact)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Retained evidence root; never fetched or mutated.")
    parser.add_argument("--output", help="Optional immutable output path.")
    args = parser.parse_args()
    result = run(root=args.root, output=args.output)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "validation": result["validation"]}, ensure_ascii=False, sort_keys=True))
