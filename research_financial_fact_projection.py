"""Fail-closed bridge from Pillar A canonical facts to historical research.

This is intentionally a projection, not a third store.  It accepts the canonical fact
records already retained in ``data/canonical-financial-facts`` and preserves their status,
period, and provenance.  Only an exact, fully-qualified corporate input set may become a
research input; ``provider_reported`` is visible but never promoted.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable, Mapping, Sequence

from canonical_conflict_decomposition import decompose_facts

VERSION = "1.0.0"
QUALIFIED = "qualified"
PROVIDER_REPORTED = "provider_reported"
CONFLICTED = "conflicted"
SUPPORTED_CORPORATE = "corporate"
SUPPORTED_BANK = "bank"
SUPPORTED_ENTITY_TYPES = frozenset({SUPPORTED_CORPORATE, SUPPORTED_BANK})

# These are the existing Phase 6A earnings/cash-conversion and capital-structure input
# identities, expressed in Pillar A's canonical vocabulary.  They are deliberately not
# relaxed for market-wide scale-out.
CORPORATE_REQUIRED_METRICS = frozenset({
    "operating_cash_flow", "net_income", "cash_and_equivalents",
    "total_interest_bearing_debt", "shareholders_equity",
})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item is not None and str(item)})
    return []


def _fact_view(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Retain identity/provenance for every fact while withholding non-qualified values."""
    status = str(fact.get("status") or "unavailable")
    return {
        "canonical_metric": fact.get("canonical_metric"),
        "status": status,
        "reason": fact.get("reason"),
        "reporting_period": fact.get("reporting_period"),
        "period_type": fact.get("period_type"),
        "period_start": fact.get("period_start"),
        "period_end": fact.get("period_end"),
        "statement_family": fact.get("statement_family"),
        "statement_scope": fact.get("statement_scope"),
        "currency": fact.get("currency"),
        "scale": fact.get("scale"),
        "unit_authority": fact.get("unit_authority"),
        "warnings": _strings(fact.get("warnings")),
        "conflicts": [dict(item) for item in fact.get("conflicts") or [] if isinstance(item, Mapping)],
        "value": fact.get("value") if status == QUALIFIED else None,
        "value_withheld": status != QUALIFIED,
        "provenance": {
            "provider": fact.get("provider"), "dialect": fact.get("dialect"),
            "raw_item_id": fact.get("raw_item_id"), "source_file": fact.get("source_file"),
            "source_sha256": fact.get("source_sha256"),
            "source_observation_ids": _strings(fact.get("source_observation_ids")),
            "observed_at": fact.get("observed_at"), "fact_id": fact.get("fact_id"),
            "identity_key": fact.get("identity_key"), "contract_version": fact.get("contract_version"),
            "mapper_version": fact.get("mapper_version"), "resolver_version": fact.get("resolver_version"),
            "citation_id": fact.get("citation_id"), "evidence_id": fact.get("evidence_id"),
        },
    }


def _research_record(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility projection for existing engines, only for an admitted fact."""
    period = str(fact.get("reporting_period") or "")
    period_type = "annual" if str(fact.get("period_type")) == "annual" else "quarter"
    year = int(period[:4]) if len(period) >= 4 and period[:4].isdigit() else None
    quarter = int(period[-1]) if "-Q" in period and period[-1:].isdigit() else None
    return {
        "canonical_metric": fact.get("canonical_metric"), "value": fact.get("value"),
        "source": "pillar_a_canonical_financial_facts", "source_field": fact.get("raw_item_id"),
        "source_statement": fact.get("statement_family"),
        "period_identity": {"fiscal_year": year, "fiscal_quarter": quarter,
                            "period_type": period_type, "period": period,
                            "period_end": fact.get("period_end")},
        "statement_scope": fact.get("statement_scope"), "currency": fact.get("currency"),
        "unit_scale": fact.get("scale"), "derivation_status": "direct" if not fact.get("derived_from") else "derived",
        "quality_state": "available", "reason": fact.get("reason"),
        "restatement_state": "unknown", "observation_ids": list(fact.get("source_observation_ids") or []),
        # Pillar A's qualified status already records official agreement, but its fact schema
        # intentionally does not invent a citation identifier. Existing Phase 6A requires one,
        # so this adapter does not claim the earnings-quality submodel is eligible until that
        # lineage contract is extended explicitly.
        "evidence": {"pillar_a_fact_id": fact.get("fact_id"), "citation_id": fact.get("citation_id"),
                     "evidence_id": fact.get("evidence_id"), "source_sha256": fact.get("source_sha256")},
    }


def build_projection(ticker: str, facts: Sequence[Mapping[str, Any]] | None, *,
                     entity_type: str | None, entity_authority: str | None) -> dict[str, Any]:
    """Project one ticker's retained canonical records without resolving any fact anew."""
    source_facts = [dict(fact) for fact in facts or [] if isinstance(fact, Mapping)]
    source_facts.sort(key=lambda fact: (str(fact.get("reporting_period") or ""),
                                        str(fact.get("canonical_metric") or ""),
                                        str(fact.get("fact_id") or "")))
    views = [_fact_view(fact) for fact in source_facts]
    statuses = Counter(str(fact.get("status") or "unavailable") for fact in source_facts)
    conflict_decomposition = decompose_facts(source_facts)
    reasons: list[str] = []
    selected_period = None
    admitted: list[dict[str, Any]] = []
    required_identity_conflict = False

    if entity_type in (None, "unknown"):
        status = "unknown"
        reasons.append("entity_type_unknown")
    elif entity_type not in SUPPORTED_ENTITY_TYPES:
        status = "not_applicable"
        reasons.append(f"entity_type_not_supported_for_existing_research:{entity_type}")
    elif entity_type == SUPPORTED_BANK:
        status = "not_applicable"
        reasons.append("bank_specific_pillar_a_research_contract_not_implemented")
    else:
        by_period: dict[str, list[dict[str, Any]]] = {}
        for fact in source_facts:
            if (fact.get("status") == QUALIFIED and fact.get("value") is not None
                    and fact.get("statement_scope") == "consolidated"
                    and fact.get("period_type") == "annual"):
                by_period.setdefault(str(fact.get("reporting_period")), []).append(fact)
        for period in sorted(by_period, reverse=True):
            candidates = by_period[period]
            by_metric: dict[str, list[dict[str, Any]]] = {}
            for fact in candidates:
                by_metric.setdefault(str(fact.get("canonical_metric")), []).append(fact)
            # A qualified sibling never resolves a separately retained conflict. Inspect all
            # records for this exact annual/consolidated semantic identity before admission.
            all_by_metric: dict[str, list[dict[str, Any]]] = {}
            for fact in source_facts:
                if (str(fact.get("reporting_period")) == period
                        and fact.get("statement_scope") == "consolidated"
                        and fact.get("period_type") == "annual"):
                    all_by_metric.setdefault(str(fact.get("canonical_metric")), []).append(fact)
            conflicting_required_identity = any(
                len(all_by_metric.get(metric, [])) != 1
                or all_by_metric[metric][0].get("status") != QUALIFIED
                or bool(all_by_metric[metric][0].get("conflicts"))
                for metric in CORPORATE_REQUIRED_METRICS if metric in all_by_metric
            )
            required_identity_conflict = required_identity_conflict or conflicting_required_identity
            if (CORPORATE_REQUIRED_METRICS <= set(by_metric)
                    and not conflicting_required_identity
                    and all(len(by_metric[name]) == 1 for name in CORPORATE_REQUIRED_METRICS)):
                selected_period = period
                qualified_set = [by_metric[name][0] for name in sorted(CORPORATE_REQUIRED_METRICS)]
                if all(fact.get("citation_id") and fact.get("evidence_id") and fact.get("source_observation_ids")
                       for fact in qualified_set):
                    admitted = [_research_record(fact) for fact in qualified_set]
                    break
                reasons.append("pillar_a_qualified_fact_lineage_not_exported")
        if admitted:
            status = "available"
        elif "pillar_a_qualified_fact_lineage_not_exported" in reasons:
            status = "unavailable"
        elif required_identity_conflict:
            status = "conflicted"
            reasons.append("qualified_research_required_metric_identity_conflicted")
        elif statuses[PROVIDER_REPORTED] and not statuses[QUALIFIED]:
            status = "provider_reported_only"
            reasons.append("provider_reported_facts_not_promoted_to_qualified_research")
        elif statuses[CONFLICTED]:
            status = "conflicted"
            reasons.append("qualified_research_input_conflicted_or_missing")
        else:
            status = "unavailable"
            reasons.append("qualified_corporate_research_metric_set_missing")

    # This exposes canonical conflict-family authority to the matrix without re-resolving a
    # source value. It deliberately does not alter the canonical fact status.
    reasons.extend(conflict_decomposition["reason_codes"])

    return {
        "schema_version": VERSION, "ticker": str(ticker).upper(),
        "source": "canonical_financial_facts", "entity_type": entity_type or "unknown",
        "entity_authority": entity_authority or "unknown", "status": status,
        "research_eligible": status == "available", "reason_codes": sorted(set(reasons)),
        "required_metrics": sorted(CORPORATE_REQUIRED_METRICS) if entity_type == SUPPORTED_CORPORATE else [],
        "selected_reporting_period": selected_period, "status_counts": dict(sorted(statuses.items())),
        "conflict_decomposition": conflict_decomposition,
        "facts": views, "research_financial_canonical": {
            "status": "available", "ticker": str(ticker).upper(), "records": admitted,
            "source_selection": "pillar_a_qualified_projection",
        } if admitted else None,
        "historical_only": True, "market_dependent": False, "is_actionable": False,
    }


def select_research_source(entry: Mapping[str, Any], projection: Mapping[str, Any] | None) -> dict[str, Any]:
    """Trusted pilot facts win; Pillar A is selected only after its own full gate passes."""
    trusted = _mapping(entry.get("financial_canonical"))
    trusted_records = trusted.get("records") if isinstance(trusted.get("records"), list) else []
    if trusted.get("status") == "available" and any(
        isinstance(record, Mapping) and record.get("quality_state") == "available"
        and record.get("value") is not None for record in trusted_records
    ):
        return {"selected_source": "financial_canonical", "status": "available",
                "reason_codes": ["existing_trusted_financial_canonical_preserved"],
                "financial_canonical": dict(trusted)}
    pillar = _mapping(projection)
    projected = _mapping(pillar.get("research_financial_canonical"))
    if pillar.get("research_eligible") is True and projected.get("status") == "available":
        return {"selected_source": "pillar_a_qualified_projection", "status": "available",
                "reason_codes": ["pillar_a_required_qualified_metrics_present"],
                "financial_canonical": dict(projected)}
    return {"selected_source": None, "status": str(pillar.get("status") or "unavailable"),
            "reason_codes": list(pillar.get("reason_codes") or ["research_financial_source_unavailable"]),
            "financial_canonical": None}


def coverage_summary(records: Iterable[Mapping[str, Any]], read_facts: Callable[[str], Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Read-only, deterministic coverage across the existing store."""
    rows = [dict(record) for record in records if isinstance(record, Mapping)]
    counters = Counter()
    statuses = Counter()
    for row in sorted(rows, key=lambda item: str(item.get("ticker") or "")):
        ticker = str(row.get("ticker") or "")
        facts = list(read_facts(ticker))
        projection = build_projection(ticker, facts, entity_type=row.get("issuer_entity_type"),
                                      entity_authority=row.get("archetype_authority"))
        counters["total_tickers"] += 1
        counters["entity_type_known_tickers"] += int(row.get("issuer_entity_type") not in (None, "unknown"))
        counters["tickers_with_at_least_one_canonical_fact"] += int(bool(facts))
        counters["tickers_with_at_least_one_qualified_fact"] += int(projection["status_counts"].get(QUALIFIED, 0) > 0)
        counters["research_eligible_tickers"] += int(projection["research_eligible"] is True)
        counters["corporate_research_eligible_tickers"] += int(
            projection["research_eligible"] is True and row.get("issuer_entity_type") == SUPPORTED_CORPORATE)
        counters["bank_research_eligible_tickers"] += int(
            projection["research_eligible"] is True and row.get("issuer_entity_type") == SUPPORTED_BANK)
        counters["provider_reported_only_tickers"] += int(projection["status"] == "provider_reported_only")
        counters["conflicted_tickers"] += int(projection["status_counts"].get(CONFLICTED, 0) > 0)
        counters["unsupported_archetype_tickers"] += int(projection["status"] == "not_applicable" and row.get("issuer_entity_type") not in (None, "unknown", SUPPORTED_BANK))
        statuses[projection["status"]] += 1
    return {"schema_version": VERSION, "coverage": dict(sorted(counters.items())),
            "projection_status_counts": dict(sorted(statuses.items())),
            "is_actionable": False}
