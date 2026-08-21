"""Run the bounded DNSE/FHSC closed-session volume basis qualification."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_access import BASE_URL, auth_headers, credentials_for_request
from dnse_fhsc_volume_basis import content_identity, parse_dnse_ohlc_volume, parse_dnse_ohlc_volume_history, parse_fhsc_trading_history, reconcile_volume_rows
from dnse_market_data import resolve_endpoint
from dnse_secrets_env import ensure_credentials_loaded
from fhsc_retained_live_reconciliation import TIER1_HEADER_NAME, load_finhay_api_key, parse_retained_history


TICKERS = ("HPG", "VCB", "SSI")
SESSION = "2026-08-20"
SESSIONS = ("2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20")
ARTIFACT_DIR = ROOT / "operations-review" / "dnse-fhsc-volume-basis-qualification-v1-20260821"
RAW_DIR = ARTIFACT_DIR / "raw"
DNSE_ARTIFACT = ROOT / "operations-review" / "dnse-uniform-ohlc-anchor-qualification-v1-20260821" / "dnse_uniform_ohlc_anchor_qualification_artifact.json"
FHSC_ARTIFACT = ROOT / "operations-review" / "fhsc-dnse-retained-live-reconciliation-v1-20260821" / "fhsc_dnse_retained_live_reconciliation_artifact.json"
FHSC_DOC = ROOT / "operations-review" / "fhsc-historical-price-semantics-qualification-v1-20260821" / "official-documentation" / "01_f9f7a6e034313c83.yaml"


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _fetch_trading_history(symbol: str, api_key: str, *, start: str = SESSION, end: str = SESSION) -> dict:
    params = {"from": start, "to": end, "resolution": "1D"}
    url = f"https://open-api.fhsc.com.vn/market/stocks/{symbol}/trading/history?{urlencode(params)}"
    retrieved_at = datetime.now(UTC).isoformat()
    request = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})
    try:
        with urlopen(request, timeout=30) as response:  # one foreground request, no retry
            body, status, mime_type = response.read(), int(response.status), response.headers.get_content_type()
    except HTTPError as error:
        return {"symbol": symbol, "endpoint_capability": "stock_trading_history", "request_url": url,
                "request_parameters": params, "retrieval_time": retrieved_at, "http_status": int(error.code),
                "successful": False, "failure_disposition": "HTTP_ERROR", "raw_response_retained": False}
    except OSError as error:
        return {"symbol": symbol, "endpoint_capability": "stock_trading_history", "request_url": url,
                "request_parameters": params, "retrieval_time": retrieved_at, "http_status": None,
                "successful": False, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}", "raw_response_retained": False}
    digest = hashlib.sha256(body).hexdigest()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{symbol}_stock_trading_history_{digest[:16]}.json"
    path.write_bytes(body)
    return {"symbol": symbol, "endpoint_capability": "stock_trading_history", "request_url": url,
            "request_parameters": params, "retrieval_time": retrieved_at, "http_status": status, "mime_type": mime_type,
            "successful": True, "raw_response_retained": True, "raw_path": _relative(path), "raw_sha256": digest}


def _dnse_query(symbol: str) -> dict:
    vn_tz = timezone(timedelta(hours=7))
    start = datetime.combine(datetime.fromisoformat(SESSIONS[0]).date(), time.min, vn_tz)
    end = datetime.combine(datetime.fromisoformat(SESSION).date() + timedelta(days=1), time.min, vn_tz) - timedelta(seconds=1)
    return {"symbol": symbol, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}


def _fetch_dnse_ohlc_history(symbol: str, credentials: tuple[str, str]) -> dict:
    import requests
    path, query = resolve_endpoint("ohlc"), _dnse_query(symbol)
    retrieved_at = datetime.now(UTC).isoformat()
    try:
        response = requests.get(f"{BASE_URL}{path}", params=query,
                                headers=auth_headers(credentials[0], credentials[1], "GET", path), timeout=(5, 15))
    except requests.RequestException as error:
        return {"symbol": symbol, "endpoint": path, "query": query, "retrieval_time": retrieved_at,
                "successful": False, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}", "raw_response_retained": False}
    body, digest = bytes(response.content), hashlib.sha256(bytes(response.content)).hexdigest()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{symbol}_ohlc_history_{digest[:16]}.json"
    raw_path.write_bytes(body)  # retain before parsing
    return {"symbol": symbol, "endpoint": path, "query": query, "retrieval_time": retrieved_at,
            "http_status": int(response.status_code), "mime_type": response.headers.get("Content-Type"),
            "successful": int(response.status_code) == 200, "raw_response_retained": True,
            "raw_path": _relative(raw_path), "raw_sha256": digest,
            "source_payload_identity": f"dnse_retained_raw:{digest}"}


def main() -> int:
    dnse_prior, fhsc_prior = json.loads(DNSE_ARTIFACT.read_text(encoding="utf-8")), json.loads(FHSC_ARTIFACT.read_text(encoding="utf-8"))
    output_path = ARTIFACT_DIR / "dnse_fhsc_volume_basis_qualification_artifact.json"
    replay_only = "--replay-only" in sys.argv
    existing = json.loads(output_path.read_text(encoding="utf-8")) if replay_only and output_path.exists() else None
    prior_dnse_trace = []
    for anchor in dnse_prior["corrected_dnse_anchors"]:
        source = anchor["source_evidence"]
        body = (ROOT / source["raw_path"]).read_bytes()
        parsed = parse_dnse_ohlc_volume(body, instrument=anchor["instrument"], session=anchor["session"])
        parsed["source_evidence"] = source
        prior_dnse_trace.append(parsed)
    historical_artifact = json.loads((ROOT / "operations-review" / "fhsc-historical-price-semantics-qualification-v1-20260821" / "fhsc_historical_price_semantics_qualification_artifact.json").read_text(encoding="utf-8"))
    history_by_symbol = {record["symbol"]: record for record in historical_artifact["ohcl_scale_matrix"]["fhsc_retained_evidence"] if record["symbol"] in TICKERS}
    history_rows = []
    for symbol in TICKERS:
        record = dict(history_by_symbol[symbol]); source_path = ROOT / record["raw_path"]
        body = source_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise SystemExit(f"FHSC_RETAINED_HISTORY_HASH_MISMATCH:{symbol}")
        parsed = parse_retained_history({"successful": True, "raw_path": str(source_path), "raw_sha256": record["sha256"]})
        for row in parsed["rows"]:
            if row["session"] in SESSIONS:
                history_rows.append({"instrument": symbol, "session": row["session"], "volume": row["volume"],
                                     "source_payload_sha256": record["sha256"], "source_path": record["raw_path"]})
    key = load_finhay_api_key()
    if existing is not None:
        records = list(existing["fhsc_trading_request_records"])
        dnse_request_records = list(existing["dnse_request_records"])
    else:
        first_records = [] if key is None else [_fetch_trading_history(symbol, key) for symbol in TICKERS]
        status = ensure_credentials_loaded()
        credentials = credentials_for_request() if status["configured"] else None
        dnse_request_records = [] if credentials is None else [_fetch_dnse_ohlc_history(symbol, credentials) for symbol in TICKERS]
        range_records = [] if key is None else [_fetch_trading_history(symbol, key, start=SESSIONS[0], end=SESSION) for symbol in TICKERS]
        records = first_records + range_records
    raw_dnse_rows = []
    for record in dnse_request_records:
        if not record.get("successful"):
            continue
        parsed = parse_dnse_ohlc_volume_history((ROOT / record["raw_path"]).read_bytes(), instrument=record["symbol"])
        for row in parsed.get("rows", []):
            if row["session"] in SESSIONS:
                row["source_evidence"] = {key: record[key] for key in ("endpoint", "query", "retrieval_time", "raw_path", "raw_sha256", "source_payload_identity")}
                raw_dnse_rows.append(row)
    trading_rows = []
    for record in records:
        if not record.get("successful"):
            continue
        parsed = parse_fhsc_trading_history((ROOT / record["raw_path"]).read_bytes(), instrument=record["symbol"])
        for row in parsed.get("rows", []):
            if row.get("session") in SESSIONS:
                row["source_payload_sha256"] = record["raw_sha256"]
                row["source_path"] = record["raw_path"]
                trading_rows.append(row)
    reconciliation = reconcile_volume_rows(raw_dnse_rows, history_rows, trading_rows, documented_identity=True, required_observations=len(TICKERS))
    document_sha = hashlib.sha256(FHSC_DOC.read_bytes()).hexdigest()
    artifact = {
        "schema_version": "1.0.0", "contract_version": "dnse_fhsc_volume_basis_qualification/v1",
        "artifact_type": "DNSE_FHSC_VOLUME_BASIS_QUALIFICATION", "cohort": {"tickers": list(TICKERS), "sessions": list(SESSIONS)},
        "request_budget": {"fhsc": {"per_ticker_max": 2, "total_max": 6, "used": len(records), "retries": 0},
                           "dnse": {"per_ticker_max": 2, "total_max": 6, "used": len(dnse_request_records), "retries": 0}},
        "official_fhsc_trading_identity": {"document_path": _relative(FHSC_DOC), "document_sha256": document_sha,
            "statement": "matched + put_through = total", "status": "DOCUMENTED"},
        "prior_dnse_anchor_trace": sorted(prior_dnse_trace, key=lambda row: row.get("instrument", "")),
        "dnse_request_records": dnse_request_records, "dnse_raw_volume_trace": sorted(raw_dnse_rows, key=lambda row: (row.get("instrument", ""), row.get("session", ""))),
        "fhsc_history_rows": sorted(history_rows, key=lambda row: row["instrument"]),
        "fhsc_trading_request_records": records, "fhsc_trading_rows": sorted(trading_rows, key=lambda row: row.get("instrument", "")),
        "reconciliation": reconciliation,
        "unit_metadata": {"dnse": "SHARES_PER_EXISTING_PARTIALLY_QUALIFIED_FIELD_CONTRACT; COMPOSITION_WAS_UNKNOWN_BEFORE_THIS_SCOPE",
                            "fhsc": "STOCK_TRADING_DOCUMENTATION_DESCRIBES_VOLUME_AS_SHARES",
                            "numeric_transform": "NONE", "numeric_agreement_unit_undocumented": False},
        "authority_boundaries": {"authority_effect": "NONE", "fhsc_role": "SHADOW_REFERENCE_PROVIDER",
            "liquidity_authority": False, "turnover_authority": False, "position_sizing_safe": False,
            "price_semantics_changed": False, "raw_as_traded_promoted": False},
        "exceptions": ([{"code": "ZERO_PUT_THROUGH_NON_DISCRIMINATING", "count": reconciliation["zero_put_through_non_discriminating_consistency_count"],
                         "effect": "CONSISTENT_WITH_MATCHED_AND_TOTAL; NOT_A_CONTRADICTORY_EXCEPTION"}]
                       if reconciliation["zero_put_through_non_discriminating_consistency_count"] else []),
        "deterministic_replay_network_required": False,
    }
    artifact.update(content_identity(artifact))
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "fhsc_requests_used": len(records),
                      "dnse_requests_used": len(dnse_request_records), "basis": reconciliation["dnse_volume_basis_candidate"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
