"""Deterministic qualification policy for retained Pillar A canonical facts.

This module is a read-only projection.  It never changes a fact shard, selects a
restatement by ingest order, or makes a provider value research-admissible merely
because it is plausible.  Its only evidence authority is the already verified
official-evidence contract exposed by :mod:`semantic_evidence_bridge`.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"

QUALIFIED = "qualified"
PROVIDER_REPORTED = "provider_reported"
PARTIAL = "partial"
CONFLICTED = "conflicted"
UNAVAILABLE = "unavailable"

RESTATEMENT_CONFLICT = "restated_period_column_disagrees"
PERIOD_SCOPE_CONFLICTS = frozenset({"cash_flow_period_attribution_unverified"})
ARITHMETIC_CONFLICTS = frozenset({
    "balance_sheet_identity_violated", "revenue_occurrences_do_not_reconcile_with_deductions",
})


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item is not None and str(item)})
    return []


def _known(value: Any) -> bool:
    return value not in (None, "", "unknown")


def _key(ticker: Any, metric: Any, period: Any) -> tuple[str, str, str]:
    return (str(ticker or "").upper(), str(metric or ""), str(period or ""))


def _citation_keys(fact: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Return exact identity keys plus the existing stock-metric year-end alias.

    An annual balance-sheet citation and Q4 balance-sheet observation identify the
    same instant.  This is the same narrowly-scoped alias used by
    ``canonical_fact_store.load_official_citations``; it is never applied to flows.
    """
    ticker, metric, period = _key(fact.get("ticker"), fact.get("canonical_metric"), fact.get("reporting_period"))
    keys = [(ticker, metric, period)]
    if (str(fact.get("statement_family")) == "balance_sheet" and period.endswith("-Q4")
            and len(period) == 7 and period[:4].isdigit()):
        keys.append((ticker, metric, period[:4]))
    return keys


def build_evidence_index(verified_entries: Mapping[tuple, Mapping[str, Any]] | None) -> dict[tuple, dict[str, Any]]:
    """Normalize already-verified citation entries into stable fact-identity keys."""
    result: dict[tuple, dict[str, Any]] = {}
    for key, entry in sorted((verified_entries or {}).items(), key=lambda item: tuple(map(str, item[0]))):
        if not isinstance(entry, Mapping) or not isinstance(key, tuple) or len(key) != 3:
            continue
        normalized = dict(entry)
        normalized["verified"] = True
        result[_key(*key)] = normalized
    return result


def load_evidence_index(runtime_root: Path | str) -> dict[tuple, dict[str, Any]]:
    """Read the existing hash-verified financial-identity contract; no writes occur."""
    from semantic_evidence_bridge import load_verified_financial_identities

    loaded = load_verified_financial_identities(Path(runtime_root))
    return build_evidence_index(loaded.get("by_key") if isinstance(loaded, Mapping) else None)


def _matching_evidence(fact: Mapping[str, Any], evidence_index: Mapping[tuple, Mapping[str, Any]] | None) -> dict[str, Any] | None:
    for key in _citation_keys(fact):
        entry = (evidence_index or {}).get(key)
        if not isinstance(entry, Mapping):
            continue
        try:
            if float(entry.get("value")) != float(fact.get("value")):
                continue
        except (TypeError, ValueError):
            continue
        if entry.get("statement_scope") not in (None, fact.get("statement_scope")):
            continue
        return dict(entry)
    # Direct citation/evidence fields are an already-established upstream contract.  They are
    # accepted for pure callers/tests, but are never manufactured from a provider fact here.
    if fact.get("citation_id") and fact.get("evidence_id"):
        return {
            "citation_id": fact.get("citation_id"), "evidence_id": fact.get("evidence_id"),
            "document_sha256": fact.get("document_sha256"), "citation": fact.get("citation"),
            "verified": True,
        }
    return None


def _restatement_is_explicit(conflict: Mapping[str, Any]) -> bool:
    """Only explicit document-level supersession can resolve a restatement variant."""
    return all(_known(conflict.get(field)) for field in (
        "superseding_document_id", "supersession_evidence_id", "publication_date",
    ))


def evaluate_fact(fact: Mapping[str, Any], *, evidence_index: Mapping[tuple, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Evaluate a fact against the evidence contract without mutating it.

    ``status`` is the qualification-policy result.  ``safe_promotion`` means this
    projection found a complete retained route; the caller still owns whether to
    materialize that result into the canonical store.
    """
    source_status = str(fact.get("status") or UNAVAILABLE)
    reasons: list[str] = []
    evidence = _matching_evidence(fact, evidence_index)
    conflicts = [item for item in fact.get("conflicts") or [] if isinstance(item, Mapping)]

    if fact.get("value") is None:
        reasons.append("VALUE_MISSING")
    if not (_known(fact.get("ticker")) and _known(fact.get("canonical_metric")) and _known(fact.get("reporting_period"))
            and _known(fact.get("period_start")) and _known(fact.get("period_end"))
            and _known(fact.get("statement_family"))):
        reasons.append("PERIOD_IDENTITY_INCOMPLETE")
    if fact.get("statement_scope") != "consolidated":
        reasons.append("CONSOLIDATION_SCOPE_UNQUALIFIED")
    if not _known(fact.get("provider")):
        reasons.append("SOURCE_PROVIDER_MISSING")
    if not _known(fact.get("source_sha256")):
        reasons.append("SOURCE_HASH_MISSING")
    if not _strings(fact.get("source_observation_ids")):
        reasons.append("OBSERVATION_LINEAGE_MISSING")
    if not evidence:
        reasons.append("CITATION_MISSING")
    else:
        if not _known(evidence.get("evidence_id")):
            reasons.append("SOURCE_ARTIFACT_MISSING")
        if not _known(evidence.get("citation_id")):
            reasons.append("CITATION_MISSING")
        if evidence.get("verified") is not True:
            reasons.append("DOCUMENT_AUTHORITY_INSUFFICIENT")
    if not _known(fact.get("currency")) and not (evidence and _known(evidence.get("currency"))):
        reasons.append("UNIT_OR_CURRENCY_UNQUALIFIED")
    if not _known(fact.get("scale")) and not (evidence and _known(evidence.get("unit_scale") or evidence.get("scale"))):
        reasons.append("UNIT_OR_CURRENCY_UNQUALIFIED")

    unresolved_conflicts = []
    for conflict in conflicts:
        kind = str(conflict.get("kind") or "")
        if kind == RESTATEMENT_CONFLICT:
            if not _restatement_is_explicit(conflict):
                reasons.append("RESTATEMENT_STATE_UNKNOWN")
                unresolved_conflicts.append(kind)
        elif kind in PERIOD_SCOPE_CONFLICTS:
            reasons.append("PERIOD_SCOPE_COMPATIBILITY_FAILED")
            unresolved_conflicts.append(kind)
        elif kind in ARITHMETIC_CONFLICTS:
            reasons.append("ARITHMETIC_INTEGRITY_FAILED")
            unresolved_conflicts.append(kind)
        else:
            reasons.append("SEMANTIC_CONFLICT_PRESENT")
            unresolved_conflicts.append(kind)
    if source_status == PARTIAL:
        reasons.append("CANONICAL_FACT_PARTIAL")
    if source_status == UNAVAILABLE:
        reasons.append("CANONICAL_FACT_UNAVAILABLE")

    reasons = sorted(set(reasons))
    # Fact qualification and corporate-research admissibility are intentionally separate:
    # a year-end balance-sheet stock can be fact-qualified through the existing FY/Q4 alias,
    # while the corporate research lane still accepts only explicitly annual facts.
    research_reasons = list(reasons)
    if fact.get("period_type") != "annual":
        research_reasons.append("RESEARCH_PERIOD_NOT_ANNUAL")
    if fact.get("statement_scope") != "consolidated":
        research_reasons.append("RESEARCH_SCOPE_NOT_CONSOLIDATED")
    research_reasons = sorted(set(research_reasons))
    complete = not reasons
    status = QUALIFIED if complete else (
        CONFLICTED if unresolved_conflicts else (UNAVAILABLE if source_status == UNAVAILABLE else
                                                 PARTIAL if source_status == PARTIAL else PROVIDER_REPORTED)
    )
    safe_promotion = complete and source_status != QUALIFIED
    return {
        "schema_version": VERSION, "fact_id": fact.get("fact_id"),
        "current_status": source_status, "status": status, "safe_promotion": safe_promotion,
        "reason_codes": reasons,
        "research_status": QUALIFIED if status == QUALIFIED and not research_reasons else (
            PARTIAL if status == QUALIFIED else status),
        "research_reason_codes": research_reasons,
        "semantic_identity": {
            "ticker": fact.get("ticker"), "metric": fact.get("canonical_metric"),
            "reporting_period": fact.get("reporting_period"), "period_start": fact.get("period_start"),
            "period_end": fact.get("period_end"), "statement_family": fact.get("statement_family"),
            "statement_scope": fact.get("statement_scope"), "currency": fact.get("currency"),
            "scale": fact.get("scale"), "canonical_identity_key": fact.get("identity_key"),
        },
        "evidence": {
            "provider": fact.get("provider"), "source_sha256": fact.get("source_sha256"),
            "source_observation_ids": _strings(fact.get("source_observation_ids")),
            "citation_id": evidence.get("citation_id") if evidence else None,
            "evidence_id": evidence.get("evidence_id") if evidence else None,
            "document_sha256": evidence.get("document_sha256") if evidence else None,
            "citation": evidence.get("citation") if evidence else None,
            "verified": bool(evidence and evidence.get("verified") is True),
        },
        "unresolved_conflict_kinds": sorted(set(unresolved_conflicts)),
        "is_actionable": False,
    }


def apply_policy(fact: Mapping[str, Any], *, evidence_index: Mapping[tuple, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Attach an ephemeral policy result for downstream projection; never alters fact status."""
    result = dict(fact)
    qualification = evaluate_fact(fact, evidence_index=evidence_index)
    result["qualification_policy"] = qualification
    result["qualification_status"] = qualification["status"]
    result["qualification_reason_codes"] = qualification["reason_codes"]
    result["qualification_evidence"] = qualification["evidence"]
    return result


def is_promotion_frontier(result: Mapping[str, Any]) -> bool:
    """One bounded *evidence* gap, after all semantic/integrity requirements pass."""
    if result.get("status") == QUALIFIED or result.get("unresolved_conflict_kinds"):
        return False
    reasons = set(_strings(result.get("research_reason_codes") or result.get("reason_codes")))
    evidence_gaps = {"CITATION_MISSING", "SOURCE_ARTIFACT_MISSING", "SOURCE_HASH_MISSING", "OBSERVATION_LINEAGE_MISSING"}
    return len(reasons) == 1 and reasons <= evidence_gaps


def inventory(facts: Sequence[Mapping[str, Any]] | None, *, evidence_index: Mapping[tuple, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Deterministic global policy counts and compact candidate records."""
    evaluations = [evaluate_fact(fact, evidence_index=evidence_index) for fact in facts or [] if isinstance(fact, Mapping)]
    evaluations.sort(key=lambda item: (str(item["semantic_identity"].get("ticker") or ""),
                                       str(item["semantic_identity"].get("reporting_period") or ""),
                                       str(item["semantic_identity"].get("metric") or ""), str(item.get("fact_id") or "")))
    counts = Counter()
    candidates = []
    for item in evaluations:
        reasons = set(item["reason_codes"])
        research_reasons = set(item["research_reason_codes"])
        counts["facts_total"] += 1
        counts["facts_already_qualified"] += int(item["current_status"] == QUALIFIED and item["status"] == QUALIFIED)
        counts["safe_promotions"] += int(item["safe_promotion"] is True)
        counts["provider_reported_semantic_requirements_missing_evidence"] += int(
            item["current_status"] == PROVIDER_REPORTED and bool(research_reasons) and
            not research_reasons.intersection({"RESEARCH_PERIOD_NOT_ANNUAL", "RESEARCH_SCOPE_NOT_CONSOLIDATED",
                                      "PERIOD_IDENTITY_INCOMPLETE", "CONSOLIDATION_SCOPE_UNQUALIFIED",
                                      "RESTATEMENT_STATE_UNKNOWN", "PERIOD_SCOPE_COMPATIBILITY_FAILED",
                                      "ARITHMETIC_INTEGRITY_FAILED", "SEMANTIC_CONFLICT_PRESENT",
                                      "CANONICAL_FACT_PARTIAL", "CANONICAL_FACT_UNAVAILABLE"}))
        counts["missing_citation_facts"] += int("CITATION_MISSING" in reasons)
        counts["missing_source_artifact_facts"] += int("SOURCE_ARTIFACT_MISSING" in reasons or "SOURCE_HASH_MISSING" in reasons)
        counts["missing_only_citation_facts"] += int(reasons == {"CITATION_MISSING"})
        counts["missing_only_source_artifact_or_hash_facts"] += int(
            reasons in ({"SOURCE_ARTIFACT_MISSING"}, {"SOURCE_HASH_MISSING"}))
        counts["restatement_blocked_facts"] += int("RESTATEMENT_STATE_UNKNOWN" in reasons)
        counts["period_scope_blocked_facts"] += int(bool(set(item["research_reason_codes"]).intersection({
            "RESEARCH_PERIOD_NOT_ANNUAL", "RESEARCH_SCOPE_NOT_CONSOLIDATED", "PERIOD_IDENTITY_INCOMPLETE",
            "CONSOLIDATION_SCOPE_UNQUALIFIED", "PERIOD_SCOPE_COMPATIBILITY_FAILED",
        })))
        counts["arithmetic_blocked_facts"] += int("ARITHMETIC_INTEGRITY_FAILED" in reasons)
        counts["multiple_reason_facts"] += int(len(reasons) > 1)
        if is_promotion_frontier(item):
            counts["promotion_frontier_facts"] += 1
            candidates.append(item)
    return {"schema_version": VERSION, "counts": dict(sorted(counts.items())),
            "promotion_frontier": candidates, "is_actionable": False}


def ticker_frontier(ticker: str, facts: Sequence[Mapping[str, Any]] | None, *, required_metrics: Iterable[str],
                    entity_type: str | None, evidence_index: Mapping[tuple, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Readiness-only per-ticker frontier; it does not rank issuers or expose values."""
    required = sorted({str(metric) for metric in required_metrics})
    evaluated = [evaluate_fact(fact, evidence_index=evidence_index) for fact in facts or [] if isinstance(fact, Mapping)]
    qualified = sorted({item["semantic_identity"]["metric"] for item in evaluated
                        if item["research_status"] == QUALIFIED and item["semantic_identity"]["metric"] in required
                        and item["semantic_identity"].get("statement_scope") == "consolidated"})
    frontier = sorted({item["semantic_identity"]["metric"] for item in evaluated if is_promotion_frontier(item)
                       and item["semantic_identity"]["metric"] in required})
    reasons = sorted({reason for item in evaluated for reason in item["research_reason_codes"]
                      if item["semantic_identity"]["metric"] in required})
    return {"schema_version": VERSION, "ticker": str(ticker).upper(), "entity_type": entity_type or "unknown",
            "supported_archetype": entity_type == "corporate", "required_metrics": required,
            "qualified_metrics": qualified, "promotion_frontier_metrics": frontier,
            "missing_required_metrics": sorted(set(required) - set(qualified)), "reason_codes": reasons,
            "is_actionable": False}


def candidate_manifest(facts_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]], *, required_metrics: Iterable[str],
                       entity_types: Mapping[str, str] | None = None,
                       evidence_index: Mapping[tuple, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """A compact no-value manifest for later bounded evidence materialization."""
    all_facts = [fact for ticker in sorted(facts_by_ticker) for fact in facts_by_ticker[ticker] if isinstance(fact, Mapping)]
    global_inventory = inventory(all_facts, evidence_index=evidence_index)
    frontier = []
    for item in global_inventory["promotion_frontier"]:
        identity, evidence = item["semantic_identity"], item["evidence"]
        frontier.append({"ticker": identity["ticker"], "metric": identity["metric"], "period": identity["reporting_period"],
                         "scope": identity["statement_scope"], "current_status": item["current_status"],
                         "missing_qualification_requirement": item["reason_codes"], "provider": evidence["provider"],
                         "existing_evidence": {"citation_id": evidence["citation_id"], "evidence_id": evidence["evidence_id"],
                                               "source_sha256": evidence["source_sha256"]},
                         "next_evidence_needed": item["reason_codes"]})
    tickers = [ticker_frontier(ticker, facts_by_ticker[ticker], required_metrics=required_metrics,
                               entity_type=(entity_types or {}).get(ticker), evidence_index=evidence_index)
               for ticker in sorted(facts_by_ticker)]
    return {"schema_version": VERSION, "global_inventory": global_inventory["counts"],
            "promotion_frontier_candidates": frontier, "ticker_frontier": tickers,
            "acquisition_priority_policy": ["supported_archetype", "promotion_frontier_distance",
                                            "five_metric_closure", "authoritative_document_route", "document_reuse"],
            "broad_crawl_prohibited": True, "is_actionable": False}
