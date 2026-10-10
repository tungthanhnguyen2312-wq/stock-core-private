"""Offline retained-session acceptance for LIQUIDITY_EXECUTION_CAPACITY_AND_SIZING_V1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stocklookup_core.portfolio.execution_capacity_research as capacity
import stocklookup_core.decision.current_research_decision_input as decision_input


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"OBJECT_REQUIRED:{path}")
    return value


def build_acceptance(*, official: Mapping[str, Any], integrated: Mapping[str, Any]) -> dict[str, Any]:
    policy = capacity.canonical_unbound_policy()
    public = capacity.build_retained_acceptance(official_liquidity_artifact=official, policy=policy)
    official_records = official.get("records") or {}
    integrated_records = integrated.get("records") or {}
    if len(integrated_records) != len(official_records):
        raise ValueError(f"RETAINED_DENOMINATOR_MISMATCH:{len(integrated_records)}:{len(official_records)}")
    posture_changed = decision_identity_changed = evidence_class_changed = non_liquidity_changed = 0
    existing_input_count = capacity_mismatch = 0
    additive_present = 0
    session = official.get("resolved_completed_session")
    for ticker, record in integrated_records.items():
        source = official_records.get(ticker)
        if source is None:
            raise ValueError(f"OFFICIAL_RECORD_MISSING:{ticker}")
        existing_input_count += isinstance(record.get("current_research_decision_input"), Mapping)
        baseline = decision_input.build_ticker_decision_input(session=session, record=record)
        with_official = decision_input.build_ticker_decision_input(
            session=session, record=record, official_liquidity_record=source,
        )
        before_dimensions = baseline["dimensions"]
        after_dimensions = with_official["dimensions"]
        actual = ((after_dimensions["LIQUIDITY"].get("qualified_research") or {})
                  .get("execution_capacity_research") or {})
        expected = public["records"][ticker]
        comparable_fields = ("state", "capacity_notional_vnd", "capacity_shares_lot_rounded",
                             "policy_identity", "reason_codes")
        capacity_mismatch += any(actual.get(field) != expected.get(field) for field in comparable_fields)
        posture_changed += with_official["synthesis"]["research_action_posture"] != baseline["synthesis"]["research_action_posture"]
        decision_identity_changed += with_official["provenance"]["decision_identity"] != baseline["provenance"]["decision_identity"]
        evidence_class_changed += with_official["evidence_class"] != baseline["evidence_class"]
        non_liquidity_changed += any(after_dimensions.get(name) != before_dimensions.get(name) for name in before_dimensions if name != "LIQUIDITY")
        additive_present += bool(actual)
    body = {
        "schema_version": "1.0.0",
        "contract_version": "liquidity_execution_capacity_retained_acceptance/v1",
        "session": official.get("resolved_completed_session"),
        "canonical_policy": {key: policy.get(key) for key in ("policy_version", "policy_identity", "status", "unbound_fields")},
        "capacity_counts": public["counts"],
        "current_research_additive_acceptance": {
            "governed_records": len(integrated_records),
            "retained_records_with_prior_current_research_input": existing_input_count,
            "rebuilt_current_research_capacity_mismatch": capacity_mismatch,
            "execution_capacity_research_present": additive_present,
            "research_action_posture_changed": posture_changed,
            "decision_identity_changed": decision_identity_changed,
            "evidence_class_changed": evidence_class_changed,
            "non_liquidity_dimensions_changed": non_liquidity_changed,
        },
        "source_identities": {
            "official_exchange_liquidity_research": official.get("artifact_identity"),
            "integrated_investment_decision_product": integrated.get("artifact_identity"),
        },
        "provider_calls": 0,
        "authority_boundary": capacity.use_specific_authority(capacity_state=capacity.PARTIAL, private_size_state=capacity.PARTIAL),
    }
    return {**body, **capacity._identity("liquidity_execution_capacity_retained_acceptance", body)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--integrated", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-determinism", action="store_true")
    args = parser.parse_args()
    official, integrated = _load(args.official), _load(args.integrated)
    result = build_acceptance(official=official, integrated=integrated)
    if args.verify_determinism and build_acceptance(official=official, integrated=integrated)["artifact_identity"] != result["artifact_identity"]:
        raise SystemExit("NON_DETERMINISTIC_ACCEPTANCE")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("session", "canonical_policy", "capacity_counts", "current_research_additive_acceptance", "provider_calls", "artifact_identity")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
