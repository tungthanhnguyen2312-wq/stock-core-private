"""CLI: retained-session trusted-subset materialization. Zero network acquisition."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_trusted_subset_release import (  # noqa: E402
    CanonicalTrustedSubsetError,
    materialize_canonical_trusted_subset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="YYYY-MM-DD completed canonical session")
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=None,
                        help="Write target; defaults to --runtime-root")
    parser.add_argument("--producer-root", type=Path, default=ROOT)
    parser.add_argument("--consumer-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = materialize_canonical_trusted_subset(
            args.producer_root,
            args.runtime_root,
            args.session,
            output_root=args.output_root,
            consumer_root=args.consumer_root,
        )
    except CanonicalTrustedSubsetError as exc:
        print(f"REFUSE_CANONICAL_TRUSTED_SUBSET:{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
