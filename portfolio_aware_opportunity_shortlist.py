"""Private, deterministic owner shortlist composed from retained decision products only."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "portfolio_aware_opportunity_shortlist/v1"
_POSITIVE = frozenset({"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST", "EARLY_WATCH"})
_RECOVERY = frozenset({"QUALITY_DISLOCATION", "CYCLICAL_RECOVERY_FORMING", "TURNAROUND_EVIDENCE_FORMING"})
_RISK = frozenset({"VALUE_TRAP_RISK", "DISTRESS_SPECULATIVE"})


class OpportunityShortlistError(ValueError):
    pass


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value[key] for key in value if key not in {"artifact_identity", "artifact_sha256", "requested_at"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise OpportunityShortlistError(code)


def _bucket(*, portfolio: Mapping[str, Any], dislocation: Mapping[str, Any], integrated: Mapping[str, Any]) -> str:
    action = portfolio.get("portfolio_action_research")
    posture = integrated.get("research_action_posture")
    state = dislocation.get("primary_research_state")
    held = portfolio.get("position_state") in {"HELD", "HELD_ABOVE_POLICY_CAP"}
    if state in _RISK:
        return "RISK_REVIEW"
    if posture in _POSITIVE and action in {"NO_ADD", "OVER_LIMIT_REVIEW"}:
        return "SIGNAL_VALID_BUT_PORTFOLIO_BLOCKED"
    if held:
        return "CORE_POSITION_REVIEW"
    if action.startswith("PROBE_"):
        return "TACTICAL_PROBE_CANDIDATE"
    if action.startswith("ADD_"):
        return "TACTICAL_ADD_CANDIDATE" if posture != "EARLY_WATCH" else "TACTICAL_PROBE_CANDIDATE"
    if state in _RECOVERY:
        return "ASYMMETRIC_RECOVERY_WATCH"
    return "NO_ACTION"


def _sort_key(row: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    bucket = {"CORE_POSITION_REVIEW": 0, "TACTICAL_ADD_CANDIDATE": 1, "TACTICAL_PROBE_CANDIDATE": 2,
              "NEW_POSITION_CANDIDATE": 3, "ASYMMETRIC_RECOVERY_WATCH": 4,
              "SIGNAL_VALID_BUT_PORTFOLIO_BLOCKED": 5, "RISK_REVIEW": 6, "NO_ACTION": 7}[row["bucket"]]
    action = row["portfolio_action_research"]
    action_rank = 0 if action.startswith("ADD_") else 1 if action.startswith("PROBE_") else 2
    posture = {"INITIATE_ON_BREAKOUT": 0, "ACCUMULATE_ON_RETEST": 1, "EARLY_WATCH": 2}.get(row["research_action_posture"], 3)
    state = {"QUALITY_DISLOCATION": 0, "CYCLICAL_RECOVERY_FORMING": 1, "TURNAROUND_EVIDENCE_FORMING": 2,
             "VALUE_TRAP_RISK": 3, "DISTRESS_SPECULATIVE": 4}.get(row["asymmetric_state"], 5)
    return bucket, action_rank, posture, state, row["ticker"]


def build_artifact(*, session: str, integrated_decision: Mapping[str, Any], portfolio_aware_decision: Mapping[str, Any],
                   asymmetric_dislocation: Mapping[str, Any], calibration: Mapping[str, Any] | None = None,
                   requested_at: str | None = None) -> dict[str, Any]:
    _require(integrated_decision.get("contract_version") == "integrated_investment_decision_product/v1", "INTEGRATED_DECISION_CONTRACT_MISMATCH")
    _require(portfolio_aware_decision.get("contract_version") == "portfolio_aware_decision/v1", "PORTFOLIO_AWARE_DECISION_CONTRACT_MISMATCH")
    _require(asymmetric_dislocation.get("contract_version") == "asymmetric_dislocation_research/v1", "ASYMMETRIC_DISLOCATION_CONTRACT_MISMATCH")
    _require(integrated_decision.get("session") == session == portfolio_aware_decision.get("session") == asymmetric_dislocation.get("session"), "CROSS_SESSION_INPUT_REJECTED")
    identity = integrated_decision.get("artifact_identity")
    _require((portfolio_aware_decision.get("source_artifact_identities") or {}).get("integrated_investment_decision_product_identity") == identity, "PORTFOLIO_INTEGRATED_IDENTITY_MISMATCH")
    _require(asymmetric_dislocation.get("source_integrated_decision_identity") == identity, "ASYMMETRIC_INTEGRATED_IDENTITY_MISMATCH")
    if calibration is not None:
        _require(calibration.get("contract_version") == "empirical_setup_outcome_calibration/v1", "CALIBRATION_CONTRACT_MISMATCH")
    rows: list[dict[str, Any]] = []
    for ticker, decision in sorted((integrated_decision.get("records") or {}).items()):
        portfolio = (portfolio_aware_decision.get("records") or {}).get(ticker)
        dislocation = (asymmetric_dislocation.get("records") or {}).get(ticker)
        _require(isinstance(portfolio, Mapping) and isinstance(dislocation, Mapping), f"TICKER_INPUT_MISSING:{ticker}")
        _require((portfolio.get("evidence_lineage") or {}).get("security_decision_identity") == decision.get("decision_identity"), f"PORTFOLIO_DECISION_IDENTITY_MISMATCH:{ticker}")
        _require(dislocation.get("source_decision_identity") == decision.get("decision_identity"), f"ASYMMETRIC_DECISION_IDENTITY_MISMATCH:{ticker}")
        row = {
            "ticker": ticker, "research_action_posture": decision.get("research_action_posture"),
            "portfolio_action_research": portfolio.get("portfolio_action_research"),
            "position_state": portfolio.get("position_state"), "binding_constraint": portfolio.get("binding_constraint"),
            "portfolio_constraint_completeness": portfolio.get("portfolio_constraint_completeness"),
            "portfolio_risk_quantity_ceiling": portfolio.get("portfolio_risk_quantity_ceiling"),
            "execution_qualified_quantity": portfolio.get("execution_qualified_quantity"),
            "execution_qualified_quantity_status": portfolio.get("execution_qualified_quantity_status"),
            "margin_economics_status": (portfolio.get("margin_economics") or {}).get("status"),
            "asymmetric_state": dislocation.get("primary_research_state"),
            "asymmetric_reason_codes": list(dislocation.get("reason_codes") or []),
            "calibration_context": "NOT_PROVIDED" if calibration is None else "OPTIONAL_RESEARCH_CONTEXT",
        }
        row["bucket"] = _bucket(portfolio=portfolio, dislocation=dislocation, integrated=decision)
        rows.append(row)
    rows.sort(key=_sort_key)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(row["bucket"], []).append(row)
    reason_counts = Counter(code for row in rows for code in row["asymmetric_reason_codes"])
    result: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session,
        "requested_at": requested_at, "records": rows, "buckets": buckets,
        "coverage": {"shortlist_size": len(rows), "active_positions_represented": sum(1 for r in rows if r["position_state"] in {"HELD", "HELD_ABOVE_POLICY_CAP"}),
                     "bucket_counts": {k: len(v) for k, v in sorted(buckets.items())},
                     "reason_code_counts": dict(sorted(reason_counts.items())),
                     "execution_qualified_count": sum(1 for r in rows if r["execution_qualified_quantity"] is not None),
                     "calibration_context_counts": dict(Counter(r["calibration_context"] for r in rows))},
        "source_artifact_identities": {"integrated_investment_decision_product": identity,
                                        "portfolio_aware_decision": portfolio_aware_decision.get("artifact_identity"),
                                        "asymmetric_dislocation_research": asymmetric_dislocation.get("artifact_identity"),
                                        "empirical_setup_outcome_calibration": calibration.get("artifact_identity") if calibration else None},
        "authority_boundary": {"private_local_only": True, "selection_only_no_recomputation": True,
                               "no_new_buy_sell_vocabulary": True, "no_execution_authority": True,
                               "no_private_cost_basis_or_pnl_ranking": True}}
    result.update(_identity(result))
    return result


def public_console_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": "SHORTLIST_READY", "session": artifact.get("session"), "portfolio_aware_opportunity_shortlist_identity": artifact.get("artifact_identity"),
            "shortlist_size": (artifact.get("coverage") or {}).get("shortlist_size"), "bucket_counts": (artifact.get("coverage") or {}).get("bucket_counts"),
            "reason_code_counts": (artifact.get("coverage") or {}).get("reason_code_counts"), "active_positions_represented": (artifact.get("coverage") or {}).get("active_positions_represented"),
            "execution_qualified_count": (artifact.get("coverage") or {}).get("execution_qualified_count"),
            "calibration_context_counts": (artifact.get("coverage") or {}).get("calibration_context_counts"),
            "source_artifact_identities": artifact.get("source_artifact_identities")}


def write_private_artifact(artifact: Mapping[str, Any], *, portfolio_root: Path) -> Path:
    path = portfolio_root.expanduser().resolve() / "portfolio_aware_opportunity_shortlists" / str(artifact["session"]) / "portfolio_aware_opportunity_shortlist_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canon(artifact) + "\n", encoding="utf-8")
    return path
