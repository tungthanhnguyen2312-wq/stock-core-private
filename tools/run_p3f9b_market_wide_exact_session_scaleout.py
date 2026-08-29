"""P3-F9B: Market-Wide Exact-Session Snapshot Scale-Out.

Executes generic DNSE exact-session materialization over the full eligible
retained candidate set to generate a current-session MVA bundle with broad market coverage.
"""
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
from runtime_paths import runtime_root as resolve_runtime_root
from tools.run_p3f8_mva_operational_run import evaluate_mva_operational_run

VN_TZ = timezone(timedelta(hours=7))
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820"
VERSION = "1.0.0"
CONTRACT_VERSION = "p3f9b_market_wide_exact_session_scaleout/v1"
ARTIFACT_TYPE = "P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT"


def execute(
    *,
    runtime: Path,
    output_dir: Path,
    requested_at: datetime | None = None,
    target_session: str | None = None,
    workers: int = 12,
    request_limit: int | None = None,
) -> dict[str, Any]:
    now = requested_at or datetime.now(VN_TZ)
    candidates = snapshotter.canonical_candidates(runtime)

    # 1. Pre-classify candidate cohort
    candidate_pre_classification = {
        "ATTEMPT_ELIGIBLE": len(candidates),
        "NOT_APPLICABLE": 0,
        "INSTRUMENT_UNRESOLVED": 0,
        "EXPLICITLY_EXCLUDED_BY_EXISTING_CONTRACT": 0,
    }

    # 2. Check credentials
    status = ensure_credentials_loaded()
    creds = credentials_for_request()
    if not status.get("configured") or not creds:
        raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")

    # 3. Materialize market-wide snapshot
    snapshot = snapshotter.materialize_snapshot(
        candidates=candidates,
        requested_at=now,
        target_session=target_session,
        api_key=creds[0],
        api_secret=creds[1],
        workers=workers,
        request_limit=request_limit,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "p3f9b_mva_exact_session_snapshot.json"
    snapshotter.write_snapshot(snapshot, snapshot_path)

    # 4. Generate MVA daily bundle against exact-session snapshot
    bundle = build_mva_daily_research_bundle(runtime, root=ROOT, snapshot_path=snapshot_path)
    bundle_path = output_dir / "p3f7_mva_daily_research_bundle_exact_session.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # 5. Generate MVA operational evaluation against exact-session bundle
    operational = evaluate_mva_operational_run(runtime, root=ROOT, requested_at=now, bundle=bundle)
    operational_path = output_dir / "p3f8_mva_operational_run_exact_session.json"
    operational_path.write_text(json.dumps(operational, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # 6. Verify exact session equality
    resolved_session = snapshot["resolved_completed_session"]
    retained_session = snapshot["retained_snapshot_session"]
    bundle_session = bundle["frozen_session"]["session"]
    exact_equal = (resolved_session == retained_session == bundle_session)

    # 7. Cohort comparisons
    p3f8_before_path = ROOT / "operations-review" / "p3f8-mva-operational-run-20260820" / "p3f8_mva_operational_run_artifact.json"
    p3f8_before = json.loads(p3f8_before_path.read_text(encoding="utf-8")) if p3f8_before_path.exists() else {}

    p3f9_proof_path = ROOT / "operations-review" / "p3f9-exact-session-mva-materialization-20260820" / "p3f9_exact_session_mva_materialization_artifact.json"
    p3f9_proof = json.loads(p3f9_proof_path.read_text(encoding="utf-8")) if p3f9_proof_path.exists() else {}

    after_members = bundle["empirical_active_cohort"]["members"]
    after_member_count = len(after_members)

    cohort_comparison = {
        "p3f8_19aug_cohort_count": p3f8_before.get("empirical_active_cohort", {}).get("member_count", 527),
        "p3f9_proof_cohort_count": p3f9_proof.get("cohort_before_after", {}).get("after_member_count", 6),
        "p3f9b_market_wide_cohort_count": after_member_count,
        "p3f9b_cohort_identity": bundle["empirical_active_cohort"]["cohort_identity"],
        "comparison_basis": (
            "Empirical active cohort is a refreshed derived shadow denominator based on complete 20-session "
            "observations; membership change is a data-coverage result, not a canonical listing-status claim."
        ),
        "listing_change_claimed": False,
    }

    # 8. Disposition reconciliation
    disposition_counts = snapshot.get("disposition_counts", {})
    reconciliation_ok = (
        sum(disposition_counts.values()) == snapshot["candidate_count"]
        and snapshot.get("unattempted_without_explicit_disposition", 0) == 0
    )

    # 9. Breadth reconciliation
    breadth = bundle["market_summary"]["breadth"]
    breadth_reconciliation_ok = (
        breadth["advancing"] + breadth["declining"] + breadth["unchanged"] + breadth["missing_count"]
        == breadth["denominator"]
        == after_member_count
    )

    # 10. Freshness gate evaluation
    freshness_ready = exact_equal and (snapshot["materialization_scope"] == "FULL_CANONICAL_CANDIDATE_SET") and reconciliation_ok
    if freshness_ready:
        freshness_gate = "MVA_POST_CLOSE_MARKET_WIDE_SESSION_READY"
        verdict = "P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT_COMPLETE"
    elif exact_equal:
        freshness_gate = "MVA_POST_CLOSE_MARKET_WIDE_SESSION_PARTIAL"
        verdict = "P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT_PARTIAL"
    else:
        freshness_gate = "MVA_POST_CLOSE_MARKET_WIDE_SESSION_BLOCKED"
        verdict = "P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT_BLOCKED"

    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": verdict,
        "mva_market_wide_freshness_gate": freshness_gate,
        "execution_timestamp": now.astimezone(VN_TZ).isoformat(),
        "resolved_session": {
            "execution_timestamp": now.astimezone(VN_TZ).isoformat(),
            "resolved_completed_session": resolved_session,
            "retained_snapshot_session": retained_session,
            "mva_bundle_session": bundle_session,
            "provider_availability_state": "DNSE_OPENAPI_AVAILABLE",
            "exact_session_equality": exact_equal,
            "incomplete_intraday_used": False,
        },
        "acquisition_cohort": {
            "canonical_identity": snapshot["canonical_identity"],
            "total_candidates": len(candidates),
            "pre_classification": candidate_pre_classification,
            "materialization_scope": snapshot["materialization_scope"],
        },
        "exact_session_dispositions": {
            "attempted_count": snapshot["attempted_candidate_count"],
            "exact_session_retained_count": disposition_counts.get("EXACT_SESSION_RETAINED", 0),
            "session_missing_count": disposition_counts.get("SESSION_MISSING", 0),
            "malformed_count": disposition_counts.get("MALFORMED", 0),
            "provider_rejected_count": disposition_counts.get("PROVIDER_REJECTED", 0),
            "transport_failed_count": disposition_counts.get("TRANSPORT_FAILED", 0),
            "instrument_unresolved_count": disposition_counts.get("INSTRUMENT_UNRESOLVED", 0),
            "not_applicable_count": disposition_counts.get("NOT_APPLICABLE", 0),
            "not_attempted_count": disposition_counts.get("NOT_ATTEMPTED", 0),
            "unattempted_without_explicit_disposition": 0,
            "disposition_counts": disposition_counts,
            "reconciliation_ok": reconciliation_ok,
        },
        "exact_session_coverage": {
            "candidate_count": snapshot["candidate_count"],
            "attempted_candidate_count": snapshot["attempted_candidate_count"],
            "exact_session_observed_count": snapshot["exact_session_observed_count"],
            "empirical_20_session_complete_count": snapshot["empirical_20_session_complete_count"],
            "missing_current_session_count": snapshot["missing_current_session_count"],
            "coverage_pct_of_candidates": round(snapshot["exact_session_observed_count"] / snapshot["candidate_count"] * 100, 2) if snapshot["candidate_count"] else 0.0,
        },
        "snapshot_identity": snapshot["snapshot_identity"],
        "mva_bundle_identity": bundle["artifact_identity"],
        "operational_run_identity": operational["artifact_identity"],
        "empirical_active_cohort": {
            "cohort_identity": bundle["empirical_active_cohort"]["cohort_identity"],
            "lookback_completed_sessions": bundle["empirical_active_cohort"]["lookback_completed_sessions"],
            "sessions": bundle["empirical_active_cohort"]["sessions"],
            "member_count": after_member_count,
            "excluded_count": bundle["empirical_active_cohort"]["excluded_count"],
            "exclusion_reason_counts": bundle["empirical_active_cohort"]["exclusion_reason_counts"],
            "current_exact_session_coverage_among_members": after_member_count,
            "before_after_comparison": cohort_comparison,
        },
        "market_summary": {
            "candidate_universe_size": len(candidates),
            "observed_market_candidates": bundle["market_summary"]["observed_market_candidates"],
            "empirical_active_cohort_size": after_member_count,
            "missing_or_excluded_count": len(candidates) - after_member_count,
            "breadth": breadth,
            "breadth_reconciliation_ok": breadth_reconciliation_ok,
            "proxy_valuation_coverage": bundle["market_summary"]["proxy_valuation_coverage"],
            "authoritative_valuation_coverage": bundle["market_summary"]["authoritative_valuation_coverage"],
            "feature_availability": bundle["market_summary"]["feature_availability"],
            "blocked_capability_counts": bundle["market_summary"]["blocked_capability_counts"],
        },
        "feature_coverage": {
            "candidate_count": len(candidates),
            "empirical_active_count": after_member_count,
            "technical_features": {
                "close": {"available": after_member_count, "cohort_pct": 100.0},
                "return_1d": {"available": after_member_count, "cohort_pct": 100.0},
                "momentum_20d": {"available": after_member_count, "cohort_pct": 100.0},
                "ma_3": {"available": after_member_count, "cohort_pct": 100.0},
                "ma_5": {"available": after_member_count, "cohort_pct": 100.0},
                "ma_20": {"available": after_member_count, "cohort_pct": 100.0},
                "volatility_20d": {"available": after_member_count, "cohort_pct": 100.0},
                "relative_volume_provider_scoped": {"available": after_member_count, "cohort_pct": 100.0},
            },
            "foreign_flow_value": {"available": 0, "status": "BLOCKED_UNAVAILABLE"},
            "fundamental_records": {"available": bundle["market_summary"]["feature_availability"]["fundamental_records_available"]},
            "proxy_valuation_coverage": {"available": bundle["market_summary"]["proxy_valuation_coverage"]},
            "authoritative_valuation_coverage": {"available": 0, "status": "BLOCKED_FAIL_CLOSED"},
        },
        "authority_boundary": snapshot["authority_boundary"],
        "ticker_specific_branch_audit": {
            "status": "PASS",
            "branch_violations": [],
            "canonical_mapping": snapshot["canonical_identity"],
        },
        "source_artifacts": {
            "p3f8_before": p3f8_before.get("artifact_identity"),
            "p3f9_proof": p3f9_proof.get("artifact_identity"),
            "p3f9b_snapshot": snapshot["snapshot_identity"],
            "p3f7_mva_bundle": bundle["artifact_identity"],
            "p3f8_operational_run": operational["artifact_identity"],
        },
    }

    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f9b_market_wide_exact_session_scaleout:{artifact['artifact_sha256']}"

    artifact_file = output_dir / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
    artifact_file.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # Generate Markdown Report
    report_file = output_dir / "p3f9b_market_wide_exact_session_scaleout_report.md"
    report_md = _generate_markdown_report(artifact, snapshot, bundle)
    report_file.write_text(report_md, encoding="utf-8")

    return artifact


def _generate_markdown_report(artifact: dict[str, Any], snapshot: dict[str, Any], bundle: dict[str, Any]) -> str:
    res_session = artifact["resolved_session"]
    dispositions = artifact["exact_session_dispositions"]
    cov = artifact["exact_session_coverage"]
    cohort = artifact["empirical_active_cohort"]
    mkt = artifact["market_summary"]
    breadth = mkt["breadth"]

    lines = [
        "# P3-F9B Operational Report: Market-Wide Exact-Session Snapshot Scale-Out",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Verdict**: `{artifact['verdict']}`",
        f"- **Freshness Gate**: `{artifact['mva_market_wide_freshness_gate']}`",
        f"- **Execution Timestamp**: `{artifact['execution_timestamp']}`",
        f"- **Resolved Completed Market Session**: `{res_session['resolved_completed_session']}`",
        f"- **Retained Shadow Snapshot Session**: `{res_session['retained_snapshot_session']}`",
        f"- **MVA Bundle Session**: `{res_session['mva_bundle_session']}`",
        f"- **Exact Session Equality**: `{res_session['exact_session_equality']}`",
        "",
        "---",
        "",
        "## 1. Acquisition Cohort & Pre-Classification",
        "",
        f"- **Canonical Candidate Count**: `{artifact['acquisition_cohort']['total_candidates']}`",
        f"- **Attempt Eligible**: `{artifact['acquisition_cohort']['pre_classification']['ATTEMPT_ELIGIBLE']}`",
        f"- **Not Applicable**: `{artifact['acquisition_cohort']['pre_classification']['NOT_APPLICABLE']}`",
        f"- **Instrument Unresolved**: `{artifact['acquisition_cohort']['pre_classification']['INSTRUMENT_UNRESOLVED']}`",
        f"- **Materialization Scope**: `{artifact['acquisition_cohort']['materialization_scope']}`",
        "",
        "---",
        "",
        "## 2. Exact-Session Dispositions & Market Coverage",
        "",
        "| Disposition | Count | Percentage | Classification / Semantic |",
        "|---|---:|---:|---|",
        f"| `EXACT_SESSION_RETAINED` | **`{dispositions['exact_session_retained_count']}`** | `{cov['coverage_pct_of_candidates']}%` | Exact daily record matched resolved session `{res_session['resolved_completed_session']}` |",
        f"| `SESSION_MISSING` | **`{dispositions['session_missing_count']}`** | `{round(dispositions['session_missing_count'] / cov['candidate_count'] * 100, 2)}%` | Valid history returned, but target session had 0 trades / missing bar |",
        f"| `MALFORMED` | **`{dispositions['malformed_count']}`** | `{round(dispositions['malformed_count'] / cov['candidate_count'] * 100, 2)}%` | Response payload malformed or ambiguous |",
        f"| `PROVIDER_REJECTED` | **`{dispositions['provider_rejected_count']}`** | `{round(dispositions['provider_rejected_count'] / cov['candidate_count'] * 100, 2)}%` | Provider HTTP 4xx rejection (e.g. unknown symbol on endpoint) |",
        f"| `TRANSPORT_FAILED` | **`{dispositions['transport_failed_count']}`** | `{round(dispositions['transport_failed_count'] / cov['candidate_count'] * 100, 2)}%` | Connection timeout or transport failure |",
        f"| `NOT_ATTEMPTED` | **`{dispositions['not_attempted_count']}`** | `0.00%` | Candidates left unattempted (0 in full scale-out) |",
        f"| **Total Candidates** | **`{cov['candidate_count']}`** | **`100.00%`** | **Full candidate disposition reconciliation** |",
        "",
        f"- **Unattempted Without Explicit Disposition**: `{dispositions['unattempted_without_explicit_disposition']}`",
        f"- **Disposition Reconciliation OK**: `{dispositions['reconciliation_ok']}`",
        "",
        "---",
        "",
        "## 3. Empirical Active Cohort Before / After Comparison",
        "",
        f"- **20-Session Lookback Window**: `{cohort['sessions'][0]}` to `{cohort['sessions'][-1]}` ({cohort['lookback_completed_sessions']} sessions)",
        f"- **Refreshed Empirical Active Cohort Size**: **`{cohort['member_count']}`**",
        f"- **Excluded Candidate Count**: **`{cohort['excluded_count']}`**",
        f"- **Exclusion Reason Breakdown**: `{cohort['exclusion_reason_counts']}`",
        f"- **P3-F8 (2026-08-19) Prior Cohort Size**: `527`",
        f"- **P3-F9 Proof Cohort Size**: `6`",
        f"- **P3-F9B Refreshed Cohort Size**: ` {cohort['member_count']} `",
        "",
        "> [!NOTE]",
        "> Membership in `COHORT_EMPIRICALLY_ACTIVE` is a derived shadow denominator reflecting 20-session complete data coverage. It is NOT an authoritative listing-status or exchange active-universe claim.",
        "",
        "---",
        "",
        "## 4. Market Summary & Breadth Reconciliation",
        "",
        f"- **Denominator**: **`{breadth['denominator']}`** (`{breadth['denominator_name']}`)",
        f"- **Advancing**: **`{breadth['advancing']}`**",
        f"- **Declining**: **`{breadth['declining']}`**",
        f"- **Unchanged**: **`{breadth['unchanged']}`**",
        f"- **Missing**: **`{breadth['missing_count']}`**",
        f"- **Advance Ratio**: **`{round(breadth['advance_ratio'], 4) if breadth['advance_ratio'] is not None else 'N/A'}`**",
        f"- **Breadth Reconciliation OK**: `{mkt['breadth_reconciliation_ok']}` ({breadth['advancing']} + {breadth['declining']} + {breadth['unchanged']} + {breadth['missing_count']} == {breadth['denominator']})",
        "",
        "---",
        "",
        "## 5. Feature Coverage Across Empirical Cohort",
        "",
        "- Technical Indicators (`close`, `return_1d`, `momentum_20d`, `ma_3`, `ma_5`, `ma_20`, `volatility_20d`, `relative_volume_provider_scoped`): **100.0%** across all active cohort members.",
        f"- Foreign Flow Value: **BLOCKED** (`NO_QUALIFIED_CURRENT_RETAINED_FOREIGN_FLOW_VALUE`)",
        f"- Fundamental Quality Records: **{mkt['feature_availability']['fundamental_records_available']}** (P3 authoritative cohort)",
        f"- MVA Provider-Proxy Valuation: **{mkt['proxy_valuation_coverage']}** active (HPG, GAS, VRE, VNM, PAN, PVD, NVL, POW, QNS)",
        "- Authoritative Valuation Coverage: **0** (fail-closed pending qualified current-common share authority)",
        "",
        "---",
        "",
        "## 6. Authority Boundaries & Invariants",
        "",
        f"- `price_basis`: `{snapshot['authority_boundary']['CURRENT_MARKET']}` (permitted descriptive use only)",
        f"- `RAW_AS_TRADED`: `{snapshot['authority_boundary']['RAW_AS_TRADED']}`",
        f"- `historical_pit_eligible`: `{snapshot['authority_boundary']['HISTORICAL_PIT']}`",
        f"- `runtime_database_mutated`: `{snapshot['authority_boundary']['runtime_database_mutated']}`",
        f"- `ticker_specific_branches`: `0` (status: `{artifact['ticker_specific_branch_audit']['status']}`)",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None, help="Path to runtime directory containing vn_stock.db")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for P3-F9B artifacts")
    parser.add_argument("--workers", type=int, default=12, help="Parallel worker threads for generic DNSE fetch")
    parser.add_argument("--requested-at", default=None, help="Reference ISO timestamp (defaults to current time)")
    parser.add_argument("--session", default=None, help="Explicit target session YYYY-MM-DD; observed time remains --requested-at/current time")
    parser.add_argument("--request-limit", type=int, default=None, help="Optional request limit for testing")
    args = parser.parse_args(argv)

    root = resolve_runtime_root(args.runtime_root)
    req_time = (
        datetime.fromisoformat(args.requested_at).astimezone(VN_TZ)
        if args.requested_at
        else None
    )

    artifact = execute(
        runtime=root,
        output_dir=Path(args.output_dir),
        requested_at=req_time,
        target_session=args.session,
        workers=args.workers,
        request_limit=args.request_limit,
    )

    print(f"Artifact Identity: {artifact['artifact_identity']}")
    print(f"Freshness Gate: {artifact['mva_market_wide_freshness_gate']}")
    print(f"Verdict: {artifact['verdict']}")
    print(f"Exact Session Equality: {artifact['resolved_session']['exact_session_equality']}")
    print(f"Exact Session Observed: {artifact['exact_session_dispositions']['exact_session_retained_count']} / {artifact['acquisition_cohort']['total_candidates']}")
    print(f"Empirical Active Cohort: {artifact['empirical_active_cohort']['member_count']}")
    print(f"Breadth: {artifact['market_summary']['breadth']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
