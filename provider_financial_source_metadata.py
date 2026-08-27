"""Raw KBS annual response retention and narrow semantic-metadata sidecars.

The public KBS route is already the route used by vnstock's KBS Finance adapter.  This module
uses the adapter only to obtain its existing public request headers, then retains the exact HTTP
body before the adapter's JSON parser can discard ``Head``, ``Audit`` and ``Unit`` metadata.
There are no retries, delays, background work, or provider-wide inferences here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import requests

from raw_financial_observations import extract_payload, sha256_file

CONTRACT_VERSION = "provider_financial_source_metadata/v1"
KBS_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/finance-info"
KBS_ANNUAL_FAMILIES = {"income_statement": "KQKD", "cash_flow": "LCTT"}
KBS_SCOPE_LABELS = {"Hợp nhất": "consolidated", "Riêng lẻ": "separate"}
FLOW_IDENTITIES = ("revenue", "net_income", "operating_cash_flow")
FLOW_COMPARISON_STATES = ("AGREE_EXACT", "AGREE_WITH_EXPLICIT_PROVIDER_TRANSFORM", "CONFLICT",
                          "NOT_COMPARABLE_SCOPE_UNKNOWN", "NOT_COMPARABLE_UNIT_UNKNOWN",
                          "NOT_COMPARABLE_CURRENCY_UNKNOWN", "NOT_COMPARABLE_PERIOD",
                          "MISSING_PROVIDER", "MISSING_OFFICIAL")
METADATA_FIELDS = (
    "PeriodBegin", "PeriodEnd", "ReportDate", "LastUpdate", "United", "AuditedStatus",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def plan_for_tickers(tickers: Iterable[str]) -> list[dict[str, Any]]:
    """One exact raw endpoint request per ticker/family, with no hidden pagination."""
    return [
        {
            "provider": "KBS", "ticker": str(ticker).upper(), "statement_family": family,
            "request_mode": "annual", "endpoint_contract": "KBS_FINANCE_INFO_ANNUAL_PAGE_1",
            "url": f"{KBS_URL}/{str(ticker).upper()}",
            "params": ({"page": 1, "pageSize": 4, "type": report_type, "unit": 1000,
                        "termtype": 1, "languageid": 1}
                       if family != "cash_flow" else
                       {"page": 1, "pageSize": 4, "type": report_type, "unit": 1000,
                        "termtype": 1, "termType": 1, "code": str(ticker).upper()}),
        }
        for ticker in sorted({str(item).upper() for item in tickers if str(item).strip()})
        for family, report_type in KBS_ANNUAL_FAMILIES.items()
    ]


def raw_response_path(root: Path | str, request: Mapping[str, Any], response_hash: str) -> Path:
    return Path(root) / "raw" / f"{request['ticker']}_{request['statement_family']}_{response_hash}.json"


def fetch_raw_once(request: Mapping[str, Any]) -> dict[str, Any]:
    """Perform exactly one public KBS request and retain the unparsed body in the result."""
    from vnstock.explorer.kbs.financial import Finance

    client = Finance(symbol=str(request["ticker"]), period="year", show_log=False)
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        response = requests.get(str(request["url"]), headers=dict(client.headers),
                                params=dict(request["params"]), timeout=20)
        body = response.content
        result = {**request, "retrieved_at": retrieved_at, "http_status": response.status_code,
                  "raw_response_bytes": body, "raw_response_sha256": _hash_bytes(body)}
        try:
            result["raw_response"] = json.loads(body.decode("utf-8"))
            result["disposition"] = "SUCCESS" if response.ok else "HTTP_ERROR"
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["raw_response"] = None
            result["disposition"] = "NON_JSON_RESPONSE"
        return result
    except requests.RequestException as exc:
        return {**request, "retrieved_at": retrieved_at, "disposition": "TRANSPORT_ERROR",
                "error_kind": type(exc).__name__, "raw_response_bytes": None,
                "raw_response_sha256": None, "raw_response": None}


def _period_label(head: Mapping[str, Any]) -> str | None:
    year = str(head.get("YearPeriod") or "").strip()
    return year if year.isdigit() else None


def metadata_rows(request: Mapping[str, Any], raw: Mapping[str, Any], *, raw_hash: str,
                  adapter_payload_sha256: str) -> list[dict[str, Any]]:
    """Retain only source-present metadata; all unavailable fields stay explicitly unknown."""
    response = raw if isinstance(raw, Mapping) else {}
    audits = {str(row.get("AuditedStatusCode")): row.get("Description")
              for row in response.get("Audit", []) if isinstance(row, Mapping)}
    units = {str(row.get("UnitedCode")): row.get("UnitedName")
             for row in response.get("Unit", []) if isinstance(row, Mapping)}
    rows = []
    for head in response.get("Head", []):
        if not isinstance(head, Mapping) or not _period_label(head):
            continue
        period = _period_label(head)
        audited_code = head.get("AuditedStatus")
        scope_code = head.get("United")
        scope_label = units.get(str(scope_code)) if scope_code is not None else None
        source_fields = {key: head.get(key) for key in METADATA_FIELDS}
        rows.append({
            "contract_version": CONTRACT_VERSION, "provider": "KBS",
            "endpoint_contract": request["endpoint_contract"], "request_parameters": dict(request["params"]),
            "ticker": request["ticker"], "statement_family": request["statement_family"],
            "request_mode": "annual", "fiscal_period": period, "fiscal_year": period,
            "provider_period_code": head.get("YearPeriod"), "provider_period_name": head.get("TermName"),
            "period_start": head.get("PeriodBegin"), "period_end": head.get("PeriodEnd"),
            "report_date": head.get("ReportDate"), "publication_date": None,
            "provider_update_date": head.get("LastUpdate"),
            "statement_scope": head.get("StatementScope") or KBS_SCOPE_LABELS.get(scope_label),
            "provider_scope_label": scope_label, "provider_scope_code": scope_code,
            "currency": head.get("Currency") or None, "unit": None, "unit_code": None, "scale": None,
            "audit_review_status": audits.get(str(audited_code), audited_code), "audit_review_code": audited_code,
            "raw_head_fields": source_fields, "raw_response_sha256": raw_hash,
            "source_payload_identity": raw_hash, "adapter_payload_sha256": adapter_payload_sha256,
            "retrieved_at": request["retrieved_at"],
            "metadata_availability_status": "SOURCE_FIELDS_RETAINED",
            "metadata_qualification_status": "PARTIAL_NO_SCOPE_OR_CURRENCY_UNLESS_SOURCE_FIELD_PRESENT",
        })
    return rows


def adapter_dataframe_from_raw(request: Mapping[str, Any], raw: Mapping[str, Any]) -> pd.DataFrame:
    """Apply the installed adapter's parser to retained raw JSON, without another request."""
    from vnstock.explorer.kbs.financial import Finance
    if request["statement_family"] == "income_statement":
        report_key = "Kết quả kinh doanh"
    else:
        report_key = next((str(key) for key in raw.get("Content", {}) if str(key).startswith("Lưu chuyển tiền tệ")), "")
    adapter = Finance(symbol=str(request["ticker"]), period="year", show_log=False)
    return adapter._parse_financial_response(dict(raw), report_key, unit_multiplier=1000.0)


def materialize_lineage_bound_facts(request: Mapping[str, Any], raw: Mapping[str, Any], output_path: Path) -> dict[str, Any]:
    """Create a derived adapter-output payload and annual observations tied to the raw hash."""
    frame = adapter_dataframe_from_raw(request, raw)
    frame.insert(0, "ticker", request["ticker"])
    frame.insert(1, "report_type", request["statement_family"])
    frame.insert(2, "source", "KBS")
    frame.insert(3, "scraped_at", request["retrieved_at"])
    frame.to_parquet(output_path, index=False)
    payload_hash = sha256_file(output_path)
    extracted = extract_payload(frame, ticker=str(request["ticker"]), statement_family=str(request["statement_family"]),
                                reporting_frequency="year", source_file=output_path.name, source_sha256=payload_hash)
    return {"adapter_payload_sha256": payload_hash, "adapter_payload_file": output_path.name,
            "observations": extracted["observations"], "adapter_row_count": len(frame),
            "annual_observation_count": sum(x["period_type"] == "annual" for x in extracted["observations"])}


def join_metadata_exact(observations: Iterable[Mapping[str, Any]], metadata: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Attach metadata only with exact provider/ticker/family/year/derived-payload lineage."""
    index = {(m["provider"], m["ticker"], m["statement_family"], m["fiscal_period"], m["adapter_payload_sha256"]): m
             for m in metadata}
    joined = []
    for observation in observations:
        key = (observation.get("provider"), observation.get("ticker"), observation.get("statement_family"),
               observation.get("reporting_period"), observation.get("source_sha256"))
        sidecar = index.get(key)
        joined.append({"observation_id": observation["observation_id"], "lineage_key": key,
                       "metadata_joined": sidecar is not None,
                       "metadata": sidecar if sidecar is not None else None})
    return joined


def reconcile_annual_flow_facts(facts: Iterable[Mapping[str, Any]], metadata: Iterable[Mapping[str, Any]],
                                official_citations: Mapping[tuple, Mapping[str, Any]]) -> dict[str, Any]:
    """Reconcile only facts whose exact derived payload has a metadata sidecar.

    The gates intentionally use sidecar values, not canonical facts that may have inherited
    citation currency during an exact match.  Thus no numerical equality can fill source-absent
    currency/unit fields.
    """
    meta_index = {(m["provider"], m["ticker"], m["statement_family"], m["fiscal_period"], m["adapter_payload_sha256"]): m
                  for m in metadata}
    candidates = {}
    rows = []
    for fact in facts:
        metric = str(fact.get("canonical_metric"))
        if metric not in FLOW_IDENTITIES or fact.get("value") is None or not fact.get("provider"):
            continue
        key = (fact["provider"], fact["ticker"], fact["statement_family"], fact["reporting_period"], fact["source_sha256"])
        sidecar = meta_index.get(key)
        fact_key = (fact["ticker"], metric, fact["reporting_period"])
        candidates[fact_key] = fact
        citation = official_citations.get(fact_key)
        if citation is None:
            state = "MISSING_OFFICIAL"
        elif sidecar is None:
            state = "NOT_COMPARABLE_PERIOD"
        elif sidecar.get("statement_scope") is None:
            state = "NOT_COMPARABLE_SCOPE_UNKNOWN"
        elif sidecar.get("currency") is None:
            state = "NOT_COMPARABLE_CURRENCY_UNKNOWN"
        elif sidecar.get("unit") is None or sidecar.get("scale") is None:
            state = "NOT_COMPARABLE_UNIT_UNKNOWN"
        elif fact.get("value") == citation.get("value"):
            state = "AGREE_EXACT"
        else:
            state = "CONFLICT"
        rows.append({"ticker": fact["ticker"], "canonical_metric": metric, "fiscal_year": fact["reporting_period"],
                     "provider": fact["provider"], "statement_family": fact["statement_family"],
                     "classification": state, "source_metadata_joined": sidecar is not None,
                     "provider_value": fact["value"], "official_value": citation.get("value") if citation else None})
    for (ticker, metric, period), citation in official_citations.items():
        if metric in FLOW_IDENTITIES and (ticker, metric, period) not in candidates:
            rows.append({"ticker": ticker, "canonical_metric": metric, "fiscal_year": period, "provider": None,
                         "statement_family": None, "classification": "MISSING_PROVIDER", "source_metadata_joined": False,
                         "provider_value": None, "official_value": citation.get("value")})
    rows.sort(key=lambda row: (row["ticker"], row["canonical_metric"], row["fiscal_year"], row["provider"] or ""))
    counts = {state: sum(row["classification"] == state for row in rows) for state in FLOW_COMPARISON_STATES}
    return {"contract_version": CONTRACT_VERSION, "comparisons": rows, "counts": counts,
            "residual": len(rows) - sum(counts.values()), "residual_zero": len(rows) == sum(counts.values())}
