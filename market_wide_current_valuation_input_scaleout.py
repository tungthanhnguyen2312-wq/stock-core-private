"""Deterministic, fail-closed market-wide current valuation snapshot.

This consumes retained current-session price, share-basis, and fundamental
artifacts only. It emits a blocked metric rather than substitute provider
trends, issued shares, or a historical price for a missing compatible input.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id
import mva_provider_share_proxy as issued_share_proxy

CONTRACT_VERSION = "market_wide_current_valuation/v1"
ARTIFACT_TYPE = "MARKET_WIDE_CURRENT_VALUATION"
METRICS = ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales", "EV/EBITDA")
SHADOW_METRICS = ("proxy_market_cap", "proxy_P/E", "proxy_P/B", "proxy_P/S", "proxy_EV", "proxy_EV/Sales", "proxy_EV/EBITDA")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_valuation:{digest}"}


def _share_disposition(ticker: str, promotion: Mapping[str, Any]) -> dict[str, Any]:
    """Only ticker-level retained share evidence may describe a ticker's basis."""
    cohort = (promotion.get("projected_coverage_impact") or {}).get("cohort_rows") or []
    row = next((item for item in cohort if item.get("ticker") == ticker), None)
    source = promotion.get("artifact_identity")
    if row is None:
        return {"status": "UNAVAILABLE", "authority": "UNAVAILABLE", "value": None,
                "source_artifact_identity": source, "freshness": "UNKNOWN",
                "blocked_reasons": ["NO_TICKER_LEVEL_CURRENT_SHARE_BASIS_EVIDENCE_RETAINED"]}
    # The retained official reference did not prove coverage through the newer price session.
    return {"status": "PROVIDER_REPORTED_STALE", "authority": str(row.get("resolver_authority") or "UNAVAILABLE"),
            "value": row.get("provider_value"), "source_artifact_identity": source,
            "freshness": str(row.get("freshness_state") or "UNKNOWN"),
            "blocked_reasons": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"],
            "retained_evidence": dict(row)}


def _price_input(record: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    observation = (record.get("observations") or [{}])[-1]
    ready = record.get("disposition") == "EXACT_SESSION_RETAINED"
    return {"status": "PRICE_READY" if ready else "PRICE_UNAVAILABLE", "value": observation.get("close") if ready else None,
            "session": snapshot.get("resolved_completed_session"), "source": snapshot.get("source"),
            "basis": "CURRENT_SESSION_DESCRIPTIVE_CURRENT_VALUATION_PRICE_LEG", "currency": "VND",
            "raw_as_traded": "NOT_PROMOTED", "historical_pit_eligible": False,
            "source_snapshot_identity": snapshot.get("snapshot_identity"),
            "blocked_reasons": [] if ready else [f"PRICE_{record.get('disposition', 'UNAVAILABLE')}"]}


def _applicability(entity: str, metric: str) -> str:
    if metric == "market_cap":
        return "APPLICABLE"
    if entity == "corporate":
        return "APPLICABLE" if metric != "EV/EBITDA" else "APPLICABLE_IF_EXACT_EBITDA"
    if entity in {"bank", "securities"}:
        return "APPLICABLE" if metric in {"P/E", "P/B"} else "NOT_APPLICABLE"
    if entity in {"finance_company", "insurance"}:
        return "NOT_APPLICABLE"
    return "BLOCKED_ENTITY_CLASS_UNKNOWN"


def _financial_input(fundamental: Mapping[str, Any] | None, artifact: Mapping[str, Any]) -> dict[str, Any]:
    if fundamental is None:
        return {"authority": "UNAVAILABLE", "calculation_grade": False, "blocked_reasons": ["NO_RETAINED_FINANCIAL_RECORD"]}
    tier = fundamental.get("authority_tier")
    if tier != "OFFICIAL_QUALIFIED":
        return {"authority": tier, "calculation_grade": False,
                "blocked_reasons": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"],
                "source_artifact_identity": artifact.get("artifact_identity")}
    return {"authority": "OFFICIAL_QUALIFIED", "calculation_grade": True,
            "source_artifact_identity": artifact.get("artifact_identity"),
            "metric_count": len(fundamental.get("metrics") or []),
            "period_context": fundamental.get("official_metric_context")}


def _metric(metric: str, applicability: str, price: Mapping[str, Any], share: Mapping[str, Any], financial: Mapping[str, Any]) -> dict[str, Any]:
    if applicability == "NOT_APPLICABLE":
        return {"metric_id": metric, "status": "NOT_APPLICABLE", "value": None, "applicability": applicability,
                "formula_version": CONTRACT_VERSION, "blocked_reasons": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]}
    blockers = []
    if price["status"] != "PRICE_READY":
        blockers.extend(price["blocked_reasons"])
    if share["status"] != "QUALIFIED_OFFICIAL":
        blockers.extend(share["blocked_reasons"])
    if metric != "market_cap":
        if applicability == "BLOCKED_ENTITY_CLASS_UNKNOWN":
            blockers.append("ENTITY_CLASS_UNRESOLVED")
        if not financial["calculation_grade"]:
            blockers.extend(financial["blocked_reasons"])
        if metric == "EV/EBITDA":
            blockers.append("EXACT_EBITDA_COMPARABILITY_NOT_RETAINED")
    return {"metric_id": metric, "status": "BLOCKED", "value": None, "applicability": applicability,
            "formula_version": CONTRACT_VERSION, "blocked_reasons": sorted(set(blockers)),
            "price_session": price.get("session"), "is_actionable": False, "historical_pit_eligible": False}


def build_current_valuation_artifact(*, price_snapshot: Mapping[str, Any], fundamental_artifact: Mapping[str, Any],
                                     share_promotion_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize one record per retained price-universe ticker without imputation."""
    records: dict[str, Any] = {}
    fundamentals = fundamental_artifact.get("records") or {}
    for ticker, price_record in sorted((price_snapshot.get("records") or {}).items()):
        fundamental = fundamentals.get(ticker)
        entity = str((fundamental or {}).get("entity_class") or "unknown")
        price = _price_input(price_record, price_snapshot)
        share = _share_disposition(ticker, share_promotion_artifact)
        financial = _financial_input(fundamental, fundamental_artifact)
        metric_rows = {metric: _metric(metric, _applicability(entity, metric), price, share, financial) for metric in METRICS}
        row = {"ticker": ticker, "entity_class": entity, "entity_class_source": (fundamental or {}).get("entity_class_provenance"),
               "price_input": price, "share_basis_input": share, "financial_input": financial,
               "metrics": metric_rows, "warnings": ["CURRENT_DESCRIPTIVE_NOT_HISTORICAL_PIT", "NO_RANKING_OR_RECOMMENDATION"],
               "is_actionable": False}
        row["content_identity"] = stable_id(row)
        records[ticker] = row
    metric_ready = {metric: sum(row["metrics"][metric]["status"] == "READY" for row in records.values()) for metric in METRICS}
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "valuation_session": price_snapshot.get("resolved_completed_session"),
        "source_artifacts": {"current_price": price_snapshot.get("snapshot_identity"), "fundamental": fundamental_artifact.get("artifact_identity"), "share_basis": share_promotion_artifact.get("artifact_identity")},
        "records": records,
        "coverage": {"candidate_universe": len(records), "price_ready": sum(r["price_input"]["status"] == "PRICE_READY" for r in records.values()),
                     "share_ready": sum(r["share_basis_input"]["status"] == "QUALIFIED_OFFICIAL" for r in records.values()),
                     "both_price_and_share_ready": sum(r["price_input"]["status"] == "PRICE_READY" and r["share_basis_input"]["status"] == "QUALIFIED_OFFICIAL" for r in records.values()),
                     "metric_ready_counts": metric_ready,
                     "share_authority_tiers": dict(sorted(Counter(r["share_basis_input"]["status"] for r in records.values()).items())),
                     "financial_authority_tiers": dict(sorted(Counter(r["financial_input"]["authority"] for r in records.values()).items())),
                     "entity_classes": dict(sorted(Counter(r["entity_class"] for r in records.values()).items())),
                     "blocked_or_not_applicable": dict(sorted(Counter(m["status"] for r in records.values() for m in r["metrics"].values()).items()))},
        "authority_boundary": {"current_snapshot_only": True, "historical_pit_eligible": False, "raw_as_traded": "NOT_PROMOTED", "provider_financial_absolute_inputs": "BLOCKED", "ranking": False, "recommendation": False, "target_price": False},
        "valuation_context": {"status": "SKIPPED", "reason": "NO_METRIC_READY_COMPARABLE_COHORT"}, "is_actionable": False,
    }
    artifact.update(content_identity(artifact))
    return artifact


def _shadow_price(record: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    base = _price_input(record, snapshot)
    return {"status": "PRICE_READY" if base["status"] == "PRICE_READY" else "PRICE_BLOCKED",
            "value": base["value"], "reason_codes": base["blocked_reasons"], "provider": base["source"],
            "field_identity": "close", "session": base["session"], "payload_identity": base["source_snapshot_identity"],
            "price_basis": base["basis"], "price_namespace": "CURRENT_MARKET", "raw_as_traded": "NOT_PROMOTED"}


def _shadow_metric(name: str, source: Mapping[str, Any], *, entity: str) -> dict[str, Any]:
    status = source.get("status")
    ready = status in {"PROXY_MARKET_CAP_READY", "MVA_PROXY_READY"}
    return {"metric_id": name, "status": "SHADOW_PROXY_READY" if ready else ("NOT_APPLICABLE" if status == "NOT_APPLICABLE" else "BLOCKED"),
            "value": source.get("value") if ready else None, "entity_class": entity,
            "formula_version": issued_share_proxy.POLICY_VERSION, "labels": ["SHADOW", "DESCRIPTIVE", "NON_AUTHORITATIVE", "NOT_COMMON_OUTSTANDING_SHARE_BASIS", "NOT_PIT", "NOT_FOR_TARGET_PRICE", "NOT_FOR_SIZING", "NOT_FOR_EXECUTION"],
            "blocked_reasons": list(source.get("blockers") or []), "is_actionable": False}


def attach_shadow_proxy_valuation(*, authoritative_artifact: Mapping[str, Any], price_snapshot: Mapping[str, Any],
                                  p3e_artifact: Mapping[str, Any], provider_observations: Mapping[str, Mapping[str, Any]],
                                  safety_states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Add the owner-approved issued-share MVA shadow lane without changing strict metrics."""
    artifact = copy.deepcopy(dict(authoritative_artifact))
    envelope = dict(issued_share_proxy.REQUIRED_ENVELOPE)
    issuers = {str(item["issuer_identity"]["ticker"]): item for item in (p3e_artifact.get("refreshed_panel_data") or {}).get("issuers", [])}
    freshness, proxy_statuses, financial_usage, blockers = Counter(), Counter(), Counter(), Counter()
    shadow_ready = Counter()
    for ticker, row in artifact["records"].items():
        price = _shadow_price((price_snapshot.get("records") or {}).get(ticker, {}), price_snapshot)
        proxy = issued_share_proxy.qualify_provider_issued_shares_proxy(
            {"canonical_ticker": ticker}, provider_observations.get(ticker), valuation_date=str(price_snapshot.get("resolved_completed_session")),
            safety_state=safety_states.get(ticker), envelope=envelope,
        )
        cap = issued_share_proxy.build_provider_proxy_market_cap(price, proxy, envelope=envelope)
        entity = row["entity_class"]
        values: dict[str, Mapping[str, Any]] = {"proxy_market_cap": cap}
        issuer = issuers.get(ticker)
        if issuer is not None:
            calculated = issued_share_proxy.evaluate_mva_proxy_issuer(issuer, price=price, proxy=proxy, envelope=envelope)
            method_map = calculated["methods"]
            values.update({f"proxy_{name}": method_map[name] for name in ("P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA")})
            # P3-F emits EV as an intermediate on EV/Sales; retain it only when the same exact inputs did.
            ev_sales = method_map["EV/Sales"]
            values["proxy_EV"] = {"status": "MVA_PROXY_READY" if ev_sales.get("status") == "MVA_PROXY_READY" else ev_sales.get("status"),
                                  "value": ev_sales.get("enterprise_value"), "blockers": ev_sales.get("blockers")}
            financial_usage["OFFICIAL_QUALIFIED"] += 1
        else:
            for name in ("proxy_P/E", "proxy_P/B", "proxy_P/S", "proxy_EV", "proxy_EV/Sales", "proxy_EV/EBITDA"):
                base_metric = name.removeprefix("proxy_")
                applicable = _applicability(entity, base_metric if base_metric != "EV" else "enterprise_value")
                values[name] = ({"status": "NOT_APPLICABLE", "value": None, "blockers": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]}
                                if applicable == "NOT_APPLICABLE" else
                                {"status": "VALUATION_BLOCKED", "value": None, "blockers": ["OFFICIAL_QUALIFIED_FINANCIAL_INPUT_UNAVAILABLE"]})
            financial_usage["UNAVAILABLE_OR_PROVIDER_RESEARCH_ONLY"] += 1
        metrics = {name: _shadow_metric(name, values[name], entity=entity) for name in SHADOW_METRICS}
        for metric in metrics.values():
            if metric["status"] == "SHADOW_PROXY_READY":
                shadow_ready[metric["metric_id"]] += 1
            for reason in metric["blocked_reasons"]:
                blockers[reason] += 1
        freshness[proxy["freshness_state"]] += 1
        proxy_statuses[proxy["status"]] += 1
        row["shadow_proxy_valuation"] = {
            "share_basis_type": "PROVIDER_ISSUED_SHARE_PROXY", "authority_tier": "SHADOW_RESEARCH_ONLY",
            "provider": proxy.get("provider_source"), "source_observation": proxy,
            "price_session": price.get("session"), "age_days": proxy.get("observation_age_days"),
            "allowed_uses": ["CURRENT_DESCRIPTIVE_SHADOW_VALUATION_ONLY"],
            "forbidden_uses": ["COMMON_SHARES_OUTSTANDING", "AUTHORITATIVE_VALUATION", "PIT", "TARGET_PRICE", "SIZING", "EXECUTION", "RANKING", "RECOMMENDATION"],
            "metrics": metrics, "is_actionable": False,
        }
    for metric in SHADOW_METRICS:
        shadow_ready.setdefault(metric, 0)
    artifact["shadow_proxy_valuation_coverage"] = {
        "proxy_share_statuses": dict(sorted(proxy_statuses.items())), "share_freshness_buckets": dict(sorted(freshness.items())),
        "financial_authority_usage": dict(sorted(financial_usage.items())), "metric_ready_counts": dict(sorted(shadow_ready.items())),
        "tickers_with_any_shadow_proxy_metric": sum(any(m["status"] == "SHADOW_PROXY_READY" for m in r["shadow_proxy_valuation"]["metrics"].values()) for r in artifact["records"].values()),
        "blocker_reasons": dict(sorted(blockers.items())),
    }
    artifact["source_artifacts"]["provider_issued_share_proxy_policy"] = issued_share_proxy.POLICY_VERSION
    artifact["authority_boundary"]["shadow_proxy_issued_shares"] = "SHADOW_RESEARCH_ONLY_NOT_COMMON_OUTSTANDING"
    artifact["authority_boundary"]["authoritative_metrics_unchanged"] = True
    artifact.update(content_identity(artifact))
    return artifact
