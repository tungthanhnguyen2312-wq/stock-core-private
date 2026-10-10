"""Immutable supplemental T-state context for prospective research learning."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

METHOD = "prospective_research_context_extension/v1"
SUPERSEDED_LEGACY_EXTENSION_ID = "prospective_research_context_extension:1248d909c9ffd204d9bbcfbf3c886a4621e690c6739b5c8736fcab3bf7f58339"
SUPERSEDED_LEGACY_DOWNSIDE_ID = "downside_uncertainty_research_context:da28e80273f2aaf488fbd9060b3a908584202ed030b2e5314c2d81e77933dfef"
ATTRIBUTION_SAFE_SUCCESSOR_ID = "prospective_research_context_extension:6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _require_same_session(expected: str, name: str, artifact: Mapping[str, Any]) -> None:
    if str(artifact.get("research_session")) != expected:
        raise ValueError(f"TEMPORAL_SOURCE_SESSION_MISMATCH:{name}")


def _level_identity(level: Mapping[str, Any]) -> str:
    return "price_level_candidate:" + _hash(level)


def build(snapshot: Mapping[str, Any], setup: Mapping[str, Any], price: Mapping[str, Any], market: Mapping[str, Any],
          downside: Mapping[str, Any], relative: Mapping[str, Any]) -> dict[str, Any]:
    session = str(snapshot.get("research_session"))
    if session != "2026-08-20" or snapshot.get("future_outcomes") != "PENDING_FUTURE_OBSERVATION":
        raise ValueError("PROSPECTIVE_SNAPSHOT_NOT_PENDING_T_STATE")
    for name, artifact in (("setup", setup), ("price", price), ("market", market), ("downside", downside), ("relative", relative)):
        _require_same_session(session, name, artifact)
    frozen = {row["ticker"]: row for row in snapshot["frozen_records"]}
    setup_rows = {row["ticker"]: row for row in setup["records"]}
    price_rows = {row["ticker"]: row for row in price["records"]}
    downside_rows = {row["ticker"]: row for row in downside["records"]}
    relative_rows = {row["ticker"]: row for row in relative["records"]}
    if not frozen or not (set(frozen) == set(setup_rows) == set(price_rows) == set(downside_rows) == set(relative_rows)):
        raise ValueError("EXTENSION_COHORT_MEMBERSHIP_MISMATCH")
    source_ids = {"original_snapshot": snapshot["snapshot_id"], "setup": setup["artifact_identity"],
                  "price": price["artifact_identity"], "market": market["artifact_identity"],
                  "downside": downside["artifact_identity"], "relative": relative["artifact_identity"]}
    participation = next(item["descriptor"] for item in market["descriptors"] if item["descriptor"].startswith("EMPIRICAL_COHORT_TREND_PARTICIPATION"))
    shared_market = {"research_session": session, "source_identity": market["artifact_identity"],
                     "trend_descriptor": market["breadth"]["trend"]["descriptor"]["descriptor"],
                     "momentum_descriptor": market["breadth"]["momentum"]["descriptor"]["descriptor"],
                     "trend_participation_descriptor": participation,
                     "authority": market["cohort"]["authority"]}
    shared_market["market_context_content_identity"] = "prospective_market_context:" + _hash(shared_market)
    records = []
    for ticker in sorted(frozen):
        source_setup = setup_rows[ticker]; source_price = price_rows[ticker]; source_downside = downside_rows[ticker]; source_relative = relative_rows[ticker]
        evaluations = [{"setup_id": item["setup_id"], "qualification_state": item["qualification_state"],
                        "authority_ceiling": item["authority_ceiling"], "setup_content_identity": item["setup_content_identity"]}
                       for item in source_setup["setup_evaluations"]]
        resistance = source_price["levels"]["prior_19_session_close_resistance"]
        support = source_price["levels"]["prior_19_session_close_support"]
        relative_state = {"context_status": source_relative["context_status"],
                          "relative_context_authority": source_relative.get("relative_context_authority", "UNAVAILABLE"),
                          "cohort_identity": source_relative.get("cohort", {}).get("cohort_identity") if source_relative.get("cohort") else None,
                          "unavailable_reasons": [metric["missing_or_exclusion_reason"] for metric in source_relative["relative_metrics"] if metric["status"] == "UNAVAILABLE"],
                          "available_metric_identities": [metric["metric_identity"] for metric in source_relative["relative_metrics"] if metric["status"] == "AVAILABLE"]}
        relative_authority = relative_state["relative_context_authority"]
        relative_key = "relative_authority:QUALIFIED" if relative_authority == "QUALIFIED_CLASSIFICATION" else "relative_authority:PROVIDER_DESCRIPTIVE" if relative_authority == "PROVIDER_DESCRIPTIVE_CLASSIFICATION" else "relative_authority:UNAVAILABLE"
        keys = ([f"setup:{item['setup_id']}" for item in evaluations if item["qualification_state"] in ("QUALIFIED_SHADOW", "QUALIFIED_LOWER_AUTHORITY")] +
                [f"market:{shared_market['trend_descriptor']}", f"downside:{source_downside['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status']}",
                 f"authority:{frozen[ticker]['fundamental_authority']}", relative_key])
        record = {"ticker": ticker, "research_session": session, "original_frozen_record_identity": "prospective_frozen_record:" + _hash(frozen[ticker]),
                  "original_snapshot_identity": snapshot["snapshot_id"], "setup": {"active_setup_ids": source_setup["active_setup_ids"],
                  "record_setup_state": source_setup["record_setup_state"], "evaluations": evaluations, "source_identity": setup["artifact_identity"]},
                  "price_structure": {"structure_status": source_price["structure_status"], "range_state": source_price.get("range_state"),
                  "volume_proxy_state": source_price.get("volume_proxy_state"), "method": source_price["method"], "warnings": source_price["warnings"],
                  "resistance_candidate": {"identity": _level_identity(resistance), "value": resistance["value"], "distance_from_close": resistance["distance_from_close"]},
                  "support_candidate": {"identity": _level_identity(support), "value": support["value"], "distance_from_close": support["distance_from_close"]}, "source_identity": price["artifact_identity"]},
                  "market_context_reference": shared_market["market_context_content_identity"],
                  "downside_uncertainty": {"technical": source_downside["domains"]["TECHNICAL_DOWNSIDE_CONTEXT"], "scenario": source_downside["domains"]["SCENARIO_DOWNSIDE_CONTEXT"],
                  "evidence_uncertainty": source_downside["domains"]["EVIDENCE_UNCERTAINTY"], "execution": source_downside["domains"]["EXECUTION_RISK_STATUS"],
                  "event_visibility": source_downside["domains"]["EVENT_VISIBILITY"], "human_review_reasons": source_downside["human_downside_review_reasons"], "source_identity": downside["artifact_identity"]},
                  "relative_context": {**relative_state, "source_identity": relative["artifact_identity"]}, "prospective_cohort_keys": sorted(set(keys))}
        record["context_record_content_identity"] = "prospective_context_record:" + _hash(record)
        records.append(record)
    key_counts = Counter(key for row in records for key in row["prospective_cohort_keys"])
    artifact = {"schema_version": "1.0.0", "contract_version": METHOD, "research_session": session,
                "original_snapshot_identity": snapshot["snapshot_id"], "source_artifact_identities": source_ids,
                "seal": {"sealed_before_accepted_future_observation": True, "precondition": "NO_RETAINED_EXACT_SESSION_GT_2026_08_20_AT_CREATION",
                         "data_session_not_software_creation_timestamp": True, "future_outcomes": "PENDING_FUTURE_OBSERVATION"},
                "shared_market_context": shared_market, "records": records,
                "coverage": {"records": len(records), "setup_linkage_count": len(records), "price_structure_linkage_count": len(records),
                             "market_context_linkage_count": len(records), "downside_linkage_count": len(records), "relative_context_linkage_count": len(records),
                             "cohort_key_count": len(key_counts), "cohort_key_member_counts": dict(sorted(key_counts.items())),
                             "relative_authority_counts": dict(Counter(row["relative_context"]["relative_context_authority"] for row in records)),
                             "no_distinct_setup_count": sum(row["setup"]["record_setup_state"] == "NO_DISTINCT_SETUP" for row in records),
                             "unavailable_relative_context_count": sum(row["relative_context"]["context_status"] != "AVAILABLE" for row in records)},
                "authority_boundary": {"shadow_t_state_only": True, "not_historical_pit_backtest_or_strategy_performance": True,
                                       "provider_relative_volume_is_derived_proxy_not_liquidity": True, "no_outcome_conditioned_feature_construction": True},
                "verdict": "PROSPECTIVE_RESEARCH_CONTEXT_EXTENSION_V1_READY"}
    artifact["extension_content_identity"] = "prospective_research_context_extension:" + _hash(artifact)
    return artifact


def write_immutable(path: Path, extension: Mapping[str, Any]) -> None:
    payload = _canon(extension) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_CONTEXT_EXTENSION_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

def build_successor(snapshot: Mapping[str, Any], predecessor: Mapping[str, Any], setup: Mapping[str, Any], price: Mapping[str, Any], market: Mapping[str, Any], downside_v1: Mapping[str, Any], downside_v2: Mapping[str, Any], relative: Mapping[str, Any]) -> dict[str, Any]:
    if predecessor.get('research_session') != snapshot.get('research_session') or predecessor.get('seal', {}).get('future_outcomes') != 'PENDING_FUTURE_OBSERVATION':
        raise ValueError('PREDECESSOR_EXTENSION_NOT_PRE_OUTCOME_T_STATE')
    if predecessor.get('extension_content_identity') != SUPERSEDED_LEGACY_EXTENSION_ID or predecessor.get('source_artifact_identities', {}).get('downside') != SUPERSEDED_LEGACY_DOWNSIDE_ID:
        raise ValueError('UNEXPECTED_PREDECESSOR_EXTENSION_LINEAGE')
    if downside_v1.get('contract_version') != 'downside_uncertainty_research_context/v1' or downside_v2.get('contract_version') != 'downside_uncertainty_research_context/v2':
        raise ValueError('DOWNSIDE_VERSION_LINEAGE_INVALID')
    base = build(snapshot, setup, price, market, downside_v1, relative)
    v2 = {row['ticker']: row for row in downside_v2['records']}
    for row in base['records']:
        row['downside_uncertainty']['price_structure_downside_context'] = v2[row['ticker']]['domains']['PRICE_STRUCTURE_DOWNSIDE_CONTEXT']
        row['downside_uncertainty']['v2_source_identity'] = downside_v2['artifact_identity']
        row['prospective_cohort_keys'] = [key for key in row['prospective_cohort_keys'] if not key.startswith('downside:')]
        row['prospective_cohort_keys'].append('downside:' + row['downside_uncertainty']['technical']['status'] + '_V1')
        if row['price_structure']['structure_status'] == 'NEAR_RECENT_SUPPORT': row['prospective_cohort_keys'].append('price_structure:NEAR_RECENT_SUPPORT_CONTEXT')
        if row['price_structure']['structure_status'] == 'BREAKDOWN_CONFIRMED_BY_RULE': row['prospective_cohort_keys'].append('price_structure:BREAKDOWN_CONTEXT')
        row['prospective_cohort_keys'] = sorted(set(row['prospective_cohort_keys']))
        row['context_record_content_identity'] = 'prospective_context_record:' + _hash({key: value for key, value in row.items() if key != 'context_record_content_identity'})
    key_counts = Counter(key for row in base['records'] for key in row['prospective_cohort_keys'])
    base['source_artifact_identities']['downside_v1_core'] = downside_v1['artifact_identity']; base['source_artifact_identities']['downside_v2_price_structure'] = downside_v2['artifact_identity']
    base['predecessor_extension_identity'] = predecessor['extension_content_identity']; base['supersession'] = {'status': 'SUPERSEDED_FOR_FUTURE_ATTRIBUTION', 'reason': 'DOWNSIDE_V1_SEMANTIC_VERSION_REPAIR_PRICE_STRUCTURE_SEPARATED', 'legacy_downside_identity': SUPERSEDED_LEGACY_DOWNSIDE_ID, 'restored_v1_core_identity': downside_v1['artifact_identity'], 'v2_price_structure_identity': downside_v2['artifact_identity']}; base['attribution_eligibility'] = 'SAFE_SUCCESSOR_FOR_FIRST_ATTRIBUTION'
    base['coverage']['cohort_key_count'] = len(key_counts); base['coverage']['cohort_key_member_counts'] = dict(sorted(key_counts.items())); base['coverage']['core_v1_adverse_count'] = key_counts['downside:OBSERVED_ADVERSE_TECHNICAL_CONTEXT_V1']; base['coverage']['price_near_support_count'] = key_counts['price_structure:NEAR_RECENT_SUPPORT_CONTEXT']; base['coverage']['price_breakdown_count'] = key_counts['price_structure:BREAKDOWN_CONTEXT']
    base['seal']['ambiguous_predecessor_retained_not_attribution_eligible'] = True
    base.pop('extension_content_identity', None); base['extension_content_identity'] = 'prospective_research_context_extension:' + _hash(base)
    return base
