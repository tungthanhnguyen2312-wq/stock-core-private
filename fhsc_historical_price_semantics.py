"""Fail-closed FHSC legacy-history scale calibration for shadow reconciliation only."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

from fhsc_retained_live_reconciliation import (
    FHSC_BASE_URL,
    PRICE_HISTORY_PATH,
    TIER1_HEADER_NAME,
    load_finhay_api_key,
    parse_retained_history,
)


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CALIBRATION_VERSION = "fhsc_historical_price_scale_calibration/v1"
LEGACY_CAPABILITY = "price_histories_chart_1d"
FIELDS = ("open", "high", "low", "close")
CALIBRATION_TICKERS = ("HPG", "VCB", "SSI", "VNM", "FPT", "VIC", "MWG", "GAS", "DPM", "VJC")
SESSIONS = ("2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20")
DOCUMENT_URLS = (
    "https://developers.fhsc.com.vn/openapi.yaml",
    "https://developers.fhsc.com.vn/authentication.md",
    "https://developers.fhsc.com.vn/api-reference/b%E1%BA%A3ng-gi%C3%A1-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng/l%E1%BB%8Bch-s%E1%BB%AD-gi%C3%A1-c%E1%BB%95-phi%E1%BA%BFu.md",
    "https://developers.fhsc.com.vn/api-reference/b%E1%BA%A3ng-gi%C3%A1-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng/gi%C3%A1-realtime-c%E1%BB%95-phi%E1%BA%BFu.md",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _portable_path(path: Path) -> str:
    """Use a repository-relative path when available, otherwise a stable test label."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return path.name


def retain_official_documents(output: Path) -> list[dict[str, Any]]:
    """Retain the official documentation bytes and only then inspect them."""
    destination = output / "official-documentation"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for index, url in enumerate(DOCUMENT_URLS):
        retrieved_at = datetime.now(UTC).isoformat()
        request = Request(url, method="GET")
        with urlopen(request, timeout=30) as response:
            body = response.read()
            status = int(response.status)
            mime_type = response.headers.get_content_type()
        digest = _sha256(body)
        path = destination / f"{index + 1:02d}_{digest[:16]}.{'yaml' if url.endswith('.yaml') else 'md'}"
        path.write_bytes(body)
        records.append({"url": url, "retrieval_time": retrieved_at, "http_status": status, "mime_type": mime_type,
                        "raw_path": path, "sha256": digest, "bytes": len(body)})
    return records


def documentation_verdict(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Bind the verdict to retained official bytes; never infer legacy semantics."""
    texts = {str(record["url"]): Path(str(record["raw_path"])).read_text(encoding="utf-8") for record in records}
    spec = next(text for url, text in texts.items() if url.endswith("openapi.yaml"))
    exact_descriptions = (
        "Lịch sử giá OHLCV của 1 mã cổ phiếu — chuỗi nến `{t, o, h, l, c, v}`.",
        "`data.series` là mảng nến `{t, o, h, l, c, v}`.",
        "Đơn vị tiền tệ (bỏ qua với chỉ số).",
        "Dữ liệu realtime của 1 mã cổ phiếu.",
        "Giá mở cửa. `null` với chuỗi close-only.",
        "Giá đóng cửa. `null` với nến yield-only (trái phiếu Chính phủ).",
        "Khối lượng. `null` với chuỗi close-only.",
    )
    corpus = "\n".join(texts.values())
    missing = [statement for statement in exact_descriptions if statement not in corpus]
    if missing:
        raise ValueError(f"official_documentation_phrase_missing:{len(missing)}")
    return {
        "legacy_capability": LEGACY_CAPABILITY,
        "legacy_endpoint": PRICE_HISTORY_PATH,
        "legacy_endpoint_in_current_openapi": PRICE_HISTORY_PATH in spec,
        "current_history_endpoint": "/market/quotes/stocks/{symbol}/history",
        "current_history_schema": "data.series:{t,o,h,l,c,v}; currency is a series field",
        "realtime_capability_separate": "/market/quotes/stocks/{symbol}",
        "price_unit": "UNDOCUMENTED",
        "adjustment_basis": "UNDOCUMENTED",
        "finalization": "UNDOCUMENTED",
        "volume_basis": "BASIS_UNRESOLVED",
        "relevant_exact_field_descriptions": list(exact_descriptions),
        "relevant_documented_statements": [
            "Tier 1 market GET endpoints require X-FH-APIKEY only.",
            "Current stock history is an OHLCV candle series {t, o, h, l, c, v}; from/to use Unix seconds.",
            "Current history exposes a currency field described as currency unit, but no numeric price scale declaration.",
            "Realtime stock quote is a distinct capability and is described as realtime.",
        ],
        "absence_scope": "No retained official material explicitly assigns a numeric unit scale, adjustment basis, or closed-session finalization rule to the retained legacy columnar endpoint.",
    }


def calibration_request_parameters(symbol: str) -> dict[str, str]:
    start = int(datetime(2026, 8, 7, tzinfo=UTC).timestamp())
    end = int(datetime(2026, 8, 20, tzinfo=UTC).timestamp())
    return {"symbol": symbol.upper(), "resolution": "1D", "from": str(start), "to": str(end)}


def fetch_legacy_history_and_retain(symbol: str, api_key: str, raw_directory: Path) -> dict[str, Any]:
    """One bounded Tier-1 legacy history request, retained before parsing."""
    from urllib.parse import urlencode
    from urllib.error import HTTPError

    parameters = calibration_request_parameters(symbol)
    url = f"{FHSC_BASE_URL}{PRICE_HISTORY_PATH}?{urlencode(parameters)}"
    retrieval_time = datetime.now(UTC).isoformat()
    request = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            status = int(response.status)
            mime_type = response.headers.get_content_type()
    except HTTPError as error:
        return {"symbol": symbol.upper(), "request_url": url, "request_parameters": parameters,
                "retrieval_time": retrieval_time, "http_status": int(error.code), "successful": False,
                "raw_response_retained": False, "failure_disposition": "HTTP_ERROR"}
    except OSError as error:
        return {"symbol": symbol.upper(), "request_url": url, "request_parameters": parameters,
                "retrieval_time": retrieval_time, "http_status": None, "successful": False,
                "raw_response_retained": False, "failure_disposition": f"NETWORK_ERROR:{type(error).__name__}"}
    digest = _sha256(body)
    raw_directory.mkdir(parents=True, exist_ok=True)
    path = raw_directory / f"{symbol.upper()}_legacy_history_{digest[:16]}.json"
    path.write_bytes(body)
    return {"symbol": symbol.upper(), "request_url": url, "request_parameters": parameters,
            "retrieval_time": retrieval_time, "http_status": status, "mime_type": mime_type, "successful": True,
            "raw_response_retained": True, "raw_path": path, "raw_sha256": digest}


def retained_dnse_ohlc(snapshot_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the already-retained DNSE closed-session matrix without network access."""
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = []
    for ticker in CALIBRATION_TICKERS:
        record = payload["records"].get(ticker)
        if not isinstance(record, dict) or record.get("disposition") != "EXACT_SESSION_RETAINED":
            continue
        for observation in record.get("observations", []):
            if observation.get("session") not in SESSIONS:
                continue
            rows.append({"provider": "DNSE", "instrument": ticker, "session": observation["session"],
                         **{field: observation.get(field) for field in FIELDS}})
    identity = {"path": _portable_path(snapshot_path), "sha256": _sha256(snapshot_path.read_bytes()),
                "snapshot_identity": payload.get("snapshot_identity"), "price_basis": "ADJUSTED_RETROSPECTIVE"}
    return rows, identity


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def ratio_classification(dnse_value: Any, fhsc_value: Any) -> tuple[str, str | None, Decimal | None]:
    left, right = _decimal(dnse_value), _decimal(fhsc_value)
    if left is None or right is None or right == 0:
        return "NOT_COMPARABLE", None, None
    ratio = left / right
    if ratio == Decimal("1"):
        return "EXACT_1_TO_1", "1", ratio
    if ratio == Decimal("1000"):
        return "EXACT_1000_TO_1", "1000", ratio
    return "OTHER_CONSTANT_RATIO", format(ratio, "f"), ratio


def calibration_matrix(dnse_rows: Iterable[Mapping[str, Any]], fhsc_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare each OHLC field independently, leaving both source values unchanged."""
    fhsc_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    evidence = []
    for record in fhsc_records:
        parsed = parse_retained_history(record)
        if parsed.get("parse_status") != "PARSED":
            continue
        for row in parsed["rows"]:
            if row["session"] in SESSIONS:
                fhsc_by_key[(str(record["symbol"]), str(row["session"]))] = dict(row)
        evidence.append({"symbol": record["symbol"], "sha256": record.get("raw_sha256"),
                         "raw_path": _portable_path(Path(record["raw_path"])),
                         "request_url": record["request_url"]})
    pairs = []
    for dnse in sorted((dict(row) for row in dnse_rows), key=lambda row: (row["instrument"], row["session"])):
        fhsc = fhsc_by_key.get((dnse["instrument"], dnse["session"]))
        for field in FIELDS:
            classification, ratio_text, ratio = ratio_classification(dnse.get(field), fhsc.get(field) if fhsc else None)
            residual_1 = None
            residual_1000 = None
            left, right = _decimal(dnse.get(field)), _decimal(fhsc.get(field) if fhsc else None)
            if left is not None and right is not None:
                residual_1 = str(abs(left - right))
                residual_1000 = str(abs(left - right * Decimal("1000")))
            pairs.append({"instrument": dnse["instrument"], "session": dnse["session"], "field": field,
                          "dnse_raw_value": dnse.get(field), "fhsc_raw_value": fhsc.get(field) if fhsc else None,
                          "classification": classification, "ratio_dnse_to_fhsc": ratio_text,
                          "residual_candidate_1": residual_1, "residual_candidate_1000": residual_1000})
    by_field = {}
    for field in FIELDS:
        entries = [entry for entry in pairs if entry["field"] == field]
        classes = {entry["classification"] for entry in entries}
        ratios = {entry["ratio_dnse_to_fhsc"] for entry in entries if entry["ratio_dnse_to_fhsc"] is not None}
        by_field[field] = {"pair_count": len(entries), "classifications": {label: sum(row["classification"] == label for row in entries) for label in sorted(classes)},
                           "distinct_ratios": sorted(ratios), "invariant_ratio": next(iter(ratios)) if len(ratios) == 1 else None}
    comparable = [entry for entry in pairs if entry["classification"] != "NOT_COMPARABLE"]
    all_ratios = {entry["ratio_dnse_to_fhsc"] for entry in comparable}
    max_residual_1000 = max((_decimal(entry["residual_candidate_1000"]) or Decimal(0) for entry in comparable), default=Decimal(0))
    return {"pairs": pairs, "field_summary": by_field, "total_comparable_pairs": len(comparable),
            "total_pairs": len(pairs), "exact_1000_count": sum(row["classification"] == "EXACT_1000_TO_1" for row in pairs),
            "exact_1_count": sum(row["classification"] == "EXACT_1_TO_1" for row in pairs),
            "other_ratio_count": sum(row["classification"] == "OTHER_CONSTANT_RATIO" for row in pairs),
            "exceptions": [row for row in pairs if row["classification"] not in {"EXACT_1_TO_1", "EXACT_1000_TO_1"}],
            "candidate_transform_invariant_across_fields_issuers_sessions": len(all_ratios) == 1,
            "observed_ratios": sorted(all_ratios), "maximum_residual_after_candidate_x1000": str(max_residual_1000),
            "fhsc_retained_evidence": evidence}


def build_artifact(document_records: list[dict[str, Any]], dnse_rows: list[dict[str, Any]], dnse_identity: dict[str, Any],
                   fhsc_records: list[dict[str, Any]]) -> dict[str, Any]:
    docs = documentation_verdict(document_records)
    matrix = calibration_matrix(dnse_rows, fhsc_records)
    artifact = {"schema_version": VERSION, "contract_version": CALIBRATION_VERSION,
                "artifact_type": "FHSC_HISTORICAL_PRICE_SEMANTICS_QUALIFICATION", "documentation": docs,
                "official_documentation": [{key: (_portable_path(value) if key == "raw_path" else value) for key, value in record.items()} for record in document_records],
                "empirical_cohort": {"tickers": list(CALIBRATION_TICKERS), "sessions": list(SESSIONS), "dnse_evidence": dnse_identity,
                                      "scope": "retained_closed_session_only"}, "ohcl_scale_matrix": matrix,
                "normalization_contract": {"status": "NO_TRANSFORM_QUALIFIED", "provider": "FHSC", "capability": LEGACY_CAPABILITY,
                                             "reason": "PROVIDER_UNIT_UNDOCUMENTED_AND_SCALE_NOT_INVARIANT_ACROSS_OHLC_FIELDS",
                                             "authority_effect": "NONE", "allowed_uses": [], "forbidden_uses": ["market_data_authority", "valuation", "sizing", "backtests", "RAW_AS_TRADED"]},
                "remaining_unknown_semantics": {"adjustment_basis": "UNDOCUMENTED", "finalization": "UNDOCUMENTED", "volume_basis": "BASIS_UNRESOLVED"},
                "authority_boundaries": {"fhsc_promoted": False, "dnse_replaced": False, "dnse_authority_altered": False,
                                         "raw_as_traded_promoted": False, "historical_adjustment_basis_promoted": False,
                                         "liquidity_sizing_promoted": False, "provider_fundamentals_promoted": False,
                                         "runtime_or_database_mutated": False}, "authority_effect": "NONE"}
    stable = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    artifact["artifact_sha256"] = _sha256(stable.encode("utf-8"))
    artifact["artifact_identity"] = f"fhsc_historical_price_semantics:{artifact['artifact_sha256']}"
    return artifact
