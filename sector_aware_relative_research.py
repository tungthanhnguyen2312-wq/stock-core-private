"""Deterministic current peer-relative research; never a ranking or recommendation."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "sector_aware_relative_research/v1"
MIN_COHORT = 5
TECHNICAL_METRICS = ("return_1d", "momentum_20d", "ma20_distance", "volatility_20d", "relative_volume_provider_scoped")
FUNDAMENTAL_DIMENSIONS = ("revenue_direction", "earnings_direction", "revenue_vs_earnings_alignment", "assets_direction", "equity_direction", "operating_cash_flow_direction")
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
PREOPEN_47 = ("ABB", "ABS", "BCA", "BHN", "BSH", "BTH", "DCV", "DHB", "FDC", "GCF", "H11", "HCC", "KTL", "LMC", "LMH", "MEL", "MKV", "PJC", "POM", "PWA", "SHN", "SPM", "TH1", "TNI", "TTS", "VMS", "VQC", "VRC", "VSF", "VVS", "AGG", "AVC", "BMC", "BMP", "C47", "HD6", "SMC", "TDT", "VC3", "VCF", "VIC", "VNS", "VPL", "AAN", "ABW", "DHG", "HCM")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "sector_aware_relative_research:" + digest}


def _entity(ticker: str, descriptive: Mapping[str, Any], fundamental: Mapping[str, Any]) -> tuple[str, Mapping[str, Any] | None]:
    row, fundamental_row = descriptive.get(ticker) or {}, fundamental.get(ticker) or {}
    sector = row.get("sector_classification") or {}
    value = fundamental_row.get("entity_class") or sector.get("entity_class")
    return (str(value).lower() if isinstance(value, str) and value else "unknown", sector or fundamental_row.get("entity_class_provenance"))


def _membership(ticker: str, descriptive: Mapping[str, Any], fundamental: Mapping[str, Any]) -> dict[str, Any]:
    row = descriptive.get(ticker) or {}; fundamental_row = fundamental.get(ticker) or {}; sector = row.get("sector_classification") or {}; entity, source = _entity(ticker, descriptive, fundamental)
    industry = sector.get("safe_normalized_label") if sector.get("classification_level") == "PROVIDER_INDUSTRY" else None
    # Qualified entity records deliberately take precedence in the descriptive artifact.
    # Their retained provider-industry candidate remains available in the fundamental
    # provenance and is allowed here solely as descriptive peer grouping.
    if not industry:
        candidates = ((fundamental_row.get("entity_class_provenance") or {}).get("selected_sources") or [])
        retained = next((item for item in candidates if item.get("source_type") == "VCI_PROVIDER_INDUSTRY" and isinstance(item.get("reason"), str)), None)
        if retained:
            raw = retained["reason"].removeprefix("retained_provider_industry:").strip()
            if raw: industry, sector = raw.casefold(), {"raw_label": raw, "safe_normalized_label": raw.casefold(), "classification_level": "PROVIDER_INDUSTRY", "classification_authority": "PROVIDER_DESCRIPTIVE_CLASSIFICATION", "source_artifact": retained.get("source_artifact"), "as_of": retained.get("observed_at"), "provider_qualification_status": retained.get("qualification_state")}
    base = {"ticker": ticker, "entity_class": entity, "classification_source": sector or source, "source_identity_or_record": (sector or source or {}).get("source_artifact") or (sector or source or {}).get("source_artifact_identity"), "observed_or_effective_at": sector.get("as_of")}
    if entity == "corporate" and isinstance(industry, str) and industry:
        return base | {"peer_group_id": "CORPORATE_INDUSTRY:" + industry, "peer_group_label": sector.get("raw_label") or industry, "peer_group_level": "RETAINED_PROVIDER_DESCRIPTIVE_INDUSTRY", "qualification_state": sector.get("provider_qualification_status") or "PROVIDER_DESCRIPTIVE_CLASSIFICATION", "fallback_reason": None, "limitations": ["Descriptive retained-provider industry only; not global entity authority."]}
    if entity != "unknown":
        return base | {"peer_group_id": "ENTITY_CLASS:" + entity.upper(), "peer_group_label": entity.upper(), "peer_group_level": "QUALIFIED_ENTITY_CLASS", "qualification_state": "QUALIFIED_OR_RETAINED_ENTITY_CLASS", "fallback_reason": "NO_RETAINED_INDUSTRY_FOR_QUALIFIED_ENTITY", "limitations": ["Broad entity-class fallback; not industry-relative context."]}
    if isinstance(industry, str) and industry:
        return base | {"peer_group_id": "RETAINED_INDUSTRY:" + industry, "peer_group_label": sector.get("raw_label") or industry, "peer_group_level": "RETAINED_PROVIDER_DESCRIPTIVE_INDUSTRY", "qualification_state": sector.get("provider_qualification_status") or "PROVIDER_DESCRIPTIVE_CLASSIFICATION", "fallback_reason": "ENTITY_CLASS_NOT_RETAINED", "limitations": ["Industry is descriptive-only; entity class remains unknown."]}
    return base | {"peer_group_id": "UNKNOWN", "peer_group_label": "UNKNOWN", "peer_group_level": "INSUFFICIENT", "qualification_state": "UNRESOLVED", "fallback_reason": "NO_RETAINED_CLASSIFICATION", "limitations": ["No peer comparison is asserted."]}


def _bucket(percentile: float) -> str:
    return "LOWER_QUARTILE" if percentile < .25 else "LOWER_MIDDLE" if percentile < .5 else "UPPER_MIDDLE" if percentile < .75 else "UPPER_QUARTILE"


def _technical_value(row: Mapping[str, Any], metric: str) -> float | None:
    values = ((row.get("technical_features") or {}).get("values") or {})
    if metric == "ma20_distance":
        close, ma20 = values.get("close"), values.get("ma_20")
        return ((close / ma20) - 1.0) if isinstance(close, (int, float)) and isinstance(ma20, (int, float)) and ma20 else None
    value = values.get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _numeric_context(ticker: str, metric: str, peers: list[str], descriptive: Mapping[str, Any]) -> dict[str, Any]:
    subject = _technical_value(descriptive[ticker], metric); valid = [(peer, _technical_value(descriptive[peer], metric)) for peer in peers]; valid = [(peer, value) for peer, value in valid if value is not None]
    if subject is None: return {"metric": metric, "status": "UNAVAILABLE", "reason": "SUBJECT_METRIC_MISSING"}
    if len(valid) < MIN_COHORT: return {"metric": metric, "status": "INSUFFICIENT_COHORT", "valid_observation_count": len(valid), "reason": "INSUFFICIENT_VALID_PEER_OBSERVATIONS"}
    numbers = sorted(value for _, value in valid); percentile = (sum(value < subject for value in numbers) + .5 * sum(value == subject for value in numbers)) / len(numbers)
    return {"metric": metric, "status": "AVAILABLE", "valid_observation_count": len(numbers), "subject_value": subject, "peer_median": median(numbers), "percentile": percentile, "descriptive_bucket": _bucket(percentile), "authority_tier": "SHADOW_ONLY" if metric != "relative_volume_provider_scoped" else "DERIVED_PROXY"}


def _fundamental_value(row: Mapping[str, Any], dimension: str) -> str | None:
    value = (row.get("fundamental_trajectory_context") or {}).get(dimension)
    if isinstance(value, Mapping): value = value.get("status")
    return str(value) if isinstance(value, str) and value not in {"UNAVAILABLE", "UNKNOWN"} else None


def _fundamental_context(ticker: str, peers: list[str], fundamental: Mapping[str, Any]) -> dict[str, Any]:
    subject = fundamental.get(ticker) or {}; dimensions: dict[str, Any] = {}; available = 0
    for dimension in FUNDAMENTAL_DIMENSIONS:
        value = _fundamental_value(subject, dimension); distribution = Counter(_fundamental_value(fundamental.get(peer) or {}, dimension) for peer in peers); distribution.pop(None, None)
        if value is None: dimensions[dimension] = {"status": "UNAVAILABLE", "reason": "SUBJECT_DIMENSION_MISSING"}
        elif sum(distribution.values()) < MIN_COHORT: dimensions[dimension] = {"status": "INSUFFICIENT_COHORT", "valid_observation_count": sum(distribution.values())}
        else:
            available += 1; dimensions[dimension] = {"status": "AVAILABLE", "subject_value": value, "peer_distribution": dict(sorted(distribution.items())), "matching_peer_count": distribution[value], "valid_observation_count": sum(distribution.values()), "authority_tier": subject.get("authority_tier")}
    return {"status": "AVAILABLE" if available else "UNAVAILABLE", "available_dimension_count": available, "dimensions": dimensions, "authority_tier": subject.get("authority_tier"), "limitations": ((subject.get("fundamental_trajectory_context") or {}).get("data_limitations") or [])}


def _expectation(tactical: Mapping[str, Any], fund: Mapping[str, Any], technical: Mapping[str, Any]) -> str:
    state = tactical.get("entry_state"); alignment = ((fund.get("dimensions") or {}).get("revenue_vs_earnings_alignment") or {}).get("subject_value"); momentum = ((technical.get("metrics") or {}).get("momentum_20d") or {}).get("descriptive_bucket")
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} and alignment == "BOTH_EXPANDING": return "MARKET_AND_FUNDAMENTALS_ALIGNED_POSITIVE"
    if state in {"BREAKDOWN_RISK", "DISTRIBUTION_RISK", "DOWNTREND"} and alignment == "BOTH_CONTRACTING": return "MARKET_AND_FUNDAMENTALS_ALIGNED_NEGATIVE"
    if momentum == "UPPER_QUARTILE" and alignment == "BOTH_CONTRACTING": return "MARKET_STRENGTH_AHEAD_OF_FUNDAMENTALS"
    if momentum == "LOWER_QUARTILE" and alignment == "BOTH_EXPANDING": return "FUNDAMENTALS_AHEAD_OF_MARKET"
    if state == "EARLY_REVERSAL_CANDIDATE" and not alignment: return "TECHNICAL_RECOVERY_WITH_FUNDAMENTAL_UNCERTAINTY"
    return "MIXED_OR_INSUFFICIENT_EVIDENCE"


def _research_block(record: Mapping[str, Any]) -> dict[str, Any]:
    technical, fundamental = record["technical_peer_context"], record["fundamental_peer_context"]
    positions = [metric for metric in technical.get("metrics", {}).values() if metric.get("status") == "AVAILABLE"]
    unusual = [f"{metric['metric']}:{metric['descriptive_bucket']}" for metric in positions if metric.get("descriptive_bucket") in {"UPPER_QUARTILE", "LOWER_QUARTILE"}]
    return {"ticker": record["ticker"], "entity_class": record["peer_membership"]["entity_class"], "peer_group": record["peer_membership"]["peer_group_label"], "peer_group_level": record["peer_membership"]["peer_group_level"], "peer_group_size": record["peer_membership"]["member_count"], "comparison_eligible_counts": {"technical": technical["eligible_count"], "fundamental": fundamental["available_dimension_count"], "valuation": 0}, "current_peer_position_context": positions, "what_is_unusual": unusual or ["NO_EXTREME_RETAINED_PEER_POSITION"], "what_is_not_unusual": [f"{metric['metric']}:{metric['descriptive_bucket']}" for metric in positions if metric.get("descriptive_bucket") not in {"UPPER_QUARTILE", "LOWER_QUARTILE"}] or ["NO_COMPARABLE_METRIC"], "technical_vs_peer_evidence": technical, "fundamental_vs_peer_evidence": fundamental, "valuation_peer_context": record["valuation_peer_context"], "expectations_context": record["expectations_context"], "counter_evidence": record["expectations_context"].get("counter_evidence", []), "data_gaps": record["data_gaps"], "authority_limitations": record["authority_limitations"]}


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any]) -> dict[str, Any]:
    d, t, f, v = descriptive["records"], tactical["records"], fundamental["records"], valuation["records"]
    memberships = {ticker: _membership(ticker, d, f) for ticker in sorted(d)}; groups: dict[str, list[str]] = defaultdict(list)
    for ticker, membership in memberships.items(): groups[membership["peer_group_id"]].append(ticker)
    group_summary: dict[str, Any] = {}
    for group_id, members in sorted(groups.items()):
        technical_count = sum(bool((d[x].get("technical_features") or {}).get("is_current_session")) for x in members); fundamental_count = sum(bool((f.get(x) or {}).get("fundamental_trajectory_context")) for x in members)
        group_summary[group_id] = {"peer_group_id": group_id, "peer_group_label": memberships[members[0]]["peer_group_label"], "peer_group_level": memberships[members[0]]["peer_group_level"], "member_count": len(members), "members": sorted(members), "technically_comparable_count": technical_count, "fundamentally_comparable_count": fundamental_count, "valuation_comparable_count": 0, "minimum_member_requirement": MIN_COHORT, "status": "AVAILABLE" if len(members) >= MIN_COHORT else "INSUFFICIENT_COHORT"}
    records: dict[str, Any] = {}
    for ticker in sorted(d):
        membership = copy.deepcopy(memberships[ticker]); peers = sorted(groups[membership["peer_group_id"]]); group = group_summary[membership["peer_group_id"]]; membership.update({"member_count": group["member_count"], "status": group["status"]})
        current_peers = [x for x in peers if (d[x].get("technical_features") or {}).get("is_current_session")]; metrics = {metric: _numeric_context(ticker, metric, current_peers, d) for metric in TECHNICAL_METRICS}; states = Counter((t.get(x) or {}).get("entry_state") for x in current_peers); states.pop(None, None)
        technical = {"status": "AVAILABLE" if group["status"] == "AVAILABLE" and any(value.get("status") == "AVAILABLE" for value in metrics.values()) else "INSUFFICIENT_COHORT_OR_METRIC_UNAVAILABLE", "eligible_count": len(current_peers), "metrics": metrics, "tactical_state_distribution": dict(sorted(states.items())), "technical_state": (t.get(ticker) or {}).get("ticker_structure_state"), "entry_state": (t.get(ticker) or {}).get("entry_state")}
        fund = _fundamental_context(ticker, peers, f) if group["status"] == "AVAILABLE" else {"status": "INSUFFICIENT_COHORT", "available_dimension_count": 0, "dimensions": {}, "authority_tier": (f.get(ticker) or {}).get("authority_tier"), "limitations": ["INSUFFICIENT_COHORT"]}
        shadow = (((v.get(ticker) or {}).get("shadow_proxy_valuation") or {}).get("metrics") or {}); valuation_context = {"status": "VALUATION_PEER_CONTEXT_UNAVAILABLE", "eligible_count": 0, "reason_codes": ["SHARE_PROXY_SEMANTICS_AND_FINANCIAL_AUTHORITY_METRIC_IDENTITY_OR_COHORT_NOT_SIMULTANEOUSLY_ESTABLISHED"], "shadow_proxy_available": any(value.get("status") == "SHADOW_PROXY_READY" for value in shadow.values() if isinstance(value, Mapping))}
        expectation = _expectation(t.get(ticker) or {}, fund, technical)
        records[ticker] = {"ticker": ticker, "peer_membership": membership, "technical_peer_context": technical, "fundamental_peer_context": fund, "valuation_peer_context": valuation_context, "expectations_context": {"state": expectation, "descriptive_only": True, "counter_evidence": ["VALUATION_PEER_CONTEXT_UNAVAILABLE"] if expectation != "MIXED_OR_INSUFFICIENT_EVIDENCE" else []}, "tactical_state_preserved": {key: (t.get(ticker) or {}).get(key) for key in ("entry_state", "action", "is_actionable", "is_full_position_ready")}, "data_gaps": ["VALUATION_PEER_CONTEXT_UNAVAILABLE"] + ([] if membership["status"] == "AVAILABLE" else ["INSUFFICIENT_COHORT"]), "authority_limitations": ["No ranking, recommendation, target, probability, sizing, alpha, or valuation comparison.", "Technical metrics are retained shadow/provider-scoped descriptive facts only."], "is_actionable": False}
    representative_ids = [group_id for group_id, group in group_summary.items() if group["status"] == "AVAILABLE" and group["peer_group_level"] == "RETAINED_PROVIDER_DESCRIPTIVE_INDUSTRY"][:4]
    blocks = {"watchlist": [_research_block(records[x]) for x in WATCHLIST if x in records], "preopen_47": [_research_block(records[x]) for x in PREOPEN_47 if x in records], "representative_peer_groups": {group_id: _research_block(records[group_summary[group_id]["members"][0]]) for group_id in ["ENTITY_CLASS:BANK", "ENTITY_CLASS:SECURITIES", *representative_ids] if group_id in group_summary}}
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "source_artifacts": {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"]}, "peer_groups": group_summary, "records": records, "human_use_research_blocks": blocks, "coverage": {"candidate_universe": len(records), "peer_membership_available": sum(record["peer_membership"]["status"] == "AVAILABLE" for record in records.values()), "unresolved_peer_membership": sum(record["peer_membership"]["peer_group_id"] == "UNKNOWN" for record in records.values()), "technical_peer_available": sum(record["technical_peer_context"]["status"] == "AVAILABLE" for record in records.values()), "fundamental_peer_available": sum(record["fundamental_peer_context"]["status"] == "AVAILABLE" for record in records.values()), "valuation_peer_available": 0, "shadow_valuation_available": sum(record["valuation_peer_context"]["shadow_proxy_available"] for record in records.values()), "expectations_counts": dict(sorted(Counter(record["expectations_context"]["state"] for record in records.values()).items()))}, "authority_boundary": {"ranking": False, "recommendation": False, "target_price": False, "probability": False, "sizing": False, "provider_absolute_fundamentals": False, "shadow_valuation_non_authoritative": True}, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact
