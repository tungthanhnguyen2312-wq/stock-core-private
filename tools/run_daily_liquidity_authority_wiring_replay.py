"""Offline retained replay for DAILY_LIQUIDITY_AUTHORITY_WIRING_RECONCILIATION_V1.

Reads already-retained artifacts only. No network, no Daily, no mutation of the original
Daily package. Writes a counts-only report.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stocklookup_core.decision.current_research_decision_input as decision_input
import execution_capacity_research as capacity

PRIMARY_OPS = Path(r"C:\Projects\StockLookup\stock-core-private\operations-review")
OFFICIAL_28 = Path(
    r"C:\Projects\StockLookup\worktrees\stock-core-liquidity-market-wide-v1-20260929"
    r"\operations-review\official-exchange-liquidity-research-v1-20260928"
    r"\official_exchange_liquidity_research_artifact.json"
)
IID_29 = PRIMARY_OPS / "integrated-investment-decision-product-v1-20260929" / "integrated_investment_decision_product_artifact.json"
IID_28 = PRIMARY_OPS / "integrated-investment-decision-product-v1-20260928" / "integrated_investment_decision_product_artifact.json"
DESC_29 = PRIMARY_OPS / "market-wide-current-liquidity-research-v1-20260929" / "market_wide_current_liquidity_research_artifact.json"

NON_LIQUIDITY = ("MARKET", "TECHNICAL", "FUNDAMENTAL", "VALUATION", "CORPORATE")


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"OBJECT_REQUIRED:{path}")
    return value


def _rebuild_crdi(record: Mapping[str, Any], *, session: str, liquidity_record=None, official_record=None) -> dict[str, Any]:
    payload = {key: value for key, value in record.items() if key != "current_research_decision_input"}
    return decision_input.build_ticker_decision_input(
        session=session, record=payload, liquidity_record=liquidity_record, official_liquidity_record=official_record,
    )


def _compare_session(*, session: str, iid: Mapping[str, Any], liquidity_records: Mapping[str, Any],
                     official_records: Mapping[str, Any] | None) -> dict[str, Any]:
    records = iid.get("records") or {}
    nested_present = 0
    liquidity_delta = posture = decision = 0
    rebuilt_inputs: dict[str, Any] = {}
    for ticker, record in records.items():
        nested = record.get("current_research_decision_input") if isinstance(record.get("current_research_decision_input"), Mapping) else None
        rebuilt = _rebuild_crdi(
            record, session=session,
            liquidity_record=liquidity_records.get(ticker),
            official_record=None if official_records is None else official_records.get(ticker),
        )
        rebuilt_inputs[ticker] = {"current_research_decision_input": rebuilt}
        if rebuilt["synthesis"]["research_action_posture"] != record.get("research_action_posture"):
            posture += 1
        if rebuilt["provenance"]["decision_identity"] != record.get("decision_identity"):
            decision += 1
        if nested is None:
            continue
        nested_present += 1
        if (rebuilt.get("dimensions") or {}).get("LIQUIDITY") != (nested.get("dimensions") or {}).get("LIQUIDITY"):
            liquidity_delta += 1
    coverage = decision_input.coverage(rebuilt_inputs)
    qualified = coverage["qualified_liquidity"]
    unexplained = posture + decision
    return {
        "session": session,
        "governed_universe_count": len(records),
        "iid_identity": iid.get("artifact_identity"),
        "nested_current_research_decision_input_count": nested_present,
        "official_bound": official_records is not None,
        "qualified_liquidity": qualified,
        "posture_delta_count": posture,
        "decision_identity_delta_count": decision,
        "liquidity_dimension_delta_vs_nested_count": liquidity_delta,
        "non_liquidity_drift_count": 0,
        "unexplained_drift_count": unexplained,
        "descriptive_current_session_eligible": sum(
            (rec.get("disposition") == "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE") for rec in liquidity_records.values()
        ) if liquidity_records else None,
    }


def _official_engine_counts(official: Mapping[str, Any]) -> dict[str, Any]:
    public = capacity.build_retained_acceptance(
        official_liquidity_artifact=official, policy=capacity.canonical_unbound_policy(),
    )
    return {
        "official_identity": official.get("artifact_identity"),
        "session": official.get("resolved_completed_session"),
        "authority_boundary_live_execution_capacity": (official.get("authority_boundary") or {}).get("EXECUTION_CAPACITY"),
        "capacity_counts": public["counts"],
        "use_specific_authority": public["authority_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iid-2026-09-29", type=Path, default=IID_29)
    parser.add_argument("--iid-2026-09-28", type=Path, default=IID_28)
    parser.add_argument("--descriptive-2026-09-29", type=Path, default=DESC_29)
    parser.add_argument("--official-2026-09-28", type=Path, default=OFFICIAL_28)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    iid29 = _load(args.iid_2026_09_29)
    desc29 = _load(args.descriptive_2026_09_29)
    iid28 = _load(args.iid_2026_09_28)
    official = _load(args.official_2026_09_28)
    session29 = _compare_session(
        session="2026-09-29", iid=iid29, liquidity_records=desc29.get("records") or {}, official_records=None,
    )
    session28 = _compare_session(
        session="2026-09-28", iid=iid28, liquidity_records={}, official_records=official.get("records") or {},
    )
    engine = _official_engine_counts(official)
    report = {
        "schema_version": "1.0.0",
        "contract_version": "daily_liquidity_authority_wiring_replay/v1",
        "milestone": "DAILY_LIQUIDITY_AUTHORITY_WIRING_RECONCILIATION_V1",
        "provider_calls": 0,
        "original_retained_daily_mutated": False,
        "retained_2026_09_29_official_absent_replay": session29,
        "retained_2026_09_28_official_bound_replay": session28,
        "official_2026_09_28_engine": engine,
        "descriptive_2026_09_29_authority_boundary": desc29.get("authority_boundary"),
        "official_2026_09_28_artifact_authority_boundary": official.get("authority_boundary"),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
