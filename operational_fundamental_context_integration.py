"""Entity-aware bridge from retained operational features to Current Research context.

This module never computes financial facts. It only qualifies existing feature-store
records for a narrower Current Research use and preserves each source feature.

``build_artifact`` replays the frozen 2026-09-24 cohort (regression evidence only).
``build_daily_artifact`` is the ordinary-Daily binding: the same per-ticker qualification over
a generic, deterministic selection, never a ticker list.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
import calendar
from typing import Any, Mapping, Sequence

from entity_classification_contract import (
    APPLICABILITY_RESOLVED, CURRENT_RESEARCH_ENTITY_APPLICABILITY_CONTRACT,
    entity_applicability_content_identity,
)
from stocklookup_core.financial.financial_entity_applicability import CORPORATE_ENTITY_TYPES, FINANCIAL_ENTITY_TYPES
import market_wide_fundamental_feature_store as feature_store_contract
from market_wide_fundamental_feature_store import (
    COMPATIBILITY_VERSION, FEATURE_FAMILY, NATIVE, PARTIAL, PIT, PROXY, READY,
)


CONTRACT_VERSION = "entity_aware_operational_fundamental_context_integration/v1"
DAILY_BINDING_MODE = "ORDINARY_DAILY_GENERIC_SELECTION"
#: The one selection rule the Daily binding may use. The Integrated Decision consults this
#: bridge only for a ticker whose Financial V2 direction is INSUFFICIENT and not conflicted or
#: blocked; evaluating anything else could never change a decision.
DAILY_SELECTION_RULE = "FINANCIAL_V2_DIRECTION_INSUFFICIENT_NOT_CONFLICTED_OR_BLOCKED"


class OperationalFundamentalIntegrationError(ValueError):
    """A supplied source contract or identity is invalid; the binding fails closed."""
MAX_COMPLETED_QUARTER_LAG = 4
USABLE_STATUSES = frozenset({READY, PROXY, PARTIAL})
USABLE_COMPATIBILITY = frozenset({NATIVE, PIT, "EXACT_TYPED_RESEARCH_COMPATIBLE"})
PERMITTED_DURATION = frozenset({"STANDALONE_QUARTER", "POINT_IN_TIME_BALANCE_SHEET"})
CORE_SECONDARY_CORPORATE = frozenset({
    "revenue_same_period_yoy", "net_income_same_period_yoy", "net_margin", "gross_margin",
    "total_assets_pit_trajectory", "shareholders_equity_pit_trajectory",
    "cash_earnings_alignment", "operating_cash_flow_sign",
})
CORE_SECONDARY_FINANCIAL = frozenset({
    "total_assets_pit_trajectory", "shareholders_equity_pit_trajectory",
})
FINANCIAL_ALLOWED = frozenset({
    "profit_state", "net_income_same_period_yoy", "total_assets_pit_trajectory",
    "shareholders_equity_pit_trajectory", "cash_and_cash_equivalents_pit_trajectory",
})
CORPORATE_ALLOWED = frozenset(FEATURE_FAMILY)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _quarter_index(label: Any) -> int | None:
    match = re.fullmatch(r"(20\d{2})-Q([1-4])", str(label or ""))
    return int(match[1]) * 4 + int(match[2]) if match else None


def _feature_fitness(feature: Mapping[str, Any], *, session: str) -> tuple[str, list[str]]:
    if feature.get("status") not in USABLE_STATUSES:
        return "SOURCE_BLOCKED", list(feature.get("blocker_reason_codes") or ["FEATURE_SOURCE_BLOCKED"])
    if (feature.get("research_fitness") != feature.get("status")
            or feature.get("compatibility_class") not in USABLE_COMPATIBILITY
            or feature.get("compatibility_rule_version") != COMPATIBILITY_VERSION):
        return "METHOD_CONFLICT", ["METHOD_CONFLICT"]
    if (feature.get("authority_tier") != "OPERATIONAL_PROVIDER_RESEARCH_ONLY"
            or feature.get("authoritative_financial_eligible") is not False
            or feature.get("pit_backtest_eligible") is not False
            or feature.get("is_actionable") is not False):
        return "AUTHORITY_CONFLICT", ["AUTHORITY_CONFLICT"]
    if feature.get("blocker_reason_codes") or not feature.get("method"):
        return "METHOD_CONFLICT", list(feature.get("blocker_reason_codes") or ["METHOD_CONFLICT"])
    periods = feature.get("input_periods") or []
    indices = [_quarter_index(label) for label in periods]
    if not indices or any(index is None for index in indices):
        return "PERIOD_SEMANTICS_INSUFFICIENT", ["PERIOD_SEMANTICS_INSUFFICIENT"]
    day = date.fromisoformat(session)
    session_quarter = (day.month - 1) // 3 + 1
    session_index = day.year * 4 + session_quarter
    end_month = session_quarter * 3
    last_completed = session_index if day >= date(day.year, end_month, calendar.monthrange(day.year, end_month)[1]) else session_index - 1
    if max(indices) > last_completed:
        return "PERIOD_SEMANTICS_INSUFFICIENT", ["PERIOD_SEMANTICS_INSUFFICIENT"]
    if session_index - max(indices) > MAX_COMPLETED_QUARTER_LAG:
        return "FEATURE_STALE", ["FEATURE_STALE"]
    durations = feature.get("duration_semantics") or []
    scopes = feature.get("scope") or []
    lineage = feature.get("provider_source_lineage") or []
    if (not durations or not set(durations) <= PERMITTED_DURATION or not scopes
            or not lineage or len(lineage) != len(periods)):
        return "SCOPE_CONFLICT", ["SCOPE_CONFLICT"]
    if (feature.get("feature_id", "").endswith("_pit_trajectory")
            and durations != ["POINT_IN_TIME_BALANCE_SHEET"]):
        return "PERIOD_SEMANTICS_INSUFFICIENT", ["PERIOD_SEMANTICS_INSUFFICIENT"]
    if feature.get("feature_id") == "profit_state" and durations != ["STANDALONE_QUARTER"]:
        return "PERIOD_SEMANTICS_INSUFFICIENT", ["PERIOD_SEMANTICS_INSUFFICIENT"]
    # An unknown external consolidated/separate label is retained as unknown.
    # Same-native comparisons may still be used within their explicitly retained
    # provider, file, period, and scope group; no cross-issuer or absolute claim follows.
    if any(not isinstance(item, Mapping) or not item.get("provider") or not item.get("source_file")
           or not item.get("source_sha256") for item in lineage):
        return "SCOPE_CONFLICT", ["SCOPE_CONFLICT"]
    if len({(item["provider"], item["source_file"]) for item in lineage}) != 1:
        return "SCOPE_CONFLICT", ["SCOPE_CONFLICT"]
    if len(set(scopes)) != 1:
        return "SCOPE_CONFLICT", ["SCOPE_CONFLICT"]
    return "RESEARCH_USABLE", []


def evaluate_ticker(*, ticker: str, entity_class: str | None, feature_record: Mapping[str, Any] | None,
                    session: str) -> dict[str, Any]:
    """Qualify existing features; an absent specialist metric never erases valid core evidence."""
    entity = str(entity_class or "unknown").lower()
    source = feature_record or {}
    source_entity = str(source.get("entity_type") or "unknown").lower()
    supported = entity in CORPORATE_ENTITY_TYPES | FINANCIAL_ENTITY_TYPES
    if feature_record is None:
        # No retained feature record: the absent evidence is the reason, never an entity
        # mismatch against a record that does not exist.
        reasons = ["FEATURE_STORE_RECORD_ABSENT", *([] if supported else ["ENTITY_CLASS_UNRESOLVED"])]
        return {"ticker": ticker, "entity_class": entity, "status": "BLOCKED", "primary_reason": "FEATURE_STORE_RECORD_ABSENT",
                "reason_codes": reasons, "usable_features": {}, "blocked_features": {}, "non_applicable_features": {},
                "financial_context": None, "source_entity_class": None}
    if not supported or entity != source_entity:
        reason = "ENTITY_CLASS_UNRESOLVED" if not supported else "ENTITY_CLASS_CONFLICT"
        return {"ticker": ticker, "entity_class": entity, "status": "BLOCKED", "primary_reason": reason,
                "reason_codes": [reason], "usable_features": {}, "blocked_features": {}, "non_applicable_features": {},
                "financial_context": None, "source_entity_class": source_entity}
    authority = source.get("authority_boundary") or {}
    if (authority.get("authoritative") is not False or authority.get("pit") is not False
            or authority.get("actionable") is not False or source.get("ticker") != ticker):
        return {"ticker": ticker, "entity_class": entity, "status": "BLOCKED", "primary_reason": "AUTHORITY_CONFLICT",
                "reason_codes": ["AUTHORITY_CONFLICT"], "usable_features": {}, "blocked_features": {},
                "non_applicable_features": {}, "financial_context": None, "source_entity_class": source_entity}
    allowed = CORPORATE_ALLOWED if entity in CORPORATE_ENTITY_TYPES else FINANCIAL_ALLOWED
    usable: dict[str, Any] = {}
    blocked: dict[str, Any] = {}
    not_applicable: dict[str, Any] = {}
    for feature_id, feature in sorted((source.get("features") or {}).items()):
        preserved = deepcopy(feature)
        if feature_id not in allowed or "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE" in (feature.get("blocker_reason_codes") or []):
            not_applicable[feature_id] = preserved
            continue
        status, reasons = _feature_fitness(feature, session=session)
        if status == "RESEARCH_USABLE":
            usable[feature_id] = preserved
        else:
            blocked[feature_id] = {"integration_fitness": status, "reason_codes": reasons, "source_feature": preserved}
    secondary = CORE_SECONDARY_CORPORATE if entity in CORPORATE_ENTITY_TYPES else CORE_SECONDARY_FINANCIAL
    has_core = "profit_state" in usable and bool(secondary & usable.keys())
    if not has_core:
        profit_block = blocked.get("profit_state", {})
        if "MISSING_STANDALONE_QUARTER_EARNINGS" in profit_block.get("reason_codes", []):
            primary = "MISSING_STANDALONE_QUARTER_EARNINGS"
        elif profit_block.get("integration_fitness") == "FEATURE_STALE":
            primary = "FEATURE_STALE"
        elif profit_block.get("integration_fitness") in {"AUTHORITY_CONFLICT", "SCOPE_CONFLICT", "METHOD_CONFLICT", "PERIOD_SEMANTICS_INSUFFICIENT"}:
            primary = profit_block["integration_fitness"]
        elif "profit_state" not in usable:
            primary = "REQUIRED_METRIC_MISSING"
        else:
            primary = "FEATURE_APPLICABILITY_INSUFFICIENT"
        return {"ticker": ticker, "entity_class": entity, "status": "BLOCKED", "primary_reason": primary,
                "reason_codes": sorted({primary, *(reason for item in blocked.values() for reason in item["reason_codes"])}),
                "usable_features": usable, "blocked_features": blocked, "non_applicable_features": not_applicable,
                "financial_context": None, "source_entity_class": source_entity}
    profit = usable["profit_state"]["categorical_state"]
    growth = usable.get("net_income_same_period_yoy", {}).get("categorical_state")
    context = {
        "status": "AVAILABLE", "fitness": "OPERATIONAL_PROVIDER_RESEARCH_ONLY",
        "source": CONTRACT_VERSION, "entity_class": entity,
        "profitability_state": profit if profit in {"PROFITABLE", "LOSS_MAKING"} else "UNAVAILABLE",
        "earnings_turnaround_state": "TURNAROUND" if growth == "TURNAROUND_TO_PROFIT" else "UNAVAILABLE",
        "growth_state": "CONTRACTING" if growth in {"TURNED_TO_LOSS", "LOSS_WIDENED"} else "UNAVAILABLE",
        "reason_codes": [], "is_actionable": False, "authoritative_financial_eligible": False,
        "warnings": (["UNKNOWN_EXTERNAL_STATEMENT_SCOPE_SAME_NATIVE_RESEARCH_ONLY"]
                     if any("unknown" in (item.get("scope") or []) for item in usable.values()) else []),
    }
    # If the source's profit sign itself is not interpretable, two generic
    # trajectories cannot manufacture a fundamental direction.
    if context["profitability_state"] == "UNAVAILABLE":
        return {"ticker": ticker, "entity_class": entity, "status": "BLOCKED",
                "primary_reason": "FEATURE_APPLICABILITY_INSUFFICIENT", "reason_codes": ["FEATURE_APPLICABILITY_INSUFFICIENT"],
                "usable_features": usable, "blocked_features": blocked, "non_applicable_features": not_applicable,
                "financial_context": None, "source_entity_class": source_entity}
    return {"ticker": ticker, "entity_class": entity, "status": "RESEARCH_USABLE",
            "primary_reason": None, "reason_codes": [], "usable_features": usable,
            "blocked_features": blocked, "non_applicable_features": not_applicable,
            "financial_context": context, "source_entity_class": source_entity}


def build_artifact(*, session: str, capability_map_identity: str, cohort: Mapping[str, str],
                   feature_records: Mapping[str, Mapping[str, Any]], feature_store_identity: str,
                   financial_analysis_identity: str) -> dict[str, Any]:
    records = {ticker: evaluate_ticker(ticker=ticker, entity_class=cohort[ticker],
                                       feature_record=feature_records.get(ticker), session=session)
               for ticker in sorted(cohort)}
    result = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session,
              "capability_map_identity": capability_map_identity,
              "source_artifact_identities": {"fundamental_feature_store": feature_store_identity,
                                             "financial_analysis": financial_analysis_identity},
              "cohort_tickers": sorted(cohort), "records": records,
              "coverage": {"frozen_cohort": len(cohort),
                           "research_usable": sum(row["status"] == "RESEARCH_USABLE" for row in records.values()),
                           "blocked": sum(row["status"] != "RESEARCH_USABLE" for row in records.values()),
                           "residual_primary_reasons": dict(sorted(Counter(row["primary_reason"] for row in records.values()
                                                                    if row["primary_reason"]).items())),
                           "entity_classes": dict(sorted(Counter(row["entity_class"] for row in records.values()).items()))},
              "authority_boundary": {"current_research_only": True, "source_authority_tier": "OPERATIONAL_PROVIDER_RESEARCH_ONLY",
                                     "authoritative_financial_eligible": False, "pit_backtest_eligible": False,
                                     "valuation_authority": False, "execution_authority": False,
                                     "is_actionable": False},
              "freshness_rule": {"maximum_completed_quarter_lag": MAX_COMPLETED_QUARTER_LAG,
                                 "scope": "integration fitness only; original feature status and period are preserved"}}
    result.update(content_identity(result))
    return result


def _verify_daily_sources(feature_store_artifact: Mapping[str, Any],
                          entity_applicability_artifact: Mapping[str, Any]) -> None:
    if (feature_store_artifact.get("contract_version") != feature_store_contract.CONTRACT_VERSION
            or feature_store_contract.content_identity(feature_store_artifact).get("artifact_identity")
            != feature_store_artifact.get("artifact_identity")
            or not isinstance(feature_store_artifact.get("records"), Mapping)):
        raise OperationalFundamentalIntegrationError("FEATURE_STORE_SOURCE_IDENTITY_INVALID")
    applicability = entity_applicability_artifact
    if (applicability.get("contract_version") != CURRENT_RESEARCH_ENTITY_APPLICABILITY_CONTRACT
            or entity_applicability_content_identity(applicability) != applicability.get("artifact_identity")
            or not isinstance(applicability.get("records"), Mapping)):
        raise OperationalFundamentalIntegrationError("ENTITY_APPLICABILITY_SOURCE_IDENTITY_INVALID")
    if (applicability.get("authority_scope") != "CURRENT_STATE_ONLY"
            or applicability.get("historical_pit_authority") != "NOT_ESTABLISHED"):
        raise OperationalFundamentalIntegrationError("ENTITY_APPLICABILITY_AUTHORITY_SCOPE_INVALID")


def build_daily_artifact(*, session: str, candidate_tickers: Sequence[str],
                         feature_store_artifact: Mapping[str, Any],
                         entity_applicability_artifact: Mapping[str, Any],
                         financial_analysis_identity: str,
                         selection_rule: str = DAILY_SELECTION_RULE) -> dict[str, Any]:
    """Ordinary-Daily binding over the same validated feature contract as the frozen replay.

    ``candidate_tickers`` is produced by the caller under ``selection_rule``; the bridge itself
    never consults a ticker list. Each candidate's entity class comes from the governed
    current-state entity applicability; an unresolved or conflicting class stays blocked, and the
    feature record's own entity type must still agree with it.
    """
    if selection_rule != DAILY_SELECTION_RULE:
        raise OperationalFundamentalIntegrationError("DAILY_SELECTION_RULE_UNSUPPORTED")
    if not financial_analysis_identity:
        raise OperationalFundamentalIntegrationError("FINANCIAL_ANALYSIS_SOURCE_IDENTITY_MISSING")
    _verify_daily_sources(feature_store_artifact, entity_applicability_artifact)
    feature_records = feature_store_artifact["records"]
    applicability_records = entity_applicability_artifact["records"]
    tickers = sorted({str(item).upper().strip() for item in candidate_tickers if str(item).strip()})
    missing = [ticker for ticker in tickers if ticker not in applicability_records]
    if missing:
        raise OperationalFundamentalIntegrationError("ENTITY_APPLICABILITY_TICKER_MISSING:" + ",".join(missing[:10]))
    records: dict[str, Any] = {}
    for ticker in tickers:
        applicability = applicability_records[ticker]
        entity = (applicability.get("entity_class")
                  if applicability.get("applicability_status") == APPLICABILITY_RESOLVED else "unknown")
        row = evaluate_ticker(ticker=ticker, entity_class=entity, feature_record=feature_records.get(ticker),
                              session=session)
        if applicability.get("applicability_status") != APPLICABILITY_RESOLVED and row["status"] == "BLOCKED":
            row["reason_codes"] = sorted({*row["reason_codes"], *(applicability.get("reason_codes") or [])})
        row["entity_applicability"] = {key: deepcopy(applicability.get(key)) for key in (
            "entity_class", "applicability_status", "authority_tier", "reason_codes")}
        records[ticker] = row
    result = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session,
              "binding_mode": DAILY_BINDING_MODE,
              "selection": {"rule": selection_rule, "candidate_count": len(tickers)},
              "source_artifact_identities": {
                  "fundamental_feature_store": feature_store_artifact.get("artifact_identity"),
                  "fundamental_feature_store_input_period_semantics": feature_store_artifact.get("input_period_semantics_identity"),
                  "financial_analysis": financial_analysis_identity,
                  "entity_applicability": entity_applicability_artifact.get("artifact_identity"),
                  "entity_authority": entity_applicability_artifact.get("authority_identity"),
              },
              "cohort_tickers": tickers, "records": records,
              "coverage": {"candidates": len(tickers),
                           "research_usable": sum(row["status"] == "RESEARCH_USABLE" for row in records.values()),
                           "blocked": sum(row["status"] != "RESEARCH_USABLE" for row in records.values()),
                           "residual_primary_reasons": dict(sorted(Counter(row["primary_reason"] for row in records.values()
                                                                    if row["primary_reason"]).items())),
                           "entity_classes": dict(sorted(Counter(row["entity_class"] for row in records.values()).items()))},
              "authority_boundary": {"current_research_only": True, "source_authority_tier": "OPERATIONAL_PROVIDER_RESEARCH_ONLY",
                                     "authoritative_financial_eligible": False, "pit_backtest_eligible": False,
                                     "valuation_authority": False, "execution_authority": False,
                                     "is_actionable": False},
              "freshness_rule": {"maximum_completed_quarter_lag": MAX_COMPLETED_QUARTER_LAG,
                                 "scope": "integration fitness only; original feature status and period are preserved"}}
    result.update(content_identity(result))
    return result
