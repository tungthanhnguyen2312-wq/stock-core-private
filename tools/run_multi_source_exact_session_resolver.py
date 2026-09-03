"""Standalone driver: DNSE Pass 1 + VCI/KBS recovery (Passes 2-4), multi-source exact-session
market evidence resolver.

Mirrors tools/run_p3f9b_market_wide_exact_session_scaleout.py's own CLI shape (this is that
tool's product-critical successor for canonical Daily acquisition -- see
daily_session_level2_package.ensure_exact_session_snapshot, which calls the same underlying
functions in-process; the standalone P3F9B tool itself is unchanged and remains available as a
DNSE-only diagnostic). Intended for owner-directed diagnostic/acceptance runs -- canonical Daily
itself never shells out to this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credentials_for_request  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
from multi_source_exact_session_resolver import (  # noqa: E402
    WATCHLIST_11,
    DnseProviderWideQualityDegraded,
    assert_dnse_quality_acceptable,
    read_candidate_metadata,
    resolve_multi_source_exact_session_snapshot,
    select_sentinel_cohort,
)
import mva_exact_session_snapshot as snapshotter  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

VN_TZ = timezone(timedelta(hours=7))
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "multi-source-exact-session-resolver"


def execute(
    *,
    runtime: Path,
    output_dir: Path,
    requested_at: datetime | None = None,
    target_session: str | None = None,
    workers: int = 12,
    recovery_window_days: int = 15,
    max_recovery_candidates: int | None = None,
) -> dict[str, Any]:
    now = requested_at or datetime.now(VN_TZ)
    candidates = snapshotter.canonical_candidates(runtime)

    status = ensure_credentials_loaded()
    creds = credentials_for_request()
    if not status.get("configured") or not creds:
        raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")

    dnse_snapshot = snapshotter.materialize_snapshot(
        candidates=candidates, requested_at=now, target_session=target_session,
        api_key=creds[0], api_secret=creds[1], workers=workers,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    dnse_only_path = output_dir / "dnse_only_exact_session_snapshot.json"
    snapshotter.write_snapshot(dnse_snapshot, dnse_only_path)

    dnse_exact_tickers = [
        ticker for ticker, record in dnse_snapshot["records"].items()
        if record.get("disposition") == "EXACT_SESSION_RETAINED"
    ]
    candidate_metadata = read_candidate_metadata(runtime, candidates)
    sentinel = select_sentinel_cohort(
        candidate_metadata=candidate_metadata, dnse_exact_tickers=dnse_exact_tickers,
    )
    sentinel_path = output_dir / "dnse_quality_sentinel_cohort.json"
    sentinel_path.write_text(json.dumps(sentinel, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse_snapshot,
        target_session=dnse_snapshot["resolved_completed_session"],
        requested_at=dnse_snapshot["requested_at"],
        recovery_window_days=recovery_window_days,
        max_recovery_candidates=max_recovery_candidates,
        sentinel_cohort=sentinel["tickers"],
    )
    evidence_path = output_dir / "multi_source_exact_session_market_evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    projected_path = output_dir / "resolved_exact_session_snapshot.json"
    snapshotter.write_snapshot(projected, projected_path)

    watchlist_status = {}
    for ticker in WATCHLIST_11:
        record = projected["records"].get(ticker)
        if record is None:
            watchlist_status[ticker] = {"disposition": "NOT_IN_CANDIDATE_SET"}
            continue
        obs = record.get("observations") or []
        watchlist_status[ticker] = {
            "disposition": record.get("disposition"),
            "provider": obs[0].get("provider") if obs else None,
            "close": obs[0].get("close") if obs else None,
            "multi_source_recovery_result": record.get("multi_source_recovery_result"),
        }

    result = {
        "session": dnse_snapshot["resolved_completed_session"],
        "candidate_count": len(candidates),
        "dnse_exact_count": evidence["dnse_exact_session_count"],
        "vci_recovery_attempts": evidence["recovery_attempts"]["VCI"],
        "vci_recovery_count": evidence["recovery_successes"]["VCI"],
        "kbs_recovery_attempts": evidence["recovery_attempts"]["KBS"],
        "kbs_recovery_count": evidence["recovery_successes"]["KBS"],
        "resolved_exact_session_count": projected["exact_session_observed_count"],
        "resolved_denominator": projected["attempted_candidate_count"],
        "resolved_coverage_ratio": round(projected["exact_session_observed_count"] / projected["attempted_candidate_count"], 6) if projected["attempted_candidate_count"] else 0.0,
        "corroborated_count": evidence["resolution_counts"]["RESOLVED_CORROBORATED"],
        "single_source_count": evidence["resolution_counts"]["RESOLVED_SINGLE_SOURCE_RESEARCH"],
        "conflict_count": evidence["resolution_counts"][ "SOURCE_CONFLICT"],
        "all_sources_missing_count": evidence["resolution_counts"]["SESSION_MISSING_ALL_SOURCES"],
        "watchlist_11_status": watchlist_status,
        "dnse_quality_sentinel": evidence["dnse_quality_sentinel"],
        "evidence_identity": evidence["evidence_identity"],
        "resolved_snapshot_identity": projected["snapshot_identity"],
        "dnse_only_snapshot_identity": dnse_snapshot["snapshot_identity"],
        "output_dir": str(output_dir),
    }
    result_path = output_dir / "run_summary.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    # Every artifact above is now persisted regardless of outcome -- the quality gate below may
    # still refuse to hand back a "resolved" result, but it never costs the real evidence.
    assert_dnse_quality_acceptable(evidence)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--requested-at", default=None)
    parser.add_argument("--session", default=None, help="Explicit target session YYYY-MM-DD")
    parser.add_argument("--recovery-window-days", type=int, default=15)
    parser.add_argument("--max-recovery-candidates", type=int, default=None, help="Bounded diagnostic probe only")
    args = parser.parse_args(argv)

    root = resolve_runtime_root(args.runtime_root)
    req_time = datetime.fromisoformat(args.requested_at).astimezone(VN_TZ) if args.requested_at else None

    try:
        result = execute(
            runtime=root, output_dir=Path(args.output_dir), requested_at=req_time,
            target_session=args.session, workers=args.workers,
            recovery_window_days=args.recovery_window_days,
            max_recovery_candidates=args.max_recovery_candidates,
        )
    except DnseProviderWideQualityDegraded as exc:
        sentinel = exc.dnse_quality_sentinel
        health = sentinel["health"]
        print("DNSE_PROVIDER_HEALTH_STATE: DNSE_BROAD_STALE_OR_INCOMPLETE_EOD")
        print(f"DNSE_SENTINEL_COHORT_VERSION: {sentinel['cohort_version']}")
        print(f"DNSE_SENTINEL_SIZE: {sentinel['cohort_size']}")
        print(f"DNSE_SENTINEL_CONFLICT_COUNT: {health['conflict_count']}")
        print(f"DNSE_SENTINEL_CORROBORATED_COUNT: {health['corroborated_count']}")
        print(f"DNSE_SENTINEL_ASSESSED_COUNT: {health['dnse_assessed_count']}")
        print("ACTION_REQUIRED: expand recovery scope to all DNSE-exact tickers explicitly "
              "(operator-chosen re-run) -- no automatic full-universe pass was started.")
        print(f"DETAIL: {exc}")
        print(f"EVIDENCE_PERSISTED_DESPITE_DEGRADED_VERDICT: {args.output_dir}")
        return 3

    print(f"SESSION: {result['session']}")
    print(f"DNSE_EXACT_COUNT: {result['dnse_exact_count']}")
    print(f"VCI_RECOVERY_ATTEMPTS: {result['vci_recovery_attempts']}")
    print(f"VCI_RECOVERY_COUNT: {result['vci_recovery_count']}")
    print(f"KBS_RECOVERY_ATTEMPTS: {result['kbs_recovery_attempts']}")
    print(f"KBS_RECOVERY_COUNT: {result['kbs_recovery_count']}")
    print(f"RESOLVED_EXACT_SESSION_COUNT: {result['resolved_exact_session_count']}")
    print(f"RESOLVED_DENOMINATOR: {result['resolved_denominator']}")
    print(f"RESOLVED_COVERAGE_RATIO: {result['resolved_coverage_ratio']}")
    print(f"CORROBORATED_COUNT: {result['corroborated_count']}")
    print(f"SINGLE_SOURCE_COUNT: {result['single_source_count']}")
    print(f"CONFLICT_COUNT: {result['conflict_count']}")
    print(f"ALL_SOURCES_MISSING_COUNT: {result['all_sources_missing_count']}")
    print(f"WATCHLIST_11_STATUS: {json.dumps(result['watchlist_11_status'], sort_keys=True)}")
    sentinel = result["dnse_quality_sentinel"]
    if sentinel is not None:
        health = sentinel["health"]
        print(f"DNSE_SENTINEL_COHORT_VERSION: {sentinel['cohort_version']}")
        print(f"DNSE_SENTINEL_SIZE: {sentinel['cohort_size']}")
        print(f"DNSE_PROVIDER_HEALTH_STATE: {health['state']}")
        print(f"DNSE_SENTINEL_CORROBORATED_COUNT: {health['corroborated_count']}")
        print(f"DNSE_SENTINEL_CONFLICT_COUNT: {health['conflict_count']}")
        print(f"DNSE_SENTINEL_UNCORROBORATED_COUNT: {health['uncorroborated_count']}")
    print(f"OUTPUT_DIR: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
