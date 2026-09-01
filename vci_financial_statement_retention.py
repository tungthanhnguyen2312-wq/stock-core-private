"""Bounded raw-first retention for VCI financial statements.

This is an acquisition adapter, not a semantic resolver.  It retains the provider's exact
JSON response beside a mapped wide Parquet convenience payload and records the report-level
metadata (`yearReport`, `lengthReport`, `publicDate`, `createDate`, `updateDate`) per period.
`lengthReport` is intentionally never translated into YTD or standalone duration here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

import requests

PROVIDER = "VCI"
CONTRACT_VERSION = "vci_financial_statement_retention/v1"
FAMILIES = ("income_statement", "balance_sheet", "cash_flow")
FREQUENCIES = ("quarter", "year")
_SECTION = {"income_statement": "INCOME_STATEMENT", "balance_sheet": "BALANCE_SHEET", "cash_flow": "CASH_FLOW"}
_METADATA_FIELDS = ("yearReport", "lengthReport", "publicDate", "createDate", "updateDate", "organCode", "ticker")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def period_label(record: Mapping[str, Any], *, frequency: str) -> str | None:
    """Return an identity label only; no duration semantics are inferred."""
    year = record.get("yearReport")
    if not isinstance(year, (int, float)) or isinstance(year, bool):
        return None
    year = int(year)
    if frequency == "year":
        return str(year)
    length = record.get("lengthReport")
    if not isinstance(length, (int, float)) or isinstance(length, bool) or int(length) not in (1, 2, 3, 4):
        return None
    return f"{year}-Q{int(length)}"


def period_metadata(records: list[Mapping[str, Any]], *, frequency: str) -> dict[str, dict[str, Any]]:
    """Keep one unambiguous metadata record per period, otherwise preserve conflict."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        label = period_label(record, frequency=frequency)
        if label:
            grouped.setdefault(label, []).append({key: record.get(key) for key in _METADATA_FIELDS})
    result: dict[str, dict[str, Any]] = {}
    for label, values in grouped.items():
        unique = {_canonical(value) for value in values}
        result[label] = (values[0] if len(unique) == 1 else {
            "metadata_conflict": True, "records": values,
            "reason": "MULTIPLE_VCI_REPORT_METADATA_RECORDS_FOR_PERIOD"})
    return result


def fetch_statement(ticker: str, family: str, frequency: str, *, timeout: int = 30) -> tuple[bytes, list[dict[str, Any]], Any]:
    """Fetch one declared VCI statement route and return exact bytes plus parsed rows.

    The adapter uses vnstock solely for its existing VCI session/header handling and its
    provider metric dictionary.  The financial-statement HTTP body itself is retained before
    transformation so a later parser can be replayed against the provider payload.
    """
    if family not in FAMILIES or frequency not in FREQUENCIES:
        raise ValueError("unsupported VCI financial family/frequency")
    from vnstock.explorer.vci.const import _VCIQ_URL
    from vnstock.core.utils.user_agent import get_headers
    base_url = _VCIQ_URL
    session = requests.Session()
    session.headers.update(get_headers(data_source="VCI"))
    url = f"{base_url}/v1/company/{ticker.upper()}/financial-statement"
    response = session.get(url, params={"section": _SECTION[family]}, timeout=timeout)
    response.raise_for_status()
    raw = bytes(response.content)
    payload = response.json()
    if not isinstance(payload, Mapping) or payload.get("successful") is not True:
        raise ValueError(f"VCI statement response unsuccessful:{payload.get('code') if isinstance(payload, Mapping) else 'unparseable'}")
    data = payload.get("data")
    key = "years" if frequency == "year" else "quarters"
    records = list(data.get(key) or []) if isinstance(data, Mapping) else []
    if not records or not all(isinstance(row, Mapping) for row in records):
        raise ValueError("VCI response records malformed")
    metric_response = session.get(f"{base_url}/v1/company/{ticker.upper()}/financial-statement/metrics", timeout=timeout)
    metric_response.raise_for_status()
    metric_payload = metric_response.json()
    metric_data = metric_payload.get("data") if isinstance(metric_payload, Mapping) else None
    if not isinstance(metric_data, Mapping):
        raise ValueError("VCI metric dictionary unavailable")
    field_names = {str(item.get("field")): str(item.get("titleEn") or item.get("field"))
                   for values in metric_data.values() if isinstance(values, list)
                   for item in values if isinstance(item, Mapping) and item.get("field")}
    # Map only after retaining the raw body. This convenience representation is deliberately
    # mechanical: unknown VCI fields are kept under their native code rather than dropped.
    import pandas as pd
    wide: dict[str, dict[str, Any]] = {}
    for record in records:
        label = period_label(record, frequency=frequency)
        if not label:
            continue
        for field, value in record.items():
            if field in _METADATA_FIELDS or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            item_id = re.sub(r"[^a-z0-9]+", "_", field_names.get(field, field).lower()).strip("_") or field
            wide.setdefault(item_id, {"item_id": item_id, "item": field_names.get(field, field), "item_en": field_names.get(field, field)})[label] = value
    mapped = pd.DataFrame([wide[key] for key in sorted(wide)])
    return raw, [dict(row) for row in records], mapped


def retain_statement(runtime_root: Path | str, ticker: str, family: str, frequency: str, *, execute: bool,
                     retrieved_at: str | None = None) -> dict[str, Any]:
    root = Path(runtime_root)
    raw, records, mapped = fetch_statement(ticker, family, frequency)
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_hash = _sha(raw)
    filename = f"{ticker.upper()}_{family}_{frequency}__vci.parquet"
    raw_name = f"{ticker.upper()}_{family}_{frequency}__vci.{source_hash}.raw.json"
    data_root = root / "data_bctc"
    raw_root = root / "data" / "market-wide-financials" / "vci-raw"
    metadata = {
        "contract_version": CONTRACT_VERSION, "provider": PROVIDER, "ticker": ticker.upper(),
        "statement_family": family, "reporting_frequency": frequency, "retrieved_at": retrieved_at,
        "raw_filename": raw_name, "raw_sha256": source_hash,
        "period_metadata": period_metadata(records, frequency=frequency),
        "duration_semantics": "UNKNOWN_NOT_INFERRED_FROM_LENGTH_REPORT",
    }
    if execute:
        data_root.mkdir(parents=True, exist_ok=True); raw_root.mkdir(parents=True, exist_ok=True)
        mapped = mapped.copy()
        mapped.insert(0, "ticker", ticker.upper()); mapped.insert(1, "report_type", family)
        mapped.insert(2, "source", PROVIDER); mapped.insert(3, "scraped_at", retrieved_at)
        mapped.to_parquet(data_root / filename, index=False)
        (data_root / filename).with_suffix(".metadata.json").write_text(_canonical(metadata), encoding="utf-8")
        (raw_root / raw_name).write_bytes(raw)
    return {"ticker": ticker.upper(), "statement_family": family, "reporting_frequency": frequency,
            "raw_sha256": source_hash, "raw_record_count": len(records), "period_metadata": metadata["period_metadata"],
            "execute": execute, "output": str(data_root / filename)}
