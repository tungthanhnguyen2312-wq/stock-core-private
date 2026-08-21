from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from dnse_closed_session_ohlc_representation import (
    FIELDS, IDENTITY_TRANSFORMATION, parse_raw_ohlc_bytes, uniform_anchor,
)
from provider_reference_reconciliation import (
    BASIS_UNRESOLVED, CLOSED_SESSION_OBSERVATION, provider_reference_observation, reconcile_observations,
)


VN = timezone(timedelta(hours=7))


def _raw_body() -> bytes:
    epoch = int(datetime(2026, 8, 20, 9, tzinfo=VN).timestamp())
    return json.dumps({"t": [epoch], "o": [21.25], "h": [21.45], "l": [21.15], "c": [21.15], "v": [123]}).encode()


def test_raw_parser_preserves_all_ohlc_values_without_hidden_scaling() -> None:
    parsed = parse_raw_ohlc_bytes(_raw_body(), instrument="HPG", session="2026-08-20")
    assert parsed["parse_status"] == "PARSED"
    assert parsed["raw_values"] == {"open": 21.25, "high": 21.45, "low": 21.15, "close": 21.15}


def test_uniform_anchor_uses_one_identity_transformation_for_all_ohlc_fields() -> None:
    parsed = parse_raw_ohlc_bytes(_raw_body(), instrument="HPG", session="2026-08-20")
    anchor = uniform_anchor(parsed, source={"source_payload_identity": "test", "raw_sha256": parsed["raw_sha256"]})
    assert anchor["uniform_representation_gate"] == "PASS"
    assert set(anchor["field_representation"].values()) == {IDENTITY_TRANSFORMATION}
    assert {field: anchor["fields"][field]["normalized_numeric_value"] for field in FIELDS} == parsed["raw_values"]
    assert anchor["authority_effect"] == "NONE"


def test_uniform_anchor_replay_is_deterministic_and_agreement_creates_no_authority() -> None:
    parsed = parse_raw_ohlc_bytes(_raw_body(), instrument="HPG", session="2026-08-20")
    left = uniform_anchor(parsed, source={"source_payload_identity": "test", "raw_sha256": parsed["raw_sha256"]})
    right = uniform_anchor(parsed, source={"source_payload_identity": "test", "raw_sha256": parsed["raw_sha256"]})
    assert left == right
    common = {"provider_interface": "test", "endpoint_capability": "ohlc", "instrument": "HPG", "exchange": None,
              "session": "2026-08-20", "event_time": None, "retrieval_time": "2026-08-21T00:00:00+00:00", "field": "close",
              "raw_value": 21.15, "normalized_value": 21.15, "unit": "UNSPECIFIED_PRICE_UNIT", "basis": "UNDOCUMENTED",
              "semantic_status": BASIS_UNRESOLVED, "finalization_status": CLOSED_SESSION_OBSERVATION}
    result = reconcile_observations([provider_reference_observation(provider="DNSE", **common), provider_reference_observation(provider="FHSC", **common)])
    assert result["verdict"] == BASIS_UNRESOLVED
    assert result["authority_effect"] == "NONE"
    assert result["selected_provider"] is None


def test_missing_or_ambiguous_session_is_excluded() -> None:
    parsed = parse_raw_ohlc_bytes(_raw_body(), instrument="HPG", session="2026-08-19")
    assert uniform_anchor(parsed, source={}) == {"status": "EXCLUDED", "reason": "EXACT_SESSION_MISSING"}
