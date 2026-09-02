"""Offline importer for retained ``tcbs_bank_public_company_capture/v1`` bundles.

This is deliberately an import boundary, not a TCBS client: it accepts an
already-retained public-company capture, validates it deterministically, scans
the complete raw response for private keys before mapping any value, and emits
only normalized bank research components plus non-sensitive diagnostics.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import bank_financial_research_component as component

CONTRACT_VERSION = "tcbs_bank_research_component_bundle/v1"
SOURCE_CAPTURE_CONTRACT = "tcbs_bank_public_company_capture/v1"
TCBS_PROVIDER = "TCBS_MCP"
SUPPORTED_TOOLS = frozenset({
    "getIncomeStatementForBank", "getBalanceSheetForBank", "getFinancialRatioForBank",
})
FIELD_MAPPINGS = {
    "getBalanceSheetForBank": {
        "customerLoan": ("customer_loan", component.STRUCTURED_RESEARCH_COMPONENT),
        "deposit": ("deposit", component.STRUCTURED_RESEARCH_COMPONENT),
        "nonPerformingLoan": ("non_performing_loan", component.STRUCTURED_RESEARCH_COMPONENT),
        "provision": ("provision", component.STRUCTURED_RESEARCH_COMPONENT),
        "totalAsset": ("total_asset", component.STRUCTURED_RESEARCH_COMPONENT),
        "totalDebt": ("total_debt", component.STRUCTURED_RESEARCH_COMPONENT),
        "totalEquity": ("total_equity", component.STRUCTURED_RESEARCH_COMPONENT),
    },
    "getIncomeStatementForBank": {
        "operationExpense": ("operation_expense", component.STRUCTURED_RESEARCH_COMPONENT),
        "totalOperationIncome": ("total_operation_income", component.STRUCTURED_RESEARCH_COMPONENT),
        "preProvisionOperatingProfit": ("pre_provision_operating_profit", component.STRUCTURED_RESEARCH_COMPONENT),
        "netInterestIncome": ("net_interest_income", component.STRUCTURED_RESEARCH_COMPONENT),
        "postTaxProfit": ("post_tax_profit", component.STRUCTURED_RESEARCH_COMPONENT),
    },
    "getFinancialRatioForBank": {
        "netInterestMargin": ("net_interest_margin", component.PROVIDER_DERIVED_RESEARCH_PROXY),
    },
}


class TCBSBankCaptureImportError(ValueError):
    pass


class TCBSBankCapturePrivacyError(TCBSBankCaptureImportError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tool_family(value: Any) -> str | None:
    name = _text(value)
    return next((tool for tool in SUPPORTED_TOOLS if name == tool or name.endswith(f"-{tool}") or name.endswith(f"__{tool}")), None)


def _timestamp(value: Any) -> bool:
    # Capture timestamps are provenance labels, not a clock source.  This
    # rejects absent/non-string values without silently rewriting an offset.
    return bool(_text(value))


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _period(row: Mapping[str, Any]) -> tuple[int, int, str, list[str]] | None:
    year, quarter = row.get("year"), row.get("quarter")
    if not isinstance(year, int) or isinstance(year, bool) or not isinstance(quarter, int) or isinstance(quarter, bool):
        return None
    if 1 <= quarter <= 4:
        return year, quarter, component.QUARTER, []
    if quarter == 5:
        return year, quarter, component.FISCAL_YEAR, ["TCBS_QUARTER_5_EMPIRICAL_FY_BEHAVIOR_NOT_DECLARED_CONTRACT"]
    return None


def _currency_scale(raw: Mapping[str, Any], row: Mapping[str, Any]) -> tuple[Any, Any]:
    # TCBS's known payload has no unit contract.  Retain only explicit payload
    # fields; no tool documentation, provider convention, or magnitude inference.
    return row.get("currency", raw.get("currency")), row.get("scale", raw.get("scale"))


def _diagnostic(code: str, **fields: Any) -> dict[str, Any]:
    return {"code": code, **{key: value for key, value in fields.items() if value not in (None, "")}}


def _capture_identity(tool: str, ticker: str, raw_sha: str) -> str:
    return f"TCBS_MCP_CAPTURE:{tool}:{ticker}:{raw_sha}"


def import_capture_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Validate/import one retained bundle, with no filesystem or network side effects."""
    if not isinstance(bundle, Mapping) or bundle.get("capture_contract") != SOURCE_CAPTURE_CONTRACT:
        raise TCBSBankCaptureImportError("UNSUPPORTED_CAPTURE_CONTRACT")
    captures = bundle.get("captures")
    if not isinstance(captures, Sequence) or isinstance(captures, (str, bytes, bytearray)):
        raise TCBSBankCaptureImportError("CAPTURES_SEQUENCE_REQUIRED")
    if bundle.get("bundle_sha256") is not None:
        expected = _hash({key: value for key, value in bundle.items() if key != "bundle_sha256"})
        if bundle.get("bundle_sha256") != expected:
            raise TCBSBankCaptureImportError("BUNDLE_SHA256_MISMATCH")

    # Privacy is global fail-closed: scan every raw response before any value is
    # validated, transformed, retained, or reported.  No exception contains a value.
    private_paths: list[str] = []
    for index, capture in enumerate(captures):
        if isinstance(capture, Mapping):
            private_paths.extend(f"captures[{index}]{path[1:]}" for path in component.private_field_paths(capture.get("raw_response")))
    if private_paths:
        raise TCBSBankCapturePrivacyError("PRIVATE_FIELD_REJECTED:" + ",".join(sorted(private_paths)))

    observations: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    failures = 0
    imported = 0
    seen_capture_ids: set[tuple[str, str, str]] = set()
    for index, capture in enumerate(captures):
        if not isinstance(capture, Mapping):
            failures += 1; diagnostics.append(_diagnostic("CAPTURE_NOT_MAPPING", capture_index=index)); continue
        tool, ticker = _tool_family(capture.get("tool_name")), _text(capture.get("ticker")).upper()
        if tool is None:
            diagnostics.append(_diagnostic("SKIP_UNSUPPORTED_TOOL", capture_index=index, tool_name=_text(capture.get("tool_name")))); continue
        raw, raw_sha = capture.get("raw_response"), _text(capture.get("raw_response_sha256"))
        if not ticker or not isinstance(raw, Mapping) or not raw_sha or _hash(raw) != raw_sha or not _timestamp(capture.get("captured_at")):
            failures += 1; diagnostics.append(_diagnostic("CAPTURE_INTEGRITY_FAILED", capture_index=index, ticker=ticker, tool=tool)); continue
        capture_key = (tool, ticker, raw_sha)
        if capture_key in seen_capture_ids:
            diagnostics.append(_diagnostic("DUPLICATE_CAPTURE_IDENTITY", ticker=ticker, tool=tool)); continue
        seen_capture_ids.add(capture_key)
        rows = raw.get("result")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
            failures += 1; diagnostics.append(_diagnostic("MALFORMED_RESULT_ENVELOPE", ticker=ticker, tool=tool)); continue
        source_identity = _capture_identity(tool, ticker, raw_sha)
        for row_index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                diagnostics.append(_diagnostic("ROW_NOT_MAPPING", ticker=ticker, tool=tool, row_index=row_index)); continue
            if _text(row.get("ticker")).upper() != ticker:
                diagnostics.append(_diagnostic("ROW_TICKER_MISMATCH", ticker=ticker, tool=tool, row_index=row_index)); continue
            period = _period(row)
            if period is None:
                diagnostics.append(_diagnostic("ROW_PERIOD_INVALID", ticker=ticker, tool=tool, row_index=row_index)); continue
            year, quarter, period_kind, limitations = period
            for provider_field, (metric_id, fitness) in FIELD_MAPPINGS[tool].items():
                value = row.get(provider_field)
                if value is None:
                    diagnostics.append(_diagnostic("MISSING_VALUE", ticker=ticker, metric_id=metric_id, year=year, quarter=quarter)); continue
                if not _numeric(value):
                    diagnostics.append(_diagnostic("NON_NUMERIC_VALUE", ticker=ticker, metric_id=metric_id, year=year, quarter=quarter)); continue
                currency, scale = _currency_scale(raw, row)
                observation = component.build_observation(
                    provider=TCBS_PROVIDER, ticker=ticker, entity_type="bank", year=year, quarter=quarter,
                    period_kind=period_kind, period_semantics_status=component.EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS,
                    metric_id=metric_id, raw_value=value, source_identity=source_identity,
                    retrieved_at=_text(capture.get("captured_at")), fitness=fitness, currency=currency, scale=scale,
                    limitations=limitations, source_payload=raw,
                )
                observation.update({"capture_tool": tool, "capture_identity": source_identity,
                                    "provider_timestamp": capture.get("provider_timestamp"),
                                    "provider_source_reference": capture.get("provider_source_reference")})
                observation.update(component.content_identity(observation))
                observations.append(observation)
        imported += 1

    # Exact observation duplicates share one capture identity/value and are retained once.
    unique: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for observation in observations:
        identity = observation["component_identity"]
        if identity in unique:
            duplicate_count += 1
        else:
            unique[identity] = observation
    observations = list(unique.values())
    if duplicate_count:
        diagnostics.append(_diagnostic("EXACT_OBSERVATION_DUPLICATE_DEDUPED", count=duplicate_count))

    conflicts: list[dict[str, Any]] = []
    by_metric: dict[tuple[str, str, int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        by_metric[(observation["provider"], observation["ticker"], observation["year"], observation["quarter"], observation["metric_id"])].append(observation)
    for key, members in by_metric.items():
        values = {item["raw_value"] for item in members}
        identities = sorted({item["source_identity"] for item in members})
        if len(values) > 1 and len(identities) > 1:
            conflict = {"code": "CAPTURE_VALUE_CONFLICT", "provider": key[0], "ticker": key[1], "year": key[2],
                        "quarter": key[3], "metric_id": key[4], "source_identities": identities}
            conflicts.append(conflict)
            for item in members:
                item["conflict_status"] = "CAPTURE_VALUE_CONFLICT"
                item.update(component.content_identity(item))

    observations.sort(key=lambda x: (x["ticker"], x["year"], x["quarter"], x["metric_id"], x["source_identity"]))
    diagnostics.sort(key=lambda x: _canonical(x))
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "source_capture_contract": SOURCE_CAPTURE_CONTRACT,
        "source_capture_identity": bundle.get("bundle_sha256") or "BUNDLE_IDENTITY_NOT_PROVIDED",
        "tickers": sorted({item["ticker"] for item in observations}), "captures_seen": len(captures),
        "captures_imported": imported, "captures_failed": failures, "observations": observations,
        "diagnostics": diagnostics + ([] if bundle.get("bundle_sha256") is not None else [_diagnostic("BUNDLE_IDENTITY_NOT_PROVIDED")]),
        "privacy_rejections": [], "conflicts": conflicts,
    }
    digest = _hash(artifact)
    artifact.update({"content_sha256": digest, "content_identity": f"{CONTRACT_VERSION}:{digest}"})
    return artifact


def import_capture_file(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return import_capture_bundle(json.load(handle))
