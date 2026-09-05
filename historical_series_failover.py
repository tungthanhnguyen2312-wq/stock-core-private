"""Feature-safe Current-Research historical-series failover.

This is intentionally a small extension of the existing technical-history recovery
contract, not a second history store or a blended OHLC engine.  Each provider keeps an
independently attributable series.  A consumer receives exactly one selected series only
after its target-session close agrees with the resolved exact-session snapshot.

The contract is useful for close-only Current Research (structure and momentum).  It never
promotes a provider history to RAW_AS_TRADED or PIT, and it deliberately leaves volume,
OHLC-geometry, liquidity, and execution uses blocked unless their own fitness is proven.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from datetime import date, timedelta
from typing import Any, Callable, Mapping, Sequence


CONTRACT_VERSION = "historical_series_failover/v1"
PROVIDER_INTERFACE = {
    "DNSE": "dnse_openapi_rest_unversioned_2026",
    "KBS": "vnstock_quote_history/v4",
    "VCI": "vnstock_quote_history/v4",
}
PROVIDER_ENDPOINT = {
    "DNSE": "/price/ohlc",
    "KBS": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/history",
    "VCI": "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
}
HISTORICAL_CLOSE_SOURCE_ORDER = ("DNSE", "KBS", "VCI")
CLOSE_FEATURE_FAMILIES = frozenset({"TECHNICAL_CLOSE_HISTORY", "MOMENTUM", "TACTICAL_STRUCTURE"})
VOLUME_FEATURE_FAMILIES = frozenset({"TECHNICAL_VOLUME_HISTORY", "PARTICIPATION", "RELATIVE_VOLUME"})


class HistoricalSeriesFailoverError(ValueError):
    """Raised only for an invalid caller/contract shape, never a provider miss."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"series_sha256", "series_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"series_sha256": digest, "series_identity": f"historical_provider_series:{digest}"}


def _session(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _observations(rows: Sequence[Mapping[str, Any]], *, target_session: str) -> tuple[list[dict[str, Any]], list[str], str | None]:
    target = _session(target_session)
    if target is None:
        raise HistoricalSeriesFailoverError("TARGET_SESSION_INVALID")
    by_session: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        session = _session(row.get("session"))
        if session is None:
            return [], duplicates, "SESSION_INVALID"
        if session > target:
            return [], duplicates, "FUTURE_SESSION_ROW_PROHIBITED"
        if session in by_session:
            duplicates.append(session)
            continue
        close = _number(row.get("close"))
        if close is None:
            return [], duplicates, "CLOSE_MISSING_OR_INVALID"
        normalized = {"session": session, "close": close}
        for field in ("open", "high", "low", "volume"):
            value = _number(row.get(field))
            if value is not None:
                normalized[field] = value
        by_session[session] = normalized
    if duplicates:
        return [], sorted(duplicates), "DUPLICATE_SESSION_ROW"
    return [by_session[session] for session in sorted(by_session)], [], None


def build_provider_series(
    *, ticker: str, provider: str, target_session: str, requested_at: str,
    requested_start: str, requested_end: str, rows: Sequence[Mapping[str, Any]],
    retrieval_identity: str | None = None, provider_revision_observations: Sequence[Mapping[str, Any]] = (),
    request_attempts: int = 1, retry_count: int = 0, latency_seconds: float | None = None,
    provider_requested_end: str | None = None,
    native_representation: str | None = None, price_representation: str | None = None,
    price_basis: str = "CURRENT_RESEARCH_PROVIDER_REPORTED_ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED",
    volume_basis: str = "PROVIDER_NATIVE_VOLUME_SEMANTICS_UNQUALIFIED",
    status: str = "SUCCESS", reason: str | None = None,
) -> dict[str, Any]:
    """Retain one provider-native series and compute its local feature fitness.

    ``rows`` are deliberately never joined to another source here.  Their close values must be
    in the exact native representation used by the resolved snapshot for the target session;
    the selector below is responsible for proving that compatibility.
    """
    provider = str(provider).upper()
    if provider not in PROVIDER_INTERFACE:
        raise HistoricalSeriesFailoverError(f"UNKNOWN_HISTORICAL_PROVIDER:{provider}")
    if request_attempts < 0 or retry_count < 0:
        raise HistoricalSeriesFailoverError("REQUEST_ACCOUNTING_INVALID")
    observations, duplicates, invalid_reason = _observations(rows, target_session=target_session) if status == "SUCCESS" else ([], [], reason or "PROVIDER_UNAVAILABLE")
    terminal_reason = invalid_reason or reason
    target_row = next((row for row in observations if row["session"] == target_session), None)
    has_volume = bool(observations) and all("volume" in row for row in observations)
    close_ready = terminal_reason is None and target_row is not None and len(observations) >= 20
    volume_ready = close_ready and provider == "DNSE" and has_volume
    field_set = sorted({field for row in observations for field in row if field != "session"})
    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "ticker": str(ticker).upper(),
        "provider": provider,
        "provider_interface": PROVIDER_INTERFACE[provider],
        "provider_endpoint": PROVIDER_ENDPOINT[provider],
        "requested_at": requested_at,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "provider_requested_end": provider_requested_end or requested_end,
        "retrieval_identity": retrieval_identity,
        "retrieval_identity_hash": hashlib.sha256(_canonical_json(list(rows)).encode("utf-8")).hexdigest(),
        "request_accounting": {"request_attempts": request_attempts, "retry_count": retry_count, "latency_seconds": latency_seconds},
        "status": "READY" if close_ready else "BLOCKED",
        "reason": terminal_reason if not close_ready else None,
        "observed_session_set": [row["session"] for row in observations],
        "session_count": len(observations),
        "duplicates": duplicates,
        "missing_target_session": target_row is None,
        "ordering": "ASCENDING_STRICT" if observations else "UNAVAILABLE",
        "field_set": field_set,
        "native_representation": native_representation or f"{provider}_NATIVE_PROVIDER_HISTORY",
        "price_representation": price_representation or f"{provider}_NATIVE_SCALE",
        "price_basis": price_basis,
        "volume_basis": volume_basis,
        "provider_revision_observations": [dict(item) for item in provider_revision_observations],
        "observations": observations,
        "fitness": {
            "TECHNICAL_CLOSE_HISTORY": "READY" if close_ready else "BLOCKED",
            "TECHNICAL_VOLUME_HISTORY": "READY" if volume_ready else "BLOCKED",
            "OHLC_GEOMETRY": "BLOCKED",
            "MOMENTUM": "READY" if close_ready else "BLOCKED",
            "TACTICAL_STRUCTURE": "READY" if close_ready else "BLOCKED",
            "PARTICIPATION": "READY" if volume_ready else "BLOCKED",
            "PIT_BACKTEST": "BLOCKED",
            "EXECUTION_LIQUIDITY": "BLOCKED",
        },
        "limitations": [
            "CURRENT_RESEARCH_ONLY",
            "RAW_AS_TRADED_NOT_PROMOTED",
            "PIT_NOT_PROMOTED",
            "OHLC_GEOMETRY_NOT_QUALIFIED",
            "EXECUTION_LIQUIDITY_NOT_QUALIFIED",
        ],
        "authority_boundary": {
            "CURRENT_RESEARCH": "PROVIDER_REPORTED_FEATURE_SAFE_ONLY",
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "PIT": "BLOCKED",
            "LIQUIDITY_SIZING_EXECUTION": "BLOCKED",
        },
    }
    result.update(content_identity(result))
    return result


def series_target_close(series: Mapping[str, Any], target_session: str) -> float | None:
    for row in series.get("observations") or []:
        if isinstance(row, Mapping) and row.get("session") == target_session:
            return _number(row.get("close"))
    return None


def snapshot_target_close(snapshot_record: Mapping[str, Any] | None, target_session: str) -> float | None:
    if not isinstance(snapshot_record, Mapping):
        return None
    for row in snapshot_record.get("observations") or []:
        if isinstance(row, Mapping) and row.get("session") == target_session:
            return _number(row.get("close"))
    return None


def select_feature_safe_series(
    *, ticker: str, target_session: str, feature_family: str,
    snapshot_record: Mapping[str, Any] | None, provider_series: Mapping[str, Mapping[str, Any]],
    provider_order: Sequence[str] = HISTORICAL_CLOSE_SOURCE_ORDER,
) -> dict[str, Any]:
    """Choose exactly one complete, compatible provider series for one feature family.

    A clean provider miss stops an unnecessary next-provider request at acquisition time; this
    selector is deliberately stricter and only answers whether retained provider series are
    usable.  No fragments are ever spliced.
    """
    expected_close = snapshot_target_close(snapshot_record, target_session)
    if expected_close is None:
        return {"ticker": ticker, "target_session": target_session, "feature_family": feature_family,
                "selected_provider": None, "selected_series_identity": None, "history_depth": 0,
                "compatibility_with_exact_session": "BLOCKED", "fitness": "BLOCKED",
                "fallback_reason": None, "blocked_reason": "EXACT_SESSION_TARGET_CLOSE_MISSING"}
    attempted: list[dict[str, str]] = []
    for provider in provider_order:
        series = provider_series.get(provider)
        if not isinstance(series, Mapping):
            attempted.append({"provider": provider, "reason": "SERIES_NOT_RETAINED"})
            continue
        fitness = (series.get("fitness") or {}).get(feature_family)
        if fitness != "READY":
            attempted.append({"provider": provider, "reason": f"FITNESS_{fitness or 'UNAVAILABLE'}"})
            continue
        observed_close = series_target_close(series, target_session)
        if observed_close != expected_close:
            attempted.append({"provider": provider, "reason": "TARGET_SESSION_CLOSE_MISMATCH"})
            continue
        return {
            "ticker": ticker, "target_session": target_session, "feature_family": feature_family,
            "selected_provider": provider, "selected_series_identity": series.get("series_identity"),
            "history_depth": series.get("session_count", 0),
            "compatibility_with_exact_session": "EXACT_TARGET_CLOSE_MATCH",
            "fitness": "READY", "fallback_reason": None if provider == "DNSE" else f"DNSE_HISTORY_UNAVAILABLE_{provider}_FALLBACK",
            "blocked_reason": None, "attempted_providers": attempted,
        }
    return {
        "ticker": ticker, "target_session": target_session, "feature_family": feature_family,
        "selected_provider": None, "selected_series_identity": None, "history_depth": 0,
        "compatibility_with_exact_session": "INCOMPATIBLE_SERIES", "fitness": "BLOCKED",
        "fallback_reason": None, "blocked_reason": "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES",
        "attempted_providers": attempted,
    }


def recovery_record_from_selection(
    *, selection: Mapping[str, Any], provider_series: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Project a selected historical series into the existing recovery-record shape."""
    provider = selection.get("selected_provider")
    if not provider:
        return {
            "ticker": selection.get("ticker"), "state": "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK",
            "reason": selection.get("blocked_reason"), "selection": dict(selection), "attempted_provider_series": dict(provider_series),
        }
    series = provider_series[str(provider)]
    return {
        "ticker": selection.get("ticker"), "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY",
        "reason": None, "provider": provider, "provider_interface": series.get("provider_interface"),
        "endpoint": series.get("provider_endpoint"), "payload_sha256": series.get("retrieval_identity_hash"),
        "attempt_count": (series.get("request_accounting") or {}).get("request_attempts", 0),
        "observations": list(series.get("observations") or []), "selection": dict(selection),
        "historical_series": dict(series), "attempted_provider_series": dict(provider_series),
    }


def vnstock_provider_series(
    *, ticker: str, provider: str, target_session: str, requested_at: str,
    requested_start: str, requested_end: str, fetch: Callable[..., Any], latency_seconds: float | None = None,
) -> dict[str, Any]:
    """Adapt the existing VCI/KBS fetch primitive without a new provider adapter.

    ``fetch_single_source`` returns normalized VND values.  Its explicit source scale is reversed
    here to retain the provider-native representation that the exact-session projection exposes,
    so target-session compatibility is an equality check in one declared representation.
    """
    # KBS's retained quote-history adapter treats ``end`` as exclusive; VCI does not. Query
    # KBS through the next calendar date, retain the logical target end separately, and still
    # reject every returned row after the target session below.
    provider_request_end = requested_end
    if provider.upper() == "KBS":
        try:
            provider_request_end = (date.fromisoformat(requested_end) + timedelta(days=1)).isoformat()
        except ValueError as exc:
            raise HistoricalSeriesFailoverError("REQUESTED_END_INVALID") from exc
    began = time.monotonic()
    outcome = fetch(ticker, provider, requested_start, provider_request_end)
    observed_latency = latency_seconds if latency_seconds is not None else round(time.monotonic() - began, 3)
    accounting = {
        "request_attempts": int(getattr(outcome, "request_attempts", 0) or 0),
        "retry_count": int(getattr(outcome, "retry_count", 0) or 0),
    }
    if getattr(outcome, "status", None) != "success":
        status = "CLEAN_MISSING" if getattr(outcome, "status", None) == "empty" else "TRANSPORT_OR_PROVIDER_FAILURE"
        return build_provider_series(
            ticker=ticker, provider=provider, target_session=target_session, requested_at=requested_at,
            requested_start=requested_start, requested_end=requested_end, provider_requested_end=provider_request_end, rows=[], status=status,
            reason=(list(getattr(outcome, "errors", None) or []) or [status])[0], latency_seconds=observed_latency, **accounting,
        )
    frame = getattr(outcome, "data", None)
    if frame is None or not hasattr(frame, "iterrows"):
        return build_provider_series(
            ticker=ticker, provider=provider, target_session=target_session, requested_at=requested_at,
            requested_start=requested_start, requested_end=requested_end, provider_requested_end=provider_request_end, rows=[], status="MALFORMED",
            reason="VNSTOCK_NORMALIZED_FRAME_MISSING", latency_seconds=observed_latency, **accounting,
        )
    scale = getattr(frame, "attrs", {}).get("unit_scale", 1)
    if not isinstance(scale, (int, float)) or not scale:
        return build_provider_series(
            ticker=ticker, provider=provider, target_session=target_session, requested_at=requested_at,
            requested_start=requested_start, requested_end=requested_end, provider_requested_end=provider_request_end, rows=[], status="MALFORMED",
            reason="VNSTOCK_PROVIDER_SCALE_MISSING", latency_seconds=observed_latency, **accounting,
        )
    rows = []
    for _, row in frame.iterrows():
        native = {"session": str(row["date"])[:10], "volume": _number(row.get("volume"))}
        for field in ("open", "high", "low", "close"):
            value = _number(row.get(field))
            native[field] = (value / float(scale)) if value is not None else None
        rows.append(native)
    lineage = list(getattr(outcome, "lineage", None) or [])
    return build_provider_series(
        ticker=ticker, provider=provider, target_session=target_session, requested_at=requested_at,
        requested_start=requested_start, requested_end=requested_end, provider_requested_end=provider_request_end, rows=rows,
        retrieval_identity=hashlib.sha256(_canonical_json(lineage).encode("utf-8")).hexdigest(),
        native_representation=f"{provider}_NATIVE_SCALE", price_representation=f"{provider}_NATIVE_SCALE",
        volume_basis="VCI_KBS_VOLUME_FAMILY_NOT_COMPARABLE_TO_DNSE",
        latency_seconds=observed_latency, **accounting,
    )


def provider_fitness_matrix(provider_series: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Compact per-provider/feature report for operations review, with no new authority."""
    return {
        "contract_version": CONTRACT_VERSION,
        "providers": {
            provider: {
                "series_identity": series.get("series_identity"), "session_count": series.get("session_count"),
                "status": series.get("status"), "reason": series.get("reason"), "fitness": series.get("fitness"),
                "price_representation": series.get("price_representation"), "price_basis": series.get("price_basis"),
                "volume_basis": series.get("volume_basis"),
            }
            for provider, series in sorted(provider_series.items())
        },
        "authority_boundary": {"PIT_BACKTEST": "BLOCKED", "EXECUTION_LIQUIDITY": "BLOCKED", "RAW_AS_TRADED": "NOT_PROMOTED"},
    }


def provider_counts(records: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(
        str(record.get("provider")) for record in records.values()
        if record.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    ).items()))
