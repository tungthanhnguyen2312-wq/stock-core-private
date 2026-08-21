"""Retain a bounded DNSE raw OHLC cohort and build uniform closed-session anchors."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_access import BASE_URL, auth_headers, credentials_for_request
from dnse_closed_session_ohlc_representation import (  # noqa: E402
    CONTRACT_VERSION, FIELDS, IDENTITY_TRANSFORMATION, parse_raw_ohlc_bytes, uniform_anchor,
)
from dnse_market_data import resolve_endpoint  # noqa: E402
from dnse_secrets_env import ensure_credentials_loaded  # noqa: E402
from fhsc_retained_live_reconciliation import parse_retained_history  # noqa: E402
from provider_reference_reconciliation import (  # noqa: E402
    BASIS_UNRESOLVED, CLOSED_SESSION_OBSERVATION, SHADOW_REFERENCE_PROVIDER,
    provider_reference_observation, reconcile_observations,
)


TICKERS = ("HPG", "VCB", "SSI")
SESSION = "2026-08-20"
VN_TZ = timezone(timedelta(hours=7))
OUTPUT = ROOT / "operations-review" / "dnse-uniform-ohlc-anchor-qualification-v1-20260821"
FHSC_ARTIFACT = ROOT / "operations-review" / "fhsc-dnse-retained-live-reconciliation-v1-20260821" / "fhsc_dnse_retained_live_reconciliation_artifact.json"


def _query(ticker: str) -> dict[str, Any]:
    day = datetime.fromisoformat(SESSION).date()
    start = datetime.combine(day, time.min, VN_TZ)
    end = datetime.combine(day + timedelta(days=1), time.min, VN_TZ) - timedelta(seconds=1)
    return {"symbol": ticker, "resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}


def _fetch_raw_bytes(ticker: str, credentials: tuple[str, str]) -> dict[str, Any]:
    path = resolve_endpoint("ohlc", None)
    query = _query(ticker)
    response = requests.get(f"{BASE_URL}{path}", params=query, headers=auth_headers(credentials[0], credentials[1], "GET", path), timeout=(5, 15))
    raw = bytes(response.content)
    return {"ticker": ticker, "endpoint": path, "query": query, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "http_status": int(response.status_code), "mime_type": response.headers.get("Content-Type"), "raw_bytes": raw,
            "raw_sha256": hashlib.sha256(raw).hexdigest()}


def _fhsc_records() -> dict[str, dict[str, Any]]:
    payload = json.loads(FHSC_ARTIFACT.read_text(encoding="utf-8"))
    records = {}
    for record in payload["request_records"]:
        if record.get("endpoint_capability") != "price_histories_chart_1d":
            continue
        restored = dict(record)
        restored["raw_path"] = ROOT / restored["raw_path"]
        parsed = parse_retained_history(restored)
        records[record["symbol"]] = {"record": restored, "parsed": parsed}
    return records


def _fhsc_observation(ticker: str, field: str, record: Mapping[str, Any], parsed: Mapping[str, Any]) -> dict[str, Any] | None:
    row = next((item for item in parsed.get("rows", []) if item.get("session") == SESSION), None)
    if not isinstance(row, Mapping):
        return None
    return provider_reference_observation(
        provider="FHSC", provider_interface="fhsc_open_api_tier1", endpoint_capability="price_histories_chart_1d",
        instrument=ticker, exchange=None, session=SESSION, event_time=row.get("event_time"), retrieval_time=record.get("retrieval_time"),
        field=field, raw_value=row.get(field), normalized_value=None, unit="UNSPECIFIED_PRICE_UNIT",
        basis="ADJUSTMENT_AND_PRICE_UNIT_UNSPECIFIED_BY_PUBLISHED_CONTRACT", semantic_status=BASIS_UNRESOLVED,
        finalization_status=CLOSED_SESSION_OBSERVATION, source_payload_identity=f"fhsc_retained:{record['raw_sha256']}",
        source_payload_sha256=record["raw_sha256"], provenance={"retained_raw_path": str(record["raw_path"].relative_to(ROOT)).replace("\\", "/")},
        source_role=SHADOW_REFERENCE_PROVIDER,
    )


def _dnse_observation(anchor: Mapping[str, Any], field: str) -> dict[str, Any]:
    item = anchor["fields"][field]
    return provider_reference_observation(
        provider="DNSE", provider_interface="dnse_openapi_retained_raw", endpoint_capability="ohlc_1d",
        instrument=anchor["instrument"], exchange=None, session=anchor["session"], event_time=None,
        retrieval_time=anchor["source_evidence"]["retrieved_at"], field=field, raw_value=item["raw_numeric_value"],
        normalized_value=item["normalized_numeric_value"], unit="UNSPECIFIED_PRICE_UNIT",
        basis="ADJUSTMENT_BASIS_UNDOCUMENTED_FOR_THIS_ANCHOR", semantic_status=BASIS_UNRESOLVED,
        finalization_status=CLOSED_SESSION_OBSERVATION, source_payload_identity=anchor["source_evidence"]["source_payload_identity"],
        source_payload_sha256=anchor["source_evidence"]["raw_sha256"], provenance={"raw_path": anchor["source_evidence"]["raw_path"], "transformation_identity": IDENTITY_TRANSFORMATION},
        source_role="PRIMARY_CANDIDATE",
    )


def _stable_artifact(value: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return value | {"artifact_sha256": digest, "artifact_identity": f"dnse_uniform_ohlc_anchor_qualification:{digest}"}


def main() -> int:
    status = ensure_credentials_loaded()
    if not status["configured"]:
        raise SystemExit("DNSE_CREDENTIAL_INJECTION_REQUIRED")
    credentials = credentials_for_request()
    assert credentials is not None
    OUTPUT.mkdir(parents=True, exist_ok=False)
    raw_root = OUTPUT / "raw"
    raw_root.mkdir()
    request_records, anchors = [], []
    for ticker in TICKERS:
        try:
            response = _fetch_raw_bytes(ticker, credentials)
        except requests.RequestException as error:
            request_records.append({"ticker": ticker, "status": "TRANSPORT_FAILURE", "error_type": type(error).__name__})
            continue
        raw_path = raw_root / f"{ticker}_ohlc_{response['raw_sha256'][:16]}.json"
        raw_path.write_bytes(response.pop("raw_bytes"))
        record = response | {"raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"), "source_payload_identity": f"dnse_retained_raw:{response['raw_sha256']}"}
        request_records.append(record)
        if record["http_status"] != 200:
            continue
        parsed = parse_raw_ohlc_bytes(raw_path.read_bytes(), instrument=ticker, session=SESSION)
        anchor = uniform_anchor(parsed, source=record)
        anchors.append(anchor)
    fhsc = _fhsc_records()
    replay = []
    for anchor in anchors:
        if anchor.get("status") != "UNIFORM_REPRESENTATION_READY":
            continue
        source = fhsc.get(anchor["instrument"], {})
        for field in FIELDS:
            dnse = _dnse_observation(anchor, field)
            challenger = _fhsc_observation(anchor["instrument"], field, source.get("record", {}), source.get("parsed", {}))
            raw_equal = challenger is not None and dnse["raw_value"] == challenger["raw_value"]
            replay.append({"instrument": anchor["instrument"], "session": SESSION, "field": field,
                           "raw_to_raw_numeric_equal": raw_equal, "normalized_to_normalized_available": False,
                           "provider_reference_reconciliation": reconcile_observations([dnse, challenger] if challenger else [dnse])})
    artifact = _stable_artifact({
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": "DNSE_UNIFORM_OHLC_ANCHOR_QUALIFICATION",
        "request_budget": {"maximum": 6, "used": len(request_records), "per_ticker_max": 2, "retry_count": 0},
        "p3f9b_root_cause_trace": {"status": "SUPERSEDED_FOR_RECONCILIATION", "close_transform": "float(provider_close) * 1000.0", "ohl_transform": "identity", "root_cause": "MIXED_SOURCE_REPRESENTATION_DEFECT"},
        "uniform_ohlc_contract": {"version": CONTRACT_VERSION, "all_fields": list(FIELDS), "transformation_identity": IDENTITY_TRANSFORMATION,
                                  "unit_verdict": "EMPIRICALLY_UNIFORM_REPRESENTATION_UNIT_UNDOCUMENTED", "formal_price_unit_authority": "NOT_QUALIFIED"},
        "request_records": request_records, "corrected_dnse_anchors": anchors, "fhsc_replay": replay,
        "excluded_observations": [anchor for anchor in anchors if anchor.get("status") != "UNIFORM_REPRESENTATION_READY"],
        "authority_boundaries": {"authority_effect": "NONE", "raw_as_traded_promoted": False, "adjustment_basis_qualified": False,
                                 "fhsc_promoted": False, "dnse_replaced": False, "runtime_or_database_mutated": False},
    })
    (OUTPUT / "dnse_uniform_ohlc_anchor_qualification_artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
