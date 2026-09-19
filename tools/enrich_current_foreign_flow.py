"""Operator command: current foreign-flow enrichment for one exact, already-completed session.

Default behavior is a no-network plan/status report (zero DNSE calls, no credential read).
``--live`` is the only way to allow a real network call, and it must be paired with an explicit
owner authorization to run this after Core Daily/post-close has already produced that session's
canonical handoff -- this tool never decides that boundary for the owner, it only enforces that
``allow_network`` is never on by default.

    python tools/enrich_current_foreign_flow.py --session 2026-09-18 --dry-run
    python tools/enrich_current_foreign_flow.py --session 2026-09-18 --live
    python tools/enrich_current_foreign_flow.py --session 2026-09-18 --live --retry-failed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_foreign_flow_enrichment_operation import (  # noqa: E402
    acquire_foreign_flow_for_manifest, write_operation_snapshot,
)
from current_foreign_flow_retention import build_manifest_from_root  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, help="Exact completed market session YYYY-MM-DD.")
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="No-network plan/status (also the default).")
    parser.add_argument("--resume", action="store_true",
                        help="Informational only -- acquisition is always resumable/idempotent by construction.")
    parser.add_argument("--live", action="store_true", help="Explicit owner authorization for real DNSE network calls.")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--secrets-file", default=None)
    args = parser.parse_args(argv)
    if args.dry_run and args.live:
        parser.error("--dry-run and --live are mutually exclusive")

    root_dir = ROOT
    runtime_root = resolve_runtime_root(args.runtime_root)
    manifest = build_manifest_from_root(root_dir, args.session)
    operation = acquire_foreign_flow_for_manifest(
        manifest, runtime_root=runtime_root, allow_network=bool(args.live and not args.dry_run),
        retry_failed=args.retry_failed, secrets_file=args.secrets_file,
    )
    output = (root_dir / "operations-review" / "current-foreign-flow-enrichment-v1"
             / args.session / "current_foreign_flow_enrichment_operation.json")
    write_operation_snapshot(output, operation)
    print(json.dumps({
        "status": operation["status"], "operation_identity": operation["operation_identity"],
        "manifest_identity": operation["acquisition_manifest_identity"], "reference_session": operation["reference_session"],
        "requested_count": len(operation["requested_tickers"]), "complete_count": operation["complete_count"],
        "pending_count": operation["pending_count"], "failed_count": operation["failed_count"],
        "conflict_count": operation["conflict_count"], "session_issue_count": operation["session_issue_count"],
        "network_calls_made": operation["network"]["network_calls_made"],
        "credentials_available": operation["network"]["credentials_available"],
        "counts": operation["counts"], "output_path": str(output),
    }, sort_keys=True, indent=2))
    return 0 if operation["status"] != "FAILED_OPERATIONAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
