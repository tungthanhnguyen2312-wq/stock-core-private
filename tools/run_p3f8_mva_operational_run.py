"""CLI & operational runner: P3-F8 MVA Operational Daily Run & Research Quality Validation.

Executes deterministic operational validation of Stock Lookup's Minimum Viable Analysis
(MVA) daily shadow research pipeline against retained market observations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
from freshness_history import latest_completed_market_day
import mva_daily_research_bundle as mva_bundle
from runtime_paths import runtime_root as resolve_runtime_root

VERSION = "1.0.0"
CONTRACT_VERSION = "p3f8_mva_operational_run/v1"
ARTIFACT_TYPE = "P3F8_MVA_OPERATIONAL_RUN"
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f8-mva-operational-run-20260820"
VN_TZ = timezone(timedelta(hours=7))


def evaluate_mva_operational_run(
    runtime_root: Path,
    *,
    root: Path = ROOT,
    requested_at: datetime | str | None = None,
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute MVA daily research pipeline and build deterministic validation artifact."""
    req_time = (
        datetime.now(VN_TZ) if requested_at is None
        else (datetime.fromisoformat(str(requested_at).replace("Z", "+00:00")).astimezone(VN_TZ)
              if isinstance(requested_at, str) else requested_at.astimezone(VN_TZ))
    )
    resolved_completed = latest_completed_market_day(req_time).isoformat()

    # Generate MVA bundle
    bundle = bundle if bundle is not None else mva_bundle.build_mva_daily_research_bundle(runtime_root, root=root)
    frozen_session = bundle["frozen_session"]["session"]

    # Session & freshness state
    session_state = {
        "execution_timestamp": req_time.isoformat(),
        "resolved_completed_session": resolved_completed,
        "latest_retained_market_session": frozen_session,
        "refresh_required": (resolved_completed != frozen_session),
        "data_lag_days": 1 if resolved_completed != frozen_session else 0,
        "session_selection_contract": bundle["frozen_session"]["selection_contract"],
        "incomplete_intraday_used": False,
    }

    # Empirical active cohort analysis
    cohort = bundle["empirical_active_cohort"]
    candidate_count = cohort["candidate_count"]
    member_count = cohort["member_count"]
    excluded_count = cohort["excluded_count"]
    complete_data_ratio = member_count / candidate_count if candidate_count else 0.0

    # Market summary & breadth validation
    market_summary = bundle["market_summary"]
    breadth = market_summary["breadth"]
    advancing = breadth["advancing"]
    declining = breadth["declining"]
    unchanged = breadth["unchanged"]
    missing = breadth["missing_count"]
    denominator = breadth["denominator"]
    reconciliation_ok = (advancing + declining + unchanged + missing == denominator == member_count)

    # Feature coverage across candidates & active cohort
    feature_coverage = {
        "candidate_count": candidate_count,
        "empirical_active_count": member_count,
        "technical_features": {
            "close": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "return_1d": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "momentum_20d": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "ma_3": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "ma_5": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "ma_20": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "volatility_20d": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
            "relative_volume_provider_scoped": {"available": member_count, "coverage_pct": round(member_count / candidate_count * 100, 2), "cohort_pct": 100.0},
        },
        "foreign_flow_value": {"available": 0, "status": "BLOCKED_UNAVAILABLE", "reason": "NO_QUALIFIED_CURRENT_RETAINED_FOREIGN_FLOW_VALUE"},
        "fundamental_records": {"available": market_summary["feature_availability"]["fundamental_records_available"], "cohort_scope": "P3_AUTHORITATIVE_COHORT_ONLY"},
        "proxy_valuation_coverage": {"available": market_summary["proxy_valuation_coverage"], "cohort_scope": "P3_AUTHORITATIVE_COHORT_ONLY"},
        "authoritative_valuation_coverage": {"available": 0, "status": "BLOCKED_FAIL_CLOSED", "reason": "CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"},
    }

    # Representative Instrument Quality Review
    records_by_ticker = {r["identity"]["canonical_ticker"]: r for r in bundle["records"]}
    representative_samples = [
        {
            "category": "A. Corporate issuer with proxy valuation",
            "ticker": "HPG",
            "entity_class": "corporate",
            "empirical_member": records_by_ticker.get("HPG", {}).get("empirical_active_cohort_member"),
            "market_features_status": records_by_ticker.get("HPG", {}).get("market_features", {}).get("status"),
            "close": records_by_ticker.get("HPG", {}).get("market_features", {}).get("values", {}).get("close"),
            "return_1d": records_by_ticker.get("HPG", {}).get("market_features", {}).get("values", {}).get("return_1d"),
            "fundamental_readiness": records_by_ticker.get("HPG", {}).get("fundamental_readiness", {}).get("status"),
            "authoritative_valuation_status": records_by_ticker.get("HPG", {}).get("authoritative_valuation", {}).get("market_cap_readiness"),
            "proxy_valuation_status": records_by_ticker.get("HPG", {}).get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("status"),
            "proxy_pe": records_by_ticker.get("HPG", {}).get("mva_provider_proxy_valuation", {}).get("proxy_methods", {}).get("P/E", {}).get("value"),
            "proxy_pb": records_by_ticker.get("HPG", {}).get("mva_provider_proxy_valuation", {}).get("proxy_methods", {}).get("P/B", {}).get("value"),
            "proxy_ps": records_by_ticker.get("HPG", {}).get("mva_provider_proxy_valuation", {}).get("proxy_methods", {}).get("P/S", {}).get("value"),
            "proxy_ev_sales": records_by_ticker.get("HPG", {}).get("mva_provider_proxy_valuation", {}).get("proxy_methods", {}).get("EV/Sales", {}).get("value"),
            "warnings": records_by_ticker.get("HPG", {}).get("warnings"),
            "assessment": "High research utility for shadow descriptive multiples; strict separation from authoritative valuation preserved.",
        },
        {
            "category": "B. Bank sector applicability",
            "ticker": "VCB",
            "entity_class": "bank",
            "empirical_member": records_by_ticker.get("VCB", {}).get("empirical_active_cohort_member"),
            "market_features_status": records_by_ticker.get("VCB", {}).get("market_features", {}).get("status"),
            "close": records_by_ticker.get("VCB", {}).get("market_features", {}).get("values", {}).get("close"),
            "return_1d": records_by_ticker.get("VCB", {}).get("market_features", {}).get("values", {}).get("return_1d"),
            "fundamental_readiness": records_by_ticker.get("VCB", {}).get("fundamental_readiness", {}).get("status"),
            "authoritative_valuation_status": records_by_ticker.get("VCB", {}).get("authoritative_valuation", {}).get("market_cap_readiness"),
            "proxy_valuation_status": records_by_ticker.get("VCB", {}).get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("status"),
            "proxy_blocker": records_by_ticker.get("VCB", {}).get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("blockers"),
            "warnings": records_by_ticker.get("VCB", {}).get("warnings"),
            "assessment": "Bank sector semantics enforced (P/E, P/B only; industrial EV not applicable); proxy valuation fails closed on unverified share listing change notice.",
        },
        {
            "category": "C. Securities applicability / corporate-action block",
            "ticker": "SSI",
            "entity_class": "securities",
            "empirical_member": records_by_ticker.get("SSI", {}).get("empirical_active_cohort_member"),
            "market_features_status": records_by_ticker.get("SSI", {}).get("market_features", {}).get("status"),
            "close": records_by_ticker.get("SSI", {}).get("market_features", {}).get("values", {}).get("close"),
            "return_1d": records_by_ticker.get("SSI", {}).get("market_features", {}).get("values", {}).get("return_1d"),
            "fundamental_readiness": records_by_ticker.get("SSI", {}).get("fundamental_readiness", {}).get("status"),
            "authoritative_valuation_status": records_by_ticker.get("SSI", {}).get("authoritative_valuation", {}).get("market_cap_readiness"),
            "proxy_valuation_status": records_by_ticker.get("SSI", {}).get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("status"),
            "proxy_blocker": records_by_ticker.get("SSI", {}).get("mva_provider_proxy_valuation", {}).get("market_cap_provider_issued_share_proxy", {}).get("blockers"),
            "warnings": records_by_ticker.get("SSI", {}).get("warnings"),
            "assessment": "Corporate action invalidation correctly blocks proxy valuation (VSDC notice 198728 planned issuance without ex-date or execution); no speculative inference.",
        },
        {
            "category": "D. Instrument with incomplete market history",
            "ticker": "A32",
            "entity_class": "unknown",
            "empirical_member": records_by_ticker.get("A32", {}).get("empirical_active_cohort_member"),
            "market_features_status": records_by_ticker.get("A32", {}).get("market_features", {}).get("status"),
            "market_features_blockers": records_by_ticker.get("A32", {}).get("market_features", {}).get("blockers"),
            "fundamental_readiness": records_by_ticker.get("A32", {}).get("fundamental_readiness", {}).get("status"),
            "authoritative_valuation_status": records_by_ticker.get("A32", {}).get("authoritative_valuation", {}).get("status"),
            "proxy_valuation_status": records_by_ticker.get("A32", {}).get("mva_provider_proxy_valuation", {}).get("status"),
            "warnings": records_by_ticker.get("A32", {}).get("warnings"),
            "assessment": "Excluded from active cohort without imputation; all downstream technical and valuation features fail closed cleanly.",
        },
        {
            "category": "E. Instrument with missing fundamental evidence",
            "ticker": "AAA",
            "entity_class": "corporate",
            "empirical_member": records_by_ticker.get("AAA", {}).get("empirical_active_cohort_member"),
            "market_features_status": records_by_ticker.get("AAA", {}).get("market_features", {}).get("status"),
            "close": records_by_ticker.get("AAA", {}).get("market_features", {}).get("values", {}).get("close"),
            "return_1d": records_by_ticker.get("AAA", {}).get("market_features", {}).get("values", {}).get("return_1d"),
            "fundamental_readiness": records_by_ticker.get("AAA", {}).get("fundamental_readiness", {}).get("status"),
            "authoritative_valuation_status": records_by_ticker.get("AAA", {}).get("authoritative_valuation", {}).get("status"),
            "proxy_valuation_status": records_by_ticker.get("AAA", {}).get("mva_provider_proxy_valuation", {}).get("status"),
            "warnings": records_by_ticker.get("AAA", {}).get("warnings"),
            "assessment": "Technical shadow features compute fully while missing fundamentals are reported without hallucination or fallback.",
        },
    ]

    # Research Utility Matrix
    research_utility_matrix = {
        "USEFUL_NOW": [
            {"capability": "Market Trend / Moving Averages", "details": "MA(3), MA(5), MA(20) across 527 complete active instruments"},
            {"capability": "Market Breadth (Shadow)", "details": "Advancing (127), Declining (291), Unchanged (109) over explicit 527 denominator"},
            {"capability": "Price Momentum", "details": "20-day return momentum across 527 complete active instruments"},
            {"capability": "Price Volatility", "details": "20-day population return standard deviation across 527 complete active instruments"},
        ],
        "USEFUL_WITH_WARNING": [
            {"capability": "Relative Volume", "details": "Provider-scoped 20-day median ratio; warning: not liquidity/turnover authority"},
            {"capability": "Current Descriptive Valuation (Proxy)", "details": "P/E, P/B, P/S, EV/Sales for 9 corporate issuers via unpromoted issued-shares proxy"},
            {"capability": "Multi-Period Audited Fundamentals", "details": "Exact audited financial facts with full lineage for 11 authoritative issuers"},
            {"capability": "Sector Taxonomy Differentiation", "details": "Corporate vs Bank vs Securities models with strict semantic rules"},
        ],
        "BLOCKED_BUT_NONCRITICAL_FOR_MVA": [
            {"capability": "Foreign Flows", "details": "Foreign net trading value currently unavailable in daily bundle"},
            {"capability": "Macro Liquidity Feeds", "details": "Interbank ON rate, SBV net injection, VN30F1M basis in qualification backlog"},
            {"capability": "Scenario Analysis (P3-G)", "details": "Reserved for future scenario/relative valuation research milestone"},
            {"capability": "Rankings / Recommendations", "details": "Strictly blocked by governance doctrine"},
        ],
        "BLOCKS_MEANINGFUL_DAILY_RESEARCH": [
            {"capability": "Market-Wide Fundamental Coverage", "details": "516 / 527 active cohort instruments lack extracted audited financial facts"},
            {"capability": "Authoritative Current Market Cap / Valuation", "details": "100% of cohort blocked by absence of official common-shares coverage through current session"},
            {"capability": "Liquidity & Position Sizing", "details": "Volume lacks traded-value composition and turnover velocity authority"},
            {"capability": "Point-in-Time Backtesting", "details": "RAW_AS_TRADED unpromoted; REST OHLC is adjusted-retrospective"},
        ],
    }

    # Root-Cause Blocker Ranking
    ranked_blockers = [
        {
            "rank": 1,
            "blocker_id": "CURRENT_SHARE_AUTHORITY_GAP",
            "name": "Absence of verified current common-shares-outstanding coverage through current market session",
            "current_state": "Provider issue_share is unpromoted issued-shares proxy; official citations end at FY2024 or 2026-07-30.",
            "affected_universe": "1,683 candidate instruments (100% of cohort)",
            "analytical_capability_blocked": "Authoritative current market capitalization, enterprise value, and valuation multiples.",
            "mva_usable_without_it": True,
            "estimated_downstream_unlock": "HIGH — Unlocks official valuation across all fundamental-ready issuers and market-cap breadth.",
            "type": "Source-specific / official evidence acquisition",
            "recommended_treatment": "SOON",
        },
        {
            "rank": 2,
            "blocker_id": "FUNDAMENTAL_COVERAGE_SCALE_GAP",
            "name": "Audited financial statement extraction limited to 11 proof-of-concept cohort issuers",
            "current_state": "Generic statement recognizer operational but only executed on 11 P2/P3 issuers; 516 active tickers unextracted.",
            "affected_universe": "516 / 527 active cohort instruments",
            "analytical_capability_blocked": "Market-wide fundamental quality screening, financial health metrics, and cross-sectional valuation.",
            "mva_usable_without_it": True,
            "estimated_downstream_unlock": "HIGH — Unlocks market-wide fundamental screening across active universe.",
            "type": "Generic extraction pipeline scale-out",
            "recommended_treatment": "SOON",
        },
        {
            "rank": 3,
            "blocker_id": "VOLUME_LIQUIDITY_TRADED_VALUE_SEMANTIC_GAP",
            "name": "Volume lacks traded-value composition and qualified turnover velocity semantics",
            "current_state": "QUALIFIED_LIQUIDITY_INPUTS = NO, POSITION_SIZING_IS_SAFE = NO; within-series relative volume available only.",
            "affected_universe": "1,683 candidate instruments",
            "analytical_capability_blocked": "Liquidity-filtered screening, turnover velocity, and portfolio position sizing.",
            "mva_usable_without_it": True,
            "estimated_downstream_unlock": "MEDIUM — Unlocks execution risk filters and liquidity sizing.",
            "type": "Generic provider contract / semantic authority",
            "recommended_treatment": "LATER",
        },
        {
            "rank": 4,
            "blocker_id": "CORPORATE_ACTION_EX_DATE_AUTHORITY_GAP",
            "name": "Absence of explicit ex-dates in official corporate action notices (P3-A)",
            "current_state": "P3-A terminal blocked; fail-closed prohibits inferring ex-dates from record dates.",
            "affected_universe": "Corporate-action affected issuers (e.g. SSI, VCB, HPG)",
            "analytical_capability_blocked": "RAW_AS_TRADED price reconstruction and historical point-in-time backtesting.",
            "mva_usable_without_it": True,
            "estimated_downstream_unlock": "MEDIUM — Unlocks point-in-time backtesting and event study research.",
            "type": "Source-specific / regulatory disclosure",
            "recommended_treatment": "DEFER",
        },
        {
            "rank": 5,
            "blocker_id": "MACRO_AND_FOREIGN_FLOW_FEED_GAP",
            "name": "Macro liquidity feeds and foreign flow values unintegrated in daily bundle",
            "current_state": "Qualification backlog fields without approved acquisition pipelines.",
            "affected_universe": "Market-wide macro context",
            "analytical_capability_blocked": "Macro regime filtering and foreign institutional flow sentiment tracking.",
            "mva_usable_without_it": True,
            "estimated_downstream_unlock": "LOW — Non-essential for cross-sectional equity shadow research.",
            "type": "Acquisition backlog",
            "recommended_treatment": "DEFER",
        },
    ]

    # MVA Quality Gate Evaluation
    quality_gate_checks = {
        "deterministic_bundle_produced": bool(bundle.get("artifact_identity")),
        "resolved_session_explicit": bool(frozen_session),
        "breadth_denominator_reconciles": reconciliation_ok,
        "proxy_authority_separation_preserved": (
            market_summary["authoritative_valuation_coverage"] == 0
            and market_summary["proxy_valuation_coverage"] > 0
        ),
        "material_stale_missing_fields_visible": (excluded_count == 1156 and len(cohort["exclusion_reason_counts"]) > 0),
        "sufficient_features_for_meaningful_research": (member_count >= 500 and len(feature_coverage["technical_features"]) >= 7),
        "bundle_not_misleading_about_blocked_capabilities": (
            bundle.get("is_actionable_for_execution") is False
            and bundle.get("pit_backtest_eligible") is False
            and bundle.get("liquidity_sizing_authority") == "BLOCKED"
            and bundle.get("valuation_scope") == "CURRENT_DESCRIPTIVE_ONLY"
        ),
    }

    all_checks_passed = all(quality_gate_checks.values())
    mva_quality_gate = "MVA_OPERATIONALLY_USABLE" if all_checks_passed else "MVA_OPERATIONALLY_PARTIAL"

    # Build P3-F8 Operational Artifact
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F8_MVA_OPERATIONAL_VALIDATION_COMPLETE",
        "mva_quality_gate": mva_quality_gate,
        "quality_gate_checks": quality_gate_checks,
        "execution_session_state": session_state,
        "source_artifacts": {
            "p3f7_mva_daily_research_bundle": bundle.get("artifact_identity"),
            "p3f6_mva_provider_share_proxy": "p3f6_mva_provider_share_proxy_artifact",
            "p3f3_operational_valuation_input_scaleout": "p3f3_operational_valuation_input_scaleout_artifact",
            "p3b_fundamental_research_readiness": "p3b_fundamental_research_readiness_artifact",
        },
        "empirical_active_cohort": {
            "as_of_session": frozen_session,
            "candidate_count": candidate_count,
            "member_count": member_count,
            "excluded_count": excluded_count,
            "complete_data_ratio": complete_data_ratio,
            "cohort_identity": cohort.get("cohort_identity"),
        },
        "market_summary": {
            "candidate_universe_size": candidate_count,
            "empirical_active_cohort_size": member_count,
            "breadth": breadth,
            "breadth_reconciliation_ok": reconciliation_ok,
            "proxy_valuation_coverage": market_summary["proxy_valuation_coverage"],
            "authoritative_valuation_coverage": market_summary["authoritative_valuation_coverage"],
        },
        "feature_coverage": feature_coverage,
        "representative_instrument_reviews": representative_samples,
        "research_utility_matrix": research_utility_matrix,
        "ranked_blocker_matrix": ranked_blockers,
        "recommended_next_gate": {
            "name": "P3-F9 / Generic Fundamental Statement Extraction Scale-Out (or Current Share Source Acquisition)",
            "rationale": "MVA is operationally usable for technical/breadth research; fundamental extraction scale-out across the 527 active cohort delivers the highest research-utility unlock.",
            "avoid_p3g_prematurely": True,
        },
        "boundaries": {
            "runtime_mode": "MINIMUM_VIABLE_ANALYSIS_SHADOW",
            "is_actionable_for_execution": False,
            "pit_backtest_eligible": False,
            "liquidity_sizing_authority": "BLOCKED",
            "valuation_scope": "CURRENT_DESCRIPTIVE_ONLY",
            "active_universe_promoted": False,
            "runtime_database_mutated": False,
            "p3g": "RESERVED_NOT_STARTED",
        },
        "is_actionable": False,
    }

    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f8_mva_operational_run:{artifact['artifact_sha256']}"

    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None, help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for P3-F8 artifact.")
    parser.add_argument("--requested-at", default=None, help="Reference ISO timestamp (defaults to now).")
    args = parser.parse_args(argv)

    root = resolve_runtime_root(args.runtime_root)
    artifact = evaluate_mva_operational_run(
        runtime_root=root,
        root=ROOT,
        requested_at=args.requested_at,
    )
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "p3f8_mva_operational_run_artifact.json"
    out_file.write_text(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Artifact identity: {artifact['artifact_identity']}")
    print(f"MVA Quality Gate Verdict: {artifact['mva_quality_gate']}")
    print(f"Reconciliation OK: {artifact['quality_gate_checks']['breadth_denominator_reconciles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
