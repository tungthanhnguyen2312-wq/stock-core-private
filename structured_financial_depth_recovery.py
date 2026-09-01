"""Recover only explicit financial-statement depth from retained semantic rows.

The source corpus already carries direct VCI short- and long-term borrowing facts,
but its old derived total loses provider/file lineage.  This projection restores a
usable *derived* total only when both explicit components share every relevant
representation identity.  It neither guesses debt from liabilities nor fills any
missing component with zero.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "structured_financial_depth_context/v1"
SCHEMA_VERSION = "1.0.0"
PIT = "POINT_IN_TIME_BALANCE_SHEET"
EXPLICIT_DEBT_COMPONENTS = ("short_term_interest_bearing_debt", "long_term_interest_bearing_debt")
WORKING_CAPITAL_METRICS = ("current_assets", "current_liabilities")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items()
               if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _usable_component(row: Mapping[str, Any]) -> bool:
    lineage = row.get("source_lineage") or {}
    return (row.get("source_status") == "provider_reported" and row.get("lineage_complete") is True
            and not row.get("source_conflicts") and _numeric(row.get("reported_value"))
            and row.get("period_semantic_state") == PIT
            and all(lineage.get(name) not in (None, "", "unknown")
                    for name in ("provider", "source_file", "source_sha256", "fact_id")))


def _component_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    lineage = row["source_lineage"]
    unit = row.get("normalized_candidate_unit") or {}
    return (str(row.get("ticker") or "").upper(), str(row.get("native_period_label") or row.get("period_end") or ""),
            str(lineage.get("provider")), str(lineage.get("source_file")), str(lineage.get("source_sha256")),
            str(row.get("statement_scope")), _canonical(unit))


def _recovered_total(short: Mapping[str, Any], long: Mapping[str, Any]) -> dict[str, Any]:
    lineage = short["source_lineage"]
    value = short["reported_value"] + long["reported_value"]
    identity = {"ticker": short.get("ticker"), "canonical_metric": "total_interest_bearing_debt",
                "period": short.get("native_period_label") or short.get("period_end"),
                "provider": lineage.get("provider"), "source_file": lineage.get("source_file"),
                "source_sha256": lineage.get("source_sha256"),
                "components": [short["source_lineage"].get("fact_id"), long["source_lineage"].get("fact_id")]}
    return {
        **{key: value for key, value in short.items() if key not in {"source_lineage", "source_conflicts", "blocker_reason_codes", "reported_value", "canonical_metric"}},
        "canonical_metric": "total_interest_bearing_debt", "reported_value": value,
        "source_status": "provider_reported", "source_conflicts": [], "lineage_complete": True,
        "blocker_reason_codes": [], "recovery_status": "RECOVERED_EXPLICIT_COMPONENT_SUM",
        "recovery_reason": "EXPLICIT_SHORT_AND_LONG_TERM_BORROWINGS_SAME_PROVIDER_SOURCE_SCOPE_UNIT_PERIOD",
        "derived_from": list(EXPLICIT_DEBT_COMPONENTS),
        "source_lineage": {**dict(lineage), "fact_id": _hash(identity),
                           "raw_item_id": "derived_explicit_short_plus_long_term_borrowings",
                           "raw_item_occurrence": None,
                           "source_observation_ids": sorted(set(
                               list(short["source_lineage"].get("source_observation_ids") or [])
                               + list(long["source_lineage"].get("source_observation_ids") or []))),
                           "component_fact_ids": identity["components"]},
    }


def recover(rows: Sequence[Mapping[str, Any]], *, requested_at: str) -> dict[str, Any]:
    components: dict[tuple[str, str, str, str, str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    tickers = sorted({str(row.get("ticker") or "").upper() for row in rows if row.get("ticker")})
    existing_metrics: dict[str, set[str]] = defaultdict(set)
    retained_providers: dict[str, set[str]] = defaultdict(set)
    has_kbs_income: set[str] = set()
    has_vci_assets: set[str] = set()
    incomplete: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            existing_metrics[ticker].add(str(row.get("canonical_metric") or ""))
        lineage = row.get("source_lineage") or {}
        provider = str(lineage.get("provider") or "")
        if ticker and provider:
            retained_providers[ticker].add(provider)
        if (ticker and provider == "KBS" and row.get("canonical_metric") == "net_income"
                and _usable_component({**row, "period_semantic_state": PIT})):
            has_kbs_income.add(ticker)
        if (ticker and provider == "VCI" and row.get("canonical_metric") == "total_assets"
                and _usable_component(row)):
            has_vci_assets.add(ticker)
        if row.get("canonical_metric") not in EXPLICIT_DEBT_COMPONENTS or not _usable_component(row):
            continue
        key = _component_key(row)
        components[key][str(row["canonical_metric"])] = row
    recovered: list[dict[str, Any]] = []
    for key, found in sorted(components.items()):
        ticker = key[0]
        if set(found) == set(EXPLICIT_DEBT_COMPONENTS):
            recovered.append(_recovered_total(found[EXPLICIT_DEBT_COMPONENTS[0]], found[EXPLICIT_DEBT_COMPONENTS[1]]))
        else:
            incomplete.add(ticker)

    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recovered:
        by_ticker[str(row["ticker"]).upper()].append(row)
    records = {}
    for ticker in tickers:
        recovered_rows = by_ticker[ticker]
        missing = []
        for metric in WORKING_CAPITAL_METRICS:
            if metric not in existing_metrics[ticker]:
                missing.append({"canonical_metric": metric,
                                "disposition": ("SOURCE_EXPOSES_NOT_RETAINED" if "VCI" in retained_providers[ticker]
                                                else "SOURCE_ROUTE_DEPTH_LIMIT"),
                                "reason": ("VCI_RAW_SCHEMA_EXPOSED_FIELD_NOT_PRESENT_IN_RETAINED_WIDE_CANONICAL_CORPUS"
                                           if "VCI" in retained_providers[ticker]
                                           else "NO_RETAINED_VCI_BALANCE_SHEET_SOURCE_FOR_THIS_TICKER")})
        if not recovered_rows:
            missing.append({"canonical_metric": "total_interest_bearing_debt",
                            "disposition": "DEBT_COMPONENT_SET_INCOMPLETE" if ticker in incomplete else "RETAINED_ARTIFACT_MISSING",
                            "reason": "BOTH_EXPLICIT_SAME_PROVIDER_SHORT_AND_LONG_TERM_BORROWING_COMPONENTS_REQUIRED"})
        missing.extend([
            {"canonical_metric": "finance_lease_liabilities",
             "disposition": "SOURCE_EXPOSES_NOT_RETAINED" if "VCI" in retained_providers[ticker] else "SOURCE_ROUTE_DEPTH_LIMIT",
             "reason": "SAMPLE_VCI_SCHEMA_HAS_SHORT_AND_LONG_FINANCE_LEASE_LINES_BUT_WIDE_CANONICAL_CORPUS_DOES_NOT_RETAIN_THEM"},
            {"canonical_metric": "same_provider_roa",
             "disposition": "PROVIDER_SCOPE_SPLIT" if ticker in has_kbs_income and ticker in has_vci_assets else "RETAINED_ARTIFACT_MISSING",
             "reason": ("RETAINED_USABLE_NET_INCOME_IS_KBS_WHILE_USABLE_TOTAL_ASSETS_ARE_VCI"
                        if ticker in has_kbs_income and ticker in has_vci_assets else "NO_COMPATIBLE_SAME_PROVIDER_NET_INCOME_AND_TOTAL_ASSETS_PAIR")},
        ])
        records[ticker] = {"ticker": ticker, "recovered_canonical_facts": [
            {"canonical_metric": row["canonical_metric"], "reporting_period": row.get("native_period_label"),
             "reported_value": row["reported_value"], "provider": row["source_lineage"]["provider"],
             "source_file": row["source_lineage"]["source_file"], "source_sha256": row["source_lineage"]["source_sha256"],
             "statement_scope": row.get("statement_scope"), "unit": row.get("normalized_candidate_unit"),
             "period_semantic_state": row.get("period_semantic_state"), "fitness": "RESEARCH_SEMANTIC_READY",
             "derived_from": row["derived_from"]} for row in recovered_rows],
            "missing_components": missing}
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "requested_at": requested_at,
        "records": records,
        "coverage": {"ticker_denominator": len(tickers), "ticker_record_count": len(records),
                     "zero_silent_ticker_drops": len(tickers) == len(records),
                     "recovered_explicit_debt_fact_count": len(recovered),
                     "recovered_explicit_debt_ticker_count": len(by_ticker),
                     "debt_component_set_incomplete_ticker_count": len(incomplete),
                     "working_capital_source_exposes_not_retained_ticker_count": sum("VCI" in retained_providers[ticker] for ticker in tickers),
                     "same_provider_capital_efficiency_source_gap_ticker_count": len(has_kbs_income & has_vci_assets)},
        "capability_matrix": {
            "VCI": {"income_statement": "SOURCE_ROUTE_DEPTH_LIMIT", "balance_sheet": {
                "current_assets": "SOURCE_EXPOSES_NOT_RETAINED", "current_liabilities": "SOURCE_EXPOSES_NOT_RETAINED",
                "short_term_borrowings": "RETAINED_AND_CANONICALIZED", "long_term_borrowings": "RETAINED_AND_CANONICALIZED",
                "finance_lease_liabilities": "SOURCE_EXPOSES_NOT_RETAINED"}},
            "KBS": {"income_statement": "RETAINED_AND_CANONICALIZED", "cash_flow": {
                "operating_cash_flow": "RETAINED_AND_CANONICALIZED", "capital_expenditure": "RETAINED_AND_CANONICALIZED"},
                "balance_sheet": "SOURCE_ROUTE_DEPTH_LIMIT"},
        },
        "authority_boundary": {"retained_only": True, "new_provider": False, "financial_authority_promoted": False,
                               "cross_provider_roa_promoted": False, "fcf_fabricated": False, "is_actionable": False},
    }
    artifact.update(content_identity(artifact))
    return {"artifact": artifact, "recovered_rows": recovered}
