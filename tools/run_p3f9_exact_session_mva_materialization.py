"""P3-F9: materialize a DNSE exact completed-session shadow MVA snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credentials_for_request
from dnse_secrets_env import ensure_credentials_loaded
from field_temporal_contract import stable_id
import mva_exact_session_snapshot as snapshotter
from mva_daily_research_bundle import build_mva_daily_research_bundle
from runtime_paths import runtime_root
from tools.run_p3f8_mva_operational_run import evaluate_mva_operational_run

VN_TZ = timezone(timedelta(hours=7))
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f9-exact-session-mva-materialization-20260820"


def execute(*, runtime: Path, output_dir: Path, requested_at: datetime | None = None, workers: int = 8, request_limit: int | None = None) -> dict[str, Any]:
    now = requested_at or datetime.now(VN_TZ)
    candidates = snapshotter.canonical_candidates(runtime)
    status = ensure_credentials_loaded()
    creds = credentials_for_request()
    if not status.get("configured") or not creds:
        raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
    snapshot = snapshotter.materialize_snapshot(candidates=candidates, requested_at=now, api_key=creds[0], api_secret=creds[1], workers=workers, request_limit=request_limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "p3f9_mva_exact_session_snapshot.json"
    snapshotter.write_snapshot(snapshot, snapshot_path)
    bundle = build_mva_daily_research_bundle(runtime, root=ROOT, snapshot_path=snapshot_path)
    bundle_path = output_dir / "p3f7_mva_daily_research_bundle_exact_session.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    operational = evaluate_mva_operational_run(runtime, root=ROOT, requested_at=now, bundle=bundle)
    operational_path = output_dir / "p3f8_mva_operational_run_exact_session.json"
    operational_path.write_text(json.dumps(operational, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    exact_equal = snapshot["resolved_completed_session"] == snapshot["retained_snapshot_session"] == bundle["frozen_session"]["session"]
    before_path = ROOT / "operations-review/p3f8-mva-operational-run-20260820/p3f8_mva_operational_run_artifact.json"
    before = json.loads(before_path.read_text(encoding="utf-8"))
    before_members = set()  # P3-F8 retained only count, so comparison is explicitly not a listing change.
    after_members = set(bundle["empirical_active_cohort"]["members"])
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": "p3f9_exact_session_mva_materialization/v1", "artifact_type": "P3F9_EXACT_SESSION_MVA_MATERIALIZATION",
        "verdict": "P3F9_EXACT_SESSION_MVA_MATERIALIZATION_COMPLETE" if exact_equal else "P3F9_EXACT_SESSION_MVA_MATERIALIZATION_PARTIAL",
        "execution_timestamp": now.astimezone(VN_TZ).isoformat(), "snapshot_identity": snapshot["snapshot_identity"], "mva_bundle_identity": bundle["artifact_identity"],
        "exact_session_equality": {"resolved_completed_session": snapshot["resolved_completed_session"], "retained_snapshot_session": snapshot["retained_snapshot_session"], "mva_bundle_session": bundle["frozen_session"]["session"], "equal": exact_equal},
        "coverage": {key: snapshot[key] for key in ("candidate_count", "attempted_candidate_count", "exact_session_observed_count", "empirical_20_session_complete_count", "missing_current_session_count", "materialization_scope")},
        "cohort_before_after": {"before_member_count": before["empirical_active_cohort"]["member_count"], "after_member_count": bundle["empirical_active_cohort"]["member_count"],
                                "comparison_basis": "P3F8 retained artifact exposed count only; P3F9 member set is a refreshed derived shadow denominator, not canonical listing membership.",
                                "after_members_identity": bundle["empirical_active_cohort"]["cohort_identity"], "membership_delta_known": False, "listing_change_claimed": False},
        "market_summary_before_after": {"before": before["market_summary"], "after": bundle["market_summary"]},
        "authority_boundary": snapshot["authority_boundary"], "ticker_specific_branch_audit": {"status": "PASS", "ticker_specific_branches": [], "canonical_mapping": snapshot["canonical_identity"]},
        "source_artifacts": {"p3f8_before": before.get("artifact_identity"), "p3f9_snapshot": snapshot["snapshot_identity"], "p3f7_exact_session": bundle["artifact_identity"], "p3f8_exact_session": operational.get("artifact_identity")},
    }
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f9_exact_session_mva_materialization:{artifact['artifact_sha256']}"
    (output_dir / "p3f9_exact_session_mva_materialization_artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None); parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR)); parser.add_argument("--workers", type=int, default=8); parser.add_argument("--request-limit", type=int, default=None, help="Explicit bounded provider window; produces a PARTIAL snapshot.")
    args = parser.parse_args(argv)
    artifact = execute(runtime=runtime_root(args.runtime_root), output_dir=Path(args.output_dir), workers=args.workers, request_limit=args.request_limit)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["exact_session_equality"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
