"""Attach the HNX/UPCoM official security-status enrichment to the refreshed official-universe
artifact, and write the retained validation/reconciliation evidence for this milestone."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_official_market_universe import attach_hnx_upcom_security_status, build_no_bar_explanation_summary

OFFICIAL = ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
STATUS = ROOT / "operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913/hnx_upcom_official_security_status_artifact.json"
OUT_DIR = ROOT / "operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913"


def main():
    official = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    enriched = attach_hnx_upcom_security_status(official, status)
    (OUT_DIR / "current_official_market_universe_with_security_status_artifact.json").write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("enriched artifact:", enriched["artifact_identity"])
    print(enriched["hnx_upcom_security_status_enrichment"])

    summary = build_no_bar_explanation_summary(status)
    # HNX vs UPCOM split
    by_market = {}
    for ticker, row in summary["cohort_50_classified"].items():
        by_market.setdefault(row["market"], []).append(row["explanatory_bucket"])
    market_summary = {market: {b: buckets.count(b) for b in set(buckets)} for market, buckets in by_market.items()}

    reconciliation_summary = {
        "no_bar_population": 50,
        "current_status_acquired": sum(1 for r in summary["cohort_50_classified"].values() if r["outcome"] == "CURRENT_PROFILE_FOUND"),
        "official_active": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIALLY_ACTIVE_BUT_NO_RETAINED_BAR"),
        "official_restricted": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIALLY_RESTRICTED"),
        "official_temporarily_stopped": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIALLY_TEMPORARILY_STOPPED"),
        "official_suspended": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIALLY_SUSPENDED"),
        "official_cancelled_or_delisted": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIAL_CANCELLATION_OR_DELISTING_STATUS"),
        "status_unavailable": sum(1 for r in summary["cohort_50_classified"].values() if r["explanatory_bucket"] == "OFFICIAL_STATUS_UNAVAILABLE"),
        "target_session_status_qualified": 0,
        "no_bar_explained_by_official_status": summary["no_bar_explained_by_official_status"],
        "no_bar_still_source_gap": summary["no_bar_still_source_coverage_gap"],
        "temporally_unresolved": summary["no_bar_temporally_unresolved"],
        "by_market": market_summary,
        "six_residual": {t: r["explanatory_bucket"] for t, r in summary["cohort_six_classified"].items()},
    }
    (OUT_DIR / "reconciliation_summary.json").write_text(
        json.dumps(reconciliation_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print()
    print(reconciliation_summary)

    # per-ticker CSV
    import csv
    rows = list(summary["cohort_50_classified"].values()) + list(summary["cohort_six_classified"].values())
    with open(OUT_DIR / "per_ticker_status_table.csv", "w", newline="", encoding="utf-8") as f:
        fieldnames = ["ticker", "market", "outcome", "official_control_status_raw", "official_control_status",
                      "official_trading_status_raw", "official_trading_status", "explanatory_bucket", "target_session_applicability"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in sorted(rows, key=lambda r: r["ticker"]):
            w.writerow({k: row.get(k) for k in fieldnames})
    print("wrote per_ticker_status_table.csv,", len(rows), "rows")


if __name__ == "__main__":
    main()
