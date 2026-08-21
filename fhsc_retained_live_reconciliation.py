"""Bounded FHSC Tier-1 retained-response reconciliation helpers.

The network boundary is intentionally fixed to the one published historical
OHLCV endpoint used by the live milestone.  It loads only FINHAY_API_KEY from
the operator-approved local file, never persists the key or request headers,
and retains successful bytes before they are parsed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from provider_reference_reconciliation import (
    BASIS_UNRESOLVED,
    CLOSED_SESSION_OBSERVATION,
    FINALIZATION_STATUS_UNKNOWN,
    SHADOW_REFERENCE_PROVIDER,
    provider_reference_observation,
    reconcile_observations,
)


ROOT = Path(__file__).resolve().parent
FHSC_BASE_URL = "https://open-api.fhsc.com.vn"
PRICE_HISTORY_PATH = "/market/price-histories-chart"
STOCK_REALTIME_PATH = "/market/stock-realtime"
TIER1_HEADER_NAME = "X-FH-APIKEY"
APPROVED_SECRETS_PATH = Path(r"C:\Users\tungt\.stocklookup\secrets.env")
HISTORICAL_SESSION = "2026-08-20"
TICKERS = ("HPG", "VCB", "SSI")


def load_finhay_api_key(path: Path = APPROVED_SECRETS_PATH) -> str | None:
    """Read exactly the approved key from dotenv-like text without logging it."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return None
    for line in lines:
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if item.startswith("export "):
            item = item[7:].strip()
        name, separator, value = item.partition("=")
        if separator and name.strip() == "FINHAY_API_KEY":
            candidate = value.strip().strip("\"'")
            return candidate or None
    return None


def historical_request_parameters(symbol: str) -> dict[str, str]:
    """Return the published daily-chart parameters for exactly one closed day."""
    start = int(datetime(2026, 8, 20, tzinfo=UTC).timestamp())
    end = int(datetime(2026, 8, 21, tzinfo=UTC).timestamp())
    return {"symbol": symbol.upper(), "resolution": "1D", "from": str(start), "to": str(end)}


def request_url(symbol: str) -> str:
    return f"{FHSC_BASE_URL}{PRICE_HISTORY_PATH}?{urlencode(historical_request_parameters(symbol))}"


def realtime_request_url(symbol: str) -> str:
    return f"{FHSC_BASE_URL}{STOCK_REALTIME_PATH}?{urlencode({'symbol': symbol.upper()})}"


def fetch_and_retain(symbol: str, api_key: str, raw_directory: Path) -> dict[str, Any]:
    """Make exactly one fixed GET and retain a successful response before parsing."""
    url = request_url(symbol)
    request = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})
    retrieval_time = datetime.now(UTC).isoformat()
    try:
        with urlopen(request, timeout=30) as response:  # no retry or polling
            body = response.read()
            status = int(response.status)
            mime_type = response.headers.get_content_type()
    except HTTPError as error:
        return {
            "symbol": symbol.upper(), "endpoint_capability": "price_histories_chart_1d", "request_url": url, "request_parameters": historical_request_parameters(symbol),
            "retrieval_time": retrieval_time, "http_status": int(error.code), "successful": False,
            "failure_disposition": "HTTP_ERROR", "raw_response_retained": False,
        }
    except OSError as error:
        return {
            "symbol": symbol.upper(), "endpoint_capability": "price_histories_chart_1d", "request_url": url, "request_parameters": historical_request_parameters(symbol),
            "retrieval_time": retrieval_time, "http_status": None, "successful": False,
            "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}", "raw_response_retained": False,
        }

    digest = hashlib.sha256(body).hexdigest()
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{symbol.upper()}_price_histories_chart_{digest[:16]}.json"
    raw_path.write_bytes(body)  # retention precedes JSON parsing below
    return {
        "symbol": symbol.upper(), "endpoint_capability": "price_histories_chart_1d", "request_url": url, "request_parameters": historical_request_parameters(symbol),
        "retrieval_time": retrieval_time, "http_status": status, "mime_type": mime_type, "successful": True,
        "raw_response_retained": True, "raw_path": raw_path, "raw_sha256": digest,
    }


def fetch_realtime_and_retain(symbol: str, api_key: str, raw_directory: Path) -> dict[str, Any]:
    """Make one documented current-payload request; it is never a closed-session qualifier."""
    url = realtime_request_url(symbol)
    request = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})
    retrieval_time = datetime.now(UTC).isoformat()
    try:
        with urlopen(request, timeout=30) as response:  # no retry or polling
            body = response.read()
            status = int(response.status)
            mime_type = response.headers.get_content_type()
    except HTTPError as error:
        return {"symbol": symbol.upper(), "endpoint_capability": "stock_realtime", "request_url": url,
                "request_parameters": {"symbol": symbol.upper()}, "retrieval_time": retrieval_time,
                "http_status": int(error.code), "successful": False, "failure_disposition": "HTTP_ERROR",
                "raw_response_retained": False}
    except OSError as error:
        return {"symbol": symbol.upper(), "endpoint_capability": "stock_realtime", "request_url": url,
                "request_parameters": {"symbol": symbol.upper()}, "retrieval_time": retrieval_time,
                "http_status": None, "successful": False, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}",
                "raw_response_retained": False}
    digest = hashlib.sha256(body).hexdigest()
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{symbol.upper()}_stock_realtime_{digest[:16]}.json"
    raw_path.write_bytes(body)
    return {"symbol": symbol.upper(), "endpoint_capability": "stock_realtime", "request_url": url,
            "request_parameters": {"symbol": symbol.upper()}, "retrieval_time": retrieval_time, "http_status": status,
            "mime_type": mime_type, "successful": True, "raw_response_retained": True,
            "raw_path": raw_path, "raw_sha256": digest}


def parse_retained_history(record: Mapping[str, Any]) -> dict[str, Any]:
    """Parse only the retained bytes and identify daily rows by UTC date."""
    if not record.get("successful"):
        return {"parse_status": "NO_SUCCESSFUL_RESPONSE"}
    raw_path = Path(str(record["raw_path"]))
    body = raw_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != record["raw_sha256"]:
        return {"parse_status": "RETAINED_BYTES_HASH_MISMATCH"}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RETAINED_BYTES_NOT_JSON"}
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {"parse_status": "DOCUMENTED_DATA_OBJECT_ABSENT"}
    arrays = {name: data.get(name) for name in ("time", "open", "high", "low", "close", "volume")}
    if not all(isinstance(value, list) for value in arrays.values()):
        return {"parse_status": "DOCUMENTED_COLUMNAR_ARRAYS_ABSENT"}
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        return {"parse_status": "COLUMNAR_LENGTH_MISMATCH", "lengths": {key: len(value) for key, value in arrays.items()}}
    rows = []
    for index, timestamp in enumerate(arrays["time"]):
        try:
            session = datetime.fromtimestamp(float(timestamp), tz=UTC).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            continue
        rows.append({"session": session, "event_time": datetime.fromtimestamp(float(timestamp), tz=UTC).isoformat(),
                     **{name: arrays[name][index] for name in ("open", "high", "low", "close", "volume")}})
    return {"parse_status": "PARSED", "symbol": data.get("symbol"), "resolution": data.get("resolution"), "rows": rows}


def parse_retained_realtime(record: Mapping[str, Any]) -> dict[str, Any]:
    """Parse only a retained current realtime payload, without session qualification."""
    if not record.get("successful"):
        return {"parse_status": "NO_SUCCESSFUL_RESPONSE"}
    body = Path(str(record["raw_path"])).read_bytes()
    if hashlib.sha256(body).hexdigest() != record["raw_sha256"]:
        return {"parse_status": "RETAINED_BYTES_HASH_MISMATCH"}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"parse_status": "RETAINED_BYTES_NOT_JSON"}
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return {"parse_status": "DOCUMENTED_RESULT_OBJECT_ABSENT"}
    return {"parse_status": "PARSED_CURRENT_SESSION_ONLY", "symbol": result.get("symbol"),
            "name": result.get("name"), "exchange": result.get("exchange"), "stock_type": result.get("stockType"),
            "total_volume": result.get("totalVolume"), "volume": result.get("volume"),
            "foreign_bought": result.get("foreignBought"), "foreign_sold": result.get("foreignSold"),
            "foreign_remain": result.get("foreignRemain"), "provider_session_qualification": "NOT_ATTEMPTED_CURRENT_ENDPOINT"}


def fhsc_close_observation(record: Mapping[str, Any], parsed: Mapping[str, Any]) -> dict[str, Any] | None:
    """Create a non-promoting observation for the requested completed session.

    The published contract labels values as prices but does not establish a
    price unit or adjustment/finalization basis, so those remain fail-closed.
    """
    rows = parsed.get("rows") if isinstance(parsed, Mapping) else None
    if not isinstance(rows, list):
        return None
    row = next((item for item in rows if item.get("session") == HISTORICAL_SESSION), None)
    if not isinstance(row, Mapping):
        return None
    raw_path = Path(str(record["raw_path"]))
    return provider_reference_observation(
        provider="FHSC", provider_interface="fhsc_open_api_tier1", endpoint_capability="price_histories_chart_1d",
        instrument=str(record["symbol"]), exchange=None, session=HISTORICAL_SESSION, event_time=row.get("event_time"),
        retrieval_time=record.get("retrieval_time"), field="close", raw_value=row.get("close"), normalized_value=None,
        unit="UNSPECIFIED_PRICE_UNIT", basis="ADJUSTMENT_AND_PRICE_UNIT_UNSPECIFIED_BY_PUBLISHED_CONTRACT",
        semantic_status=BASIS_UNRESOLVED, finalization_status=FINALIZATION_STATUS_UNKNOWN,
        source_payload_identity=f"fhsc_retained:{record['raw_sha256']}", source_payload_sha256=record["raw_sha256"],
        provenance={"retained_raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"), "request_url": record["request_url"],
                    "request_parameters": dict(record["request_parameters"]), "http_status": record["http_status"],
                    "mime_type": record["mime_type"], "parsed_from_retained_bytes": True,
                    "published_endpoint": PRICE_HISTORY_PATH}, source_role=SHADOW_REFERENCE_PROVIDER,
    )


def reconciliation_artifact(dnse_rows: list[dict[str, Any]], request_records: list[dict[str, Any]],
                            parsed_records: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    """Build deterministic, authority-neutral replay data from retained responses."""
    comparisons = []
    for dnse in dnse_rows:
        ticker = dnse["instrument"]
        record = next((item for item in request_records if item["symbol"] == ticker and item.get("endpoint_capability") != "stock_realtime"), None)
        parsed = next((item for item in parsed_records if item.get("symbol") == ticker), {})
        fhsc = fhsc_close_observation(record, parsed) if record and record.get("successful") else None
        comparisons.append(reconcile_observations([dnse, fhsc] if fhsc else [dnse]))
    artifact = {
        "schema_version": "1.0.0", "contract_version": "provider_reference_observation/v1",
        "artifact_type": "FHSC_DNSE_RETAINED_LIVE_RECONCILIATION", "session_target": HISTORICAL_SESSION,
        "request_budget": {"per_ticker_max": 6, "total_max": 18, "used": len(request_records)},
        "official_contract": {"base_url": FHSC_BASE_URL, "endpoint": PRICE_HISTORY_PATH,
                              "documented_response_key": "data", "documented_shape": "columnar_ohlcv",
                              "published_price_unit": "UNSPECIFIED", "published_finalization": "UNSPECIFIED",
                              "current_only_endpoint": STOCK_REALTIME_PATH},
        "request_records": [{key: value for key, value in record.items() if key != "raw_path"} | ({"raw_path": str(Path(record["raw_path"]).relative_to(output_root.parent.parent)).replace("\\", "/")} if record.get("raw_path") else {}) for record in request_records],
        "parsed_records": parsed_records, "reconciliation_rows": comparisons,
        "authority_boundaries": {"fhsc_promoted": False, "dnse_replaced": False, "raw_as_traded_promoted": False,
                                 "liquidity_sizing_promoted": False, "provider_fundamentals_promoted": False,
                                 "canonical_facts_created": 0, "runtime_or_database_mutated": False},
    }
    stable = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    artifact["artifact_sha256"] = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    artifact["artifact_identity"] = f"fhsc_dnse_retained_live_reconciliation:{artifact['artifact_sha256']}"
    return artifact
