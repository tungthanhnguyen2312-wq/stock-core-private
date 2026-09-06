"""Read-only CLI for canonical_daily_release_acceptance/v1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_daily_release_acceptance import ReleaseAcceptanceError, evaluate_artifact_root, human_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one retained Canonical Daily release without writes or network access.")
    parser.add_argument("--artifact-root", type=Path, required=True, help="Exact Daily Session Operation artifact directory.")
    parser.add_argument("--dashboard-root", type=Path, help="Optional explicit Dashboard release root; no latest-path discovery is performed.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    args = parser.parse_args()
    try:
        report = evaluate_artifact_root(args.artifact_root, dashboard_root=args.dashboard_root)
    except ReleaseAcceptanceError as exc:
        print("CANONICAL_DAILY_RELEASE_ACCEPTANCE=BLOCKED", file=sys.stderr)
        print("REASON=" + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(human_summary(report))
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["overall_state"] in {"PASS", "PASS_WITH_EXPLICIT_PARTIALS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
