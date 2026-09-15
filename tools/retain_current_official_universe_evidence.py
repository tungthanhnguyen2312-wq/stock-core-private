"""OFFICIAL_SCOPE_EVIDENCE_OPERATIONALIZATION_AND_DASHBOARD_CUTOVER_READINESS_V1: operator-safe
migration/seed tool.

Promotes an explicitly-named, already-qualified ``current_official_market_universe`` artifact
into its durable, git-tracked retained-evidence location
(``operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913/current_official_
market_universe_with_security_status_artifact.json`` -- the exact path
``canonical_current_product_projections.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE`` pins),
so a clean checkout of this repository can resolve it without depending on the specific worktree
that originally produced it.

Never discovers the source automatically (no glob, no sibling-worktree search, no latest-mtime
pick) -- always pass ``--source`` explicitly. Performs no network access. Idempotent: promoting
the same source twice is a no-op success; promoting a *different* qualification to the same
destination path is refused.

Usage:
    python tools/retain_current_official_universe_evidence.py \\
        --source "<explicit path to the qualified artifact>" \\
        --expected-identity current_official_market_universe:92ddcca2...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import canonical_current_product_projections as ccpp  # noqa: E402
from current_official_universe_evidence_retention import RetentionError, retain_evidence  # noqa: E402

DEFAULT_DESTINATION = PROJECT_ROOT / ccpp.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Explicit path to the qualified current_official_market_universe artifact to promote.")
    parser.add_argument("--destination", default=str(DEFAULT_DESTINATION), help="Durable retained-evidence destination (default: the repository's pinned CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE path).")
    parser.add_argument("--expected-identity", default=None, help="Optional artifact_identity the source must match (e.g. current_official_market_universe:92ddcca2...). Recommended for a deliberate, auditable promotion.")
    args = parser.parse_args()

    try:
        result = retain_evidence(
            source_path=args.source,
            destination_path=args.destination,
            expected_identity=args.expected_identity,
        )
    except RetentionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result["status"] == "RETAINED":
        print(
            "\nNOTE: the destination file now exists on disk but is not yet git-tracked. "
            "This tool intentionally performs no git operations. Track it explicitly, e.g.:\n"
            f"  git add -f {Path(args.destination)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
