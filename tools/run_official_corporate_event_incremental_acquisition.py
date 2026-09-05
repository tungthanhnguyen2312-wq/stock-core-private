"""Run one bounded official HNX/HOSE corporate-event acquisition attempt and, on success,
materialize a fresh current_official_event_context snapshot from it.

OFFICIAL_CORPORATE_EVENT_INCREMENTAL_ACQUISITION_AND_FRESHNESS_V1.

This is the explicit incremental acquisition entrypoint the mission asks for, replacing the prior
one-off manual invocation (tools/run_current_official_event_context.py, left untouched -- it
remains a historical diagnostic artifact, not something this milestone repurposes). Suitable for
canonical Daily or a bounded pre-Daily acquisition stage: it performs exactly one acquisition
attempt (no loop, no retry) and fails closed with an explicit retained disposition on error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_corporate_event_incremental_acquisition import (
    IncrementalAcquisitionError,
    acquire,
    materialize_current_official_event_context,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default=None, help="Acquisition session date (YYYY-MM-DD); defaults to today (Asia/Ho_Chi_Minh).")
    parser.add_argument("--skip-acquisition", action="store_true",
                         help="Materialize only, from whatever session is already the latest successful retained attempt. "
                              "Performs no network access at all.")
    args = parser.parse_args(argv)

    if not args.skip_acquisition:
        attempt = acquire(ROOT, session=args.session)
        print(json.dumps({
            "acquisition_session": attempt["acquisition_session"],
            "disposition": attempt["disposition"],
            "any_change_since_prior_success": attempt.get("any_change_since_prior_success"),
        }, indent=2))
        if attempt["disposition"] != "SUCCESS":
            print(f"ACQUISITION_FAILED: {attempt.get('error_type')}: {attempt.get('error_message')}", file=sys.stderr)
            return 1

    try:
        result = materialize_current_official_event_context(ROOT)
    except IncrementalAcquisitionError as exc:
        print(f"MATERIALIZATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
