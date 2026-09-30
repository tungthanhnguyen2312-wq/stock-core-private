"""Offline retained replay for DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_V1. No network."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_research_decision_input as decision_input  # noqa: E402
import daily_official_liquidity_rollforward as rollforward  # noqa: E402
import execution_capacity_research as capacity  # noqa: E402
import official_liquidity_market_wide as wide  # noqa: E402

PRIMARY_OPS = Path(r"C:\Projects\StockLookup\stock-core-private\operations-review")
OFFICIAL_28 = Path(
    r"C:\Projects\StockLookup\worktrees\stock-core-liquidity-market-wide-v1-20260929"
    r"\operations-review\official-exchange-liquidity-research-v1-20260928"
    r"\official_exchange_liquidity_research_artifact.json"
)
IID_28 = PRIMARY_OPS / "integrated-investment-decision-product-v1-20260928" / "integrated_investment_decision_product_artifact.json"
IID_29 = PRIMARY_OPS / "integrated-investment-decision-product-v1-20260929" / "integrated_investment_decision_product_artifact.json"
DESC_28 = PRIMARY_OPS / "market-wide-current-liquidity-research-v1-20260928" / "market_wide_current_liquidity_research_artifact.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"OBJECT_REQUIRED:{path}")
    return value


def _rebuild(record: Mapping[str, Any], *, session: str, liquidity_record=None, official_record=None) -> dict[str, Any]:
    payload = {key: value for key, value in record.items() if key != "current_research_decision_input"}
    return decision_input.build_ticker_decision_input(
        session=session, record=payload, liquidity_record=liquidity_record, official_liquidity_record=official_record,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-2026-09-28", type=Path, default=OFFICIAL_28)
    parser.add_argument("--iid-2026-09-28", type=Path, default=IID_28)
    parser.add_argument("--iid-2026-09-29", type=Path, default=IID_29)
    parser.add_argument("--descriptive-2026-09-28", type=Path, default=DESC_28)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    official = _load(args.official_2026_09_28)
    iid28 = _load(args.iid_2026_09_28)
    iid29 = _load(args.iid_2026_09_29)
    desc28 = _load(args.descriptive_2026_09_28)

    retained_root = args.scratch / "retained"
    dest = retained_root / "operations-review" / "official-exchange-liquidity-research-v1-20260928"
    dest.mkdir(parents=True, exist_ok=True)
    dest.joinpath("official_exchange_liquidity_research_artifact.json").write_bytes(args.official_2026_09_28.read_bytes())
    attempt = args.scratch / "attempt"
    order = ["materialize"]
    component = rollforward.materialize_same_session_official_liquidity(
        session="2026-09-28", artifact_root=attempt, retained_evidence_root=retained_root, allow_network=False,
    )
    bound, bound_status = rollforward.accept_same_session_official_artifact(
        json.loads((attempt / "operations-review" / "official-exchange-liquidity-research-v1-20260928" / "official_exchange_liquidity_research_artifact.json").read_text(encoding="utf-8")),
        "2026-09-28",
    )
    order.append("consume")
    _, other = rollforward.accept_same_session_official_artifact(official, "2026-09-29")
    missing = rollforward.materialize_same_session_official_liquidity(
        session="2026-09-29", artifact_root=args.scratch / "missing", allow_network=False,
    )
    frame = rollforward._frame_from_universe({"records": {
        ticker: {
            "stocklookup_candidate": True,
            "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY" if rec.get("route_exchange") else "STOCKLOOKUP_ONLY_UNRESOLVED",
            "exchange_or_market": {"HOSE": "HOSE", "HNX": "HNX_LISTED", "UPCOM": "UPCOM"}.get(rec.get("route_exchange") or "", "DELISTED"),
            "qualification": "Q",
        }
        for ticker, rec in official["records"].items()
    }})
    retained = {}
    for ticker, rec in official["records"].items():
        refs = rec.get("evidence_refs") or {}
        if refs.get("newest"):
            retained[ticker] = {"newest": refs["newest"], "parse_failures": [], "rows": {refs["newest"]: {}}}
    plan_29 = rollforward.plan_daily_rollforward(frame, retained, target_session="2026-09-29")

    records = iid28.get("records") or {}
    liquidity_records = desc28.get("records") or {}
    official_records = official.get("records") or {}
    posture = decision = liquidity_delta = 0
    rebuilt_inputs: dict[str, Any] = {}
    for ticker, record in records.items():
        nested = record.get("current_research_decision_input") if isinstance(record.get("current_research_decision_input"), Mapping) else None
        rebuilt = _rebuild(
            record, session="2026-09-28",
            liquidity_record=liquidity_records.get(ticker),
            official_record=official_records.get(ticker),
        )
        rebuilt_inputs[ticker] = {"current_research_decision_input": rebuilt}
        if rebuilt["synthesis"]["research_action_posture"] != record.get("research_action_posture"):
            posture += 1
        if rebuilt["provenance"]["decision_identity"] != record.get("decision_identity"):
            decision += 1
        if nested is not None and (rebuilt.get("dimensions") or {}).get("LIQUIDITY") != (nested.get("dimensions") or {}).get("LIQUIDITY"):
            liquidity_delta += 1
    coverage = decision_input.coverage(rebuilt_inputs)["qualified_liquidity"]
    public = capacity.build_retained_acceptance(
        official_liquidity_artifact=official, policy=capacity.canonical_unbound_policy(),
    )
    summary = wide.artifact_authority_summary(official["records"])
    report = {
        "milestone": rollforward.MILESTONE,
        "live_acceptance": rollforward.LIVE_ACCEPTANCE,
        "root_cause": rollforward.ROOT_CAUSE,
        "materialize_before_consume": order == ["materialize", "consume"],
        "bound_2026_09_28": {
            "status": component.get("status"),
            "reason": component.get("reason"),
            "http_requests_made": component.get("http_requests_made"),
            "artifact_identity": None if bound is None else bound.get("artifact_identity"),
            "consumer_status": bound_status,
            "bound_before_consumer": component.get("bound_before_consumer"),
        },
        "other_session_rejection": {"status": other},
        "missing_component": {
            "status": missing.get("status"),
            "reason": missing.get("reason"),
            "daily_continues": True,
        },
        "plan_2026_09_29": {
            "status": plan_29.get("status"),
            "planned_requests": plan_29.get("planned_requests"),
            "planned_by_exchange": plan_29.get("planned_by_exchange"),
            "hnx_upcom_planned_requests": plan_29.get("hnx_upcom_planned_requests"),
            "reused_retained_by_exchange": plan_29.get("reused_retained_by_exchange"),
            "hard_request_budget": plan_29.get("hard_request_budget"),
            "retry_allowance": plan_29.get("retry_allowance"),
        },
        "retained_2026_09_28": {
            "iid_identity": iid28.get("artifact_identity"),
            "official_identity": official.get("artifact_identity"),
            "governed_universe_count": len(records),
            "current_session_eligible": summary["CURRENT_SESSION_LIQUIDITY_RESEARCH"]["eligible_count"],
            "adtv_eligible": summary["ADTV_RESEARCH"]["eligible_count"],
            "adv_partial": summary["ADV_VOLUME_RESEARCH"]["eligible_count"],
            "qualified_liquidity": coverage,
            "posture_delta_count": posture,
            "decision_identity_delta_count": decision,
            "liquidity_dimension_delta_vs_nested_count": liquidity_delta,
            "execution_capacity_counts": public["counts"],
            "use_specific_authority": public["authority_boundary"],
        },
        "iid_2026_09_29_identity": iid29.get("artifact_identity"),
        "provider_calls": 0,
        "raw_exchange_response_bodies_published": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": component.get("status"), "plan_status": plan_29.get("status")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
