"""Fail-closed identity records for explicitly observed vnstock responses."""
from __future__ import annotations

import math
import re
from typing import Any, Mapping


_FREQUENCIES = {"quarter": "quarterly", "year": "annual"}
_QUARTER = re.compile(r"^\d{4}-Q[1-4](?:_\d+)?$")
_YEAR = re.compile(r"^\d{4}(?:-Năm)?$")


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return int(number) if number.is_integer() else number


def qualify_statement_identity(
    frame: Any, *, ticker: str, provider: str, library_version: str,
    method: str, parameters: Mapping[str, Any], observed_at: str,
) -> dict[str, Any]:
    """Qualify frequency only when invocation and every response period agree.

    The public KBS/VCI frames have no consolidated/separate field.  Scope is
    intentionally returned as unknown even where a provider may have a default.
    """
    period = str(parameters.get("period") or "")
    frequency = _FREQUENCIES.get(period)
    headers = [str(c) for c in getattr(frame, "columns", []) if str(c) not in {"item", "item_en", "item_id"}]
    matcher = _QUARTER if period == "quarter" else _YEAR if period == "year" else None
    valid = bool(frequency and headers and matcher and all(matcher.fullmatch(header) for header in headers))
    return {
        "ticker": ticker.upper(), "provider": provider, "library_version": library_version,
        "method": method, "parameters": dict(parameters), "observed_at": observed_at,
        "reporting_frequency": frequency if valid else "unknown",
        "frequency_quality_state": "qualified" if valid else "unqualified",
        "frequency_reason": None if valid else "invocation_and_response_period_headers_incompatible",
        "statement_scope": "unknown", "statement_scope_quality_state": "unqualified",
        "statement_scope_reason": "provider_response_has_no_consolidated_or_separate_field",
        "period_headers": headers,
    }


def qualify_capital_structure_observation(
    record: Mapping[str, Any], *, ticker: str, provider: str, library_version: str,
    method: str, parameters: Mapping[str, Any], observed_at: str,
) -> dict[str, Any]:
    """Keep current overview observations without inventing basis, unit or as-of date."""
    if str(record.get("symbol") or record.get("organ_code") or "").upper() != ticker.upper():
        raise ValueError("overview ticker mismatch")
    shares, market_cap = _number(record.get("issue_share")), _number(record.get("market_cap"))
    provenance = {"provider": provider, "library_version": library_version, "method": method,
                  "parameters": dict(parameters), "observed_at": observed_at}
    return {
        "ticker": ticker.upper(), "provenance": provenance,
        "outstanding_shares": {"value": shares, "share_basis_state": "unknown",
            "as_of_date": None, "observed_at": observed_at, "currency": None, "unit": "unknown",
            "source_field": "issue_share", "quality_state": "observed_basis_unqualified",
            "reason": "provider_does_not_identify_basic_diluted_treasury_or_effective_date"},
        "market_cap": {"value": market_cap, "as_of_date": None, "observed_at": observed_at,
            "currency": None, "unit": "unknown", "source_field": "market_cap",
            "quality_state": "observed_unit_and_as_of_unqualified",
            "reason": "provider_response_has_no_currency_unit_or_market_cap_as_of_date"},
        "timestamp_alignment": {"state": "aligned_observation_time" if shares is not None and market_cap is not None else "partial",
                                "observed_at": observed_at},
    }


def empty_identity_export() -> dict[str, Any]:
    """Truthful additive export when no hash-retained observation was ingested."""
    return {"status": "unavailable", "records": [],
            "reason": "no_persisted_qualified_financial_identity_observation"}
