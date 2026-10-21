"""Pure temporal measurements and explicit-policy freshness envelopes.

No axis eligibility, investment thresholds, registry discovery or orchestration.
Callers own policy; legacy labels and temporal/UNKNOWN semantics are preserved.
"""
from __future__ import annotations
import calendar
from datetime import date
import re
from typing import Any, Mapping

CONTRACT_VERSION = "opportunity_axis_freshness/v1"
FINANCIAL_PERIOD_FRESHNESS_CONTRACT = "financial_period_freshness/v1"
CURRENT = "CURRENT"
STALE_BUT_RESEARCH_USABLE = "STALE_BUT_RESEARCH_USABLE"
STALE_NOT_USABLE_FOR_THIS_AXIS = "STALE_NOT_USABLE_FOR_THIS_AXIS"
UNAVAILABLE = "UNAVAILABLE"
FRESHNESS_STATES = (CURRENT, STALE_BUT_RESEARCH_USABLE, STALE_NOT_USABLE_FOR_THIS_AXIS, UNAVAILABLE)
COMPATIBLE = "TEMPORALLY_COMPATIBLE"
INCOMPATIBLE_FUTURE = "FUTURE_INFORMATION_PROHIBITED"
INCOMPATIBLE_STALE = "STALE_AXIS_LOCALIZED"
MISSING = "SOURCE_SESSION_ABSENT"



class FutureInformationError(ValueError):
    """An input artifact or observation is strictly later than the decision session."""


def _session(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _envelope(axis: str, decision_session: str, source_session: str | None, known_at: str | None,
              source_period: str | None, source_artifact_identity: str | None, state: str,
              compatibility: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "axis": axis,
        "decision_session": decision_session,
        "source_session": source_session,
        "source_period": source_period,
        "known_at": known_at,
        "source_artifact_identity": source_artifact_identity,
        "freshness_status": state,
        "compatibility_status": compatibility,
        "older_evidence_usable": bool(contract["older_usable"]) and state == STALE_BUT_RESEARCH_USABLE,
        "rewritten_as_current": False,
        "contract_version": CONTRACT_VERSION,
    }


def separate_financial_clock(*, financial_period: Any, financial_period_end: Any,
                             price_as_of: Any, knowledge_available_at: Any,
                             decision_session: str, maximum_completed_quarter_lag: int) -> dict[str, Any]:
    """Age the financial period. A price session never becomes the financial clock.

    Annual labels are read as that year's fourth calendar quarter here only.
    ``completed_quarter_lag`` itself still accepts only ``YYYY-Qn``.
    """
    end = str(financial_period_end)[:10] if financial_period_end else None
    price = str(price_as_of)[:10] if price_as_of else None
    price_was_not_period_end = False
    if end and price and end == price:
        end = None
        price_was_not_period_end = True
    label = None
    implied_end = None
    text = str(financial_period or "")
    quarter = re.fullmatch(r"(\d{4})-Q([1-4])", text)
    annual = re.fullmatch(r"(?:FY)?(\d{4})(?:-FY)?", text)
    if end:
        try:
            day = date.fromisoformat(end)
            label = f"{day.year}-Q{(day.month - 1) // 3 + 1}"
        except ValueError:
            label = None
    elif quarter:
        label = text
    elif annual:
        label = f"{annual[1]}-Q4"
        implied_end = f"{annual[1]}-12-31"
    if label is None:
        lag, behind, blocker = None, None, "FINANCIAL_SOURCE_PERIOD_UNRESOLVED" if financial_period else "FINANCIAL_SOURCE_PERIOD_ABSENT"
    else:
        lag, behind, blocker = completed_quarter_lag(label, decision_session)
    if blocker:
        state, reasons = UNAVAILABLE, [blocker]
    elif lag > maximum_completed_quarter_lag:
        state, reasons = STALE_BUT_RESEARCH_USABLE, ["FINANCIAL_PERIOD_BEYOND_MAXIMUM_COMPLETED_QUARTER_LAG"]
    else:
        state, reasons = CURRENT, []
    return {
        "price_as_of": price_as_of,
        "financial_period": financial_period,
        "financial_period_end": end or implied_end,
        "knowledge_available_at": knowledge_available_at,
        "resolved_quarter_label": label,
        "freshness_status": state,
        "financial_freshness": state,
        "completed_quarter_lag": lag,
        "quarters_behind_last_completed": behind,
        "reason_codes": reasons,
        "price_session_does_not_set_financial_freshness": True,
        "price_session_not_used_as_financial_period_end": price_was_not_period_end,
        "rewritten_as_current": False,
        "research_usable": state in {CURRENT, STALE_BUT_RESEARCH_USABLE},
    }


def completed_quarter_lag(source_period: Any, decision_session: str) -> tuple[int | None, int | None, str | None]:
    """``(lag, quarters_behind_last_completed, blocker)`` for one ``YYYY-Qn`` financial period.

    ``lag`` is the decision session's quarter index minus the period's, the measure every
    Current Research financial window already uses. A period that has not ended by the decision
    session is future information; a label that is not a quarter is unresolved.
    """
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(source_period or ""))
    if not match:
        return None, None, "FINANCIAL_SOURCE_PERIOD_UNRESOLVED"
    period_index = int(match[1]) * 4 + int(match[2])
    day = date.fromisoformat(str(decision_session)[:10])
    quarter = (day.month - 1) // 3 + 1
    session_index = day.year * 4 + quarter
    quarter_end = date(day.year, quarter * 3, calendar.monthrange(day.year, quarter * 3)[1])
    last_completed = session_index if day >= quarter_end else session_index - 1
    if period_index > last_completed:
        return None, None, "FINANCIAL_PERIOD_AFTER_DECISION_SESSION"
    return session_index - period_index, last_completed - period_index, None




def reporting_period_basis(row: Mapping[str, Any]) -> dict[str, Any]:
    """Describe explicit accounting time without changing analytical freshness policy.

    Labels describe issuer-native periods. They never prove calendar dates,
    standalone flows, publication time, or a fiscal-calendar mapping.
    """
    label = row.get("reporting_period", row.get("native_period_label"))
    match = re.fullmatch(r"(\d{4})(?:-(Q[1-4]|H1|9M|FY))?", str(label or ""))
    if match and int(match[1]) == 0:
        match = None
    token = match[2] if match else None
    family = ("ANNUAL" if match and token in {None, "FY"} else
              "HALF_YEAR" if token == "H1" else "NINE_MONTH" if token == "9M" else
              "QUARTER" if token else "UNKNOWN")
    semantic = row.get("period_semantic_state", row.get("period_semantics"))
    mixed = isinstance(semantic, list) and len(set(str(s) for s in semantic)) > 1
    if isinstance(semantic, list):
        semantic = semantic[0] if len(semantic) == 1 else None
    nature = row.get("metric_nature")
    instant = semantic == "POINT_IN_TIME_BALANCE_SHEET" or nature == "STOCK_POINT_IN_TIME" or row.get("statement_family") == "balance_sheet"
    flow = semantic in ("STANDALONE_QUARTER", "YTD_CUMULATIVE_INTERIM", "ANNUAL") or nature == "FLOW_DURATION" or row.get("statement_family") in ("income_statement", "cash_flow")
    start, end = row.get("period_start"), row.get("period_end")
    reasons = []
    try:
        end_date = date.fromisoformat(end) if end else None
        start_date = date.fromisoformat(start) if start else None
        if (end_date and end_date.isoformat() != end) or (start_date and start_date.isoformat() != start):
            raise ValueError()
        if start_date and end_date and start_date > end_date:
            raise ValueError()
    except (ValueError, TypeError):
        start_date = end_date = None
        reasons.append("MALFORMED_EXPLICIT_PERIOD_BOUNDS")
    if not match:
        reasons.append("UNKNOWN_OR_MALFORMED_NATIVE_PERIOD_LABEL")
    if not end_date or (not instant and not start_date):
        reasons.append("EXPLICIT_REPORTING_BOUNDS_UNPROVEN")
    cumulative = ("STANDALONE" if semantic == "STANDALONE_QUARTER" or row.get("cumulative_state") == "period_only" else
                  "CUMULATIVE" if semantic in ("YTD_CUMULATIVE_INTERIM", "ANNUAL") or row.get("cumulative_state") == "cumulative" or row.get("period_type") in ("half_year", "nine_month", "annual") else "UNKNOWN")
    calendar_basis = row.get("fiscal_calendar") if row.get("fiscal_calendar") in ("CALENDAR_YEAR", "NON_CALENDAR_YEAR") else "UNKNOWN"
    if calendar_basis == "UNKNOWN":
        reasons.append("FISCAL_CALENDAR_NOT_PROVEN_BY_LABEL")
    if not instant and cumulative == "UNKNOWN":
        reasons.append("FLOW_DURATION_NOT_PROVEN_BY_QUARTER_LABEL")
    if not instant and not flow:
        reasons.append("STATEMENT_TIME_BASIS_UNPROVEN")
    if mixed:
        reasons.append("MIXED_STATEMENT_TIMING_BASIS")
    duration = (end_date - start_date).days + 1 if flow and not instant and start_date and end_date else None
    ranges = {"QUARTER": (80, 100), "HALF_YEAR": (170, 190), "NINE_MONTH": (260, 285), "ANNUAL": (350, 380)}
    if duration is not None and family in ranges and not ranges[family][0] <= duration <= ranges[family][1]:
        reasons.append("NATIVE_PERIOD_FAMILY_DURATION_CONFLICT")
    return {"native_label": label, "period_family": family,
            "fiscal_year_label": match[1] if match else None, "fiscal_calendar": calendar_basis,
            "period_start": start_date.isoformat() if start_date else None,
            "period_end": end_date.isoformat() if end_date else None,
            "time_basis": "MIXED" if mixed else "INSTANT" if instant else "DURATION" if flow else "UNKNOWN",
            "duration_days": duration,
            "cumulative_basis": "NOT_APPLICABLE_INSTANT" if instant else cumulative,
            "statement_family": row.get("statement_family"), "statement_scope": row.get("statement_scope", row.get("scope")),
            "currency": row.get("currency", row.get("reported_currency")),
            "unit_scale": row.get("unit_scale", row.get("reported_scale", row.get("scale"))),
            "canonical_metric": row.get("canonical_metric"), "reason_codes": sorted(reasons)}


def reporting_period_relation(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    """End-date ordering is distinct from duration compatibility and native label order."""
    left, right = baseline.get("period_end"), candidate.get("period_end")
    if left and right:
        return "NEWER_EXPLICIT_END" if right > left else "OLDER_EXPLICIT_END" if right < left else "SAME_EXPLICIT_END"
    # A native label progression can be shown, but is never a proved calendar comparison.
    order = {"Q1": 1, "Q2": 2, "H1": 2, "Q3": 3, "9M": 3, "Q4": 4, "FY": 4}
    pattern = r"(\d{4})(?:-(Q[1-4]|H1|9M|FY))?"
    a, b = re.fullmatch(pattern, str(baseline.get("native_label") or "")), re.fullmatch(pattern, str(candidate.get("native_label") or ""))
    if a and b and a[1] == b[1]:
        x, y = order[a[2] or "FY"], order[b[2] or "FY"]
        return "NATIVE_LABEL_PROGRESS_CALENDAR_UNPROVEN" if y > x else "SAME_NATIVE_PERIOD_POSITION" if y == x else "OLDER_NATIVE_PERIOD_POSITION"
    return "PERIOD_ORDER_UNRESOLVED"


def assert_artifact_session_not_future(session: str | None, *, decision_session: str, label: str) -> None:
    """Fail closed when a whole source artifact is later than the decision session."""
    if _session(session) and session > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{label}:{session}>{decision_session}")


def classify_freshness(
    *,
    axis: str,
    contract: Mapping[str, Any],
    decision_session: str,
    source_session: str | None,
    known_at: str | None = None,
    source_period: str | None = None,
    source_artifact_identity: str | None = None,
) -> dict[str, Any]:
    """Return the deterministic freshness envelope for one opportunity axis."""
    if not isinstance(decision_session, str) or not decision_session:
        raise ValueError("DECISION_SESSION_REQUIRED")
    source = _session(source_session)
    if source is not None and source > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{axis}:{source}>{decision_session}")
    if contract.get("period_based") and source is not None and source_period:
        clock = separate_financial_clock(
            financial_period=source_period, financial_period_end=None, price_as_of=source,
            knowledge_available_at=known_at, decision_session=decision_session,
            maximum_completed_quarter_lag=4,
        )
        # Unresolved labels such as 2026-H1 keep the session contract. A resolved
        # annual or quarter label is aged on its own and cannot inherit CURRENT
        # from the price session.
        if clock["resolved_quarter_label"]:
            state = clock["freshness_status"]
            compatibility = COMPATIBLE if state != UNAVAILABLE else MISSING
            envelope = _envelope(axis, decision_session, source, known_at, source_period,
                                 source_artifact_identity, state, compatibility, contract)
            envelope.update({
                "financial_freshness": state,
                "price_as_of": source,
                "knowledge_available_at": known_at,
                "financial_period_end": clock["financial_period_end"],
                "price_session_does_not_set_financial_freshness": True,
                "reason_codes": list(clock["reason_codes"]),
            })
            return envelope
    if source is None:
        if contract.get("period_based") and source_period:
            state, compatibility = STALE_BUT_RESEARCH_USABLE, COMPATIBLE
        else:
            state, compatibility = UNAVAILABLE, MISSING
        return _envelope(axis, decision_session, source, known_at, source_period,
                         source_artifact_identity, state, compatibility, contract)
    if source > decision_session:
        raise FutureInformationError(f"FUTURE_INFORMATION_PROHIBITED:{axis}:{source}>{decision_session}")
    if source == decision_session:
        state, compatibility = CURRENT, COMPATIBLE
    elif contract["older_usable"]:
        state, compatibility = STALE_BUT_RESEARCH_USABLE, COMPATIBLE
    else:
        state, compatibility = STALE_NOT_USABLE_FOR_THIS_AXIS, INCOMPATIBLE_STALE
    return _envelope(axis, decision_session, source, known_at, source_period,
                     source_artifact_identity, state, compatibility, contract)
