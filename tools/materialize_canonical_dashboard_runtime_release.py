"""CLI for the retained canonical Dashboard runtime release adapter."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_dashboard_runtime_release import CanonicalRuntimeReleaseError, materialize_canonical_runtime_release

def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize retained canonical Dashboard runtime inputs; never acquires data.")
    parser.add_argument("--session", required=True)
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()
    try:
        result = materialize_canonical_runtime_release(ROOT, Path(args.runtime_root), args.session)
    except CanonicalRuntimeReleaseError as exc:
        print(f"REFUSE_CANONICAL_RUNTIME_RELEASE:{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
