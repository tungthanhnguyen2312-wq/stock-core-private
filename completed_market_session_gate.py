"""Provider-aware completed-market-session gate for capability-first EOD operations.

DESIGN
    Provider/session evidence is primary. 18:00 Asia/Ho_Chi_Minh is a SAFETY FLOOR /
    operational trigger window, never market-session factual authority.

    DNSE `/market/working-dates` is retained as a forward calendar window. It can
    prove working-date identity and prior/next dates *inside the observed window*.
    It does not expose a documented "session completed" / "market closed" flag, and
    it has no historical coverage. This module never claims PROVIDER_CONFIRMED_COMPLETED.

    Two distinct phases:

    PHASE A — PRE_ACQUISITION_ATTEMPT (ATTEMPT_ELIGIBLE)
        Answers only: may the operator attempt the bounded post-close acquisition now?
        Eligible when requested_at is at/after the safety floor, the intended session
        is not future, the session has qualified working-date identity under the DNSE
        working_dates contract *or* has sufficient retained DNSE exact-session
        evidence when the forward calendar no longer covers that historical date,
        there is no contradictory session evidence, and the provider/session route
        is operationally available.
        ATTEMPT_ELIGIBLE does not mean market close, completed session, or exact-session
        data is proven. Time alone never produces Phase-B READY.

    PHASE B — POST_ACQUISITION_COMPLETION (READY)
        READY is the lower-strength semantic EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR:
        working-date identity + exact intended session + sufficient retained exact-session
        observations acquired at or after the safety floor. Only an actual retained
        response may establish this. Time alone never produces READY.

All evaluation is a pure function of injected `requested_at` plus injected or
explicitly supplied evidence. Tests must never depend on the host wall clock.
"""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import json

from field_temporal_contract import canonical_json, stable_id
from vn_time import VN_TZ, vn_now

SCHEMA_VERSION = "completed_market_session_gate/v1"
CONTRACT_VERSION = SCHEMA_VERSION
PROVIDER = "DNSE"
PROVIDER_EVIDENCE_TYPE = "DNSE_WORKING_DATES_CALENDAR_IDENTITY"
PROVIDER_SEMANTIC_STRENGTH = "WORKING_DATE_IDENTITY_AND_NEIGHBOR_SESSIONS"
PROVIDER_SEMANTIC_STRENGTH_UNAVAILABLE = "UNAVAILABLE"
READY_SEMANTIC = "EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR"
ATTEMPT_ELIGIBLE_SEMANTIC = "PRE_ACQUISITION_ATTEMPT_ELIGIBLE"
OPERATING_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_SAFETY_FLOOR = time(18, 0)
# Reuse the canonical post-close floor for full-universe snapshots only.
MIN_P3F9B_EXACT_SESSION_COVERAGE_RATIO = 0.20
MIN_PACKET_EXACT_SESSION_OBSERVATIONS = 1

STATUS_READY = "READY"
STATUS_ATTEMPT_ELIGIBLE = "ATTEMPT_ELIGIBLE"
STATUS_TOO_EARLY = "TOO_EARLY"
STATUS_NON_WORKING_DATE = "NON_WORKING_DATE"
STATUS_SESSION_MISMATCH = "SESSION_MISMATCH"
STATUS_PROVIDER_EVIDENCE_UNAVAILABLE = "PROVIDER_EVIDENCE_UNAVAILABLE"
STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT = "EXACT_SESSION_EVIDENCE_INSUFFICIENT"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_BLOCKED = "BLOCKED"

PHASE_A = "PRE_ACQUISITION_ATTEMPT"
PHASE_B = "POST_ACQUISITION_COMPLETION"

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "provider_confirmed_completed": False,
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
}

_WORKING_DATE_KEYS = ("workingDates", "working_dates", "workingdates")


class CompletedSessionGateError(ValueError):
    """Fail-closed refusal from the completed-session gate."""


def parse_requested_at(value: datetime | str, *, timezone_name: str = OPERATING_TIMEZONE) -> datetime:
    """Parse an injected ISO-8601 instant and normalize to the operating timezone."""
    if timezone_name != OPERATING_TIMEZONE:
        raise CompletedSessionGateError("UNSUPPORTED_OPERATING_TIMEZONE:" + timezone_name)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise CompletedSessionGateError("REQUESTED_AT_MISSING")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CompletedSessionGateError("REQUESTED_AT_UNPARSEABLE") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(VN_TZ)


def parse_session_date(value: str) -> str:
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError as exc:
        raise CompletedSessionGateError("INVALID_SESSION_FORMAT:" + text) from exc


def _iso_date(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return None


def extract_working_dates(payload: Any) -> list[str]:
    """Extract ISO working dates from a retained DNSE working_dates body.

    Opaque extra fields are ignored. No session-completed semantic is inferred.
    """
    if payload is None:
        return []
    body: Any = payload
    if isinstance(payload, Mapping):
        for wrapper in ("body", "raw_payload", "payload", "data"):
            inner = payload.get(wrapper)
            if isinstance(inner, Mapping) and any(key in inner for key in _WORKING_DATE_KEYS):
                body = inner
                break
            if isinstance(inner, list):
                body = inner
                break
        if isinstance(body, Mapping):
            for key in _WORKING_DATE_KEYS:
                if key in body:
                    body = body[key]
                    break
    dates: list[str] = []
    if isinstance(body, list):
        for item in body:
            if isinstance(item, Mapping):
                candidate = _iso_date(item.get("date") or item.get("workingDate") or item.get("working_date"))
            else:
                candidate = _iso_date(item)
            if candidate:
                dates.append(candidate)
    elif isinstance(body, Mapping):
        candidate = _iso_date(body.get("date"))
        if candidate:
            dates.append(candidate)
    return sorted(set(dates))


def normalize_working_dates_evidence(
    evidence: Mapping[str, Any] | None,
    *,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Normalize injected or probed working_dates evidence without promoting session completion."""
    if not isinstance(evidence, Mapping) or not evidence:
        return {
            "status": "UNAVAILABLE",
            "provider": PROVIDER,
            "provider_evidence_type": PROVIDER_EVIDENCE_TYPE,
            "provider_semantic_strength": PROVIDER_SEMANTIC_STRENGTH_UNAVAILABLE,
            "working_dates": [],
            "window_start": None,
            "window_end": None,
            "provider_evidence_identity": None,
            "retrieved_at": retrieved_at,
            "limitations": [
                "WORKING_DATES_EVIDENCE_ABSENT",
                "FORWARD_CALENDAR_WINDOW_NO_HISTORICAL_COVERAGE",
                "NO_SESSION_COMPLETED_FLAG",
            ],
        }
    dates = extract_working_dates(evidence)
    identity_payload = {"provider": PROVIDER, "dataset": "working_dates", "working_dates": dates}
    digest = stable_id(identity_payload) if dates else None
    return {
        "status": "OBSERVED" if dates else "EMPTY",
        "provider": PROVIDER,
        "provider_evidence_type": PROVIDER_EVIDENCE_TYPE,
        "provider_semantic_strength": PROVIDER_SEMANTIC_STRENGTH if dates else PROVIDER_SEMANTIC_STRENGTH_UNAVAILABLE,
        "working_dates": dates,
        "window_start": dates[0] if dates else None,
        "window_end": dates[-1] if dates else None,
        "provider_evidence_identity": f"dnse_working_dates:{digest}" if digest else None,
        "provider_evidence_hash": digest,
        "retrieved_at": retrieved_at or evidence.get("retrieved_at") or evidence.get("retrievedAt"),
        "limitations": [
            "FORWARD_CALENDAR_WINDOW_NO_HISTORICAL_COVERAGE",
            "NO_SESSION_COMPLETED_FLAG",
            "PRIOR_NEXT_ONLY_WITHIN_OBSERVED_WINDOW",
        ],
    }


def neighbor_sessions(working_dates: Sequence[str], session: str) -> dict[str, Any]:
    dates = list(working_dates)
    if session not in dates:
        return {
            "prior_working_date": None,
            "next_working_date": None,
            "in_observed_window": bool(dates) and dates[0] <= session <= dates[-1],
            "outside_observed_window": bool(dates) and (session < dates[0] or session > dates[-1]),
        }
    index = dates.index(session)
    return {
        "prior_working_date": dates[index - 1] if index > 0 else None,
        "next_working_date": dates[index + 1] if index + 1 < len(dates) else None,
        "in_observed_window": True,
        "outside_observed_window": False,
        "prior_unknown_outside_window": index == 0,
        "next_unknown_outside_window": index + 1 == len(dates),
    }


def _coverage_ratio(observed: int | None, attempted: int | None) -> float:
    if not attempted:
        return 0.0
    return float(observed or 0) / float(attempted)


def normalize_exact_session_evidence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project retained EOD packet or P3F9B/canonical envelope into one comparison record."""
    if not isinstance(evidence, Mapping) or not evidence:
        return {
            "status": "ABSENT",
            "source_contract": None,
            "resolved_completed_session": None,
            "retained_snapshot_session": None,
            "requested_at": None,
            "exact_session_observed_count": 0,
            "attempted_candidate_count": 0,
            "identity": None,
            "hash": None,
        }
    if "observations" in evidence or evidence.get("contract_version") == "capability_first_eod_collector/v1":
        session = evidence.get("session_date")
        observations = evidence.get("observations") if isinstance(evidence.get("observations"), list) else []
        acquired = []
        for row in observations:
            if not isinstance(row, Mapping):
                continue
            row_session = row.get("provider_session_date") or row.get("session")
            if row.get("status") == "ACQUIRED" and row_session == session:
                acquired.append(row)
        identity = evidence.get("packet_identity")
        digest = evidence.get("packet_sha256")
        return {
            "status": "OBSERVED" if acquired else "INSUFFICIENT",
            "source_contract": "capability_first_eod_collector/v1",
            "resolved_completed_session": session,
            "retained_snapshot_session": session,
            "requested_at": evidence.get("created_at") or evidence.get("requested_at"),
            "exact_session_observed_count": len(acquired),
            "attempted_candidate_count": len(observations),
            "identity": identity,
            "hash": digest,
        }
    resolved_block = evidence.get("resolved_session") if isinstance(evidence.get("resolved_session"), Mapping) else {}
    coverage = evidence.get("exact_session_coverage") if isinstance(evidence.get("exact_session_coverage"), Mapping) else {}
    dispositions = evidence.get("exact_session_dispositions") if isinstance(evidence.get("exact_session_dispositions"), Mapping) else {}
    acquisition = evidence.get("acquisition_cohort") if isinstance(evidence.get("acquisition_cohort"), Mapping) else {}
    resolved = (
        evidence.get("resolved_completed_session")
        or resolved_block.get("resolved_completed_session")
        or evidence.get("session_date")
        or evidence.get("session")
    )
    retained = (
        evidence.get("retained_snapshot_session")
        or resolved_block.get("retained_snapshot_session")
        or resolved
    )
    requested_at = (
        evidence.get("requested_at")
        or resolved_block.get("execution_timestamp")
        or evidence.get("execution_timestamp")
    )
    observed = evidence.get("exact_session_observed_count")
    if observed is None:
        observed = coverage.get("exact_session_observed_count")
    attempted = evidence.get("attempted_candidate_count")
    if attempted is None:
        attempted = coverage.get("attempted_candidate_count")
    identity = evidence.get("snapshot_identity") or evidence.get("artifact_identity") or evidence.get("packet_identity")
    digest = evidence.get("snapshot_sha256") or evidence.get("artifact_sha256") or evidence.get("packet_sha256")
    contract = evidence.get("contract_version") or (
        "p3f9b_market_wide_exact_session_scaleout/v1"
        if resolved_block or coverage
        else "p3f9_exact_session_mva_snapshot/v2"
    )
    return {
        "status": "OBSERVED" if int(observed or 0) > 0 else "INSUFFICIENT",
        "source_contract": contract,
        "resolved_completed_session": resolved,
        "retained_snapshot_session": retained,
        "requested_at": requested_at,
        "exact_session_observed_count": int(observed or 0),
        "attempted_candidate_count": int(attempted or 0),
        "identity": identity,
        "hash": digest,
        "materialization_scope": evidence.get("materialization_scope") or acquisition.get("materialization_scope"),
        "unattempted_without_explicit_disposition": evidence.get("unattempted_without_explicit_disposition")
        if "unattempted_without_explicit_disposition" in evidence
        else dispositions.get("unattempted_without_explicit_disposition"),
    }


def _acquired_after_safety_floor(
    requested_at_raw: Any,
    session: str,
    *,
    safety_floor: time,
) -> tuple[bool, str | None]:
    if not requested_at_raw:
        return False, "EXACT_SESSION_ACQUISITION_TIMESTAMP_MISSING"
    try:
        acquired = parse_requested_at(str(requested_at_raw))
    except CompletedSessionGateError:
        return False, "EXACT_SESSION_ACQUISITION_TIMESTAMP_UNPARSEABLE"
    if acquired.date().isoformat() != session:
        # A later-day replay of a completed session is acceptable as retained evidence.
        if acquired.date().isoformat() > session:
            return True, None
        return False, "EXACT_SESSION_ACQUIRED_BEFORE_SESSION_DATE"
    if acquired.timetz().replace(tzinfo=None) < safety_floor:
        return False, "EXACT_SESSION_ACQUIRED_BEFORE_SAFETY_FLOOR"
    return True, None


def _exact_session_sufficient(normalized: Mapping[str, Any], session: str, *, safety_floor: time) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if normalized.get("status") == "ABSENT":
        return False, ["EXACT_SESSION_EVIDENCE_ABSENT"]
    resolved = normalized.get("resolved_completed_session")
    retained = normalized.get("retained_snapshot_session")
    if resolved != session or retained != session:
        return False, ["EXACT_SESSION_IDENTITY_MISMATCH"]
    observed = int(normalized.get("exact_session_observed_count") or 0)
    attempted = int(normalized.get("attempted_candidate_count") or 0)
    contract = str(normalized.get("source_contract") or "")
    if contract == "capability_first_eod_collector/v1":
        if observed < MIN_PACKET_EXACT_SESSION_OBSERVATIONS:
            reasons.append("PACKET_EXACT_SESSION_OBSERVATIONS_INSUFFICIENT")
    else:
        if observed <= 0 or _coverage_ratio(observed, attempted) < MIN_P3F9B_EXACT_SESSION_COVERAGE_RATIO:
            reasons.append("P3F9B_EXACT_SESSION_COVERAGE_INSUFFICIENT")
    after_floor, floor_reason = _acquired_after_safety_floor(
        normalized.get("requested_at"), session, safety_floor=safety_floor,
    )
    if not after_floor:
        reasons.append(floor_reason or "EXACT_SESSION_NOT_AFTER_SAFETY_FLOOR")
    return not reasons, reasons


def _weekend(session: str) -> bool:
    return datetime.fromisoformat(session).weekday() >= 5


def _evidence_acquired_at(payload: Mapping[str, Any]) -> str:
    resolved = payload.get("resolved_session") if isinstance(payload.get("resolved_session"), Mapping) else {}
    value = (
        payload.get("requested_at")
        or resolved.get("execution_timestamp")
        or payload.get("execution_timestamp")
        or payload.get("created_at")
        or ""
    )
    return str(value)


def load_exact_session_evidence_from_root(root: Path, session: str) -> dict[str, Any] | None:
    """Load a small retained envelope; never open the full-universe P3F9B snapshot records map.

    When several scaleout envelopes exist for the same session, keep the latest
    acquisition timestamp so a pre-floor artifact cannot hide a later post-floor one.
    """
    nodash = session.replace("-", "")
    packet_candidates = [
        root / "operations-review" / f"capability-first-eod-{session}" / "session_packet.json",
        root / "operations-review" / f"capability-first-real-eod-{session}" / "session_packet.json",
        root / "operations-review" / f"daily-market-evidence-{session}" / "session_packet.json",
        root / "data" / "retained-eod" / session / "session_packet.json",
    ]
    for path in packet_candidates:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["_evidence_path"] = str(path.as_posix())
                return payload
    scaleout_name = f"p3f9b-market-wide-exact-session-scaleout-{nodash}"
    scaleout_file = "p3f9b_market_wide_exact_session_scaleout_artifact.json"
    scaleout_candidates = []
    canonical_session = root / "operations-review" / "canonical-post-close-v1" / session
    if canonical_session.is_dir():
        for attempt in sorted(canonical_session.glob("post-close-attempt-*"), reverse=True):
            scaleout_candidates.append(
                attempt / "operations-review" / scaleout_name / scaleout_file
            )
    scaleout_candidates.append(root / "operations-review" / scaleout_name / scaleout_file)
    found: list[dict[str, Any]] = []
    for path in scaleout_candidates:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["_evidence_path"] = str(path.as_posix())
                found.append(payload)
    if not found:
        return None
    found.sort(key=_evidence_acquired_at)
    return found[-1]


def _gate_record(
    *,
    requested_at: datetime,
    timezone_name: str,
    safety_floor: time,
    safety_floor_pass: bool,
    requested_session: str | None,
    resolved_session: str | None,
    working: Mapping[str, Any],
    exact: Mapping[str, Any],
    resolution_method: str,
    completion_gate_status: str,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    neighbors = neighbor_sessions(working.get("working_dates") or [], resolved_session) if resolved_session else {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "requested_at": requested_at.isoformat(),
        "timezone": timezone_name,
        "safety_floor": safety_floor.isoformat(timespec="minutes"),
        "safety_floor_pass": safety_floor_pass,
        "requested_session": requested_session,
        "resolved_session": resolved_session,
        "provider": PROVIDER,
        "provider_evidence_type": PROVIDER_EVIDENCE_TYPE,
        "provider_evidence_identity": working.get("provider_evidence_identity"),
        "provider_evidence_hash": working.get("provider_evidence_hash"),
        "provider_semantic_strength": working.get("provider_semantic_strength"),
        "working_dates_window": {
            "start": working.get("window_start"),
            "end": working.get("window_end"),
            "status": working.get("status"),
        },
        "neighbor_sessions": neighbors,
        "exact_session_evidence": {
            "status": exact.get("status"),
            "source_contract": exact.get("source_contract"),
            "resolved_completed_session": exact.get("resolved_completed_session"),
            "retained_snapshot_session": exact.get("retained_snapshot_session"),
            "requested_at": exact.get("requested_at"),
            "exact_session_observed_count": exact.get("exact_session_observed_count"),
            "attempted_candidate_count": exact.get("attempted_candidate_count"),
            "identity": exact.get("identity"),
            "hash": exact.get("hash"),
        },
        "resolution_method": resolution_method,
        "completion_gate_status": completion_gate_status,
        "reason_codes": list(reason_codes),
        "ready_semantic": READY_SEMANTIC if completion_gate_status == STATUS_READY else None,
        "authority_statement": {
            "provider_confirmed_completed": False,
            "safety_floor_is_not_session_authority": True,
            "working_dates_proves": [
                "working_date_identity_within_observed_window",
                "prior_next_working_date_within_observed_window",
            ],
            "working_dates_does_not_prove": [
                "market_session_completed",
                "market_closed",
                "historical_working_dates_outside_observed_window",
            ],
            "ready_means": READY_SEMANTIC,
            "limitations": list(working.get("limitations") or []),
            "authority_effect": "NONE",
        },
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
    }
    digest = stable_id({k: v for k, v in payload.items()})
    payload["gate_content_identity"] = digest
    payload["gate_identity"] = f"completed_market_session_gate:{digest}"
    return payload


def evaluate_completed_market_session_gate(
    *,
    requested_at: datetime | str | None = None,
    requested_session: str | None = None,
    timezone_name: str = OPERATING_TIMEZONE,
    safety_floor: time = DEFAULT_SAFETY_FLOOR,
    working_dates_evidence: Mapping[str, Any] | None = None,
    exact_session_evidence: Mapping[str, Any] | None = None,
    working_dates_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    allow_provider_probe: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phase B: evaluate post-acquisition exact-session completion evidence.

    READY means EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR. Time alone never
    returns READY. Pre-acquisition attempt eligibility is
    ``evaluate_attempt_eligibility`` (Phase A).

    `requested_at` / `now` are the only clocks. Host wall clock is used solely when
    both are omitted (operator CLI). Tests must inject `requested_at`.
    """
    instant = parse_requested_at(requested_at if requested_at is not None else now or vn_now(), timezone_name=timezone_name)
    local_date = instant.date().isoformat()
    safety_floor_pass = instant.timetz().replace(tzinfo=None) >= safety_floor
    explicit_session = parse_session_date(requested_session) if requested_session else None

    working_payload = working_dates_evidence
    if working_payload is None and allow_provider_probe and working_dates_fetcher is not None:
        working_payload = working_dates_fetcher()
    working = normalize_working_dates_evidence(working_payload, retrieved_at=instant.isoformat())
    dates = list(working.get("working_dates") or [])
    exact = normalize_exact_session_evidence(exact_session_evidence)

    def emit(status: str, reasons: Sequence[str], resolved: str | None, method: str) -> dict[str, Any]:
        return _gate_record(
            requested_at=instant,
            timezone_name=timezone_name,
            safety_floor=safety_floor,
            safety_floor_pass=safety_floor_pass,
            requested_session=explicit_session,
            resolved_session=resolved,
            working=working,
            exact=exact,
            resolution_method=method,
            completion_gate_status=status,
            reason_codes=reasons,
        )

    # Explicit future session always fails, independent of working_dates.
    if explicit_session and explicit_session > local_date:
        return emit(STATUS_BLOCKED, ["FUTURE_SESSION"], explicit_session, "EXPLICIT_SESSION")

    # Same-day before the safety floor fails before any collection.
    if explicit_session == local_date and not safety_floor_pass:
        return emit(STATUS_TOO_EARLY, ["BEFORE_SAFETY_FLOOR"], explicit_session, "EXPLICIT_SESSION")

    if working.get("status") not in {"OBSERVED"}:
        if not safety_floor_pass and (explicit_session is None or explicit_session == local_date):
            return emit(
                STATUS_TOO_EARLY,
                ["BEFORE_SAFETY_FLOOR", "WORKING_DATES_UNAVAILABLE"],
                explicit_session,
                "EXPLICIT_SESSION" if explicit_session else "OMITTED_SESSION",
            )
        return emit(
            STATUS_PROVIDER_EVIDENCE_UNAVAILABLE,
            ["WORKING_DATES_UNAVAILABLE"],
            explicit_session,
            "EXPLICIT_SESSION" if explicit_session else "OMITTED_SESSION",
        )

    window_start, window_end = working.get("window_start"), working.get("window_end")

    def in_window(session: str) -> bool:
        return bool(window_start and window_end and window_start <= session <= window_end)

    if explicit_session:
        resolved = explicit_session
        method = "EXPLICIT_SESSION"
        if _weekend(resolved):
            return emit(STATUS_NON_WORKING_DATE, ["WEEKEND_SESSION"], resolved, method)
        if resolved not in dates:
            if in_window(resolved) or resolved >= local_date:
                # Inside the observed forward window, or today's civil date not present
                # in a window that starts at/after today: not a working date.
                return emit(STATUS_NON_WORKING_DATE, ["NOT_IN_WORKING_DATES"], resolved, method)
            # Historical date before the forward window: working_dates cannot prove
            # working/non-working identity. Exact-session retained evidence may.
            sufficient, exact_reasons = _exact_session_sufficient(exact, resolved, safety_floor=safety_floor)
            if not sufficient:
                return emit(
                    STATUS_PROVIDER_EVIDENCE_UNAVAILABLE,
                    ["WORKING_DATES_WINDOW_DOES_NOT_COVER_SESSION", *exact_reasons],
                    resolved,
                    method,
                )
    else:
        method = "LATEST_DEFENSIBLE_COMPLETED_WORKING_SESSION"
        candidates: list[str] = []
        for item in dates:
            if item > local_date:
                continue
            if item == local_date and not safety_floor_pass:
                continue
            candidates.append(item)
        exact_session = exact.get("resolved_completed_session")
        if isinstance(exact_session, str) and exact_session <= local_date:
            if not (exact_session == local_date and not safety_floor_pass):
                candidates.append(exact_session)
        defensible: list[str] = []
        for item in sorted(set(candidates)):
            ok, _reasons = _exact_session_sufficient(exact, item, safety_floor=safety_floor)
            if ok:
                defensible.append(item)
        if not defensible:
            if not safety_floor_pass:
                return emit(STATUS_TOO_EARLY, ["BEFORE_SAFETY_FLOOR", "NO_DEFENSIBLE_COMPLETED_SESSION"], None, method)
            if exact.get("status") == "ABSENT":
                return emit(STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT, ["EXACT_SESSION_EVIDENCE_ABSENT"], max(candidates) if candidates else None, method)
            if exact.get("resolved_completed_session") not in {None, *candidates}:
                return emit(STATUS_SESSION_MISMATCH, ["EXACT_SESSION_IDENTITY_MISMATCH"], max(candidates) if candidates else None, method)
            return emit(
                STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT,
                ["NO_DEFENSIBLE_COMPLETED_SESSION_WITH_EXACT_EVIDENCE"],
                max(candidates) if candidates else None,
                method,
            )
        resolved = max(defensible)

    if explicit_session and exact.get("resolved_completed_session") not in {None, resolved} and exact.get("status") != "ABSENT":
        return emit(STATUS_SESSION_MISMATCH, ["PROVIDER_OR_EXACT_SESSION_MISMATCH"], resolved, method)

    sufficient, exact_reasons = _exact_session_sufficient(exact, resolved, safety_floor=safety_floor)
    if not sufficient:
        if exact.get("resolved_completed_session") not in {None, resolved} and exact.get("status") != "ABSENT":
            return emit(STATUS_SESSION_MISMATCH, exact_reasons, resolved, method)
        return emit(STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT, exact_reasons, resolved, method)

    if resolved in dates:
        # Working-date identity agrees with exact-session identity.
        pass
    elif exact.get("resolved_completed_session") == resolved:
        # Historical session proven by retained exact-session evidence only.
        pass
    else:
        return emit(STATUS_AMBIGUOUS, ["WORKING_DATE_AND_EXACT_SESSION_UNALIGNED"], resolved, method)

    return emit(STATUS_READY, ["EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR", "WORKING_DATE_IDENTITY_CONFIRMED_OR_RETAINED"], resolved, method)


def _attempt_record(
    *,
    requested_at: datetime,
    timezone_name: str,
    safety_floor: time,
    safety_floor_pass: bool,
    requested_session: str | None,
    resolved_session: str | None,
    working: Mapping[str, Any],
    exact: Mapping[str, Any],
    resolution_method: str,
    attempt_gate_status: str,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    neighbors = neighbor_sessions(working.get("working_dates") or [], resolved_session) if resolved_session else {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "phase": PHASE_A,
        "requested_at": requested_at.isoformat(),
        "timezone": timezone_name,
        "safety_floor": safety_floor.isoformat(timespec="minutes"),
        "safety_floor_pass": safety_floor_pass,
        "requested_session": requested_session,
        "resolved_session": resolved_session,
        "provider": PROVIDER,
        "provider_evidence_type": PROVIDER_EVIDENCE_TYPE,
        "provider_evidence_identity": working.get("provider_evidence_identity"),
        "provider_evidence_hash": working.get("provider_evidence_hash"),
        "provider_semantic_strength": working.get("provider_semantic_strength"),
        "working_dates_window": {
            "start": working.get("window_start"),
            "end": working.get("window_end"),
            "status": working.get("status"),
        },
        "working_dates": list(working.get("working_dates") or []),
        "neighbor_sessions": neighbors,
        "exact_session_evidence": {
            "status": exact.get("status"),
            "source_contract": exact.get("source_contract"),
            "resolved_completed_session": exact.get("resolved_completed_session"),
            "retained_snapshot_session": exact.get("retained_snapshot_session"),
            "requested_at": exact.get("requested_at"),
            "exact_session_observed_count": exact.get("exact_session_observed_count"),
            "attempted_candidate_count": exact.get("attempted_candidate_count"),
            "identity": exact.get("identity"),
            "hash": exact.get("hash"),
        },
        "resolution_method": resolution_method,
        "attempt_gate_status": attempt_gate_status,
        "completion_gate_status": None,
        "reason_codes": list(reason_codes),
        "attempt_semantic": ATTEMPT_ELIGIBLE_SEMANTIC if attempt_gate_status == STATUS_ATTEMPT_ELIGIBLE else None,
        "ready_semantic": None,
        "authority_statement": {
            "provider_confirmed_completed": False,
            "safety_floor_is_not_session_authority": True,
            "attempt_eligible_does_not_mean": [
                "market_session_completed",
                "market_closed",
                "exact_session_data_proven",
            ],
            "working_dates_proves": [
                "working_date_identity_within_observed_window",
                "prior_next_working_date_within_observed_window",
            ],
            "working_dates_does_not_prove": [
                "market_session_completed",
                "market_closed",
                "historical_working_dates_outside_observed_window",
            ],
            "ready_means": READY_SEMANTIC,
            "time_alone_never_produces_phase_b_ready": True,
            "limitations": list(working.get("limitations") or []),
            "authority_effect": "NONE",
        },
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
    }
    digest = stable_id({k: v for k, v in payload.items()})
    payload["gate_content_identity"] = digest
    payload["gate_identity"] = f"completed_market_session_attempt_gate:{digest}"
    return payload


def evaluate_attempt_eligibility(
    *,
    requested_at: datetime | str | None = None,
    requested_session: str | None = None,
    timezone_name: str = OPERATING_TIMEZONE,
    safety_floor: time = DEFAULT_SAFETY_FLOOR,
    working_dates_evidence: Mapping[str, Any] | None = None,
    exact_session_evidence: Mapping[str, Any] | None = None,
    working_dates_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    allow_provider_probe: bool = False,
    allow_historical_target_session_acquisition: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phase A: may the operator attempt bounded post-close acquisition now?

    Does not establish market close, completed session, or exact-session data.
    Time alone never yields Phase-B READY.
    """
    instant = parse_requested_at(requested_at if requested_at is not None else now or vn_now(), timezone_name=timezone_name)
    local_date = instant.date().isoformat()
    safety_floor_pass = instant.timetz().replace(tzinfo=None) >= safety_floor
    explicit_session = parse_session_date(requested_session) if requested_session else None

    working_payload = working_dates_evidence
    if working_payload is None and allow_provider_probe and working_dates_fetcher is not None:
        working_payload = working_dates_fetcher()
    working = normalize_working_dates_evidence(working_payload, retrieved_at=instant.isoformat())
    dates = list(working.get("working_dates") or [])
    exact = normalize_exact_session_evidence(exact_session_evidence)

    def emit(status: str, reasons: Sequence[str], resolved: str | None, method: str) -> dict[str, Any]:
        return _attempt_record(
            requested_at=instant,
            timezone_name=timezone_name,
            safety_floor=safety_floor,
            safety_floor_pass=safety_floor_pass,
            requested_session=explicit_session,
            resolved_session=resolved,
            working=working,
            exact=exact,
            resolution_method=method,
            attempt_gate_status=status,
            reason_codes=reasons,
        )

    if explicit_session and explicit_session > local_date:
        return emit(STATUS_BLOCKED, ["FUTURE_SESSION"], explicit_session, "EXPLICIT_SESSION")

    if explicit_session == local_date and not safety_floor_pass:
        return emit(STATUS_TOO_EARLY, ["BEFORE_SAFETY_FLOOR"], explicit_session, "EXPLICIT_SESSION")

    if working.get("status") not in {"OBSERVED"}:
        if not safety_floor_pass and (explicit_session is None or explicit_session == local_date):
            return emit(
                STATUS_TOO_EARLY,
                ["BEFORE_SAFETY_FLOOR", "WORKING_DATES_UNAVAILABLE"],
                explicit_session,
                "EXPLICIT_SESSION" if explicit_session else "OMITTED_SESSION",
            )
        return emit(
            STATUS_PROVIDER_EVIDENCE_UNAVAILABLE,
            ["WORKING_DATES_UNAVAILABLE"],
            explicit_session,
            "EXPLICIT_SESSION" if explicit_session else "OMITTED_SESSION",
        )

    window_start, window_end = working.get("window_start"), working.get("window_end")

    def in_window(session: str) -> bool:
        return bool(window_start and window_end and window_start <= session <= window_end)

    if explicit_session:
        resolved = explicit_session
        method = "EXPLICIT_SESSION"
        if _weekend(resolved):
            return emit(STATUS_NON_WORKING_DATE, ["WEEKEND_SESSION"], resolved, method)
        if resolved not in dates:
            if in_window(resolved) or resolved >= local_date:
                return emit(STATUS_NON_WORKING_DATE, ["NOT_IN_WORKING_DATES"], resolved, method)
            # A current forward calendar has no authority over a historical date
            # that it no longer covers.  A retained, post-floor DNSE exact-session
            # artifact for that exact date is already qualified trading-session
            # evidence; it is not a civil-time or weekday inference.
            sufficient, exact_reasons = _exact_session_sufficient(exact, resolved, safety_floor=safety_floor)
            if sufficient:
                return emit(
                    STATUS_ATTEMPT_ELIGIBLE,
                    [
                        "ATTEMPT_ELIGIBLE_AFTER_SAFETY_FLOOR",
                        "RETAINED_HISTORICAL_EXACT_SESSION_IDENTITY_CONFIRMED",
                    ],
                    resolved,
                    method,
                )
            if allow_historical_target_session_acquisition:
                return emit(
                    STATUS_ATTEMPT_ELIGIBLE,
                    [
                        "ATTEMPT_ELIGIBLE_HISTORICAL_TARGET_SESSION_ACQUISITION",
                        "HISTORICAL_WORKING_DATE_IDENTITY_PENDING_EXACT_DNSE_RESPONSE",
                    ],
                    resolved,
                    method,
                )
            return emit(
                STATUS_PROVIDER_EVIDENCE_UNAVAILABLE,
                ["WORKING_DATES_WINDOW_DOES_NOT_COVER_SESSION", *exact_reasons],
                resolved,
                method,
            )
    else:
        method = "LATEST_WORKING_DATE_NOT_FUTURE"
        candidates = [
            item for item in dates
            if item < local_date or (item == local_date and safety_floor_pass)
        ]
        if not candidates:
            if not safety_floor_pass:
                return emit(STATUS_TOO_EARLY, ["BEFORE_SAFETY_FLOOR", "NO_DEFENSIBLE_INTENDED_SESSION"], None, method)
            return emit(STATUS_BLOCKED, ["NO_DEFENSIBLE_INTENDED_SESSION"], None, method)
        resolved = max(candidates)
        if resolved not in dates:
            return emit(STATUS_NON_WORKING_DATE, ["NOT_IN_WORKING_DATES"], resolved, method)

    if exact.get("status") not in {None, "ABSENT"} and exact.get("resolved_completed_session") not in {None, resolved}:
        return emit(STATUS_SESSION_MISMATCH, ["PROVIDER_OR_EXACT_SESSION_MISMATCH"], resolved, method)

    return emit(
        STATUS_ATTEMPT_ELIGIBLE,
        ["ATTEMPT_ELIGIBLE_AFTER_SAFETY_FLOOR", "WORKING_DATE_IDENTITY_CONFIRMED"],
        resolved,
        method,
    )


def load_json_mapping(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = Path(path)
    if not resolved.is_file():
        raise CompletedSessionGateError("EVIDENCE_FILE_MISSING:" + str(resolved))
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CompletedSessionGateError("EVIDENCE_FILE_NOT_OBJECT:" + str(resolved))
    return payload


def canonical_dump(value: Mapping[str, Any]) -> str:
    return canonical_json(value)
