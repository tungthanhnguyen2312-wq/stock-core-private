"""Deterministic annual-provider replay and bounded annual acquisition support.

This module deliberately has no scheduler, retry, delay, or database behaviour.  It keeps the
historical ``data_bctc`` annual files separate from quarterly files and emits an additive,
versioned evidence bundle.  The optional acquisition helper makes *one* adapter call for each
approved (ticker, provider, statement-family) request in its supplied plan.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from canonical_financial_facts import build_facts
from raw_financial_observations import extract_payload_file, parse_payload_name, sha256_file

CONTRACT_VERSION = "annual_provider_financial_retention/v1"
APPROVED_ROUTE = {
    "income_statement": "KBS",
    "cash_flow": "KBS",
    "balance_sheet": "VCI",
}
TARGET_FAMILIES = tuple(APPROVED_ROUTE)
COMPARISON_STATES = (
    "AGREE_EXACT", "AGREE_WITH_EXPLICIT_PROVIDER_SCALE_TRANSFORM", "CONFLICT",
    "NOT_COMPARABLE", "MISSING_PROVIDER_ANNUAL", "MISSING_OFFICIAL_ANCHOR",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def annual_payload_paths(root: Path | str) -> list[Path]:
    """Return only correctly named annual parquet payloads, in deterministic order."""
    result: list[Path] = []
    for path in sorted(Path(root).glob("*_*.parquet"), key=lambda item: item.name):
        try:
            identity = parse_payload_name(path.stem)
        except ValueError:
            continue
        if identity["reporting_frequency"] == "year":
            result.append(path)
    return result


def request_plan(tickers: Iterable[str]) -> list[dict[str, str]]:
    """The exact approved annual request budget: one request per ticker/family."""
    return [
        {
            "ticker": str(ticker).upper(), "provider": APPROVED_ROUTE[family],
            "statement_family": family, "period": "year",
            "endpoint_contract": f"Finance(source={APPROVED_ROUTE[family]!r}, symbol=<ticker>).{family}(period='year')",
        }
        for ticker in sorted({str(item).upper() for item in tickers if str(item).strip()})
        for family in TARGET_FAMILIES
    ]


def _payload_metadata(extracted: Mapping[str, Any], *, endpoint_contract: str | None = None) -> list[dict[str, Any]]:
    """Expand annual observations without inventing provider metadata.

    Calendar bounds are explicitly derived from the provider's annual column identity; all
    unavailable provider metadata remains ``None`` / ``unknown`` rather than guessed.
    """
    rows = []
    for observation in extracted["observations"]:
        if observation["period_type"] != "annual":
            continue
        year = str(observation["reporting_period"])
        provider = observation.get("provider")
        transform = (
            "vnstock_kbs_unit_1000_then_times_1000_before_dataframe_return"
            if provider == "KBS" else "identity_provider_dataframe_value"
        )
        rows.append({
            "contract_version": CONTRACT_VERSION,
            "ticker": observation["ticker"], "provider": provider,
            "endpoint_contract": endpoint_contract,
            "statement_family": observation["statement_family"],
            "fiscal_year": year if year.isdigit() else None,
            "reporting_period": year,
            "period_start": f"{year}-01-01" if year.isdigit() else None,
            "period_end": f"{year}-12-31" if year.isdigit() else None,
            "period_bounds_provenance": "derived_from_annual_reporting_period_column",
            "report_date": None, "publication_date": None, "provider_update_date": None,
            "statement_scope": observation.get("statement_scope", "unknown"),
            "currency": observation.get("raw_currency"), "unit": observation.get("raw_scale"),
            "scale": observation.get("raw_scale"), "audit_review_metadata": None,
            "raw_field_identity": observation["raw_item_id"], "raw_label_vi": observation.get("raw_label_vi"),
            "raw_label_en": observation.get("raw_label_en"),
            "provider_native_value": observation["raw_value"],
            "transform_method": transform, "normalized_value": None,
            "retrieved_at": observation.get("scraped_at"), "source_file": observation["source_file"],
            "source_hash": observation["source_sha256"], "payload_hash": observation["source_sha256"],
            "observation_id": observation["observation_id"], "mapped_canonical_identity": None,
            "metadata_availability": {
                "report_date": "not_exposed_in_retained_dataframe",
                "publication_date": "not_exposed_in_retained_dataframe",
                "provider_update_date": "not_exposed_in_retained_dataframe",
                "statement_scope": "not_exposed_in_retained_dataframe",
                "currency_unit_scale": "not_exposed_in_retained_dataframe",
                "audit_review": "not_exposed_in_retained_dataframe",
            },
        })
    return rows


def replay_annual_payloads(payload_root: Path | str, *, official_citations: Mapping[tuple, Mapping[str, Any]],
                           profiles: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read annual payload bytes only; this never writes or consults quarterly payloads."""
    payloads = []
    observations = []
    facts = []
    for path in annual_payload_paths(payload_root):
        extracted = extract_payload_file(path)
        payloads.append({
            "source_file": path.name, "source_hash": sha256_file(path),
            "ticker": extracted["ticker"], "provider": extracted["provider"],
            "statement_family": extracted["statement_family"], "reporting_frequency": "year",
            "retrieved_at": extracted["scraped_at"], "observation_count": len(extracted["observations"]),
        })
        observations.extend(_payload_metadata(extracted))
        built = build_facts(extracted["ticker"], extracted["observations"],
                            applicability=None, official_citations=official_citations)
        for fact in built["facts"]:
            if fact.get("period_type") != "annual":
                continue
            facts.append({
                **fact,
                "provider_native_value": fact.get("value"),
                "transform_method": (
                    "vnstock_kbs_unit_1000_then_times_1000_before_dataframe_return"
                    if fact.get("provider") == "KBS" else "identity_provider_dataframe_value"
                ),
                "canonical_value": fact.get("value"),
            })
    observations.sort(key=lambda row: (row["ticker"], row["statement_family"], row["reporting_period"], row["observation_id"]))
    facts.sort(key=lambda row: (row["ticker"], row["statement_family"], row["reporting_period"], row["canonical_metric"], row["fact_id"]))
    return {
        "contract_version": CONTRACT_VERSION, "payloads": payloads, "observations": observations,
        "facts": facts, "payload_count": len(payloads), "annual_observation_count": len(observations),
        "annual_canonical_fact_count": len(facts),
        "replay_identity": _sha({"payloads": payloads, "observations": observations, "facts": facts}),
    }


def reconcile_annual_facts(annual_facts: Iterable[Mapping[str, Any]],
                           official_citations: Mapping[tuple, Mapping[str, Any]]) -> dict[str, Any]:
    """Classify all annual candidates; unknown scope/unit never becomes numerical agreement."""
    rows = []
    actual_provider = {(str(f["ticker"]).upper(), str(f["canonical_metric"]), str(f["reporting_period"]))
                       for f in annual_facts if f.get("canonical_metric") and f.get("provider") and f.get("value") is not None}
    official_keys = {(str(k[0]).upper(), str(k[1]), str(k[2])) for k in official_citations}
    for fact in annual_facts:
        if not fact.get("provider") or fact.get("value") is None:
            continue
        key = (str(fact["ticker"]).upper(), str(fact["canonical_metric"]), str(fact["reporting_period"]))
        citation = official_citations.get(key)
        if citation is None:
            state, reason = "MISSING_OFFICIAL_ANCHOR", "no annual official anchor for same ticker/identity/year"
        elif fact.get("statement_scope") in (None, "unknown", "UNKNOWN"):
            state, reason = "NOT_COMPARABLE", "provider statement scope is not evidenced"
        elif fact.get("currency") not in (citation.get("currency"), "VND") or fact.get("scale") not in (citation.get("scale"), "units"):
            state, reason = "NOT_COMPARABLE", "provider currency/unit basis is not explicitly compatible"
        elif fact.get("value") == citation.get("value"):
            state, reason = "AGREE_EXACT", "aligned annual value matches"
        else:
            state, reason = "CONFLICT", "aligned annual provider and official values differ"
        rows.append({"ticker": key[0], "canonical_metric": key[1], "fiscal_year": key[2],
                     "provider": fact.get("provider"), "statement_family": fact.get("statement_family"),
                     "classification": state, "reason": reason, "provider_value": fact.get("value"),
                     "official_value": citation.get("value") if citation else None})
    for key in sorted(official_keys - actual_provider):
        rows.append({"ticker": key[0], "canonical_metric": key[1], "fiscal_year": key[2],
                     "provider": None, "statement_family": None, "classification": "MISSING_PROVIDER_ANNUAL",
                     "reason": "no retained annual provider fact for same ticker/identity/year",
                     "provider_value": None, "official_value": official_citations[key].get("value")})
    rows.sort(key=lambda row: (row["ticker"], row["canonical_metric"], row["fiscal_year"], row["provider"] or ""))
    counts = {state: sum(row["classification"] == state for row in rows) for state in COMPARISON_STATES}
    return {"contract_version": CONTRACT_VERSION, "comparisons": rows, "counts": counts,
            "residual": len(rows) - sum(counts.values()), "residual_zero": len(rows) == sum(counts.values())}


def acquire_annual_once(plan: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    """Issue the plan literally: no retry/failover/delay and no secret-bearing logging."""
    from vnstock.api.financial import Finance
    results = []
    for request in plan:
        ticker, provider, family = request["ticker"], request["provider"], request["statement_family"]
        try:
            frame = getattr(Finance(source=provider, symbol=ticker), family)(period="year")
            if frame is None or len(frame) == 0:
                results.append({**request, "disposition": "EMPTY", "adapter_payload": None})
            else:
                results.append({**request, "disposition": "SUCCESS", "adapter_payload": frame})
        except Exception as exc:
            results.append({**request, "disposition": "ERROR", "error_kind": type(exc).__name__, "adapter_payload": None})
    return results
