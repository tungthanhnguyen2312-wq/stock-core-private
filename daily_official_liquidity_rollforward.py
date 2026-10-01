"""Same-session official liquidity materialization for ordinary Daily.

PR #24 wired per-record official fitness. Daily still only loaded an already-written
``official_exchange_liquidity_research/v1`` artifact. This module is the missing
orchestration: bind a valid same-session artifact, plan a HOSE-only incremental
refresh, stop at the existing 400-request ceiling, and never fail Core Daily.

Network stays in the established plan/probe/build runner. Analytical assembly only
consumes a same-session self-verifying artifact. Daily itself never becomes a
second crawler. HNX/UPCoM bulk stays ``PUBLIC_ACQUISITION_NOT_AUTHORIZED``.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import daily_session_level2_package as level2
import liquidity_authority_contract as contract
import official_exchange_trading_statistics as official
import official_liquidity_market_wide as wide
from atomic_io import atomic_write_json

MILESTONE = "DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_V1"
STATUS_CONTRACT = "daily_official_liquidity_rollforward/v1"
HARD_REQUEST_BUDGET = 400
OFFICIAL_CONTRACT = wide.CONTRACT_VERSION
LIVE_ACCEPTANCE = "LIVE_ACCEPTANCE_PENDING_2026_09_30_COMPLETED_SESSION"
ROOT_CAUSE = "OPERATOR_ONLY_OFFICIAL_ACQUISITION_NEVER_SCHEDULED_IN_DAILY"
BUDGET_CEILING = "DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_PARTIAL_REQUEST_BUDGET_CEILING"
WITHIN_BUDGET = "WITHIN_BUDGET"

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE_SOURCE = "UNAVAILABLE_SOURCE"
UNAVAILABLE_RIGHTS = "UNAVAILABLE_RIGHTS"
UNAVAILABLE_REQUEST_BUDGET = "UNAVAILABLE_REQUEST_BUDGET"
UNAVAILABLE_SESSION = "UNAVAILABLE_SESSION"
MALFORMED_ARTIFACT = "MALFORMED_ARTIFACT"

# Required in every artifact, including the retained pre-extension 2026-09-28 one.
LIVE_BLOCKED_KEYS = ("EXECUTION_CAPACITY", "POSITION_SIZING", "PIT_BACKTEST")
# Extended boundary: absent tolerated (older retained artifacts), promoted rejected.
EXTENDED_BLOCKED_KEYS = (
    "LIVE_POSITION_SIZING", "PORTFOLIO_CAPITAL_ALLOCATION", "HISTORICAL_PIT_SIZE_REPLAY", "EXECUTION_REPLAY",
)
NOT_PROMOTED_KEYS = ("RAW_AS_TRADED",)
BUDGET_EXCEEDED_ERROR = "GOVERNED_REQUEST_BUDGET_EXCEEDED"
STATUS_FILENAME = "daily_official_liquidity_component_status.json"
IDENTITY_EXCLUDED = frozenset({"retrieved_at", "status_path", "artifact_path", "artifact_sha256", "artifact_identity"})


class OfficialLiquidityRollforwardError(ValueError):
    """Malformed rollforward input; never silently coerced."""


def official_artifact_path(root: Path, session: str) -> Path:
    return level2.session_artifact_paths(root, session)["official_liquidity"]


def status_path(root_or_official: Path, session: str | None = None) -> Path:
    """Component status beside the official artifact.

    ``status_path(root, session)`` is the Daily path. ``status_path(official_out)``
    accepts the artifact file or its parent directory.
    """
    path = Path(root_or_official)
    if session is None:
        if path.suffix == ".json" and path.name != STATUS_FILENAME:
            return path.parent / STATUS_FILENAME
        return path / STATUS_FILENAME
    return official_artifact_path(path, session).parent / STATUS_FILENAME


def read_json_object(path: Path) -> tuple[Any, str | None]:
    """Return ``(object, None)`` or ``(None, status)`` for absent/malformed JSON."""
    path = Path(path)
    if not path.is_file():
        return None, UNAVAILABLE_SOURCE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None, MALFORMED_ARTIFACT
    if not isinstance(payload, Mapping):
        return None, MALFORMED_ARTIFACT
    return payload, None


def load_official_payload(path: Path) -> tuple[Any, str | None]:
    return read_json_object(path)


def evaluate_candidate_artifact(payload: Any, *, session: str) -> dict[str, Any]:
    """Same-session self-verifying official artifact, or a named component status."""
    if payload is None:
        return {"status": UNAVAILABLE_SOURCE, "reason_code": "OFFICIAL_ARTIFACT_ABSENT", "artifact": None}
    if not isinstance(payload, Mapping):
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    if payload.get("contract_version") != OFFICIAL_CONTRACT:
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    if payload.get("resolved_completed_session") != session:
        return {
            "status": UNAVAILABLE_SESSION,
            "reason_code": "OTHER_SESSION_OFFICIAL_ARTIFACT_NOT_SUBSTITUTED",
            "artifact": None,
        }
    try:
        identity = contract.content_identity(payload, kind="official_exchange_liquidity_research")
    except (TypeError, ValueError, KeyError):
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    if identity.get("artifact_identity") != payload.get("artifact_identity"):
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    boundary = payload.get("authority_boundary") or {}
    if not isinstance(boundary, Mapping) or (
        any(boundary.get(key) != "BLOCKED" for key in LIVE_BLOCKED_KEYS)
        or any(boundary.get(key) != "NOT_PROMOTED" for key in NOT_PROMOTED_KEYS)
        or any(key in boundary and boundary[key] != "BLOCKED" for key in EXTENDED_BLOCKED_KEYS)
    ):
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    if not isinstance(payload.get("records"), Mapping):
        return {"status": MALFORMED_ARTIFACT, "reason_code": "OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED", "artifact": None}
    return {"status": AVAILABLE, "reason_code": "SAME_SESSION_ARTIFACT_BOUND", "artifact": payload}


def accept_same_session_official_artifact(payload: Any, session: str) -> tuple[dict[str, Any] | None, str]:
    verdict = evaluate_candidate_artifact(payload, session=session)
    artifact = verdict["artifact"]
    if artifact is None:
        return None, verdict["status"]
    return artifact, AVAILABLE


def component_identity(status_body: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in status_body.items() if key not in IDENTITY_EXCLUDED}
    return contract.content_identity(payload, kind="daily_official_liquidity_rollforward")


def build_component_status(
    *,
    session: str,
    status: str,
    reason_code: str | None = None,
    reason: str | None = None,
    artifact_identity: str | None = None,
    plan_identity: str | None = None,
    planned_requests: int = 0,
    planned_hose_requests: int = 0,
    planned_hnx_upcom_requests: int = 0,
    http_requests_made: int = 0,
    reused_retained_count: int = 0,
    execute_probe: bool = False,
    allow_network: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": STATUS_CONTRACT,
        "milestone": MILESTONE,
        "target_session": session,
        "status": status,
        "reason_code": reason_code or reason,
        "allow_network": allow_network,
        "execute_probe": execute_probe,
        "hard_request_budget": HARD_REQUEST_BUDGET,
        "planned_requests": planned_requests,
        "planned_hose_requests": planned_hose_requests,
        "planned_hnx_upcom_requests": planned_hnx_upcom_requests,
        "http_requests_made": http_requests_made,
        "retries_used": 0,
        "reused_retained_count": reused_retained_count,
        "bound_artifact_identity": artifact_identity,
        "plan_identity": plan_identity,
        "live_acceptance": LIVE_ACCEPTANCE,
        "root_cause_of_2026_09_29_absence": ROOT_CAUSE,
        "acquisition_rights": {
            exchange: {"decision": row["decision"]} for exchange, row in wide.ACQUISITION_RIGHTS.items()
        },
    }
    body["reason"] = body["reason_code"]
    body["artifact_identity"] = artifact_identity
    if extra:
        body.update(dict(extra))
    ident = component_identity(body)
    body["component_identity"] = ident["artifact_identity"]
    body["component_sha256"] = ident["artifact_sha256"]
    return body


def _frame_from_universe(universe: Mapping[str, Any], dnse_resolved: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    records = universe.get("records")
    if not isinstance(records, Mapping):
        raise OfficialLiquidityRollforwardError("OFFICIAL_UNIVERSE_RECORDS_MISSING")
    return wide.frame_universe(records, dnse_resolved or {})


def frame_from_official_records(records: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    frame: dict[str, dict[str, Any]] = {}
    for ticker, record in records.items():
        if not isinstance(record, Mapping):
            continue
        universe = record.get("universe") if isinstance(record.get("universe"), Mapping) else {}
        route = record.get("route_exchange")
        frame[str(ticker)] = {
            "ticker": str(ticker),
            "official_exchange": universe.get("official_exchange") or route,
            "official_presence": universe.get("official_presence", route is not None),
            "official_current_universe_status": universe.get("official_current_universe_status"),
            "official_qualification": universe.get("official_qualification"),
            "dnse_exchange": universe.get("dnse_exchange") or route,
            "dnse_state": "RESOLVED",
            "dnse_prior_market_ids": [],
            "exchange_resolution": universe.get("exchange_resolution") or "AGREE",
            "route_exchange": route,
            "eligibility_reason": universe.get("eligibility_reason"),
        }
    return frame


def retained_slots_from_artifact(artifact: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records = artifact.get("records") if isinstance(artifact.get("records"), Mapping) else {}
    slots: dict[str, dict[str, Any]] = {}
    for ticker, record in records.items():
        if not isinstance(record, Mapping):
            continue
        refs = record.get("evidence_refs") if isinstance(record.get("evidence_refs"), Mapping) else {}
        slots[str(ticker)] = {
            "ticker": str(ticker),
            "exchange": record.get("route_exchange"),
            "newest": refs.get("newest"),
            "oldest": refs.get("oldest"),
            "parse_failures": [],
            "rows": {},
            "responses": list(refs.get("responses") or []),
        }
    return slots


def hose_planned_request_count(plan: Mapping[str, Any]) -> int:
    planned = plan.get("planned_by_exchange") if isinstance(plan.get("planned_by_exchange"), Mapping) else {}
    if official.HOSE in planned:
        return int(planned.get(official.HOSE) or 0)
    return sum(1 for request in (plan.get("requests") or []) if request.get("exchange") == official.HOSE)


def hnx_upcom_planned_request_count(plan: Mapping[str, Any]) -> int:
    planned = plan.get("planned_by_exchange") if isinstance(plan.get("planned_by_exchange"), Mapping) else {}
    counted = int(planned.get(official.HNX) or 0) + int(planned.get(official.UPCOM) or 0)
    if counted:
        return counted
    return sum(
        1
        for request in (plan.get("requests") or [])
        if request.get("exchange") in (official.HNX, official.UPCOM)
    )


def plan_within_budget(plan: Mapping[str, Any]) -> bool:
    budget = int(plan.get("hard_request_budget") if plan.get("hard_request_budget") is not None else HARD_REQUEST_BUDGET)
    planned = int(plan.get("planned_requests") or 0)
    retry = int(plan.get("retry_allowance") or 0)
    return planned + retry <= budget


def load_retained_series(prior_official_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Parse already-retained probe bytes. Missing prior evidence is an empty reuse set."""
    if prior_official_dir is None:
        return {}
    ledger = Path(prior_official_dir) / "probe" / "request_ledger.jsonl"
    if not ledger.is_file():
        return {}
    from tools import run_liquidity_authority_closure as closure
    series, _ = closure._official_series(Path(prior_official_dir))
    return series


def governed_request_budget(requested: int) -> int:
    """Callers may narrow the governed ceiling, never widen it."""
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 0 or requested > HARD_REQUEST_BUDGET:
        raise OfficialLiquidityRollforwardError(BUDGET_EXCEEDED_ERROR)
    return requested


def plan_daily_rollforward(
    frame: Mapping[str, Mapping[str, Any]],
    retained: Mapping[str, Mapping[str, Any]],
    *,
    target_session: str,
    hard_request_budget: int = HARD_REQUEST_BUDGET,
) -> dict[str, Any]:
    """Freeze the HOSE-only request list. Over-budget plans are returned, never executed."""
    hard_request_budget = governed_request_budget(hard_request_budget)
    requests: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    blocked: dict[str, list[str]] = defaultdict(list)
    for ticker, row in sorted(frame.items()):
        route = row.get("route_exchange") if isinstance(row, Mapping) else None
        if route is None:
            continue
        rights = wide.ACQUISITION_RIGHTS.get(route) or {}
        if rights.get("decision") != wide.AUTHORIZED_BOUNDED_INTERNAL:
            if not wide.retained_is_current(retained.get(ticker), target_session=target_session):
                blocked[route].append(ticker)
            else:
                reused.append({"ticker": ticker, "exchange": route})
            continue
        if wide.retained_is_current(retained.get(ticker), target_session=target_session):
            reused.append({"ticker": ticker, "exchange": route})
            continue
        requests.append(official.request_for(ticker, route, hose_page=1))
    retry_allowance = len(requests) // 10
    within = len(requests) + retry_allowance <= hard_request_budget
    inner = {
        "schema_version": "1.0.0",
        "contract_version": "official_exchange_liquidity_acquisition_plan/v1",
        "milestone": MILESTONE,
        "target_session": target_session,
        "rights": {exchange: {"decision": row["decision"]} for exchange, row in wide.ACQUISITION_RIGHTS.items()},
        "selection_rule": (
            "every route-resolved ticker whose exchange route is AUTHORIZED and whose "
            "retained series does not already reach the target session"
        ),
        "depth": "HOSE tradingresult page 1 = the newest 20 sessions; no deeper pagination is planned",
        "limits": dict(wide.ACQUISITION_MODE_LIMITS),
        "planned_requests": len(requests),
        "retry_allowance": retry_allowance,
        "hard_request_budget": hard_request_budget,
        "planned_by_exchange": dict(sorted(Counter(item["exchange"] for item in requests).items())),
        "reused_retained_by_exchange": dict(sorted(Counter(item["exchange"] for item in reused).items())),
        "not_authorized_not_planned": {exchange: len(tickers) for exchange, tickers in sorted(blocked.items())},
        "requests": requests,
        "reused": reused,
        "not_authorized_tickers": {exchange: sorted(tickers) for exchange, tickers in sorted(blocked.items())},
    }
    inner.update(contract.content_identity(inner, kind="official_exchange_liquidity_acquisition_plan"))
    return {
        "status": "PLANNED" if within else UNAVAILABLE_REQUEST_BUDGET,
        "reason": None if within else BUDGET_CEILING,
        "plan": inner,
        "plan_identity": inner.get("artifact_identity"),
        "hard_request_budget": hard_request_budget,
        "planned_requests": len(requests),
        "planned_by_exchange": dict(inner["planned_by_exchange"]),
        "reused_retained_by_exchange": dict(inner["reused_retained_by_exchange"]),
        "hnx_upcom_planned_requests": 0,
        "retry_allowance": retry_allowance,
        "limits": dict(inner["limits"]),
        "budget_state": WITHIN_BUDGET if within else BUDGET_CEILING,
        "requests": requests,
        "reused": reused,
        "not_authorized_tickers": dict(inner["not_authorized_tickers"]),
        "artifact_identity": inner.get("artifact_identity"),
    }


def resolve_for_daily(
    *,
    session: str,
    candidates: Sequence[tuple[str, Any]],
    allow_network: bool = False,
    prior_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a same-session candidate or fail the official component closed. Never HTTP."""
    last_status = UNAVAILABLE_SOURCE
    last_reason = "OFFICIAL_ARTIFACT_ABSENT"
    for _label, payload in candidates:
        if payload is None:
            continue
        verdict = evaluate_candidate_artifact(payload, session=session)
        if verdict["artifact"] is not None:
            component = build_component_status(
                session=session,
                status=AVAILABLE,
                reason_code=verdict["reason_code"],
                artifact_identity=verdict["artifact"].get("artifact_identity"),
                allow_network=allow_network,
            )
            return {"artifact": verdict["artifact"], "component": component, "execute_probe": False}
        last_status = verdict["status"]
        last_reason = verdict["reason_code"]
        if last_status == MALFORMED_ARTIFACT:
            component = build_component_status(
                session=session, status=MALFORMED_ARTIFACT, reason_code=last_reason,
                allow_network=allow_network, http_requests_made=0,
            )
            return {"artifact": None, "component": component, "execute_probe": False}

    planned_hose = 0
    planned_requests = 0
    retry_allowance = 0
    reused_count = 0
    plan_identity = None
    if prior_artifact is not None:
        frame = frame_from_official_records(prior_artifact.get("records") or {})
        retained = retained_slots_from_artifact(prior_artifact)
        plan = plan_daily_rollforward(frame, retained, target_session=session)
        planned_hose = hose_planned_request_count(plan)
        planned_requests = int(plan.get("planned_requests") or 0)
        retry_allowance = int(plan.get("retry_allowance") or 0)
        reused_count = len(plan.get("reused") or [])
        plan_identity = plan.get("artifact_identity")
        if not plan_within_budget(plan):
            last_status = UNAVAILABLE_REQUEST_BUDGET
            last_reason = BUDGET_CEILING
        elif hnx_upcom_planned_request_count(plan):
            last_status = UNAVAILABLE_RIGHTS
            last_reason = "HNX_UPCOM_BULK_REQUESTS_NOT_AUTHORIZED"
        elif allow_network:
            last_status = UNAVAILABLE_SOURCE
            last_reason = "AUTHORIZED_PROBE_NOT_EXECUTED_FROM_DAILY_ASSEMBLY"
        else:
            last_status = UNAVAILABLE_SOURCE
            last_reason = "OFFICIAL_LIQUIDITY_REFRESH_NOT_AUTHORIZED_THIS_INVOCATION"

    component = build_component_status(
        session=session,
        status=last_status,
        reason_code=last_reason,
        plan_identity=plan_identity,
        planned_requests=planned_requests,
        planned_hose_requests=planned_hose,
        planned_hnx_upcom_requests=0,
        http_requests_made=0,
        reused_retained_count=reused_count,
        execute_probe=False,
        allow_network=allow_network,
        extra={"retry_allowance": retry_allowance} if retry_allowance else None,
    )
    return {"artifact": None, "component": component, "execute_probe": False}


def load_for_daily_consumer(
    *,
    session: str,
    candidate_paths: Sequence[Path],
    component_status_paths: Sequence[Path] = (),
    allow_network: bool = False,
    prior_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a same-session artifact, preserving a valid materialized status.

    The materializer owns the request-plan result.  A consumer may re-read an
    official artifact to bind a valid same-session result, but it must not
    replace a materialized budget/rights/source outcome with a generic absent
    artifact result.
    """
    candidates: list[tuple[str, Any]] = []
    for path in candidate_paths:
        payload, error = read_json_object(Path(path))
        if error == MALFORMED_ARTIFACT:
            component = build_component_status(
                session=session,
                status=MALFORMED_ARTIFACT,
                reason_code="OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED",
                allow_network=allow_network,
                http_requests_made=0,
            )
            return {"artifact": None, "component": component, "execute_probe": False}
        candidates.append((str(path), payload))
    if not candidates:
        candidates = [("absent", None)]
    resolved = resolve_for_daily(
        session=session, candidates=candidates, allow_network=allow_network, prior_artifact=prior_artifact,
    )
    if resolved.get("artifact") is not None or (resolved.get("component") or {}).get("status") == MALFORMED_ARTIFACT:
        return resolved

    for path in component_status_paths:
        payload, error = read_json_object(Path(path))
        if error == UNAVAILABLE_SOURCE:
            continue
        if error == MALFORMED_ARTIFACT or not _valid_component_status(payload, session=session):
            component = build_component_status(
                session=session,
                status=MALFORMED_ARTIFACT,
                reason_code="OFFICIAL_LIQUIDITY_COMPONENT_STATUS_MALFORMED",
                allow_network=allow_network,
                http_requests_made=0,
            )
            return {"artifact": None, "component": component, "execute_probe": False}
        if payload.get("status") != AVAILABLE:
            return {"artifact": None, "component": dict(payload), "execute_probe": False}
    return resolved


def _valid_component_status(payload: Any, *, session: str) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("contract_version") != STATUS_CONTRACT or payload.get("target_session") != session:
        return False
    if payload.get("status") not in {
        AVAILABLE, PARTIAL, UNAVAILABLE_SOURCE, UNAVAILABLE_RIGHTS,
        UNAVAILABLE_REQUEST_BUDGET, UNAVAILABLE_SESSION, MALFORMED_ARTIFACT,
    }:
        return False
    claimed_identity = payload.get("component_identity")
    claimed_sha256 = payload.get("component_sha256")
    if not isinstance(claimed_identity, str) or not isinstance(claimed_sha256, str):
        return False
    body = {key: value for key, value in payload.items() if key not in {"component_identity", "component_sha256"}}
    try:
        expected = component_identity(body)
    except (TypeError, ValueError, KeyError):
        return False
    return claimed_identity == expected.get("artifact_identity") and claimed_sha256 == expected.get("artifact_sha256")


def _write_component(root: Path, session: str, body: Mapping[str, Any]) -> dict[str, Any]:
    target = status_path(root, session)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = dict(body)
    atomic_write_json(target, written)
    return {**written, "status_path": str(target), "artifact_path": str(official_artifact_path(root, session))}


def _copy_if_needed(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() == source.resolve():
        return
    dest.write_bytes(source.read_bytes())


def materialize_same_session_official_liquidity(
    *,
    session: str,
    artifact_root: Path,
    retained_evidence_root: Path | None = None,
    allow_network: bool = False,
    prior_official_dir: Path | None = None,
    prior_artifact: Mapping[str, Any] | None = None,
    universe: Mapping[str, Any] | None = None,
    retained_series: Mapping[str, Mapping[str, Any]] | None = None,
    execute_request: Any = None,  # noqa: ARG001 -- Daily never dispatches HTTP
    hard_request_budget: int = HARD_REQUEST_BUDGET,
) -> dict[str, Any]:
    """Bind or plan same-session official liquidity. Never raises into Core Daily.

    Production network still goes through the existing operator runner, and only
    when a frozen plan fits the governed ceiling. Daily itself copies a valid
    same-session artifact and otherwise records a component status.
    """
    artifact_root = Path(artifact_root)
    retained_evidence_root = Path(retained_evidence_root or artifact_root)
    dest = official_artifact_path(artifact_root, session)
    try:
        governed_request_budget(hard_request_budget)
        candidates: list[tuple[str, Path | None, Any]] = []
        for label, path in (
            ("attempt", dest),
            ("retained", official_artifact_path(retained_evidence_root, session)),
        ):
            if candidates and path.resolve() == dest.resolve() and label == "retained":
                continue
            payload, error = read_json_object(path)
            if error == MALFORMED_ARTIFACT:
                return _write_component(
                    artifact_root, session,
                    build_component_status(
                        session=session, status=MALFORMED_ARTIFACT,
                        reason_code="OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED",
                        allow_network=allow_network, http_requests_made=0,
                    ),
                )
            candidates.append((label, path if payload is not None else None, payload))

        for label, path, payload in candidates:
            verdict = evaluate_candidate_artifact(payload, session=session)
            if verdict["artifact"] is None:
                if verdict["status"] == UNAVAILABLE_SESSION and path is not None and path.resolve() == dest.resolve():
                    return _write_component(
                        artifact_root, session,
                        build_component_status(
                            session=session, status=UNAVAILABLE_SESSION,
                            reason_code=verdict["reason_code"],
                            allow_network=allow_network, http_requests_made=0,
                        ),
                    )
                continue
            if path is not None and path.resolve() != dest.resolve():
                _copy_if_needed(path, dest)
            reused = sum(
                1
                for record in (verdict["artifact"].get("records") or {}).values()
                if isinstance(record, Mapping) and (record.get("evidence_refs") or {}).get("newest") == session
            )
            return _write_component(
                artifact_root, session,
                build_component_status(
                    session=session, status=AVAILABLE,
                    reason_code="SAME_SESSION_ARTIFACT_BOUND",
                    artifact_identity=verdict["artifact"].get("artifact_identity"),
                    planned_requests=0, planned_hose_requests=0, http_requests_made=0,
                    reused_retained_count=reused, allow_network=allow_network,
                    extra={"bound_before_consumer": True, "source_label": label},
                ),
            )

        loaded_prior = prior_artifact
        if loaded_prior is None and universe is not None:
            frame = _frame_from_universe(universe)
            series = dict(retained_series or {})
            plan = plan_daily_rollforward(
                frame, series, target_session=session, hard_request_budget=hard_request_budget,
            )
            planned = int(plan.get("planned_requests") or 0)
            reused_count = len(plan.get("reused") or [])
            hose_count = hose_planned_request_count(plan)
            if not plan_within_budget(plan):
                return _write_component(
                    artifact_root, session,
                    build_component_status(
                        session=session, status=UNAVAILABLE_REQUEST_BUDGET,
                        reason_code=BUDGET_CEILING, planned_requests=planned,
                        planned_hose_requests=hose_count,
                        planned_hnx_upcom_requests=0, http_requests_made=0,
                        reused_retained_count=reused_count,
                        plan_identity=plan.get("plan_identity"),
                        allow_network=allow_network,
                        extra={
                            "retry_allowance": plan.get("retry_allowance"),
                            "planning_seed": "GOVERNED_OFFICIAL_UNIVERSE",
                            "planning_universe_identity": universe.get("artifact_identity"),
                        },
                    ),
                )
            if hnx_upcom_planned_request_count(plan):
                return _write_component(
                    artifact_root, session,
                    build_component_status(
                        session=session, status=UNAVAILABLE_RIGHTS,
                        reason_code="HNX_UPCOM_BULK_REQUESTS_NOT_AUTHORIZED",
                        planned_requests=planned,
                        allow_network=allow_network, http_requests_made=0,
                    ),
                )
            # Daily never becomes a crawler. execute_request is accepted for call-site
            # compatibility and is never invoked. Live refresh stays on the operator runner.
            reason = (
                "LIVE_REFRESH_USES_ESTABLISHED_RUNNER_WHEN_PLAN_FITS_BUDGET"
                if allow_network else "OFFICIAL_LIQUIDITY_REFRESH_NOT_AUTHORIZED_THIS_INVOCATION"
            )
            return _write_component(
                artifact_root, session,
                build_component_status(
                    session=session, status=UNAVAILABLE_SOURCE, reason_code=reason,
                    plan_identity=plan.get("plan_identity"),
                    planned_requests=planned, planned_hose_requests=hose_count,
                    http_requests_made=0, reused_retained_count=reused_count,
                    allow_network=allow_network,
                ),
            )
        if loaded_prior is None and prior_official_dir is not None:
            prior_path = Path(prior_official_dir) / "official_exchange_liquidity_research_artifact.json"
            payload, error = read_json_object(prior_path)
            if error == MALFORMED_ARTIFACT:
                return _write_component(
                    artifact_root, session,
                    build_component_status(
                        session=session, status=MALFORMED_ARTIFACT,
                        reason_code="OFFICIAL_LIQUIDITY_ARTIFACT_MALFORMED",
                        allow_network=allow_network, http_requests_made=0,
                    ),
                )
            loaded_prior = payload

        resolved = resolve_for_daily(
            session=session,
            candidates=[("absent", None)],
            allow_network=allow_network,
            prior_artifact=loaded_prior,
        )
        return _write_component(artifact_root, session, resolved["component"])
    except Exception as exc:  # noqa: BLE001 -- component-local: Daily proceeds without official liquidity
        return _write_component(
            artifact_root, session,
            build_component_status(
                session=session, status=UNAVAILABLE_SOURCE,
                reason_code=f"{type(exc).__name__}:{exc}",
                allow_network=allow_network, http_requests_made=0,
            ),
        )
