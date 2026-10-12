"""Deterministic, read-only explanation of Pillar A canonical fact conflicts.

This is deliberately a projection over retained canonical facts, not a resolver that chooses
between values.  The canonical builder remains the only authority that can establish a fact's
status.  In particular, an unresolved period variant or a cross-statement incompatibility stays
``conflicted``; this module makes its semantic blocker visible downstream.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"

# The names are stable downstream reason codes.  Each is an existing canonical conflict kind,
# classified without inspecting value magnitude or a wall clock.
_RULES = {
    "cash_flow_period_attribution_unverified": {
        "family": "cross_statement_period_or_scope_unverified",
        "reason_code": "CANONICAL_CASH_FLOW_PERIOD_OR_SCOPE_UNVERIFIED",
        "resolution": "blocked",
        "authority_rule": "cash_flow_requires_balance_sheet_end_cash_agreement",
        "resolution_reason": "retained balance-sheet and cash-flow values are incompatible for the stated period",
    },
    "restated_period_column_disagrees": {
        "family": "restatement_identity_ambiguous",
        "reason_code": "CANONICAL_RESTATED_PERIOD_IDENTITY_AMBIGUOUS",
        "resolution": "blocked",
        "authority_rule": "restatement_requires_explicit_source_supersession",
        "resolution_reason": "duplicate period columns differ but retained provenance has no supersession identity",
    },
    "balance_sheet_identity_violated": {
        "family": "balance_sheet_arithmetic_violation",
        "reason_code": "CANONICAL_BALANCE_SHEET_IDENTITY_VIOLATED",
        "resolution": "blocked",
        "authority_rule": "balance_sheet_assets_equal_liabilities_plus_equity",
        "resolution_reason": "retained balance-sheet arithmetic does not reconcile",
    },
    "revenue_occurrences_do_not_reconcile_with_deductions": {
        "family": "revenue_semantic_identity_unreconciled",
        "reason_code": "CANONICAL_REVENUE_SEMANTIC_IDENTITY_UNRECONCILED",
        "resolution": "blocked",
        "authority_rule": "revenue_net_of_deductions_must_reconcile",
        "resolution_reason": "retained gross, deduction, and candidate net rows do not reconcile",
    },
    "equal_priority_candidates_disagree": {
        "family": "provider_or_candidate_disagreement",
        "reason_code": "CANONICAL_FACT_PROVIDER_CONFLICT",
        "resolution": "blocked",
        "authority_rule": "no_majority_vote_or_candidate_tiebreak",
        "resolution_reason": "equal-priority candidate values differ without an existing authority rule",
    },
    "official_citation_disagrees": {
        "family": "official_provider_disagreement",
        "reason_code": "CANONICAL_FACT_OFFICIAL_PROVIDER_CONFLICT",
        "resolution": "blocked",
        "authority_rule": "official_disagreement_is_not_a_silent_override",
        "resolution_reason": "official citation and retained provider observation differ",
    },
    "component_unit_mismatch": {
        "family": "unit_or_scale_unresolved",
        "reason_code": "CANONICAL_FACT_UNIT_OR_SCALE_UNRESOLVED",
        "resolution": "blocked",
        "authority_rule": "unit_scale_requires_explicit_evidence",
        "resolution_reason": "component units or scales are not explicitly compatible",
    },
}

_IDENTITY_FIELDS = (
    "ticker", "canonical_metric", "reporting_period", "period_type", "period_start",
    "period_end", "statement_family", "statement_scope", "currency", "scale", "provider",
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item is not None and str(item)})
    return []


def semantic_identity(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Return the retained semantic dimensions; no source value is transformed."""
    identity = {field: fact.get(field) for field in _IDENTITY_FIELDS}
    identity["canonical_identity_key"] = fact.get("identity_key")
    identity["source_sha256"] = fact.get("source_sha256")
    return identity


def decompose_conflict(fact: Mapping[str, Any], conflict: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one existing conflict without selecting a competing observation."""
    kind = str(conflict.get("kind") or "unknown_canonical_conflict")
    rule = _RULES.get(kind, {
        "family": "unclassified_canonical_conflict",
        "reason_code": "CANONICAL_FACT_CONFLICT_UNCLASSIFIED",
        "resolution": "blocked",
        "authority_rule": "unclassified_conflict_fails_closed",
        "resolution_reason": "conflict kind is not covered by a deterministic authority rule",
    })
    observation_ids = set(_strings(fact.get("source_observation_ids")))
    observation_ids.update(_strings(conflict.get("source_observation_ids")))
    variant_id = conflict.get("variant_observation_id")
    if variant_id is not None and str(variant_id):
        observation_ids.add(str(variant_id))
    return {
        "conflict_kind": kind,
        "family": rule["family"],
        "reason_code": rule["reason_code"],
        "resolution": rule["resolution"],
        "resolution_reason": rule["resolution_reason"],
        "authority_rule": rule["authority_rule"],
        "semantic_identity": semantic_identity(fact),
        "source_observation_ids": sorted(observation_ids),
        "source_sha256": fact.get("source_sha256"),
        "detail": {key: value for key, value in conflict.items() if key != "kind"},
    }


def decompose_facts(facts: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Explain all conflict-bearing facts in deterministic semantic-identity order."""
    rows: list[dict[str, Any]] = []
    for fact in facts or []:
        if not isinstance(fact, Mapping):
            continue
        entries = [decompose_conflict(fact, conflict) for conflict in fact.get("conflicts") or []
                   if isinstance(conflict, Mapping)]
        if not entries:
            continue
        rows.append({
            "fact_id": fact.get("fact_id"),
            "status_before": fact.get("status"),
            # No actual retained conflict in the current store has deterministic supersession,
            # explicit scale, or equivalent duplicate proof.  The status must therefore remain.
            "status_after": fact.get("status"),
            "semantic_identity": semantic_identity(fact),
            "conflicts": sorted(entries, key=lambda item: (item["family"], item["conflict_kind"])),
        })
    rows.sort(key=lambda item: (
        str(item["semantic_identity"].get("ticker") or ""),
        str(item["semantic_identity"].get("reporting_period") or ""),
        str(item["semantic_identity"].get("canonical_metric") or ""), str(item.get("fact_id") or ""),
    ))
    conflicts = [entry for row in rows for entry in row["conflicts"]]
    families = Counter(entry["family"] for entry in conflicts)
    codes = sorted({entry["reason_code"] for entry in conflicts})
    return {
        "schema_version": VERSION,
        "conflict_identity_count": len(rows),
        "conflict_count": len(conflicts),
        "conflicted_fact_count": len(rows),
        "auto_resolved_conflict_count": 0,
        "terminally_unresolved_conflict_count": len(conflicts),
        "family_counts": dict(sorted(families.items())),
        "reason_codes": codes,
        "identities": rows,
        "is_actionable": False,
    }


def coverage_summary(records: Iterable[Mapping[str, Any]], read_facts: Any) -> dict[str, Any]:
    """Read-only global decomposition for the existing canonical store."""
    all_facts: list[Mapping[str, Any]] = []
    for record in sorted((item for item in records if isinstance(item, Mapping)),
                         key=lambda item: str(item.get("ticker") or "")):
        all_facts.extend(fact for fact in read_facts(str(record.get("ticker") or ""))
                         if isinstance(fact, Mapping))
    result = decompose_facts(all_facts)
    result["conflicted_ticker_count"] = len({
        row["semantic_identity"].get("ticker") for row in result["identities"]
    })
    # The global bundle section is an operational count summary. Per-identity provenance stays
    # with each ticker's projection rather than being duplicated across the whole universe.
    result.pop("identities", None)
    return result
