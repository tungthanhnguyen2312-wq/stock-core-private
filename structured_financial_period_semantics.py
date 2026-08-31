"""Versioned, retained-only financial-period semantics projection.

This module is deliberately a projection over canonical provider facts.  It does not
calculate a financial feature, alter a canonical fact, or promote provider evidence.
In particular, a quarter label alone is never duration evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "market_wide_structured_financial_period_semantics/v1"
ARTIFACT_TYPE = "MARKET_WIDE_STRUCTURED_FINANCIAL_PERIOD_SEMANTICS"

ANNUAL = "ANNUAL"
STANDALONE_QUARTER = "STANDALONE_QUARTER"
YTD_CUMULATIVE_INTERIM = "YTD_CUMULATIVE_INTERIM"
POINT_IN_TIME_BALANCE_SHEET = "POINT_IN_TIME_BALANCE_SHEET"
UNKNOWN_DURATION = "UNKNOWN_DURATION"
SEMANTIC_STATES = (ANNUAL, STANDALONE_QUARTER, YTD_CUMULATIVE_INTERIM,
                   POINT_IN_TIME_BALANCE_SHEET, UNKNOWN_DURATION)

LINEAGE_INCOMPLETE = "FINANCIAL_REVIEW_LINEAGE_INCOMPLETE"
STATUS_BLOCKERS = {
    "partial": "SOURCE_STATUS_PARTIAL",
    "conflicted": "SOURCE_STATUS_CONFLICTED",
    "unavailable": "SOURCE_STATUS_UNAVAILABLE",
    "not_applicable": "SOURCE_STATUS_NOT_APPLICABLE",
}
FLOW_FAMILIES = frozenset({"income_statement", "cash_flow"})
REQUIRED_LINEAGE_FIELDS = ("ticker", "canonical_metric", "provider", "statement_family",
                           "reporting_period", "source_sha256", "source_file", "fact_id")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items()
               if key not in {"artifact_sha256", "artifact_identity", "generated_at", "requested_at"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _unknown(value: Any) -> bool:
    return value in (None, "", "unknown", "UNKNOWN", "UNKNOWN_FAIL_CLOSED")


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _period_state(fact: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return state, method, and evidence without duration inference from dates/labels."""
    family = fact.get("statement_family")
    if family == "balance_sheet":
        if fact.get("period_end"):
            return (POINT_IN_TIME_BALANCE_SHEET, "balance_sheet_period_end/v1", "retained_period_end")
        return (UNKNOWN_DURATION, "balance_sheet_period_end_missing/v1", "period_end_missing")
    if fact.get("period_type") == "annual":
        return (ANNUAL, "retained_native_annual_period_type/v1", "native_period_type")
    # KBS's exact retained endpoint contract established a standalone quarterly income
    # period.  It is provider+statement-family scoped, never a generic Q-label rule.
    if family == "income_statement" and fact.get("provider") == "KBS" and fact.get("period_type") == "quarterly":
        return (STANDALONE_QUARTER, "kbs_income_statement_quarter_contract/v1",
                "provider_endpoint_period_contract")
    # The existing cash-flow beginning-cash resolver records an explicit semantic state;
    # the date range only accompanies that evidence and is not used as the inference.
    if family == "cash_flow" and fact.get("cumulative_state") == "period_only" and fact.get("period_start") and fact.get("period_end"):
        return (STANDALONE_QUARTER, "retained_cash_flow_cumulative_state_resolver/v1",
                "cumulative_state_period_only_with_retained_bounds")
    if family == "cash_flow" and fact.get("cumulative_state") == "cumulative_ytd":
        return (YTD_CUMULATIVE_INTERIM, "retained_cash_flow_cumulative_state_resolver/v1",
                "cumulative_state_ytd")
    return (UNKNOWN_DURATION, "duration_evidence_unavailable/v1", "quarter_label_or_dates_not_sufficient")


def project_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Pass through one retained canonical fact with an additive semantics envelope."""
    state, method, evidence = _period_state(fact)
    missing_lineage = [name for name in REQUIRED_LINEAGE_FIELDS if _unknown(fact.get(name))]
    blockers = []
    if missing_lineage:
        blockers.append(LINEAGE_INCOMPLETE)
    status = str(fact.get("status") or "unknown")
    if status != "provider_reported":
        blockers.append(STATUS_BLOCKERS.get(status, "SOURCE_STATUS_NOT_PROVIDER_REPORTED"))
    if state == UNKNOWN_DURATION:
        blockers.append("PERIOD_DURATION_UNRESOLVED")
        if (fact.get("statement_family") == "income_statement" and fact.get("provider") is not None
                and fact.get("provider") not in {"KBS", "VCI"}):
            blockers.append("UNSUPPORTED_PROVIDER_SCHEMA_PERIOD_CONTRACT")
    source_conflicts = list(fact.get("conflicts") or [])
    if source_conflicts and "SOURCE_STATUS_CONFLICTED" not in blockers:
        blockers.append("SOURCE_CONFLICT_PRESERVED")
    unit_missing = _unknown(fact.get("currency")) or _unknown(fact.get("scale"))
    scope_missing = _unknown(fact.get("statement_scope"))
    timestamp_missing = _unknown(fact.get("observed_at"))
    return {
        "projection_contract_version": CONTRACT_VERSION,
        "ticker": fact.get("ticker"),
        "entity_type": fact.get("entity_type"),
        "canonical_metric": fact.get("canonical_metric"),
        "statement_family": fact.get("statement_family"),
        "metric_nature": "STOCK_POINT_IN_TIME" if fact.get("statement_family") == "balance_sheet" else "FLOW_DURATION" if fact.get("statement_family") in FLOW_FAMILIES else "UNKNOWN",
        "statement_scope": fact.get("statement_scope"),
        "native_period_label": fact.get("reporting_period"),
        "period_start": fact.get("period_start"),
        "period_end": fact.get("period_end"),
        "native_period_type": fact.get("period_type"),
        "period_semantic_state": state,
        "period_semantic_method": method,
        "period_semantic_evidence": evidence,
        "reported_value": fact.get("value"),
        "reported_currency": fact.get("currency"),
        "reported_scale": fact.get("scale"),
        "normalized_candidate_value": fact.get("value"),
        "normalized_candidate_unit": {"currency": fact.get("currency"), "scale": fact.get("scale")},
        "normalization_method": "PASSTHROUGH_EXISTING_CANONICAL_FACT_NO_NEW_TRANSFORM",
        "source_status": fact.get("status"),
        "source_qualification_state": fact.get("qualification_state"),
        "source_conflicts": source_conflicts,
        "source_warnings": list(fact.get("warnings") or []),
        "source_lineage": {
            "provider": fact.get("provider"), "source_file": fact.get("source_file"),
            "source_sha256": fact.get("source_sha256"), "fact_id": fact.get("fact_id"),
            "raw_item_id": fact.get("raw_item_id"), "raw_item_occurrence": fact.get("raw_item_occurrence"),
            "source_observation_ids": list(fact.get("source_observation_ids") or []),
            "raw_label_en": fact.get("raw_label_en"), "raw_label_vi": fact.get("raw_label_vi"),
        },
        "retrieval_or_observation_timestamp": fact.get("observed_at"),
        "published_timestamp": fact.get("published_at"),
        "lineage_complete": not missing_lineage,
        "missing_lineage_fields": missing_lineage,
        "metadata_missing": {"unit": unit_missing, "scope": scope_missing, "timestamp": timestamp_missing},
        "blocker_reason_codes": blockers,
        "authority_state": "OPERATIONAL_PROVIDER_FACT_NOT_AUTHORITATIVE",
        "research_semantic_state": "RESEARCH_SEMANTIC_READY" if not blockers else "RESEARCH_SEMANTIC_BLOCKED_OR_BOUNDED",
        "authoritative_financial_eligible": False,
        "pit_backtest_eligible": False,
        "is_actionable": False,
    }


def _period_key(value: Any) -> tuple[int, int] | None:
    text = str(value or "")
    if len(text) == 7 and text[4:6] == "-Q" and text[:4].isdigit() and text[6].isdigit():
        quarter = int(text[6])
        if 1 <= quarter <= 4:
            return int(text[:4]), quarter
    return None


def _unit_scope_ready(row: Mapping[str, Any]) -> bool:
    unit = row["normalized_candidate_unit"]
    return (not row["metadata_missing"]["scope"] and not row["metadata_missing"]["unit"]
            and not _unknown(unit["currency"]) and not _unknown(unit["scale"]))


def _usable(row: Mapping[str, Any], accepted: Sequence[str]) -> bool:
    return (row["source_status"] == "provider_reported" and row["lineage_complete"]
            and not row["source_conflicts"] and row["period_semantic_state"] in accepted
            and _numeric(row["reported_value"]))


def compatibility_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count compatible inputs only; never compute features or choose conflict values."""
    yoy = 0
    series: dict[tuple[Any, ...], dict[tuple[int, int], Mapping[str, Any]]] = defaultdict(dict)
    for row in records:
        if not _usable(row, (ANNUAL, STANDALONE_QUARTER)) or not _unit_scope_ready(row):
            continue
        key = (row["ticker"], row["source_lineage"]["provider"], row["canonical_metric"],
               row["statement_scope"], row["normalized_candidate_unit"]["currency"],
               row["normalized_candidate_unit"]["scale"], row["period_semantic_state"])
        period = _period_key(row["native_period_label"])
        if period:
            series[key][period] = row
    for rows in series.values():
        for year, quarter in rows:
            if (year - 1, quarter) in rows:
                yoy += 1

    margins = 0
    margins_by_key: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for row in records:
        if not _usable(row, (ANNUAL, STANDALONE_QUARTER)) or not _unit_scope_ready(row):
            continue
        key = (row["ticker"], row["source_lineage"]["provider"], row["native_period_label"],
               row["statement_scope"], row["normalized_candidate_unit"]["currency"],
               row["normalized_candidate_unit"]["scale"], row["period_semantic_state"])
        margins_by_key[key].add(str(row["canonical_metric"]))
    margins = sum(1 for metrics in margins_by_key.values() if {"revenue", "net_income"}.issubset(metrics))

    trajectory = 0
    balance_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        if not _usable(row, (POINT_IN_TIME_BALANCE_SHEET,)) or row["metadata_missing"]["scope"]:
            continue
        key = (row["ticker"], row["source_lineage"]["provider"], row["canonical_metric"],
               row["statement_scope"], row["source_lineage"]["source_sha256"])
        balance_groups[key].append(row)
    for rows in balance_groups.values():
        periods = {row["period_end"] for row in rows if row["period_end"]}
        trajectory += max(0, len(periods) - 1)

    blocked = sum(1 for row in records if row["blocker_reason_codes"])
    return {
        "same_period_yoy_compatible_candidate_count": yoy,
        "period_margin_compatible_candidate_count": margins,
        "point_in_time_balance_trajectory_compatible_candidate_count": trajectory,
        "blocked_or_unresolved_fact_count": blocked,
        "no_feature_values_calculated": True,
    }


def _coverage(records: Sequence[Mapping[str, Any]], input_count: int) -> dict[str, Any]:
    by = lambda selector: dict(sorted(Counter(selector(row) for row in records).items()))
    provider_tickers: dict[str, set[str]] = defaultdict(set)
    for row in records:
        provider_tickers[str(row["source_lineage"]["provider"])].add(str(row["ticker"]))
    missing = Counter()
    for row in records:
        for key, value in row["metadata_missing"].items():
            if value:
                missing[key] += 1
    return {
        "input_fact_count": input_count, "emitted_fact_count": len(records),
        "zero_silent_drops": input_count == len(records),
        "ticker_count": len({row["ticker"] for row in records if row["ticker"]}),
        "provider_distribution": by(lambda row: str(row["source_lineage"]["provider"])),
        "provider_ticker_distribution": {provider: len(tickers) for provider, tickers in sorted(provider_tickers.items())},
        "metric_family_distribution": by(lambda row: str(row["canonical_metric"])),
        "semantic_state_distribution": by(lambda row: row["period_semantic_state"]),
        "statement_type_distribution": by(lambda row: str(row["statement_family"])),
        "scope_distribution": by(lambda row: str(row["statement_scope"])),
        "unresolved_duration_count": sum(row["period_semantic_state"] == UNKNOWN_DURATION for row in records),
        "missing_metadata_distribution": dict(sorted(missing.items())),
        "missing_currency_count": sum(_unknown(row["normalized_candidate_unit"]["currency"]) for row in records),
        "missing_scale_count": sum(_unknown(row["normalized_candidate_unit"]["scale"]) for row in records),
        "lineage_incomplete_count": sum(not row["lineage_complete"] for row in records),
        "conflict_preserved_count": sum(bool(row["source_conflicts"]) for row in records),
    }


def build_artifact(*, facts: Iterable[Mapping[str, Any]], source_contract: Mapping[str, Any], requested_at: str) -> dict[str, Any]:
    source_rows = list(facts)
    records = [project_fact(row) for row in source_rows]
    examples: dict[str, Mapping[str, Any]] = {}
    for row in records:
        examples.setdefault(row["period_semantic_state"], {
            "ticker": row["ticker"], "canonical_metric": row["canonical_metric"],
            "metric_nature": row["metric_nature"], "statement_family": row["statement_family"],
            "period_end": row["period_end"], "period_semantic_state": row["period_semantic_state"],
            "period_semantic_method": row["period_semantic_method"], "blocker_reason_codes": row["blocker_reason_codes"],
        })
    blockers = Counter(code for row in records for code in row["blocker_reason_codes"])
    rules = sorted({(row["period_semantic_method"], row["period_semantic_evidence"]) for row in records})
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "requested_at": requested_at, "source_contract": dict(source_contract), "records": records,
        "input_artifact_identities": {
            "canonical_fact_id_sequence_sha256": _hash([row.get("fact_id") for row in source_rows]),
            "canonical_contract_versions": dict(sorted(Counter(str(row.get("contract_version")) for row in source_rows).items())),
        },
        "coverage": _coverage(records, len(source_rows)), "compatibility": compatibility_counts(records),
        "unresolved_blocker_distribution": dict(sorted(blockers.items())),
        "provider_schema_rules_actually_used": [
            {"method": method, "evidence": evidence} for method, evidence in rules
        ],
        "representative_stock_flow_examples": [examples[key] for key in SEMANTIC_STATES if key in examples],
        "semantic_rules": {
            "states": list(SEMANTIC_STATES),
            "quarter_label_alone_is_duration_evidence": False,
            "date_range_alone_is_duration_evidence": False,
            "provider_authority_promoted": False,
            "feature_or_valuation_logic_changed": False,
        },
        "authority_boundary": {
            "projection_only": True, "authoritative_namespace_overwritten": False,
            "official_or_owner_promotion": False, "recommendation_ranking_valuation_changed": False,
            "pit_or_raw_as_traded_promoted": False,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact


def load_facts(root: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(root.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)
