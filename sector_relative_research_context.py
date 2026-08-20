"""Deterministic same-session, qualified-archetype relative research context."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Mapping

MIN_COHORT_MEMBERS = 5
NUMERIC_METRICS = (("momentum_20d", "SHADOW_ONLY"), ("volatility_20d", "SHADOW_ONLY"),
                   ("relative_volume_provider_scoped", "DERIVED_PROXY"))


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def load_qualified_entity_classes(root: Path) -> dict[str, dict[str, Any]]:
    """Reuse only the two retained, already-qualified entity-class sources."""
    p2e = json.loads((root / "operations-review/p2e-evidence-backed-entity-classification-20260819/"
                            "p2e_entity_classification_artifact.json").read_text(encoding="utf-8"))
    p2e3 = json.loads((root / "operations-review/p2e3-bounded-entity-classification-promotion-20260819/"
                             "p2e3_entity_classification_promotion_artifact.json").read_text(encoding="utf-8"))
    classes: dict[str, dict[str, Any]] = {}
    for row in p2e["part_a_known_results"]:
        value = row["classification"]
        if value["classification_status"] == "QUALIFIED":
            classes[value["ticker"]] = {"entity_class": value["entity_class"],
                                         "classification_evidence_id": value["classification_evidence_id"],
                                         "source_artifact_identity": p2e["artifact_id"], "source_id": value["source_id"]}
    for value in p2e3["promoted_records"]:
        if value["classification_status"] == "QUALIFIED":
            if value["ticker"] in classes:
                raise ValueError("ENTITY_CLASS_DUPLICATE_CONFLICT")
            classes[value["ticker"]] = {"entity_class": value["entity_class"],
                                         "classification_evidence_id": value["classification_evidence_id"],
                                         "source_artifact_identity": p2e3["artifact_id"], "source_id": value["source_id"]}
    return classes


def _bucket(percentile: float) -> str:
    if percentile < .25:
        return "LOWER_QUARTILE"
    if percentile < .50:
        return "LOWER_MIDDLE"
    if percentile < .75:
        return "UPPER_MIDDLE"
    return "UPPER_QUARTILE"


def _unavailable(metric: str, reason: str, authority: str) -> dict[str, Any]:
    return {"metric_identity": metric, "status": "UNAVAILABLE", "missing_or_exclusion_reason": reason,
            "authority_tier": authority}


def _numeric_context(metric: str, authority: str, subject: Mapping[str, Any], peers: list[Mapping[str, Any]],
                     cohort: Mapping[str, Any]) -> dict[str, Any]:
    values = [(peer["ticker"], peer["facts"].get(metric)) for peer in peers]
    valid = [(ticker, value) for ticker, value in values if isinstance(value, (int, float))]
    value = subject["facts"].get(metric)
    if not isinstance(value, (int, float)):
        return _unavailable(metric, "SUBJECT_METRIC_MISSING", authority)
    if len(valid) < MIN_COHORT_MEMBERS:
        return _unavailable(metric, "INSUFFICIENT_VALID_PEER_OBSERVATIONS", authority)
    numeric = sorted(item[1] for item in valid)
    below = sum(item < value for item in numeric)
    equal = sum(item == value for item in numeric)
    percentile = (below + .5 * equal) / len(numeric)
    return {"metric_identity": metric, "status": "AVAILABLE", "research_session": subject["facts"]["session"],
            "cohort_identity": cohort["cohort_identity"], "cohort_type": cohort["cohort_type"],
            "cohort_member_count": cohort["member_count"], "valid_observation_count": len(numeric),
            "subject_value": value, "peer_median": median(numeric), "percentile": percentile,
            "descriptive_bucket": _bucket(percentile), "authority_tier": authority,
            "source_lineage": {"subject_field": f"daily_research.{subject['ticker']}.facts.{metric}",
                               "peer_population": cohort["member_tickers"]}}


def _trend_context(subject: Mapping[str, Any], peers: list[Mapping[str, Any]], cohort: Mapping[str, Any]) -> dict[str, Any]:
    trend = subject["trend_state"]
    counts = Counter(peer["trend_state"] for peer in peers if peer["trend_state"] is not None)
    if trend is None:
        return _unavailable("trend_state", "SUBJECT_METRIC_MISSING", "SHADOW_ONLY")
    if sum(counts.values()) < MIN_COHORT_MEMBERS:
        return _unavailable("trend_state", "INSUFFICIENT_VALID_PEER_OBSERVATIONS", "SHADOW_ONLY")
    return {"metric_identity": "trend_state", "status": "AVAILABLE", "research_session": subject["facts"]["session"],
            "cohort_identity": cohort["cohort_identity"], "cohort_type": cohort["cohort_type"],
            "cohort_member_count": cohort["member_count"], "valid_observation_count": sum(counts.values()),
            "subject_value": trend, "peer_distribution": dict(sorted(counts.items())),
            "matching_peer_count": counts[trend], "matching_peer_fraction": counts[trend] / sum(counts.values()),
            "descriptive_bucket": "PEER_STATE_DISTRIBUTION", "authority_tier": "SHADOW_ONLY",
            "source_lineage": {"subject_field": f"daily_research.{subject['ticker']}.trend_state",
                               "peer_population": cohort["member_tickers"]}}


def build(product: Mapping[str, Any], dossiers: Mapping[str, Mapping[str, Any]],
          classifications: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    records = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in product["stock_research"]:
        ticker = record["ticker"]
        classification = classifications.get(ticker)
        normalized = {"ticker": ticker, "facts": record["ai_ready_brief"]["facts"],
                      "trend_state": record["research_summary"]["trend_state"], "classification": classification}
        if classification:
            grouped[classification["entity_class"]].append(normalized)
        records.append(normalized)
    cohorts: dict[str, dict[str, Any]] = {}
    for entity_class, members in grouped.items():
        tickers = sorted(member["ticker"] for member in members)
        cohort = {"cohort_type": "QUALIFIED_ENTITY_CLASS_ARCHETYPE", "entity_class": entity_class,
                  "research_session": product["daily_market_research"]["session"], "member_count": len(members),
                  "member_tickers": tickers, "minimum_member_requirement": MIN_COHORT_MEMBERS,
                  "status": "AVAILABLE" if len(members) >= MIN_COHORT_MEMBERS else "UNAVAILABLE_INSUFFICIENT_MEMBERS"}
        cohort["cohort_identity"] = "sector_relative_cohort:" + _hash(cohort)
        cohorts[entity_class] = cohort
    contexts = []
    for subject in sorted(records, key=lambda row: row["ticker"]):
        classification = subject["classification"]
        base = {"ticker": subject["ticker"], "research_session": subject["facts"]["session"],
                "dossier_identity": dossiers[subject["ticker"]]["dossier_identity"],
                "classification": classification or {"status": "UNAVAILABLE", "reason": "NO_QUALIFIED_ENTITY_CLASS"},
                "fundamental_relative_context": {"status": "UNAVAILABLE", "reason": "NO_INDIVIDUAL_LIKE_FOR_LIKE_FUNDAMENTAL_METRIC_RETAINED_IN_DAILY_RESEARCH"}}
        if not classification:
            reason = "NO_QUALIFIED_ENTITY_CLASS"
            base.update({"context_status": "UNAVAILABLE", "cohort": None,
                         "relative_metrics": [_unavailable(metric, reason, authority) for metric, authority in NUMERIC_METRICS] +
                                             [_unavailable("trend_state", reason, "SHADOW_ONLY")]})
        else:
            cohort = cohorts[classification["entity_class"]]
            if cohort["status"] != "AVAILABLE":
                reason = "QUALIFIED_ARCHETYPE_COHORT_TOO_SMALL"
                base.update({"context_status": "UNAVAILABLE", "cohort": cohort,
                             "relative_metrics": [_unavailable(metric, reason, authority) for metric, authority in NUMERIC_METRICS] +
                                                 [_unavailable("trend_state", reason, "SHADOW_ONLY")]})
            else:
                peers = grouped[classification["entity_class"]]
                base.update({"context_status": "AVAILABLE", "cohort": cohort,
                             "relative_metrics": [_numeric_context(metric, authority, subject, peers, cohort) for metric, authority in NUMERIC_METRICS] +
                                                 [_trend_context(subject, peers, cohort)]})
        contexts.append(base)
    available_metrics = sum(metric["status"] == "AVAILABLE" for context in contexts for metric in context["relative_metrics"])
    artifact = {"schema_version": "1.0.0", "contract_version": "sector_relative_research_context/v1",
                "research_session": product["daily_market_research"]["session"], "cohort_scope": "EMPIRICAL_ACTIVE_SHADOW_ONLY",
                "source_artifact_identities": {"daily_product": product["artifact_identity"],
                                                "classification_collection": "qualified_entity_classes:" + _hash(classifications)},
                "cohorts": cohorts, "records": contexts,
                "coverage": {"full_cohort_records": len(contexts), "qualified_classification_count": sum(context["classification"].get("entity_class") is not None for context in contexts),
                             "relative_context_available_count": sum(context["context_status"] == "AVAILABLE" for context in contexts),
                             "relative_context_unavailable_count": sum(context["context_status"] != "AVAILABLE" for context in contexts),
                             "available_metric_count": available_metrics,
                             "unavailable_fundamental_relative_count": len(contexts)},
                "authority_boundary": {"empirical_active_is_not_active_universe": True, "ranking": "NOT_EMITTED",
                                       "provider_cross_metric_analytics": "NOT_EMITTED", "valuation": "NOT_EMITTED"},
                "verdict": "SECTOR_RELATIVE_RESEARCH_CONTEXT_V1_READY"}
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "sector_relative_research_context:" + artifact["artifact_sha256"]
    return artifact


def review_pack_overlay(review_pack: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    by_ticker = {record["ticker"]: record for record in context["records"]}
    entries = []
    for review in review_pack["owner_review_queue"]:
        record = by_ticker[review["ticker"]]
        available = [metric for metric in record["relative_metrics"] if metric["status"] == "AVAILABLE"]
        entries.append({"ticker": review["ticker"], "dossier_identity": review["dossier_identity"],
                        "relative_context_status": record["context_status"], "relative_metrics": available,
                        "unavailable_metric_reasons": [metric["missing_or_exclusion_reason"] for metric in record["relative_metrics"] if metric["status"] == "UNAVAILABLE"],
                        "source_lineage": {"review_pack": review_pack["artifact_identity"], "relative_context": context["artifact_identity"]}})
    overlay = {"schema_version": "1.0.0", "contract_version": "sector_relative_review_pack_overlay/v1",
               "base_review_pack_identity": review_pack["artifact_identity"], "relative_context_identity": context["artifact_identity"],
               "review_entries": entries, "review_entries_with_relative_context": sum(bool(entry["relative_metrics"]) for entry in entries),
               "verdict": "SECTOR_RELATIVE_REVIEW_PACK_OVERLAY_READY"}
    overlay["artifact_sha256"] = _hash(overlay)
    overlay["artifact_identity"] = "sector_relative_review_pack_overlay:" + overlay["artifact_sha256"]
    return overlay


def markdown_overlay(overlay: Mapping[str, Any]) -> str:
    lines = ["# Sector-Relative Review Context", ""]
    for entry in overlay["review_entries"]:
        lines.append(f"## {entry['ticker']}")
        for metric in entry["relative_metrics"]:
            if metric["metric_identity"] == "trend_state":
                lines.append(f"- FACT: trend state matches {metric['matching_peer_count']}/{metric['valid_observation_count']} qualified-archetype peers.")
            else:
                lines.append(f"- FACT: {metric['metric_identity']} is {metric['descriptive_bucket']} within the retained qualified-archetype cohort (n={metric['valid_observation_count']}).")
        if not entry["relative_metrics"]:
            lines.append(f"- DATA_GAP: relative context unavailable ({', '.join(sorted(set(entry['unavailable_metric_reasons'])))}).")
    return "\n".join(lines) + "\n"
