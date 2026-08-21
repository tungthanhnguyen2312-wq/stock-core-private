"""Bounded 12-issuer DNSE/FHSC composition scale-out runner."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_access import BASE_URL, auth_headers, credentials_for_request
from dnse_fhsc_market_composition_scaleout import DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE, content_identity, reconcile_scaleout, value_matrix
from dnse_fhsc_volume_basis import parse_dnse_ohlc_volume_history, parse_fhsc_trading_history
from dnse_market_data import resolve_endpoint
from dnse_secrets_env import ensure_credentials_loaded
from fhsc_retained_live_reconciliation import TIER1_HEADER_NAME, load_finhay_api_key


SESSIONS = ("2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20")
COHORT = (
    ("HPG", "HOSE", "materials", "large_liquid"), ("VCB", "HOSE", "banking", "large_liquid"),
    ("SSI", "HOSE", "securities", "large_liquid"), ("FPT", "HOSE", "technology", "large_liquid"),
    ("VNM", "HOSE", "consumer_staples", "large_liquid"), ("MWG", "HOSE", "retail", "large_liquid"),
    ("PVS", "HNX", "energy_services", "liquid"), ("SHS", "HNX", "securities", "liquid"),
    ("ACV", "UPCOM", "transport_infrastructure", "large"), ("BSR", "UPCOM", "energy_refining", "large"),
    ("MCH", "UPCOM", "consumer_staples", "large"), ("VGI", "UPCOM", "telecommunications", "large"),
)
ARTIFACT_DIR = ROOT / "operations-review" / "dnse-fhsc-market-composition-scaleout-v1-20260821"
RAW_DIR = ARTIFACT_DIR / "raw"


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _fhsc_fetch(symbol: str, path: str, params: dict[str, str], api_key: str) -> dict:
    url = f"https://open-api.fhsc.com.vn{path}?{urlencode(params)}"
    retrieval_time = datetime.now(UTC).isoformat()
    try:
        with urlopen(Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key}), timeout=30) as response:
            body, status, mime = response.read(), int(response.status), response.headers.get_content_type()
    except HTTPError as error:
        return {"symbol": symbol, "endpoint": path, "request_parameters": params, "request_url": url, "retrieval_time": retrieval_time, "http_status": int(error.code), "successful": False, "raw_response_retained": False}
    except OSError as error:
        return {"symbol": symbol, "endpoint": path, "request_parameters": params, "request_url": url, "retrieval_time": retrieval_time, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}", "successful": False, "raw_response_retained": False}
    digest = hashlib.sha256(body).hexdigest(); RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{symbol}_{path.strip('/').replace('/', '_')}_{digest[:16]}.json"; raw.write_bytes(body)
    return {"symbol": symbol, "endpoint": path, "request_parameters": params, "request_url": url, "retrieval_time": retrieval_time, "http_status": status, "mime_type": mime, "successful": status == 200, "raw_response_retained": True, "raw_path": _rel(raw), "raw_sha256": digest}


def _dnse_fetch(symbol: str, credentials: tuple[str, str]) -> dict:
    vn_tz = timezone(timedelta(hours=7)); start = datetime.combine(datetime.fromisoformat(SESSIONS[0]).date(), time.min, vn_tz); end = datetime.combine(datetime.fromisoformat(SESSIONS[-1]).date() + timedelta(days=1), time.min, vn_tz) - timedelta(seconds=1)
    path, query = resolve_endpoint("ohlc"), {"symbol": symbol, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}
    retrieval_time = datetime.now(UTC).isoformat()
    try:
        response = requests.get(f"{BASE_URL}{path}", params=query, headers=auth_headers(credentials[0], credentials[1], "GET", path), timeout=(5, 15))
    except requests.RequestException as error:
        return {"symbol": symbol, "endpoint": path, "query": query, "retrieval_time": retrieval_time, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}", "successful": False, "raw_response_retained": False}
    body, digest = bytes(response.content), hashlib.sha256(bytes(response.content)).hexdigest(); RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{symbol}_dnse_ohlc_{digest[:16]}.json"; raw.write_bytes(body)
    return {"symbol": symbol, "endpoint": path, "query": query, "retrieval_time": retrieval_time, "http_status": int(response.status_code), "mime_type": response.headers.get("Content-Type"), "successful": int(response.status_code) == 200, "raw_response_retained": True, "raw_path": _rel(raw), "raw_sha256": digest}


def _parse_fhsc_history(record: dict) -> list[dict]:
    if not record.get("successful"):
        return []
    body = (ROOT / record["raw_path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != record["raw_sha256"]:
        return []
    try: payload = json.loads(body.decode("utf-8")); data = payload["data"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError): return []
    arrays = (data.get("time"), data.get("volume")) if isinstance(data, dict) else (None, None)
    if not all(isinstance(item, list) for item in arrays) or len(arrays[0]) != len(arrays[1]): return []
    rows = []
    for epoch, volume in zip(*arrays):
        if isinstance(epoch, (int, float)) and isinstance(volume, int):
            session = datetime.fromtimestamp(epoch, UTC).date().isoformat()
            if session in SESSIONS: rows.append({"instrument": record["symbol"], "session": session, "volume": volume, "source_payload_sha256": record["raw_sha256"]})
    return rows


def main() -> int:
    replay_only, output = "--replay-only" in sys.argv, ARTIFACT_DIR / "dnse_fhsc_market_composition_scaleout_artifact.json"
    existing = json.loads(output.read_text(encoding="utf-8")) if replay_only and output.exists() else None
    key, credential_status = load_finhay_api_key(), ensure_credentials_loaded()
    credentials = credentials_for_request() if credential_status["configured"] else None
    if existing is None:
        fhsc_history = [] if key is None else [_fhsc_fetch(symbol, "/market/price-histories-chart", {"symbol": symbol, "resolution": "1D", "from": str(int(datetime.fromisoformat(SESSIONS[0]).replace(tzinfo=UTC).timestamp())), "to": str(int(datetime.fromisoformat(SESSIONS[-1]).replace(tzinfo=UTC).timestamp()))}, key) for symbol, *_ in COHORT]
        fhsc_trading = [] if key is None else [_fhsc_fetch(symbol, f"/market/stocks/{symbol}/trading/history", {"from": SESSIONS[0], "to": SESSIONS[-1], "resolution": "1D"}, key) for symbol, *_ in COHORT]
        dnse_records = [] if credentials is None else [_dnse_fetch(symbol, credentials) for symbol, *_ in COHORT]
    else:
        fhsc_history, fhsc_trading, dnse_records = existing["fhsc_history_request_records"], existing["fhsc_trading_request_records"], existing["dnse_request_records"]
    exchange = {symbol: listing for symbol, listing, *_ in COHORT}; expected = [(symbol, session) for symbol, *_ in COHORT for session in SESSIONS]
    dnse_rows, trading_rows, history_rows = [], [], []
    for record in dnse_records:
        if record.get("successful"):
            parsed = parse_dnse_ohlc_volume_history((ROOT / record["raw_path"]).read_bytes(), instrument=record["symbol"])
            dnse_rows.extend(row for row in parsed.get("rows", []) if row["session"] in SESSIONS)
    for record in fhsc_trading:
        if record.get("successful"):
            parsed = parse_fhsc_trading_history((ROOT / record["raw_path"]).read_bytes(), instrument=record["symbol"])
            trading_rows.extend(row for row in parsed.get("rows", []) if row.get("session") in SESSIONS and row.get("parse_status") == "PARSED")
    for record in fhsc_history:
        history_rows.extend(_parse_fhsc_history(record))
    volume = reconcile_scaleout(dnse_rows, trading_rows, fhsc_history_rows=history_rows, exchange_by_ticker=exchange, expected_keys=expected)
    value = value_matrix(trading_rows, exchange_by_ticker=exchange, expected_keys=expected)
    artifact = {"schema_version": "1.0.0", "contract_version": "dnse_fhsc_market_composition_scaleout/v1", "artifact_type": "DNSE_FHSC_MARKET_COMPOSITION_SCALEOUT", "cohort": [{"ticker": a, "exchange": b, "sector": c, "liquidity_profile": d} for a,b,c,d in COHORT], "sessions": list(SESSIONS), "cohort_selection": "fixed lexical design before provider responses; no result-dependent replacement", "source_roles": {"DNSE": "PRIMARY_CANDIDATE", "FHSC": "SHADOW_REFERENCE_PROVIDER"}, "request_budget": {"fhsc": {"max": 24, "used": len(fhsc_history)+len(fhsc_trading), "per_ticker_max": 2, "retries": 0}, "dnse": {"max": 12, "used": len(dnse_records), "per_ticker_max": 1, "retries": 0}}, "fhsc_history_request_records": fhsc_history, "fhsc_trading_request_records": fhsc_trading, "dnse_request_records": dnse_records, "fhsc_history_rows": history_rows, "volume": volume, "traded_value": value, "dnse_traded_value_trace": {"status": DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE, "reason": "market_volume_value_semantic_contract.DNSE_DAILY_TRADED_VALUE_FIELD=UNKNOWN/NOT_CONFIRMED; no explicit same-session generic value endpoint in scope", "derived_price_times_volume": "PROHIBITED"}, "authority_boundaries": {"authority_effect": "NONE", "liquidity_authority": False, "turnover_authority": False, "position_sizing_safe": False, "price_semantics_changed": False, "raw_as_traded_promoted": False, "provider_authority_changed": False}, "deterministic_replay_network_required": False}
    artifact.update(content_identity(artifact)); ARTIFACT_DIR.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"identity": artifact["artifact_identity"], "volume_candidate": volume["candidate_mapping"], "fhsc_requests": artifact["request_budget"]["fhsc"]["used"], "dnse_requests": artifact["request_budget"]["dnse"]["used"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
