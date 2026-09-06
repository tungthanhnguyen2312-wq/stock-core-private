"""Materialize a frozen reconciliation-selected DNSE Trades cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_trades_canonical_shadow import materialize_cohort


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-manifest", required=True)
    parser.add_argument("--shadow-root", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(materialize_cohort(cohort_manifest_path=args.cohort_manifest, shadow_root=args.shadow_root, workers=args.workers), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
