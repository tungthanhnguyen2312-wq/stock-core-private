"""Build the current-universe activity-status and session-coverage resolution artifact.

Thin IO adapter only: reads three already-retained JSON artifacts, verifies each one's own
recorded identity, and calls the pure core in
``current_universe_status_and_session_coverage_resolution.py``. No network call, no database
write, no re-derivation of membership or session-observability (both come from the retained
``current_market_universe_breadth_foundation`` artifact unchanged).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_universe_status_and_session_coverage_resolution import build_artifact

DEFAULT_BREADTH_FOUNDATION = ROOT / "operations-review/current-market-universe-breadth-foundation-v1-20260823/current_market_universe_breadth_foundation_artifact.json"
DEFAULT_P3F9B_SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json"
DEFAULT_VCI_SNAPSHOT = ROOT / "operations-review/vci-exchange-reference-snapshot-v1-20260823/vci_exchange_reference_snapshot_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260823/current_universe_status_and_session_coverage_resolution_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--breadth-foundation-artifact", default=str(DEFAULT_BREADTH_FOUNDATION))
    parser.add_argument("--p3f9b-snapshot", default=str(DEFAULT_P3F9B_SNAPSHOT))
    parser.add_argument("--vci-exchange-reference-snapshot", default=str(DEFAULT_VCI_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    breadth_foundation = _load(Path(args.breadth_foundation_artifact))
    p3f9b_snapshot = _load(Path(args.p3f9b_snapshot))
    vci_snapshot = _load(Path(args.vci_exchange_reference_snapshot))

    artifact = build_artifact(
        breadth_foundation_artifact=breadth_foundation,
        p3f9b_snapshot=p3f9b_snapshot,
        vci_snapshot=vci_snapshot,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(artifact["artifact_identity"])
    print(f"activity_and_session_status.counts = {artifact['activity_and_session_status']['counts']}")
    print(f"current_active_equity_denominator = {artifact['current_active_equity_denominator']['count']}")
    print(f"observed_session_cohort = {artifact['observed_session_cohort']}")
    print(f"provider_rejection_resolution = {artifact['provider_rejection_resolution']}")
    print(f"security_master_unknown_resolution = {artifact['security_master_unknown_resolution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
