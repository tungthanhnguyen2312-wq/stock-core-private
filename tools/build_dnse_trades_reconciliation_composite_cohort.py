"""Build an immutable reconciliation-selected Canonical Trades cohort."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json
from dnse_trades_canonical_shadow import build_reconciliation_composite_cohort


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--stage-a-checkpoint", required=True)
    parser.add_argument("--final-review-root")
    parser.add_argument("--status-path")
    args = parser.parse_args(argv)
    status = Path(args.status_path) if args.status_path else Path(args.output_root) / "task160_run_status.json"
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = build_reconciliation_composite_cohort(reconciliation_root=args.reconciliation_root, output_root=args.output_root, stage_a_checkpoint_path=args.stage_a_checkpoint, final_review_root=args.final_review_root)
    except Exception as exc:
        atomic_write_json(status, {"state": "FAILED", "pid": os.getpid(), "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__, "error": str(exc)})
        raise
    atomic_write_json(status, {"state": "SUCCESS", "pid": os.getpid(), "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(), "result": result})
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
