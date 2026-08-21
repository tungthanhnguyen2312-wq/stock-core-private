from __future__ import annotations

import hashlib
import json

from fhsc_retained_live_reconciliation import (
    HISTORICAL_SESSION,
    PRICE_HISTORY_PATH,
    STOCK_REALTIME_PATH,
    historical_request_parameters,
    parse_retained_history,
)


def test_request_is_fixed_to_documented_daily_history_contract() -> None:
    parameters = historical_request_parameters("hpg")
    assert PRICE_HISTORY_PATH == "/market/price-histories-chart"
    assert STOCK_REALTIME_PATH == "/market/stock-realtime"
    assert parameters == {"symbol": "HPG", "resolution": "1D", "from": "1787184000", "to": "1787270400"}


def test_retained_columnar_payload_is_parsed_only_after_hash_check(tmp_path) -> None:
    body = json.dumps({"status": 200, "data": {"symbol": "HPG", "resolution": "1D", "time": [1787184000],
        "open": [21000], "high": [21200], "low": [20900], "close": [21150], "volume": [123]}}).encode()
    raw = tmp_path / "raw.json"
    raw.write_bytes(body)
    parsed = parse_retained_history({"successful": True, "raw_path": raw, "raw_sha256": hashlib.sha256(body).hexdigest()})
    assert parsed["parse_status"] == "PARSED"
    assert parsed["rows"] == [{"session": HISTORICAL_SESSION, "event_time": "2026-08-20T00:00:00+00:00",
                                "open": 21000, "high": 21200, "low": 20900, "close": 21150, "volume": 123}]
