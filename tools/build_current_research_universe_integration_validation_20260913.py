"""Build the retained validation artifact for CURRENT_RESEARCH_OFFICIAL_UNIVERSE_CONSUMER_
INTEGRATION_V1. No network. Reads only already-retained evidence."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "operations-review/current-research-official-universe-consumer-integration-v1-20260913"

from current_research_official_universe_scope import resolve_scope


def main():
    official = json.loads((ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json").read_text(encoding="utf-8"))
    enriched = json.loads((ROOT / "operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913/current_official_market_universe_with_security_status_artifact.json").read_text(encoding="utf-8"))
    status = json.loads((ROOT / "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260911/current_universe_status_and_session_coverage_resolution_artifact.json").read_text(encoding="utf-8"))["records"]

    case_a = resolve_scope(official_artifact=official, research_session="2026-09-11")
    case_b = resolve_scope(official_artifact=enriched, research_session="2026-09-20")

    pop502 = [t for t, v in status.items() if v.get("activity_and_session_reason_code") == "TARGET_SESSION_GAP_WITH_NEARBY_OBSERVED_ACTIVITY"]
    pop50 = [t for t, v in status.items() if v.get("activity_and_session_reason_code") == "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"]

    summary = {
        "contract_version": "current_research_official_universe_scope/v1",
        "reference_vs_scoped_accounting": {
            "source_reference_universe": case_b["source_reference_ticker_count"],
            "current_official_research_scope": case_b["current_research_scope_ticker_count"],
            "outside_current_scope": case_b["source_reference_ticker_count"] - case_b["current_research_scope_ticker_count"],
            "official_only_not_added": len(official["reconciliation"]["official_only_tickers"]),
        },
        "excluded_current_master_residual": {
            "delisting_correlated_count": sum(1 for r in case_b["records"].values() if r["current_research_scope_state"] == "OUTSIDE_CURRENT_OFFICIAL_MASTER_REASON_DELISTING_CORRELATED"),
            "unresolved_count": sum(1 for r in case_b["records"].values() if r["current_research_scope_state"] == "OUTSIDE_CURRENT_OFFICIAL_MASTER_REASON_UNRESOLVED"),
            "unresolved_tickers": sorted(t for t, r in case_b["records"].items() if r["current_research_scope_state"] == "OUTSIDE_CURRENT_OFFICIAL_MASTER_REASON_UNRESOLVED"),
        },
        "official_only_table": official["reconciliation"]["official_only_tickers"],
        "temporal_gate_replay": {
            "case_a_historical_session_2026_09_11": {
                "disposition": case_a["disposition"], "temporally_eligible": case_a["temporally_eligible"],
                "current_research_scope_ticker_count": case_a["current_research_scope_ticker_count"],
            },
            "case_b_synthetic_future_session_2026_09_20": {
                "disposition": case_b["disposition"], "temporally_eligible": case_b["temporally_eligible"],
                "current_research_scope_ticker_count": case_b["current_research_scope_ticker_count"],
            },
        },
        "502_source_gap_coverage": {
            "population": len(pop502),
            "in_scope": sum(1 for t in pop502 if case_b["records"][t]["current_research_scope_state"] == "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"),
        },
        "50_no_bar_coverage": {
            "population": len(pop50),
            "in_scope": sum(1 for t in pop50 if case_b["records"][t]["current_research_scope_state"] == "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"),
            "official_active_count": sum(1 for t in pop50 if case_b["records"][t].get("official_security_status") == "ACTIVE"),
            "restricted_or_suspended_count": sum(1 for t in pop50 if case_b["records"][t].get("official_security_status") in ("RESTRICTED", "SUSPENDED")),
        },
        "watchlist_safety": {
            t: case_b["records"][t]["current_research_scope_state"]
            for t in ("HPG", "FPT", "SSI", "VCB", "PAN", "PNJ", "PVD", "QNS", "VNM", "EVF", "POW", "NVL")
        },
        "authority_effect": "NONE / CURRENT_RESEARCH_UNIVERSE_CONSUMER_INTEGRATION_PREVIEW_ONLY",
        "production_cutover": "NOT_PERFORMED",
        "active_universe_authority_promotion": "NOT_PERFORMED",
        "historical_pit_universe": "BLOCKED",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "integration_validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "resolve_scope_case_a_historical_2026_09_11.json").write_text(json.dumps(case_a, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "resolve_scope_case_b_synthetic_2026_09_20.json").write_text(json.dumps(case_b, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
