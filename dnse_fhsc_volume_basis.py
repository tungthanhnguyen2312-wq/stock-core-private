"""Deterministic, authority-neutral DNSE/FHSC closed-session volume checks.

This contract deliberately keeps DNSE's ``/price/ohlc`` ``v`` field generic
until exact, retained comparisons against FHSC's explicitly decomposed trading
history establish a bounded empirical mapping.  It never enables liquidity,
turnover, sizing, or any price authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "dnse_fhsc_volume_basis_qualification/v1"
MATCHED_VOLUME = "MATCHED_VOLUME"
PUT_THROUGH_VOLUME = "PUT_THROUGH_VOLUME"
TOTAL_VOLUME = "TOTAL_VOLUME"
GENERIC_VOLUME_UNKNOWN_BASIS = "GENERIC_VOLUME_UNKNOWN_BASIS"

HISTORY_EQUALS_MATCHED = "HISTORY_EQUALS_MATCHED"
HISTORY_EQUALS_TOTAL = "HISTORY_EQUALS_TOTAL"
HISTORY_EQUALS_PUT_THROUGH = "HISTORY_EQUALS_PUT_THROUGH"
HISTORY_EQUALS_NONE = "HISTORY_EQUALS_NONE"
NOT_COMPARABLE = "NOT_COMPARABLE"

DNSE_EQUALS_MATCHED = "DNSE_EQUALS_MATCHED"
DNSE_EQUALS_TOTAL = "DNSE_EQUALS_TOTAL"
DNSE_EQUALS_PUT_THROUGH = "DNSE_EQUALS_PUT_THROUGH"
DNSE_EQUALS_NONE = "DNSE_EQUALS_NONE"
BASIS_UNRESOLVED = "BASIS_UNRESOLVED"

FHSC_HISTORY_VOLUME_MATCHED = "FHSC_HISTORY_VOLUME_MATCHED"
FHSC_HISTORY_VOLUME_TOTAL = "FHSC_HISTORY_VOLUME_TOTAL"
FHSC_HISTORY_VOLUME_OTHER = "FHSC_HISTORY_VOLUME_OTHER"
FHSC_HISTORY_VOLUME_NON_INVARIANT = "FHSC_HISTORY_VOLUME_NON_INVARIANT"
FHSC_HISTORY_VOLUME_UNRESOLVED = "FHSC_HISTORY_VOLUME_UNRESOLVED"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Return the deterministic identity without self-referential fields."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"dnse_fhsc_volume_basis_qualification:{digest}"}


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_dnse_ohlc_volume(raw_bytes: bytes, *, instrument: str, session: str) -> dict[str, Any]:
    """Extract exactly one raw ``v`` observation from a retained DNSE response."""
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RAW_BYTES_NOT_JSON", "raw_sha256": digest}
    if not isinstance(payload, Mapping):
        return {"parse_status": "PAYLOAD_NOT_OBJECT", "raw_sha256": digest}
    times, volumes = payload.get("t"), payload.get("v")
    if not isinstance(times, list) or not isinstance(volumes, list) or len(times) != len(volumes):
        return {"parse_status": "OHLC_VOLUME_ARRAYS_ABSENT_OR_MISMATCHED", "raw_sha256": digest}
    matches: list[int] = []
    for epoch, volume in zip(times, volumes):
        if not _is_integer(epoch) or not _is_integer(volume):
            return {"parse_status": "OHLC_VOLUME_NOT_NONNEGATIVE_INTEGER", "raw_sha256": digest}
        try:
            row_session = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(
                timezone.utc
            ).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return {"parse_status": "OHLC_TIMESTAMP_INVALID", "raw_sha256": digest}
        # DNSE raw epochs are retained as +07:00 session anchors; a UTC conversion
        # would move them backward.  The one-day qualification provenance supplies
        # the authoritative requested session, so select its unique raw bar below.
        matches.append(volume)
    if len(matches) != 1:
        return {"parse_status": "EXACT_SESSION_MISSING_OR_AMBIGUOUS", "raw_sha256": digest, "row_count": len(matches)}
    return {
        "parse_status": "PARSED", "instrument": instrument.upper(), "session": session,
        "raw_value": matches[0], "numeric_representation": "INTEGER", "field": "v",
        "basis": GENERIC_VOLUME_UNKNOWN_BASIS, "raw_sha256": digest,
    }


def parse_dnse_ohlc_volume_history(raw_bytes: bytes, *, instrument: str) -> dict[str, Any]:
    """Extract every integer ``v`` row, preserving DNSE's local-session epoch basis."""
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RAW_BYTES_NOT_JSON", "raw_sha256": digest}
    if not isinstance(payload, Mapping):
        return {"parse_status": "PAYLOAD_NOT_OBJECT", "raw_sha256": digest}
    times, volumes = payload.get("t"), payload.get("v")
    if not isinstance(times, list) or not isinstance(volumes, list) or len(times) != len(volumes):
        return {"parse_status": "OHLC_VOLUME_ARRAYS_ABSENT_OR_MISMATCHED", "raw_sha256": digest}
    vn_tz = timezone(timedelta(hours=7))
    rows: list[dict[str, Any]] = []
    for epoch, volume in zip(times, volumes):
        if not _is_integer(epoch) or not _is_integer(volume):
            return {"parse_status": "OHLC_VOLUME_NOT_NONNEGATIVE_INTEGER", "raw_sha256": digest}
        try:
            session = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(vn_tz).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return {"parse_status": "OHLC_TIMESTAMP_INVALID", "raw_sha256": digest}
        rows.append({"instrument": instrument.upper(), "session": session, "raw_value": volume,
                     "numeric_representation": "INTEGER", "field": "v", "basis": GENERIC_VOLUME_UNKNOWN_BASIS,
                     "raw_sha256": digest})
    return {"parse_status": "PARSED", "instrument": instrument.upper(), "rows": rows, "raw_sha256": digest}


def parse_fhsc_trading_history(raw_bytes: bytes, *, instrument: str) -> dict[str, Any]:
    """Parse retained FHSC history rows; never infer an omitted decomposition."""
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RAW_BYTES_NOT_JSON", "raw_sha256": digest}
    outer = payload.get("data") if isinstance(payload, Mapping) else None
    rows = outer.get("data") if isinstance(outer, Mapping) else None
    if not isinstance(rows, list):
        return {"parse_status": "DOCUMENTED_TRADING_HISTORY_ROWS_ABSENT", "raw_sha256": digest}
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("date"), str):
            continue
        amounts = {name: row.get(name) for name in ("matched", "put_through", "total")}
        if not all(isinstance(amount, Mapping) and _is_integer(amount.get("volume")) for amount in amounts.values()):
            parsed.append({"session": row["date"], "parse_status": "TRADING_DECOMPOSITION_ABSENT_OR_INVALID"})
            continue
        matched, put_through, total = (amounts[name]["volume"] for name in ("matched", "put_through", "total"))
        parsed.append({
            "session": row["date"], "parse_status": "PARSED", "instrument": instrument.upper(),
            "matched_volume": matched, "put_through_volume": put_through, "total_volume": total,
            "numeric_representation": "INTEGER",
            "retained_arithmetic_identity": matched + put_through == total,
        })
    return {"parse_status": "PARSED", "instrument": instrument.upper(), "rows": parsed, "raw_sha256": digest}


def _single_identity(value: int, *, matched: int, put_through: int, total: int, prefix: str) -> str:
    """Classify a value only when one explicitly named identity is unique."""
    identities = [
        ("MATCHED", matched), ("PUT_THROUGH", put_through), ("TOTAL", total),
    ]
    matches = [name for name, candidate in identities if value == candidate]
    if len(matches) != 1:
        return NOT_COMPARABLE if len(matches) > 1 else f"{prefix}_NONE"
    return f"{prefix}_{matches[0]}"


def classify_fhsc_history(history_volume: Any, trading: Mapping[str, Any], *, documented_identity: bool) -> str:
    if not documented_identity or not _is_integer(history_volume) or trading.get("parse_status") != "PARSED":
        return NOT_COMPARABLE
    if not trading.get("retained_arithmetic_identity"):
        return NOT_COMPARABLE
    return _single_identity(int(history_volume), matched=trading["matched_volume"],
                            put_through=trading["put_through_volume"], total=trading["total_volume"],
                            prefix="HISTORY_EQUALS")


def classify_dnse_volume(dnse_volume: Any, trading: Mapping[str, Any], *, documented_identity: bool) -> str:
    if not documented_identity or not _is_integer(dnse_volume) or trading.get("parse_status") != "PARSED":
        return BASIS_UNRESOLVED
    if not trading.get("retained_arithmetic_identity"):
        return BASIS_UNRESOLVED
    result = _single_identity(int(dnse_volume), matched=trading["matched_volume"],
                              put_through=trading["put_through_volume"], total=trading["total_volume"],
                              prefix="DNSE_EQUALS")
    return BASIS_UNRESOLVED if result == NOT_COMPARABLE else result


def _basis_verdict(values: Iterable[str], *, prefix: str, required_observations: int) -> str:
    ordered = list(values)
    if len(ordered) < required_observations or any(value in {NOT_COMPARABLE, BASIS_UNRESOLVED} for value in ordered):
        return FHSC_HISTORY_VOLUME_UNRESOLVED if prefix == "HISTORY_EQUALS" else "NO_VOLUME_BASIS_QUALIFIED"
    matches = {value.removeprefix(prefix + "_") for value in ordered}
    if len(matches) != 1:
        return FHSC_HISTORY_VOLUME_NON_INVARIANT if prefix == "HISTORY_EQUALS" else "NO_VOLUME_BASIS_QUALIFIED"
    identity = next(iter(matches))
    if prefix == "HISTORY_EQUALS":
        return {
            "MATCHED": FHSC_HISTORY_VOLUME_MATCHED,
            "TOTAL": FHSC_HISTORY_VOLUME_TOTAL,
            "PUT_THROUGH": FHSC_HISTORY_VOLUME_OTHER,
        }.get(identity, FHSC_HISTORY_VOLUME_OTHER)
    return {
        "MATCHED": "DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL",
        "TOTAL": "DNSE_OHLC_VOLUME_TOTAL_EMPIRICAL",
        "PUT_THROUGH": "DNSE_OHLC_VOLUME_PUT_THROUGH_EMPIRICAL",
    }.get(identity, "NO_VOLUME_BASIS_QUALIFIED")


def reconcile_volume_rows(
    dnse_rows: Iterable[Mapping[str, Any]], fhsc_history_rows: Iterable[Mapping[str, Any]],
    fhsc_trading_rows: Iterable[Mapping[str, Any]], *, documented_identity: bool,
    required_observations: int = 3,
) -> dict[str, Any]:
    """Join exact ticker/session rows and issue only bounded empirical verdicts."""
    def keyed(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        return {(str(row.get("instrument", "")).upper(), str(row.get("session", ""))): dict(row) for row in rows}
    dnse, history, trading = keyed(dnse_rows), keyed(fhsc_history_rows), keyed(fhsc_trading_rows)
    keys = sorted(set(dnse) | set(history) | set(trading))
    matrix: list[dict[str, Any]] = []
    for key in keys:
        d, h, t = dnse.get(key), history.get(key), trading.get(key)
        if not d or not h or not t:
            matrix.append({"ticker": key[0], "session": key[1], "missing_observation": True,
                           "fhsc_internal_history_verdict": NOT_COMPARABLE,
                           "dnse_cross_source_verdict": BASIS_UNRESOLVED})
            continue
        history_verdict = classify_fhsc_history(h.get("volume"), t, documented_identity=documented_identity)
        dnse_verdict = classify_dnse_volume(d.get("raw_value"), t, documented_identity=documented_identity)
        matrix.append({
            "ticker": key[0], "session": key[1], "dnse_generic_volume": d.get("raw_value"),
            "fhsc_history_volume": h.get("volume"), "fhsc_matched_volume": t.get("matched_volume"),
            "fhsc_put_through_volume": t.get("put_through_volume"), "fhsc_total_volume": t.get("total_volume"),
            "fhsc_identity_documented_and_retained_exact": bool(documented_identity and t.get("retained_arithmetic_identity")),
            "fhsc_internal_history_verdict": history_verdict, "dnse_cross_source_verdict": dnse_verdict,
            "missing_observation": False,
        })
    complete = [row for row in matrix if not row["missing_observation"]]
    discriminating = [
        row for row in complete
        if row["fhsc_put_through_volume"] > 0
    ]
    required_ticker_coverage = len({row["ticker"] for row in discriminating}) >= required_observations
    history_basis = _basis_verdict(
        (row["fhsc_internal_history_verdict"] for row in discriminating), prefix="HISTORY_EQUALS", required_observations=required_observations)
    dnse_basis = _basis_verdict(
        (row["dnse_cross_source_verdict"] for row in discriminating), prefix="DNSE_EQUALS", required_observations=required_observations)
    if not required_ticker_coverage:
        history_basis, dnse_basis = FHSC_HISTORY_VOLUME_UNRESOLVED, "NO_VOLUME_BASIS_QUALIFIED"
    return {
        "matrix": matrix,
        "fhsc_history_volume_basis": history_basis,
        "dnse_volume_basis_candidate": dnse_basis,
        "discriminating_observation_count": len(discriminating),
        "discriminating_tickers": sorted({row["ticker"] for row in discriminating}),
        "zero_put_through_non_discriminating_consistency_count": len(complete) - len(discriminating),
        "summary_counts": {
            "dnse_equals_matched": sum(row.get("dnse_cross_source_verdict") == DNSE_EQUALS_MATCHED for row in matrix),
            "dnse_equals_total": sum(row.get("dnse_cross_source_verdict") == DNSE_EQUALS_TOTAL for row in matrix),
            "dnse_equals_put_through": sum(row.get("dnse_cross_source_verdict") == DNSE_EQUALS_PUT_THROUGH for row in matrix),
            "dnse_no_match": sum(row.get("dnse_cross_source_verdict") == DNSE_EQUALS_NONE for row in matrix),
            "not_comparable": sum(row.get("fhsc_internal_history_verdict") == NOT_COMPARABLE for row in matrix),
            "missing_observations": sum(bool(row.get("missing_observation")) for row in matrix),
        },
        "authority_effect": "NONE",
        "liquidity_authority": False,
        "position_sizing_safe": False,
    }
