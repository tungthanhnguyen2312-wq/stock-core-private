"""Deterministic outcomes for genuinely retained prospective T0 research cases.

This module deliberately evaluates only immutable durable-case envelopes.  A
decision-workspace export, a historical snapshot, or a candidate record is not
a case and is never converted into one here.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from durable_prospective_research_case_store import DurableProspectiveResearchCaseStore


CONTRACT_VERSION = "prospective_decision_outcome/v1"
METHOD_VERSION = "prospective_decision_outcome_measurement/v1"
HORIZONS = {"T5": 5, "T20": 20, "T60": 60}
PENDING = "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"
UNAVAILABLE_HIGH_LOW = "UNAVAILABLE_HIGH_LOW_BASIS"


class ProspectiveOutcomeError(ValueError):
    """Raised for an attempted retroactive or non-governed evaluation."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _identity(payload: dict[str, Any], prefix: str, field: str = "content_identity") -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _case_identity_valid(case: Mapping[str, Any]) -> bool:
    body = dict(case)
    case_id = body.pop("case_id", None)
    content = body.pop("case_content_identity", None)
    expected = "prospective_research_case:" + _hash(body)
    return case_id == expected and content == expected


def _envelope_case(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    if envelope.get("record_type") != "IMMUTABLE_T0_CASE":
        raise ProspectiveOutcomeError("GENUINE_IMMUTABLE_T0_CASE_REQUIRED")
    case = envelope.get("case")
    if not isinstance(case, Mapping) or not _case_identity_valid(case):
        raise ProspectiveOutcomeError("IMMUTABLE_T0_CASE_IDENTITY_INVALID")
    draft = envelope.get("ai_draft")
    if isinstance(draft, Mapping) and (draft.get("fixture") or str(draft.get("draft_identity", "")).startswith("TEST_FIXTURE:")):
        raise ProspectiveOutcomeError("FIXTURE_CASE_NOT_ELIGIBLE_FOR_REAL_OUTCOME_MEASUREMENT")
    return case


def load_genuine_case_envelopes(store_root: str | Path | None) -> list[dict[str, Any]]:
    """Read real immutable cases; a missing explicit store means an empty cohort."""
    if store_root is None or not Path(store_root).is_dir():
        return []
    store = DurableProspectiveResearchCaseStore(store_root)
    rows: list[dict[str, Any]] = []
    for case_id in store.list_case_ids():
        envelope = store.load_case_envelope(case_id)
        try:
            _envelope_case(envelope)
        except ProspectiveOutcomeError as exc:
            if str(exc) == "FIXTURE_CASE_NOT_ELIGIBLE_FOR_REAL_OUTCOME_MEASUREMENT":
                continue
            raise
        rows.append(envelope)
    return rows


def _t0(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("outcome_measurement_t0")
    return value if isinstance(value, Mapping) else {}


def _t0_value(case: Mapping[str, Any], key: str, fallback: Any = None) -> Any:
    return _t0(case).get(key, fallback)


def _completed_sessions(sessions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[str] = set()
    accepted: list[Mapping[str, Any]] = []
    for row in sessions:
        session = row.get("session")
        gate = row.get("completed_session_gate") or {}
        if not isinstance(session, str) or not isinstance(gate, Mapping):
            raise ProspectiveOutcomeError("COMPLETED_SESSION_CONTRACT_INVALID")
        if gate.get("completion_gate_status") != "READY" or gate.get("resolved_session") not in {None, session}:
            continue
        if session in seen:
            raise ProspectiveOutcomeError("DUPLICATE_COMPLETED_SESSION")
        seen.add(session)
        accepted.append(row)
    return sorted(accepted, key=lambda item: str(item["session"]))


def _price(row: Mapping[str, Any], ticker: str) -> Mapping[str, Any] | None:
    prices = row.get("prices")
    value = prices.get(ticker) if isinstance(prices, Mapping) else None
    return value if isinstance(value, Mapping) else None


def _compatible(t0_price: Mapping[str, Any], later_price: Mapping[str, Any] | None) -> bool:
    return bool(later_price and t0_price.get("price_basis_identity") and
                t0_price.get("price_basis_identity") == later_price.get("price_basis_identity") and
                isinstance(t0_price.get("close"), (int, float)) and t0_price["close"] != 0 and
                isinstance(later_price.get("close"), (int, float)))


def _return(t0_price: Mapping[str, Any], later_price: Mapping[str, Any]) -> float:
    return later_price["close"] / t0_price["close"] - 1


def _condition(boundary: Mapping[str, Any], session: Mapping[str, Any], ticker: str) -> bool | None:
    condition = boundary.get("condition")
    if not isinstance(condition, Mapping):
        return None
    field, operator, value = condition.get("field"), condition.get("operator"), condition.get("value")
    price = _price(session, ticker) or {}
    observations = {"close": price.get("close"), **(session.get("observations", {}).get(ticker, {}) if isinstance(session.get("observations"), Mapping) else {})}
    actual = observations.get(field)
    if not isinstance(actual, (int, float)) or not isinstance(value, (int, float)):
        return None
    if operator == ">=": return actual >= value
    if operator == ">": return actual > value
    if operator == "<=": return actual <= value
    if operator == "<": return actual < value
    if operator == "==": return actual == value
    return None


def _event(boundary: Any, sessions: Sequence[Mapping[str, Any]], ticker: str, *, completed: bool) -> dict[str, Any]:
    if not isinstance(boundary, Mapping):
        return {"status": "BOUNDARY_NOT_RETAINED_AT_T0", "session": None, "sessions_to_event": None,
                "retained_t0_boundary_identity": None, "actual_observed_condition": None}
    identity = boundary.get("boundary_identity") or boundary.get("identity")
    kind = boundary.get("kind", "technical")
    evaluated = False
    for index, row in enumerate(sessions, start=1):
        result = _condition(boundary, row, ticker)
        if result is None:
            continue
        evaluated = True
        if result:
            return {"status": "CONFIRMED" if boundary.get("role") == "confirmation" else "INVALIDATED", "session": row["session"],
                    "sessions_to_event": index, "retained_t0_boundary_identity": identity, "actual_observed_condition": True,
                    "boundary_kind": kind}
    if kind == "fundamental" and not evaluated:
        status = "PENDING_NEXT_COMPATIBLE_FINANCIAL_OBSERVATION"
    elif not evaluated:
        status = "BOUNDARY_NOT_EVALUABLE"
    elif completed and boundary.get("role") == "confirmation":
        status = "CASE_COMPLETED_WITHOUT_CONFIRMATION"
    else:
        status = "NOT_CONFIRMED_YET" if boundary.get("role") == "confirmation" else "NOT_INVALIDATED_YET"
    return {"status": status, "session": None, "sessions_to_event": None, "retained_t0_boundary_identity": identity,
            "actual_observed_condition": False if evaluated else None, "boundary_kind": kind}


def _ordering(confirmation: Mapping[str, Any], invalidation: Mapping[str, Any]) -> str:
    c, i = confirmation.get("sessions_to_event"), invalidation.get("sessions_to_event")
    if isinstance(c, int) and isinstance(i, int):
        return "CONFIRMED_BEFORE_INVALIDATED" if c < i else "INVALIDATED_BEFORE_CONFIRMED"
    if isinstance(c, int): return "CONFIRMED_ONLY"
    if isinstance(i, int): return "INVALIDATED_ONLY"
    if confirmation["status"] in {"BOUNDARY_NOT_RETAINED_AT_T0", "BOUNDARY_NOT_EVALUABLE"} or invalidation["status"] in {"BOUNDARY_NOT_RETAINED_AT_T0", "BOUNDARY_NOT_EVALUABLE"}:
        return "NOT_EVALUABLE"
    return "NEITHER_YET"


def _horizon(name: str, count: int, t0_price: Mapping[str, Any] | None, later: Sequence[Mapping[str, Any]], ticker: str) -> dict[str, Any]:
    base = {"horizon": name, "required_completed_future_sessions": count, "status": None, "future_session": None,
            "return": None, "t0_close_basis": None if not t0_price else dict(t0_price), "future_close_basis": None,
            "source_identities": [], "method_version": METHOD_VERSION}
    if not t0_price:
        base["status"] = FIELD_NOT_RETAINED
        return base
    if len(later) < count:
        base["status"] = PENDING
        return base
    target = later[count - 1]
    future = _price(target, ticker)
    base["future_session"] = target["session"]
    if not future:
        base["status"] = "FUTURE_CLOSE_NOT_RETAINED"
        return base
    base["future_close_basis"] = dict(future)
    if not _compatible(t0_price, future):
        base["status"] = "PRICE_BASIS_INCOMPATIBLE"
        return base
    base["status"] = "MATURE"
    base["return"] = _return(t0_price, future)
    base["source_identities"] = [t0_price.get("source_identity"), future.get("source_identity"), target.get("session_identity")]
    return base


def _path(horizon: Mapping[str, Any], t0_price: Mapping[str, Any] | None, later: Sequence[Mapping[str, Any]], ticker: str) -> dict[str, Any]:
    if horizon["status"] != "MATURE" or not t0_price:
        return {"status": horizon["status"], "MAX_FAVORABLE_CLOSE_RETURN": None, "MAX_ADVERSE_CLOSE_RETURN": None,
                "mfe": UNAVAILABLE_HIGH_LOW, "mae": UNAVAILABLE_HIGH_LOW, "semantics": "RESEARCH_PROXY_ONLY"}
    returns = [_return(t0_price, _price(row, ticker)) for row in later[:horizon["required_completed_future_sessions"]]
               if _compatible(t0_price, _price(row, ticker))]
    if len(returns) != horizon["required_completed_future_sessions"]:
        return {"status": "PRICE_BASIS_INCOMPATIBLE", "MAX_FAVORABLE_CLOSE_RETURN": None, "MAX_ADVERSE_CLOSE_RETURN": None,
                "mfe": UNAVAILABLE_HIGH_LOW, "mae": UNAVAILABLE_HIGH_LOW, "semantics": "RESEARCH_PROXY_ONLY"}
    return {"status": "MATURE", "MAX_FAVORABLE_CLOSE_RETURN": max(returns), "MAX_ADVERSE_CLOSE_RETURN": min(returns),
            "mfe": UNAVAILABLE_HIGH_LOW, "mae": UNAVAILABLE_HIGH_LOW, "close_path_mfe_proxy": max(returns), "close_path_mae_proxy": min(returns),
            "semantics": "RESEARCH_PROXY_ONLY"}


def _benchmark(horizon: Mapping[str, Any], t0: Mapping[str, Any], later: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    benchmark = t0.get("benchmark")
    if not isinstance(benchmark, Mapping): return {"status": "BENCHMARK_RELATIVE_UNAVAILABLE", "return": None, "benchmark_identity": None}
    if horizon["status"] != "MATURE": return {"status": horizon["status"], "return": None, "benchmark_identity": benchmark.get("identity")}
    initial = benchmark.get("t0_close")
    row = later[horizon["required_completed_future_sessions"] - 1]
    future = (row.get("benchmarks") or {}).get(benchmark.get("identity")) if isinstance(row.get("benchmarks"), Mapping) else None
    if not isinstance(initial, Mapping) or not isinstance(future, Mapping) or not _compatible(initial, future):
        return {"status": "BENCHMARK_RELATIVE_UNAVAILABLE", "return": None, "benchmark_identity": benchmark.get("identity")}
    return {"status": "MATURE", "return": horizon["return"] - _return(initial, future), "benchmark_identity": benchmark.get("identity")}


def evaluate_case(envelope: Mapping[str, Any], completed_sessions: Sequence[Mapping[str, Any]], *, evaluation_as_of_session: str | None = None) -> dict[str, Any]:
    case = _envelope_case(envelope)
    t0 = _t0(case)
    t0_session = t0.get("completed_session")
    if not isinstance(t0_session, str):
        raise ProspectiveOutcomeError("T0_COMPLETED_SESSION_NOT_RETAINED")
    all_sessions = _completed_sessions(completed_sessions)
    later = [row for row in all_sessions if row["session"] > t0_session and (evaluation_as_of_session is None or row["session"] <= evaluation_as_of_session)]
    t0_price = t0.get("close") if isinstance(t0.get("close"), Mapping) else None
    horizons = {name: _horizon(name, count, t0_price, later, case["ticker"]) for name, count in HORIZONS.items()}
    completed = horizons["T60"]["status"] == "MATURE"
    confirmation = _event(t0.get("confirmation_boundary"), later, case["ticker"], completed=completed)
    invalidation = _event(t0.get("invalidation_boundary"), later, case["ticker"], completed=completed)
    outcome = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "case_id": case["case_id"], "immutable_t0_identity": case["case_content_identity"],
               "ticker": case["ticker"], "t0_session": t0_session, "evaluation_as_of_session": evaluation_as_of_session or (all_sessions[-1]["session"] if all_sessions else None),
               "known_at": case.get("known_at"), "research_stance_at_t0": _t0_value(case, "research_stance", FIELD_NOT_RETAINED),
               "entry_state_at_t0": _t0_value(case, "entry_state", FIELD_NOT_RETAINED), "entry_action_at_t0": _t0_value(case, "entry_action", FIELD_NOT_RETAINED),
               "setup_tags_at_t0": _t0_value(case, "setup_tags", FIELD_NOT_RETAINED), "fundamental_context_at_t0": _t0_value(case, "fundamental_state", FIELD_NOT_RETAINED),
               "valuation_context_at_t0": _t0_value(case, "valuation_state", FIELD_NOT_RETAINED), "confirmation": confirmation, "invalidation": invalidation,
               "event_ordering": _ordering(confirmation, invalidation), "horizons": horizons,
               "close_path": {name: _path(item, t0_price, later, case["ticker"]) for name, item in horizons.items()},
               "benchmark_relative": {name: _benchmark(item, t0, later) for name, item in horizons.items()},
               "data_limitations": list(t0.get("data_limitations") or []) + ([FIELD_NOT_RETAINED] if not t0_price else []),
               "source_identities": {"t0_case": case["case_content_identity"], "t0_price": t0_price.get("source_identity") if t0_price else None},
               "authority_boundary": {"prospective_retained_cases_only": True, "historical_backtest": "NOT_CREATED", "raw_as_traded_or_pit": "NOT_CLAIMED", "threshold_retuning": "NOT_PERMITTED", "close_path_is_not_intraday_mfe_mae": True}}
    return _identity(outcome, "prospective_decision_outcome:")


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def cohort_observation_summary(outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    axes = {"research_stance": "research_stance_at_t0", "entry_state": "entry_state_at_t0", "setup_tag": "setup_tags_at_t0", "valuation_state": "valuation_context_at_t0", "fundamental_state": "fundamental_context_at_t0"}
    for row in outcomes:
        for label, field in axes.items():
            values = row.get(field)
            values = values if isinstance(values, list) else [values]
            for value in values: groups[(label, str(value))].append(row)
    rows = []
    for (axis, value), members in sorted(groups.items()):
        matured = {h: [item["horizons"][h]["return"] for item in members if item["horizons"][h]["status"] == "MATURE"] for h in HORIZONS}
        positives = sum(value > 0 for value in matured["T5"])
        rows.append({"axis": axis, "value": value, "case_count": len(members), "mature_case_count_by_horizon": {h: len(v) for h, v in matured.items()},
                     "median_forward_return": {h: _median(v) for h, v in matured.items()}, "positive_negative_count_T5": {"positive": positives, "negative": sum(value < 0 for value in matured["T5"])},
                     "OBSERVED_POSITIVE_RATE": {"value": positives / len(matured["T5"]) if matured["T5"] else None, "N": len(matured["T5"])},
                     "OBSERVED_CONFIRMATION_RATE": {"value": sum(item["confirmation"]["status"] == "CONFIRMED" for item in members) / len(members) if members else None, "N": len(members)},
                     "invalidation_count": sum(item["invalidation"]["status"] == "INVALIDATED" for item in members), "INSUFFICIENT_SAMPLE_FOR_CALIBRATION": True})
    return {"groups": rows, "authority_boundary": {"descriptive_observations_only": True, "probability_of_success": "NOT_EMITTED", "calibration": "INSUFFICIENT_SAMPLE_FOR_CALIBRATION"}}


def build_outcome_artifact(envelopes: Sequence[Mapping[str, Any]], completed_sessions: Sequence[Mapping[str, Any]], *, evaluation_as_of_session: str | None = None) -> dict[str, Any]:
    before = {str(_envelope_case(item)["case_id"]): str(_envelope_case(item)["case_content_identity"]) for item in envelopes}
    outcomes = [evaluate_case(item, completed_sessions, evaluation_as_of_session=evaluation_as_of_session) for item in envelopes]
    after = {str(_envelope_case(item)["case_id"]): str(_envelope_case(item)["case_content_identity"]) for item in envelopes}
    if before != after: raise ProspectiveOutcomeError("IMMUTABLE_T0_IDENTITY_CHANGED")
    ordered = sorted(outcomes, key=lambda item: item["case_id"])
    coverage = {h: dict(Counter(item["horizons"][h]["status"] for item in ordered)) for h in HORIZONS}
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "method_version": METHOD_VERSION,
                "evaluation_as_of_session": evaluation_as_of_session or (_completed_sessions(completed_sessions)[-1]["session"] if _completed_sessions(completed_sessions) else None),
                "case_count": len(ordered), "outcomes": ordered, "coverage": {"horizons": coverage, "confirmation": dict(Counter(item["confirmation"]["status"] for item in ordered)), "invalidation": dict(Counter(item["invalidation"]["status"] for item in ordered)), "event_ordering": dict(Counter(item["event_ordering"] for item in ordered))},
                "cohort_observation_summary": cohort_observation_summary(ordered), "t0_immutability_verified": True,
                "authority_boundary": {"genuine_retained_t0_cases_only": True, "no_retroactive_case_fabrication": True, "no_strategy_retuning": True, "no_probability_of_success": True}}
    return _identity(artifact, "prospective_decision_outcome_artifact:", "artifact_identity")


def prospective_outcome_context(artifact: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    row = next((item for item in artifact.get("outcomes", []) if item.get("case_id") == case_id), None)
    if not isinstance(row, Mapping): raise ProspectiveOutcomeError("OUTCOME_CASE_NOT_FOUND")
    return _identity({"contract_version": "prospective_outcome_context/v1", "case_id": case_id, "outcome_identity": row.get("content_identity"),
                      "case_status": {h: row["horizons"][h]["status"] for h in HORIZONS}, "t0": {key: row.get(key) for key in ("research_stance_at_t0", "entry_state_at_t0", "entry_action_at_t0", "setup_tags_at_t0")},
                      "confirmation_status": row["confirmation"]["status"], "invalidation_status": row["invalidation"]["status"], "event_ordering": row["event_ordering"],
                      "matured_horizon_results": {h: row["horizons"][h] for h in HORIZONS if row["horizons"][h]["status"] == "MATURE"},
                      "pending_horizons": [h for h in HORIZONS if row["horizons"][h]["status"] != "MATURE"], "close_path_research_proxy": row["close_path"], "benchmark_relative": row["benchmark_relative"],
                      "authority_boundary": "RESEARCH_OBSERVATION_ONLY"}, "prospective_outcome_context:")
