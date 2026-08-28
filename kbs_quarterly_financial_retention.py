"""Repository-owned KBS KQKD quarterly lookback and semantic-retention contract.

The contract requests bounded raw KBS pages directly, preserves their bytes and `Head`
metadata, then provides deterministic period/variant and semantic sidecars.  It does not
patch vnstock, infer financial meaning from values, or promote provider observations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

import provider_financial_source_metadata as source

CONTRACT_VERSION = "kbs_quarterly_financial_retention/v1"
KBS_QUARTERLY_INCOME_TYPE = "KQKD"
PAGE_SIZE = 8
PAGES = (1, 2)
PROOF_TICKERS = ("HPG", "CMG", "CTD", "SBT", "SLS")
SCOPE_MAP = {"hợp nhất": "CONSOLIDATED", "riêng lẻ": "STANDALONE_PARENT", "đơn lẻ": "STANDALONE_PARENT"}
HEAD_FIELDS = ("PeriodBegin", "PeriodEnd", "TermName", "TermNameEN", "ReportDate", "LastUpdate",
               "United", "AuditedStatus", "YearPeriod", "Currency")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def plan_for_tickers(tickers: Iterable[str]) -> list[dict[str, Any]]:
    names = sorted({str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()})
    return [{
        "provider": "KBS", "ticker": ticker, "statement_family": "income_statement",
        "request_mode": "quarterly", "endpoint_contract": "KBS_FINANCE_INFO_KQKD_QUARTER_PAGED_V1",
        "url": f"{source.KBS_URL}/{ticker}",
        "params": {"page": page, "pageSize": PAGE_SIZE, "type": KBS_QUARTERLY_INCOME_TYPE,
                   "unit": 1000, "termtype": 2, "languageid": 1},
    } for ticker in names for page in PAGES]


def fetch_raw_once(request: Mapping[str, Any]) -> dict[str, Any]:
    """Use the existing public-route header acquisition, retaining exactly one response."""
    return source.fetch_raw_once(request)


def _quarter_number(head: Mapping[str, Any]) -> int | None:
    text = " ".join(str(head.get(name) or "") for name in ("TermName", "TermNameEN"))
    match = re.search(r"(?:quý|quarter|q)\s*([1-4])\b", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def reporting_period(head: Mapping[str, Any]) -> str | None:
    try:
        year = int(str(head.get("YearPeriod") or ""))
    except ValueError:
        return None
    quarter = _quarter_number(head)
    return f"{year}-Q{quarter}" if quarter else None


def _period_bound(value: Any, *, end: bool) -> str | None:
    text = str(value or "").strip()
    try:
        # `YYYYMM` is retained raw but not normalized: the bounded proof exposes a provider
        # period/header inconsistency, so it is not safe to assume an issuer's fiscal-calendar
        # mapping from a compact token alone.  ISO dates are the only exact date contract here.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return None
        from datetime import date
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        return None


def _duration_months(head: Mapping[str, Any]) -> int | None:
    try:
        from datetime import date
        start = date.fromisoformat(_period_bound(head.get("PeriodBegin"), end=False) or "")
        end = date.fromisoformat(_period_bound(head.get("PeriodEnd"), end=True) or "")
    except (TypeError, ValueError):
        return None
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _scope(head: Mapping[str, Any], units: Mapping[str, Any]) -> tuple[str, Any]:
    code = head.get("United")
    label = units.get(str(code)) if code is not None else None
    normalized = SCOPE_MAP.get(str(label or head.get("StatementScope") or "").strip().casefold(), "UNKNOWN")
    return normalized, label


def metadata_rows(request: Mapping[str, Any], raw: Mapping[str, Any], *, raw_hash: str) -> list[dict[str, Any]]:
    """One sidecar per returned provider period, retaining exact raw metadata and variants."""
    units = {str(row.get("UnitedCode")): row.get("UnitedName") for row in raw.get("Unit", [])
             if isinstance(row, Mapping)}
    rows: list[dict[str, Any]] = []
    occurrences: Counter[str] = Counter()
    for ordinal, head in enumerate(raw.get("Head", []), 1):
        if not isinstance(head, Mapping):
            continue
        period = reporting_period(head)
        if period is None:
            continue
        occurrences[period] += 1
        scope, scope_label = _scope(head, units)
        currency_raw = head.get("Currency")
        currency = "VND" if str(currency_raw or "").strip().upper() == "VND" else "UNKNOWN"
        duration = _duration_months(head)
        # The existing approved KBS KQKD quarterly contract establishes standalone-quarter
        # flow semantics for a returned, explicitly-labelled quarter.  Period bounds refine
        # duration metadata when present; their omission by this response does not turn the
        # already-qualified endpoint contract into a label-only inference.
        covered = (request.get("params", {}).get("type") == KBS_QUARTERLY_INCOME_TYPE
                   and request.get("params", {}).get("termtype") == 2 and period is not None)
        row = {
            "contract_version": CONTRACT_VERSION, "provider": "KBS", "ticker": request["ticker"],
            "statement_family": "income_statement", "request_mode": "quarterly",
            "endpoint_contract": request["endpoint_contract"], "request_parameters": dict(request["params"]),
            "page": request["params"]["page"], "head_ordinal": ordinal,
            "reporting_period": period, "period_variant_index": occurrences[period] - 1,
            "period_start": _period_bound(head.get("PeriodBegin"), end=False),
            "period_end": _period_bound(head.get("PeriodEnd"), end=True),
            "duration_months": duration, "flow_period_basis": "STANDALONE_QUARTER" if covered else "UNKNOWN",
            "flow_period_basis_evidence": (
                "kbs_kqkd_quarter_endpoint_contract_with_provider_period_header" if covered
                else "missing_or_nonquarter_provider_period_header"),
            "provider_period_name": head.get("TermName"), "provider_period_name_en": head.get("TermNameEN"),
            "provider_period_code": head.get("YearPeriod"), "report_date": head.get("ReportDate"),
            "provider_update_date": head.get("LastUpdate"), "provider_scope_code": head.get("United"),
            "provider_scope_label": scope_label, "statement_scope": scope,
            "currency": currency, "currency_raw": currency_raw,
            # KBS's request and parser are the only proof here: 1000-unit input is multiplied
            # by 1000 before retained adapter values, producing a base-unit scale factor of 1.
            "unit_scale_factor": 1, "normalization_method": "KBS_UNIT_1000_TO_BASE_VND",
            "normalized_monetary_basis": "BASE_VND" if currency == "VND" else "UNKNOWN",
            "audit_review_code": head.get("AuditedStatus"),
            "raw_head_fields": {name: head.get(name) for name in HEAD_FIELDS},
            "raw_response_sha256": raw_hash, "source_payload_identity": raw_hash,
            "retrieved_at": request.get("retrieved_at"),
        }
        row["metadata_identity"] = identity(row)
        rows.append(row)
    return rows


def classify_period_variants(metadata: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Preserve every duplicate provider period and classify, never silently count it twice."""
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in metadata:
        grouped[(str(row.get("ticker")), str(row.get("reporting_period")))].append(row)
    result = []
    for (ticker, period), rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: (int(row.get("page", 0)), int(row.get("head_ordinal", 0))))
        result.append({"ticker": ticker, "reporting_period": period, "primary_metadata_identity": ordered[0].get("metadata_identity"),
                       "variant_metadata_identities": [row.get("metadata_identity") for row in ordered],
                       "variant_count": len(ordered), "disposition": "SINGLE_PROVIDER_PERIOD" if len(ordered) == 1 else "RESTATEMENT_VARIANTS_RETAINED"})
    return result


def reconcile_value_variants(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Classify repeated item/period values after source-row extraction, without discarding either."""
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("ticker")), str(row.get("raw_item_id")), str(row.get("reporting_period")))].append(row)
    result = []
    for key, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda row: (int(row.get("period_variant_index", 0)), str(row.get("observation_id", ""))))
        numeric = [row.get("raw_value") for row in ordered]
        disposition = ("SINGLE_OBSERVATION" if len(ordered) == 1 else
                       "EQUAL_RESTATEMENT_VARIANTS" if len(set(numeric)) == 1 else "CONFLICTING_RESTATEMENT_VARIANTS")
        result.append({"ticker": key[0], "raw_item_id": key[1], "reporting_period": key[2], "disposition": disposition,
                       "primary_observation_id": ordered[0].get("observation_id"),
                       "variant_observation_ids": [row.get("observation_id") for row in ordered], "values": numeric})
    return result


def coverage(metadata: Iterable[Mapping[str, Any]], variants: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows, variants = list(metadata), list(variants)
    by_ticker: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_ticker[str(row["ticker"])].add(str(row["reporting_period"]))
    return {"distinct_quarters_by_ticker": {ticker: len(periods) for ticker, periods in sorted(by_ticker.items())},
            "metadata_rows": len(rows), "variant_dispositions": dict(sorted(Counter(row["disposition"] for row in variants).items())),
            "flow_period_basis": dict(sorted(Counter(row["flow_period_basis"] for row in rows).items())),
            "scope": dict(sorted(Counter(row["statement_scope"] for row in rows).items())),
            "currency": dict(sorted(Counter(row["currency"] for row in rows).items()))}
