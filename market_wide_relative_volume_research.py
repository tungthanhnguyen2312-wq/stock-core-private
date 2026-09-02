"""Deterministic, retained-only DNSE relative-volume research.

This module intentionally emits only dimensionless comparisons of one stable
provider field.  It never exposes the native magnitude as shares/lots or
derives monetary traded value, liquidity, execution capacity, or sizing.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import date
from statistics import median
from typing import Any, Mapping


CONTRACT_VERSION = "market_wide_relative_volume_research/v1"
MILESTONE = "MARKET_WIDE_RELATIVE_VOLUME_RESEARCH_V1"
FITNESS = "RESEARCH_DESCRIPTIVE_ONLY"
PROVIDER = "DNSE"
SOURCE_FIELD = "DNSE_OHLC.volume"
SOURCE_REPRESENTATIONS = frozenset({"DNSE_PROVIDER_NATIVE_RAW", "identity_provider_numeric_ohlc/v1"})

_LIMITATIONS = [
    "native_ohlc_volume_unit_unknown",
    "absolute_shares_or_lots_unknown",
    "monetary_traded_value_not_derived",
    "not_adv_or_adtv",
    "execution_capacity_blocked",
    "position_sizing_blocked",
    "descriptive_explanatory_feature_only_not_an_investment_ranking",
]


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_relative_volume_research:{digest}"}


def _valid_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _valid_volume(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _observation_status(row: Mapping[str, Any]) -> tuple[str | None, float | None, str | None]:
    session = _valid_date(row.get("session"))
    if session is None:
        return None, None, "SESSION_INVALID"
    if row.get("provider") != PROVIDER:
        return session, None, "PROVIDER_MISMATCH"
    field_identity = row.get("field_identity")
    field = field_identity.get("volume") if isinstance(field_identity, Mapping) else None
    if field != SOURCE_FIELD:
        return session, None, "NATIVE_FIELD_MISMATCH"
    representation = row.get("field_representation")
    # The retained P3F9B OHLC rows carry the native representation as a
    # record-wide transformation identity; small synthetic/direct callers may
    # carry it under the volume field instead.  Both forms identify the same
    # no-transform provider representation, never an absolute unit.
    value_representation = representation.get("volume") if isinstance(representation, Mapping) else None
    if value_representation is None:
        value_representation = row.get("transformation_identity")
    if value_representation not in SOURCE_REPRESENTATIONS:
        return session, None, "REPRESENTATION_MISMATCH"
    volume = _valid_volume(row.get("volume"))
    if volume is None:
        return session, None, "VOLUME_MISSING_OR_INVALID"
    return session, volume, None


def _ticker_record(ticker: str, observations: Any, session: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ticker": ticker,
        "session": session,
        "provider": PROVIDER,
        "source_field": SOURCE_FIELD,
        "fitness": FITNESS,
        "relative_volume_percentile": None,
        "volume_acceleration_ratio": None,
        "percentile_status": "UNAVAILABLE",
        "acceleration_status": "UNAVAILABLE",
        "limitations": list(_LIMITATIONS),
        "is_actionable": False,
    }
    if not isinstance(observations, list):
        result.update(status="UNAVAILABLE", reason="OBSERVATIONS_MISSING")
        return result
    valid_rows: dict[str, float] = {}
    future_rows = 0
    for row in observations:
        if not isinstance(row, Mapping):
            result.update(status="UNAVAILABLE", reason="OBSERVATION_MALFORMED")
            return result
        observed_session, value, reason = _observation_status(row)
        if observed_session is None:
            result.update(status="UNAVAILABLE", reason=reason)
            return result
        if observed_session > session:
            future_rows += 1
            continue
        if reason is not None:
            if observed_session == session:
                result.update(status="UNAVAILABLE", reason=reason)
                return result
            continue
        if observed_session in valid_rows:
            result.update(status="UNAVAILABLE", reason="DUPLICATE_SESSION_ROW")
            return result
        valid_rows[observed_session] = value  # type: ignore[assignment]
    if future_rows:
        result.update(status="BLOCKED", reason="FUTURE_SESSION_ROW_PROHIBITED", future_session_rows=future_rows)
        return result
    current = valid_rows.get(session)
    if current is None:
        result.update(status="UNAVAILABLE", reason="CURRENT_VOLUME_UNAVAILABLE")
        return result
    result.update(_percentile_candidate=True, _current_volume=current, percentile_status="PENDING_COHORT")
    prior_sessions = sorted((day for day in valid_rows if day < session), reverse=True)[:20]
    result["valid_prior_completed_session_count"] = len(prior_sessions)
    if len(prior_sessions) != 20:
        result.update(acceleration_status="UNAVAILABLE_INSUFFICIENT_HISTORY", status="PARTIAL")
        return result
    baseline = [valid_rows[day] for day in prior_sessions]
    baseline_median = float(median(baseline))
    if baseline_median == 0:
        result.update(acceleration_status="UNAVAILABLE_ZERO_BASELINE", status="PARTIAL")
        return result
    result.update(
        volume_acceleration_ratio=current / baseline_median,
        acceleration_status="READY",
        status="READY",
    )
    return result


def build_artifact(*, candidates: list[str], records: Mapping[str, Mapping[str, Any]], session: str, requested_at: str) -> dict[str, Any]:
    """Build a full-universe, retained-session artifact with deterministic tie percentiles."""
    target_session = _valid_date(session)
    if target_session is None:
        raise ValueError("SESSION_INVALID")
    ticker_records = {
        ticker: _ticker_record(ticker, records.get(ticker, {}).get("observations"), target_session)
        for ticker in sorted(set(candidates))
    }
    eligible = [row for row in ticker_records.values() if row.get("_percentile_candidate")]
    denominator = len(eligible)
    values = [row["_current_volume"] for row in eligible]
    for row in eligible:
        current = row.pop("_current_volume")
        below = sum(value < current for value in values)
        equal = sum(value == current for value in values)
        percentile = (below + 0.5 * equal) / denominator
        row.update(
            relative_volume_percentile=percentile,
            percentile_status="READY",
            cohort_denominator=denominator,
        )
    for row in ticker_records.values():
        row.pop("_current_volume", None)
        row.pop("_percentile_candidate", None)
        row.setdefault("cohort_denominator", denominator)
    coverage = {
        "universe_denominator": len(ticker_records),
        "current_volume_available": denominator,
        "relative_volume_percentile_ready": sum(row["percentile_status"] == "READY" for row in ticker_records.values()),
        "relative_volume_percentile_unavailable": sum(row["percentile_status"] != "READY" for row in ticker_records.values()),
        "acceleration_20d_ready": sum(row["acceleration_status"] == "READY" for row in ticker_records.values()),
        "acceleration_insufficient_history": sum(row["acceleration_status"] == "UNAVAILABLE_INSUFFICIENT_HISTORY" for row in ticker_records.values()),
        "acceleration_zero_baseline": sum(row["acceleration_status"] == "UNAVAILABLE_ZERO_BASELINE" for row in ticker_records.values()),
        "future_session_violations": sum(row.get("reason") == "FUTURE_SESSION_ROW_PROHIBITED" for row in ticker_records.values()),
        "status_counts": dict(sorted(Counter(row["status"] for row in ticker_records.values()).items())),
    }
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "resolved_completed_session": target_session,
        "universe": {"canonical_candidate_count": len(ticker_records), "authority": "retained_governed_active_equity_universe"},
        "coverage": coverage,
        "records": ticker_records,
        "authority_boundary": {
            "RELATIVE_VOLUME_RESEARCH": FITNESS,
            "ABSOLUTE_VOLUME_UNIT": "UNKNOWN",
            "ABSOLUTE_TRADED_VALUE": "NOT_IMPLEMENTED",
            "ADV_ADTV": "NOT_IMPLEMENTED",
            "EXECUTION_CAPACITY": "STILL_BLOCKED",
            "POSITION_SIZING": "BLOCKED",
            "TACTICAL_DECISION_EFFECT": "NONE",
            "STANCE_EFFECT": "NONE",
            "is_actionable": False,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact
