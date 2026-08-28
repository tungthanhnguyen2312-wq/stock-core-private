"""Append-only, non-authoritative DNSE closed-OHLC receipt observations.

This module is deliberately an EXPERIMENT/SHADOW-only retention contract.  It
does not qualify DNSE OHLC data, normalize prices, or make historical REST
responses look point-in-time safe.  A record means only that Stock Lookup saw
the exact non-secret WebSocket payload no later than its recorded receipt time.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from temporal_retention import capture_raw_receipt, project_retention_to_a1

SCHEMA_ID = "dnse.prospective_pit_observation.v1"
COLLECTOR_ID = "stocklookup.dnse_prospective_pit_shadow.v1"
AUTHORITY_STATE = "EXPERIMENT_SHADOW_ONLY"
OBSERVATIONS_FILENAME = "observations.jsonl"

_SENSITIVE_KEY_PARTS = (
    "token", "secret", "password", "passwd", "apikey", "api_key", "api-key",
    "authorization", "signature", "cookie", "credential", "otp", "x-api-key", "auth",
)


class ProspectivePitContractError(ValueError):
    """Raised before a record can be retained under this shadow contract."""


def validate_payload_correspondence(*, payload: Mapping[str, Any], expected_symbol: str,
                                    expected_resolution: str, expected_channel: str) -> None:
    """Fail closed unless a closed-bar payload matches this collector request.

    DNSE's observed ``bc`` payloads do not carry a channel field, so the
    subscription channel remains a request/collector assertion.  If a future
    payload supplies one, it must agree rather than silently changing that
    assertion.
    """
    if not isinstance(payload, Mapping):
        raise ProspectivePitContractError("payload_mapping_required")
    if payload.get("T") != "bc":
        raise ProspectivePitContractError("closed_message_type_required")
    if payload.get("symbol") != expected_symbol:
        raise ProspectivePitContractError("requested_symbol_mismatch")
    if payload.get("resolution") != expected_resolution:
        raise ProspectivePitContractError("requested_resolution_mismatch")
    if not expected_channel.startswith("ohlc_closed."):
        raise ProspectivePitContractError("expected_closed_ohlc_channel_required")
    if "channel" in payload and payload["channel"] != expected_channel:
        raise ProspectivePitContractError("requested_channel_mismatch")


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for all hashes and append-only record bytes."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ProspectivePitContractError("non_canonical_payload") from error


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_aware_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProspectivePitContractError("receipt_timestamp_timezone_required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_secret_fields(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if item and any(part in name.lower() for part in _SENSITIVE_KEY_PARTS):
                raise ProspectivePitContractError(f"secret_shaped_field_rejected:{path}.{name}")
            _reject_secret_fields(item, path=f"{path}.{name}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secret_fields(item, path=f"{path}[{index}]")


def _source_time(payload: Mapping[str, Any]) -> dict[str, Any]:
    # DNSE's published Ohlc model names `time` and `lastUpdated`.  Preserve
    # both exactly as supplied; neither is converted or replaced by receipt.
    if "time" in payload:
        start = payload["time"]
        status = "present_as_supplied"
    else:
        start = None
        status = "missing_from_payload"
    return {
        "candle_start_time": start,
        "candle_end_time": None,
        "source_event_time": payload.get("lastUpdated"),
        "trading_date": payload.get("tradingDate"),
        "trading_session_id": payload.get("tradingSessionId"),
        "source_time_status": status,
    }


def _logical_bar_identity(*, channel: str, message_type: str, payload: Mapping[str, Any],
                          source_time: Mapping[str, Any]) -> dict[str, Any] | None:
    # Without a provider-supplied candle start value we cannot honestly assert
    # two messages refer to the same bar.  They remain separately retained.
    if source_time["candle_start_time"] is None:
        return None
    return {
        "provider": "DNSE/Livespeed",
        "channel": channel,
        "message_type": message_type,
        "symbol": payload["symbol"],
        "resolution": payload["resolution"],
        "candle_start_time": source_time["candle_start_time"],
    }


def build_observation(*, payload: Mapping[str, Any], channel: str, message_type: str,
                      receipt_at: datetime, collector_execution_id: str,
                      source_transport: str = "websocket") -> dict[str, Any]:
    """Create one valid closed-OHLC observation without persisting it.

    REST input is categorically rejected so an historical response cannot be
    represented as a receipt-time WebSocket observation.
    """
    if source_transport != "websocket":
        raise ProspectivePitContractError("websocket_source_required")
    if message_type != "bc" or not channel.startswith("ohlc_closed."):
        raise ProspectivePitContractError("completed_ohlc_channel_required")
    if not isinstance(payload, Mapping):
        raise ProspectivePitContractError("payload_mapping_required")
    if payload.get("T") != message_type:
        raise ProspectivePitContractError("payload_message_type_mismatch")
    if "channel" in payload and payload["channel"] != channel:
        raise ProspectivePitContractError("payload_channel_mismatch")
    if not isinstance(collector_execution_id, str) or not collector_execution_id.strip():
        raise ProspectivePitContractError("collector_execution_id_required")
    _reject_secret_fields(payload)
    if not isinstance(payload.get("symbol"), str) or not payload["symbol"].strip():
        raise ProspectivePitContractError("symbol_required")
    if not isinstance(payload.get("resolution"), str) or not payload["resolution"].strip():
        raise ProspectivePitContractError("resolution_required")

    received_at_utc = _require_aware_utc(receipt_at)
    received_at_local = receipt_at.isoformat()
    copied_payload = json.loads(canonical_json(dict(payload)))
    source_time = _source_time(copied_payload)
    logical_identity = _logical_bar_identity(
        channel=channel, message_type=message_type, payload=copied_payload, source_time=source_time,
    )
    payload_hash = sha256_json(copied_payload)
    normalized_payload = {
        "symbol": copied_payload["symbol"],
        "resolution": copied_payload["resolution"],
        "time": copied_payload.get("time"),
        "lastUpdated": copied_payload.get("lastUpdated"),
        "open": copied_payload.get("open"),
        "high": copied_payload.get("high"),
        "low": copied_payload.get("low"),
        "close": copied_payload.get("close"),
        "volume": copied_payload.get("volume"),
        "type": copied_payload.get("type"),
    }
    observation_id = sha256_json({
        "logical_bar_identity": logical_identity,
        "payload_sha256": payload_hash,
        "first_observed_at_utc": received_at_utc,
    })
    temporal_retention = capture_raw_receipt(
        data=canonical_json(copied_payload).encode("utf-8"),
        raw_received_at=receipt_at,
        source_identity=f"{channel}:{message_type}",
        provider_or_source="DNSE/Livespeed",
        acquisition_method="DNSE_WEBSOCKET_CLOSED_OHLC_V1",
        provider_event_at=source_time["source_event_time"],
        content_type="application/json",
        warnings=["EXPERIMENT_SHADOW_ONLY"],
    )
    return {
        "schema_id": SCHEMA_ID,
        "collector_id": COLLECTOR_ID,
        "collector_execution_id": collector_execution_id,
        "authority_state": AUTHORITY_STATE,
        "observation_semantics": (
            "exact DNSE payload observed by Stock Lookup no later than recorded receipt time; "
            "not raw-as-traded, never-revised, full-volume, or retrospective PIT authority"
        ),
        "observation_id": observation_id,
        "source": {
            "provider": "DNSE/Livespeed",
            "transport": "websocket",
            "channel": channel,
            "message_type": message_type,
            "symbol": copied_payload["symbol"],
            "resolution": copied_payload["resolution"],
        },
        "source_time": source_time,
        "receipt": {
            "first_observed_at_utc": received_at_utc,
            "received_at_utc": received_at_utc,
            "received_at_local": received_at_local,
        },
        "logical_bar_identity": logical_identity,
        "payload": copied_payload,
        "payload_sha256": payload_hash,
        "normalized_payload": normalized_payload,
        "normalized_payload_sha256": sha256_json(normalized_payload),
        "temporal_retention": temporal_retention,
        "a1_temporal_projection": project_retention_to_a1(temporal_retention),
    }


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ProspectivePitContractError(f"malformed_retained_observation_line:{line_number}") from error
    return records


def retain_observation(root: Path, observation: Mapping[str, Any]) -> dict[str, Any]:
    """Append the first receipt/revision; identify identical duplicates without overwrite."""
    path = root / OBSERVATIONS_FILENAME
    existing = _read_records(path)
    logical_identity = observation.get("logical_bar_identity")
    same_bar = ([] if logical_identity is None else
                [record for record in existing if record.get("logical_bar_identity") == logical_identity])
    for record in same_bar:
        if record.get("payload_sha256") == observation.get("payload_sha256"):
            return {"classification": "duplicate_identical", "retained": False,
                    "existing_observation_id": record.get("observation_id"), "path": str(path)}
    if logical_identity is None:
        classification = "first_receipt_source_time_missing"
    elif same_bar:
        classification = "revision"
    else:
        classification = "first_receipt"
    retained = dict(observation)
    retained["retention_classification"] = classification
    retained["revises_observation_ids"] = [record["observation_id"] for record in same_bar] if same_bar else []
    root.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(retained) + "\n")
    return {"classification": classification, "retained": True,
            "observation_id": retained["observation_id"], "path": str(path)}
