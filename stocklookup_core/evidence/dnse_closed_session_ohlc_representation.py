"""Uniform, provenance-bearing DNSE closed-session OHLC representation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping


CONTRACT_VERSION = "dnse_closed_session_ohlc_representation/v1"
FIELDS = ("open", "high", "low", "close")
VN_TZ = timezone(timedelta(hours=7))
SOURCE_UNIT_UNDOCUMENTED = "SOURCE_PRICE_UNIT_UNDOCUMENTED"
UNIFORM_REPRESENTATION_UNIT_UNDOCUMENTED = "PROVIDER_NUMERIC_REPRESENTATION_UNIT_UNDOCUMENTED"
IDENTITY_TRANSFORMATION = "identity_provider_numeric_ohlc/v1"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def session_from_epoch(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(VN_TZ).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def parse_raw_ohlc_bytes(raw_bytes: bytes, *, instrument: str, session: str) -> dict[str, Any]:
    """Parse a SHA-verifiable raw DNSE OHLC payload without field transforms."""
    digest = sha256_bytes(raw_bytes)
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RAW_BYTES_NOT_JSON", "raw_sha256": digest}
    if not isinstance(payload, Mapping):
        return {"parse_status": "PAYLOAD_NOT_OBJECT", "raw_sha256": digest}
    arrays = {key: payload.get(key) for key in ("t", "o", "h", "l", "c", "v")}
    if any(not isinstance(value, list) for value in arrays.values()):
        return {"parse_status": "OHLC_ARRAYS_ABSENT", "raw_sha256": digest}
    if len({len(value) for value in arrays.values()}) != 1:
        return {"parse_status": "OHLC_ARRAY_LENGTH_MISMATCH", "raw_sha256": digest}
    matches = []
    for index, epoch in enumerate(arrays["t"]):
        if session_from_epoch(epoch) != session:
            continue
        values = {"open": arrays["o"][index], "high": arrays["h"][index], "low": arrays["l"][index], "close": arrays["c"][index]}
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values.values()):
            return {"parse_status": "OHLC_VALUE_NOT_NUMERIC", "raw_sha256": digest}
        matches.append(values)
    if len(matches) != 1:
        return {"parse_status": "EXACT_SESSION_MISSING" if not matches else "EXACT_SESSION_AMBIGUOUS", "raw_sha256": digest}
    return {"parse_status": "PARSED", "raw_sha256": digest, "instrument": instrument.upper(), "session": session,
            "raw_values": matches[0], "source_unit": SOURCE_UNIT_UNDOCUMENTED}


def uniform_anchor(parsed: Mapping[str, Any], *, source: Mapping[str, Any]) -> dict[str, Any]:
    """Build an identity-only anchor; numeric uniformity is not unit authority."""
    if parsed.get("parse_status") != "PARSED":
        return {"status": "EXCLUDED", "reason": parsed.get("parse_status")}
    values = parsed["raw_values"]
    fields = {
        field: {
            "raw_numeric_value": values[field],
            "raw_source_unit": parsed["source_unit"],
            "parsed_numeric_value": values[field],
            "normalized_numeric_value": values[field],
            "normalized_unit": UNIFORM_REPRESENTATION_UNIT_UNDOCUMENTED,
            "transformation_identity": IDENTITY_TRANSFORMATION,
        }
        for field in FIELDS
    }
    return {
        "status": "UNIFORM_REPRESENTATION_READY",
        "contract_version": CONTRACT_VERSION,
        "instrument": parsed["instrument"], "session": parsed["session"],
        "fields": fields, "field_representation": {field: IDENTITY_TRANSFORMATION for field in FIELDS},
        "uniform_representation_gate": "PASS",
        "unit_verdict": "EMPIRICALLY_UNIFORM_REPRESENTATION_UNIT_UNDOCUMENTED",
        "source_evidence": dict(source),
        "authority_effect": "NONE",
    }
