"""Market-wide current fundamental-research coverage artifact.

Joins two already-existing, independently-qualified fundamental-evidence lanes into one
deterministic, sector-aware, coverage-explicit per-ticker artifact:

* the **official-qualified tier** -- `fundamental_research_readiness.py` (P3-B) run over the
  current P3-F13 official-evidence panel (13 issuers today: GAS, HPG, NVL, PAN, POW, PVD, QNS,
  SSI, VCB, VNM, VRE, FPT, PNJ). Every metric here carries its exact/proxy status, periods used,
  evidence lineage, and sector-specific applicability (`NOT_APPLICABLE` industrial metrics on
  bank/securities issuers are preserved, never forced).
* the **provider-research tier** -- P3-F10's full 523-candidate disposition matrix (raw VCI/KBS
  retention, sector classification, blocked reason), retagged with P3-F15/P3-F16's
  `OFFICIAL_QUALIFIED` / `PROVIDER_RESEARCH` / `BLOCKED` authority vocabulary. Provider-tier
  records carry no absolute provider financial facts. Where two retained canonical observations
  share a ticker, provider, metric identity, and consecutive quarterly periods, the existing
  `provider_series_growth` permission allows a bounded trend/direction only. Statement scope,
  currency, unit scale, duration, and cross-provider equivalence remain `UNKNOWN_FAIL_CLOSED`, so
  nothing here is ever promoted to calculation-grade authority by generic inference.

This module computes no new evidence, calls no provider, discovers no new official source route,
and promotes no source/capability/valuation/ranking/recommendation authority. It only recomputes
`fundamental_research_readiness`/`p3f13_official_financial_evidence_scaleout` -- both pure,
deterministic, already-tested functions over already-retained bytes -- and reads P3-F10's frozen
2026-08-20 checkpoint for the (511 or so) candidates that remain outside the official panel. Since
that checkpoint predates two later P3-F13 promotions (PNJ, FPT), this module never trusts its
per-ticker view for a ticker that P3-F13 has since qualified; official rows always take priority
and carry an explicit `supersedes_frozen_p3f10_disposition` note when they do.
"""
from __future__ import annotations

import hashlib
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from entity_classification_contract import EntityClass
from p3f13_official_financial_evidence_scaleout import DEFAULT_P3F10 as DEFAULT_P3F10_FROZEN
from p3f13_official_financial_evidence_scaleout import execute as execute_p3f13
from sector_financial_taxonomy import evaluate_metric_sector_applicability
from sector_relative_research_context import load_qualified_entity_classes
from two_tier_fundamental_research import ALLOWED as PROVIDER_ALLOWED_USES
from two_tier_fundamental_research import FORBIDDEN as PROVIDER_FORBIDDEN_USES
from fundamental_research_readiness import NON_AUTHORIZED_DOWNSTREAM_USES


ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "market_wide_current_fundamental_research/v1"
ARTIFACT_TYPE = "MARKET_WIDE_CURRENT_FUNDAMENTAL_RESEARCH"
MILESTONE = "MARKET_WIDE_CURRENT_FUNDAMENTAL_RESEARCH_SCALEOUT_V1"
DEFAULT_CANONICAL_FACTS_ROOT = (
    ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b"
    / "data" / "canonical-financial-facts" / "facts"
)

OFFICIAL_TIER = "OFFICIAL_QUALIFIED"
PROVIDER_TIER = "PROVIDER_RESEARCH"
BLOCKED_TIER = "BLOCKED"
BLOCKED_METRIC_STATUSES = frozenset({"MISSING", "BLOCKED", "CONFLICT", "NOT_APPLICABLE"})
AVAILABLE_READINESS_STATES = frozenset({"READY", "PARTIAL"})
PROVIDER_SERIES_METRICS = (
    ("revenue_growth", "revenue", "revenue", "growth"),
    ("earnings_growth", "net_income", "earnings", "growth"),
    ("assets_direction", "total_assets", "balance_sheet", "direction"),
    ("equity_direction", "shareholders_equity", "balance_sheet", "direction"),
    ("operating_cash_flow_direction", "operating_cash_flow", "cash_flow", "direction"),
)
PROVIDER_SERIES_LIMITATIONS = (
    "provider_scoped_research_only_not_official_qualified",
    "same_provider_only_no_cross_provider_equivalence",
    "statement_scope_currency_scale_not_independently_qualified",
    "quarterly_duration_and_accounting_identity_not_promoted",
    "not_valuation_recommendation_sizing_or_point_in_time_backtest_authority",
)
PROVIDER_SERIES_COMPARABILITY_SCOPE = (
    "same_ticker_same_provider_same_canonical_metric_consecutive_quarterly_periods_only"
)
METRIC_FAMILY_CLASSIFICATION = {
    "revenue": "PERIOD_FLOW",
    "net_income": "PERIOD_FLOW",
    "operating_cash_flow": "PERIOD_FLOW",
    "total_assets": "POINT_IN_TIME_STOCK",
    "shareholders_equity": "POINT_IN_TIME_STOCK",
}

# This is a deliberately narrow *research-envelope* mapping over one retained provider taxonomy.
# It neither writes the global entity-class promotion registry nor treats a provider industry as
# official issuer identity.  Financial-services is intentionally unmapped because the retained
# label does not distinguish securities companies from finance companies (or other structures).
VCI_PROVIDER_INDUSTRY_ENTITY_CLASS_MAP = {
    "Bán lẻ": "corporate",
    "Bảo hiểm": "insurance",
    "Bất động sản": "corporate",
    "Công nghệ Thông tin": "corporate",
    "Du lịch và Giải trí": "corporate",
    "Dầu khí": "corporate",
    "Hàng & Dịch vụ Công nghiệp": "corporate",
    "Hàng cá nhân & Gia dụng": "corporate",
    "Hóa chất": "corporate",
    "Ngân hàng": "bank",
    "Thực phẩm và đồ uống": "corporate",
    "Truyền thông": "corporate",
    "Tài nguyên Cơ bản": "corporate",
    "Viễn thông": "corporate",
    "Xây dựng và Vật liệu": "corporate",
    "Y tế": "corporate",
    "Ô tô và phụ tùng": "corporate",
    "Điện, nước & xăng dầu khí đốt": "corporate",
}
VCI_AMBIGUOUS_INDUSTRY_LABELS = frozenset({"Dịch vụ tài chính"})
ENTITY_CLASS_APPLICABILITY_METRICS = (
    "revenue", "net_income", "total_assets", "shareholders_equity", "operating_cash_flow",
    "ebitda", "ev_ebitda",
)
ENTITY_CLASS_RESOLUTION_VERSION = "fundamental_entity_class_and_sector_applicability_scaleout/v1"
TRAJECTORY_CONTEXT_VERSION = "market_wide_fundamental_trajectory_context/v1"
VCI_INDUSTRY_SNAPSHOT = ROOT / "registry_snapshots" / "metadata" / "vnstock_metadata_snapshot_20260728T122548Z_16fe54ee3497.jsonl"
VCI_INDUSTRY_PROVIDER = "vnstock:Listing(source=VCI).symbols_by_industries"

# Endpoint-scoped, provider-owned schema evidence collected in the bounded V1 review.  It is
# intentionally narrower than a provider-wide accounting assertion: only KBS's `KQKD`,
# `termtype=2` endpoint has per-row `PeriodBegin` / `PeriodEnd` fields which identify the served
# quarter as its own three-month interval.  VCI's corresponding endpoint returns `quarters` with
# `yearReport` / `lengthReport`, but no documented/retained start-end duration, so it remains
# fail-closed.  The retention adapter currently omits KBS's bounds, hence they are semantic
# evidence for the endpoint contract, not fabricated per-fact dates.
INCOME_STATEMENT_PERIOD_SEMANTICS_VERSION = "provider_income_statement_period_semantics_and_trend_recovery/v1"
KBS_KQKD_QUARTER_SEMANTICS = {
    "provider": "KBS",
    "endpoint": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/finance-info/{ticker}",
    "request_contract": {"type": "KQKD", "termtype": 2, "languageid": 1},
    "response_fields": ["TermCode", "TermNameEN", "PeriodBegin", "PeriodEnd", "ReportDate", "LastUpdate", "United", "AuditedStatus"],
    "period_basis": {"Q1": "SINGLE_QUARTER", "Q2": "SINGLE_QUARTER", "Q3": "SINGLE_QUARTER", "Q4": "SINGLE_QUARTER", "FY": "NOT_IN_QUARTER_ENDPOINT"},
    "evidence": "provider_owned_kbs_kqkd_quarter_schema_periodbegin_periodend_bounded_2026-08-23",
    "retention_limitation": "canonical facts retain provider, fiscal label and source hash but not KBS PeriodBegin/PeriodEnd/United/AuditedStatus",
    "revision_semantics": "LastUpdate is exposed by the endpoint but revision lineage is not retained; no cross-snapshot restatement claim",
}
VCI_INCOME_STATEMENT_SEMANTICS = {
    "provider": "VCI",
    "endpoint": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{ticker}/financial-statement",
    "request_contract": {"section": "INCOME_STATEMENT", "response_key": "quarters"},
    "observed_response_fields": ["yearReport", "lengthReport", "publicDate", "createDate", "updateDate"],
    "period_basis": {"Q1": "UNKNOWN", "Q2": "UNKNOWN", "Q3": "UNKNOWN", "Q4": "UNKNOWN", "FY": "UNKNOWN"},
    "evidence": "provider_owned_vci_endpoint_schema_has_no_duration_range_or_first_party_duration_definition_in_retained_or_bounded_review",
    "retention_limitation": "quarter label and lengthReport are not sufficient duration authority; no numeric-pattern inference",
    "revision_semantics": "publicDate/createDate/updateDate exist on endpoint output but no retained revision-chain contract",
}


def _period_basis(fact: Mapping[str, Any], source_metric: str) -> dict[str, Any]:
    """Classify only the retained fact's supported temporal basis; never trust Q labels alone."""
    period = str(fact.get("reporting_period") or "")
    quarter = _period_key(period)
    result = {
        "fiscal_period_end": fact.get("period_end"), "fiscal_year": quarter[0] if quarter else None,
        "quarter": quarter[1] if quarter else None, "provider": fact.get("provider"),
        "scope": fact.get("statement_scope"), "currency": fact.get("currency"),
        "scale": fact.get("scale"), "semantic_identity": source_metric,
        "statement_family": fact.get("statement_family"), "duration_basis": "UNKNOWN",
        "evidence": "retained_canonical_fact_fields",
    }
    if METRIC_FAMILY_CLASSIFICATION[source_metric] == "POINT_IN_TIME_STOCK":
        result["duration_basis"] = "POINT_IN_TIME" if fact.get("period_end") else "UNKNOWN"
        result["evidence"] = "retained_balance_sheet_period_end"
    elif source_metric == "operating_cash_flow":
        state = fact.get("cumulative_state")
        if state == "period_only" and fact.get("period_start") and fact.get("period_end"):
            result["duration_basis"] = "SINGLE_QUARTER"
            result["evidence"] = "retained_cash_flow_beginning_cash_basis_resolver"
        elif state == "cumulative_ytd":
            result["duration_basis"] = "YTD_CUMULATIVE"
            result["evidence"] = "retained_cash_flow_beginning_cash_basis_resolver"
    elif source_metric in {"revenue", "net_income"} and fact.get("provider") == "KBS":
        result.update({
            "duration_basis": "SINGLE_QUARTER",
            "original_basis": "DIRECT_SINGLE_QUARTER",
            "resulting_comparable_basis": "SINGLE_QUARTER",
            "transformation_method": "NONE_DIRECT_PROVIDER_PERIOD",
            "semantic_contract_version": INCOME_STATEMENT_PERIOD_SEMANTICS_VERSION,
            "evidence": KBS_KQKD_QUARTER_SEMANTICS["evidence"],
            "provider_endpoint": KBS_KQKD_QUARTER_SEMANTICS["endpoint"],
        })
    elif source_metric in {"revenue", "net_income"} and fact.get("provider") == "VCI":
        result.update({
            "original_basis": "UNKNOWN",
            "resulting_comparable_basis": "UNKNOWN",
            "transformation_method": "NONE_SEMANTICS_UNRESOLVED",
            "semantic_contract_version": INCOME_STATEMENT_PERIOD_SEMANTICS_VERSION,
            "evidence": VCI_INCOME_STATEMENT_SEMANTICS["evidence"],
            "provider_endpoint": VCI_INCOME_STATEMENT_SEMANTICS["endpoint"],
        })
    return result


def _pair_basis_eligibility(previous: Mapping[str, Any], current: Mapping[str, Any], source_metric: str) -> tuple[bool, str | None, list[dict[str, Any]]]:
    bases = [_period_basis(previous, source_metric), _period_basis(current, source_metric)]
    # Same retained payload is the only local evidence that unknown native currency/scale are
    # invariant across both columns. It does not establish their absolute identity.
    if not previous.get("source_sha256") or previous.get("source_sha256") != current.get("source_sha256"):
        return False, "SAME_SOURCE_PAYLOAD_NOT_RETAINED", bases
    if previous.get("statement_scope") != current.get("statement_scope"):
        return False, "STATEMENT_SCOPE_NOT_COMPARABLE", bases
    classification = METRIC_FAMILY_CLASSIFICATION[source_metric]
    if classification == "POINT_IN_TIME_STOCK":
        if all(item["duration_basis"] == "POINT_IN_TIME" for item in bases):
            return True, None, bases
        return False, "POINT_IN_TIME_PERIOD_END_UNAVAILABLE", bases
    if source_metric == "operating_cash_flow" and all(item["duration_basis"] == "SINGLE_QUARTER" for item in bases):
        return True, None, bases
    if source_metric == "operating_cash_flow" and any(item["duration_basis"] == "YTD_CUMULATIVE" for item in bases):
        return False, "YTD_CUMULATIVE_DIRECT_COMPARISON_FORBIDDEN", bases
    if source_metric in {"revenue", "net_income"} and all(item["duration_basis"] == "SINGLE_QUARTER" for item in bases):
        return True, None, bases
    return False, "PERIOD_FLOW_DURATION_BASIS_UNEVIDENCED", bases


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Recompute this artifact's content hash from its own bytes, excluding the identity fields
    it carries itself -- same convention as market_wide_current_liquidity_research.content_identity()
    / market_wide_current_descriptive_research's identity helper, so export_ai_bundle.py can
    verify a retained artifact reproduces its own recorded artifact_sha256 before attaching it."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_fundamental_research:{digest}"}


def _load_retained_vci_industry_rows() -> dict[str, dict[str, Any]]:
    """Load one retained provider classification per ticker, failing closed on same-source drift."""
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in VCI_INDUSTRY_SNAPSHOT.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (row.get("provider") == VCI_INDUSTRY_PROVIDER and row.get("field") == "industry"
                and isinstance(row.get("value"), str) and row["value"].strip()):
            candidates[str(row.get("ticker") or "").upper()].append(row)
    resolved: dict[str, dict[str, Any]] = {}
    for ticker, rows in sorted(candidates.items()):
        labels = {" ".join(str(row["value"]).split()) for row in rows}
        if len(labels) != 1:
            resolved[ticker] = {
                "raw_label": None, "source_records": [f"{ticker}:industry" for _ in rows],
                "conflict_or_missing_reason": "CONFLICTING_RETAINED_VCI_INDUSTRY_LABELS",
            }
            continue
        row = rows[0]
        label = next(iter(labels))
        resolved[ticker] = {
            "raw_label": label,
            "source_record_id": f"{ticker}:industry",
            "source_provider": "VCI",
            "source_artifact": VCI_INDUSTRY_SNAPSHOT.name,
            "source": row.get("source"),
            "observed_at": row.get("timestamps", {}).get("observed_at"),
            "effective_at": row.get("timestamps", {}).get("effective_at"),
            "qualification_status": row.get("qualification_status"),
            "conflict_or_missing_reason": None,
        }
    return resolved


@lru_cache(maxsize=1)
def load_entity_classification_evidence() -> dict[str, Mapping[str, Mapping[str, Any]]]:
    """Retained-only source inventory for this artifact's bounded class resolution.

    The P2-E/P2-E3 loader supplies already-qualified records.  VCI classifications remain a
    separately-labelled provider-research source and are never routed into the global resolver.
    """
    return {
        "qualified": load_qualified_entity_classes(ROOT),
        "vci_industry": _load_retained_vci_industry_rows(),
    }


def _candidate(*, entity_class: str, source_type: str, classification_status: str,
               qualification_state: str, mapping_method: str, source: str,
               source_record_id: str | None, observed_at: str | None, reason: str,
               confidence: str, source_artifact: str | None = None,
               effective_at: str | None = None) -> dict[str, Any]:
    return {
        "entity_class": entity_class,
        "source_type": source_type,
        "source": source,
        "source_record_id": source_record_id,
        "source_artifact": source_artifact,
        "observed_at": observed_at,
        "effective_at": effective_at,
        "classification_status": classification_status,
        "qualification_state": qualification_state,
        "mapping_method": mapping_method,
        "mapping_version": ENTITY_CLASS_RESOLUTION_VERSION,
        "confidence": confidence,
        "reason": reason,
    }


def _entity_class_resolution(*, ticker: str, frozen_row: Mapping[str, Any] | None,
                             official_entity_class: str | None,
                             evidence: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Resolve only explicit retained classifications; all disagreement fails closed."""
    candidates: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    if official_entity_class and official_entity_class != "unknown":
        candidates.append(_candidate(
            entity_class=official_entity_class, source_type="OFFICIAL_CURRENT_FUNDAMENTAL_READINESS",
            classification_status="QUALIFIED", qualification_state="OFFICIAL_QUALIFIED",
            mapping_method="official_readiness_entity_class_passthrough/v1",
            source="p3f13_official_financial_evidence_scaleout", source_record_id=ticker,
            observed_at=None, reason="current_official_fundamental_readiness_issuer_identity", confidence="HIGH",
        ))
    qualified = evidence["qualified"].get(ticker)
    if qualified:
        candidates.append(_candidate(
            entity_class=str(qualified["entity_class"]), source_type="QUALIFIED_ENTITY_CLASS",
            classification_status="QUALIFIED", qualification_state="GLOBAL_CURRENT_STATE_QUALIFIED",
            mapping_method="p2e_p2e3_qualified_passthrough/v1",
            source=str(qualified["source_artifact_identity"]),
            source_record_id=str(qualified["classification_evidence_id"]), observed_at=None,
            reason=f"qualified_source_id:{qualified['source_id']}", confidence="HIGH",
        ))
    if frozen_row is not None and str(frozen_row.get("sector") or "unknown") != "unknown":
        candidates.append(_candidate(
            entity_class=str(frozen_row["sector"]), source_type="RETAINED_P3F10_EXISTING_CLASS",
            classification_status="RETAINED_EXISTING_CLASSIFICATION",
            qualification_state="PRESERVED_EXISTING_ARTIFACT_CLASS_NO_NEW_INFERENCE",
            mapping_method="p3f10_sector_passthrough/v1", source="p3f10_generic_fundamental_evidence_scaleout",
            source_record_id=ticker, observed_at=None,
            reason="preexisting_p3f10_class_preserved_without_rederiving_from_statement_shape", confidence="RETAINED",
        ))
    industry = evidence["vci_industry"].get(ticker)
    if industry:
        label = industry.get("raw_label")
        if industry.get("conflict_or_missing_reason"):
            observations.append({"source_type": "VCI_PROVIDER_INDUSTRY", "source": VCI_INDUSTRY_PROVIDER,
                                 "source_record_id": industry.get("source_record_id"), "raw_label": label,
                                 "observed_at": industry.get("observed_at"),
                                 "reason": industry["conflict_or_missing_reason"]})
        elif label in VCI_PROVIDER_INDUSTRY_ENTITY_CLASS_MAP:
            candidates.append(_candidate(
                entity_class=VCI_PROVIDER_INDUSTRY_ENTITY_CLASS_MAP[label], source_type="VCI_PROVIDER_INDUSTRY",
                classification_status="PROVIDER_RESEARCH_CLASSIFIED",
                qualification_state="PROVIDER_REPORTED_DESCRIPTIVE_MAPPING_NOT_GLOBAL_ENTITY_AUTHORITY",
                mapping_method="retained_vci_industry_to_financial_entity_class/v1",
                source=VCI_INDUSTRY_PROVIDER, source_record_id=str(industry.get("source_record_id")),
                observed_at=industry.get("observed_at"), reason=f"retained_provider_industry:{label}",
                confidence="PROVIDER_REPORTED", source_artifact=industry.get("source_artifact"),
                effective_at=industry.get("effective_at"),
            ))
        else:
            observations.append({"source_type": "VCI_PROVIDER_INDUSTRY", "source": VCI_INDUSTRY_PROVIDER,
                                 "source_record_id": industry.get("source_record_id"), "raw_label": label,
                                 "observed_at": industry.get("observed_at"),
                                 "reason": ("AMBIGUOUS_FINANCIAL_SERVICES_PROVIDER_INDUSTRY"
                                            if label in VCI_AMBIGUOUS_INDUSTRY_LABELS else "UNMAPPED_PROVIDER_INDUSTRY")})
    positive_classes = {candidate["entity_class"] for candidate in candidates}
    conflict = len(positive_classes) > 1
    if conflict:
        entity_class, status, authority, reason = (
            "unknown", "CONFLICT", "CONFLICT_UNRESOLVED",
            "CONFLICTING_RETAINED_ENTITY_CLASS_SOURCES_FAIL_CLOSED",
        )
        selected: list[dict[str, Any]] = []
    elif candidates:
        selected = candidates
        winner = candidates[0]
        entity_class, status, authority, reason = (
            winner["entity_class"], winner["classification_status"], winner["qualification_state"], winner["reason"],
        )
    else:
        selected = []
        entity_class, status, authority, reason = (
            "unknown", "UNKNOWN", "UNRESOLVED", observations[0]["reason"] if observations else "NO_RETAINED_ENTITY_CLASS_SOURCE",
        )
    return {
        "entity_class": entity_class,
        "classification_status": status,
        "classification_authority": authority,
        "resolution_version": ENTITY_CLASS_RESOLUTION_VERSION,
        "conflict": conflict,
        "unresolved_reason": reason if entity_class == "unknown" else None,
        "selected_sources": selected,
        "source_candidates": candidates,
        "source_observations": observations,
    }


def _entity_class_metric_applicability(entity_class: str) -> dict[str, Any]:
    """Expose existing taxonomy evaluations without using them to infer an issuer class."""
    sector_metrics: dict[str, Any] = {}
    for metric in ENTITY_CLASS_APPLICABILITY_METRICS:
        result = evaluate_metric_sector_applicability(EntityClass(entity_class), metric)
        sector_metrics[metric] = {
            "applicability": result.applicability.value,
            "reason_codes": list(result.reason_codes),
            "statement_family": result.statement_family,
            "temporal_nature": result.temporal_nature,
            "ordinary_corporate_metric": result.is_ordinary_corporate_metric,
        }
    return {
        "sector_metric_applicability": sector_metrics,
        "provider_series_trend_policy": {
            "status": "PERMITTED_PROVIDER_RESEARCH_DESCRIPTIVE_ONLY",
            "reason": "entity_class_applicability_does_not_block_existing_same_provider_series_contract",
            "applies_to": [item[0] for item in PROVIDER_SERIES_METRICS],
        },
    }


def _growth_direction(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value > 0:
        return "EXPANDING"
    if value < 0:
        return "CONTRACTING"
    return "UNCHANGED"


def _qoq_comparison(metric: Mapping[str, Any]) -> Mapping[str, Any] | None:
    comparison = metric.get("comparisons", {}).get("qoq")
    if isinstance(comparison, Mapping) and comparison.get("status") == "AVAILABLE":
        return comparison
    return None


def _growth_trajectory_dimension(metric: Mapping[str, Any]) -> dict[str, Any]:
    comparison = _qoq_comparison(metric)
    direction = _growth_direction(metric.get("growth_fraction")) if metric.get("status") == "AVAILABLE" else None
    if direction is None or comparison is None:
        return {
            "status": "UNAVAILABLE", "direction": None, "growth_basis": None,
            "unavailable_reason": metric.get("blocked_reason") or "NO_COMPARABLE_QOQ_PROVIDER_TREND",
        }
    return {
        "status": "AVAILABLE", "direction": direction,
        "growth_basis": {
            "comparison_type": "QoQ", "provider": comparison.get("provider"),
            "periods": list(comparison.get("periods") or []),
            "period_basis": list(comparison.get("period_basis") or []),
            "method": metric.get("method"),
        },
        "unavailable_reason": None,
    }


def _direction_trajectory_dimension(metric: Mapping[str, Any]) -> dict[str, Any]:
    if metric.get("status") != "AVAILABLE" or metric.get("direction") not in {"INCREASED", "DECREASED", "UNCHANGED"}:
        return {
            "status": "UNAVAILABLE", "direction": None, "basis": None,
            "unavailable_reason": metric.get("blocked_reason") or "NO_COMPARABLE_PROVIDER_DIRECTION",
        }
    return {
        "status": "AVAILABLE", "direction": metric["direction"],
        "basis": {
            "provider": metric.get("provider"), "periods": list(metric.get("periods") or []),
            "period_basis": list(metric.get("period_basis") or []), "method": metric.get("method"),
        },
        "unavailable_reason": None,
    }


def _revenue_earnings_alignment(revenue: Mapping[str, Any], earnings: Mapping[str, Any]) -> dict[str, Any]:
    if revenue["status"] != "AVAILABLE" and earnings["status"] != "AVAILABLE":
        return {"status": "UNAVAILABLE", "reason": "REVENUE_AND_EARNINGS_QOQ_UNAVAILABLE"}
    if revenue["status"] != "AVAILABLE" or earnings["status"] != "AVAILABLE":
        return {"status": "PARTIAL", "reason": "ONLY_ONE_INCOME_DIMENSION_QOQ_AVAILABLE"}
    revenue_basis, earnings_basis = revenue["growth_basis"], earnings["growth_basis"]
    if (revenue_basis["provider"], revenue_basis["periods"]) != (earnings_basis["provider"], earnings_basis["periods"]):
        return {"status": "PARTIAL", "reason": "REVENUE_EARNINGS_COMPARISON_PERIODS_NOT_ALIGNED"}
    pair = (revenue["direction"], earnings["direction"])
    states = {
        ("EXPANDING", "EXPANDING"): "BOTH_EXPANDING",
        ("EXPANDING", "CONTRACTING"): "REVENUE_UP_EARNINGS_DOWN",
        ("CONTRACTING", "EXPANDING"): "REVENUE_DOWN_EARNINGS_UP",
        ("CONTRACTING", "CONTRACTING"): "BOTH_CONTRACTING",
    }
    return {"status": states.get(pair, "PARTIAL"), "reason": None if pair in states else "UNCHANGED_INCOME_DIMENSION"}


def _balance_sheet_expansion_pattern(assets: Mapping[str, Any], equity: Mapping[str, Any]) -> dict[str, Any]:
    if assets["status"] != "AVAILABLE" and equity["status"] != "AVAILABLE":
        return {"status": "UNAVAILABLE", "reason": "ASSETS_AND_EQUITY_DIRECTIONS_UNAVAILABLE"}
    if assets["status"] != "AVAILABLE" or equity["status"] != "AVAILABLE":
        return {"status": "PARTIAL", "reason": "ONLY_ONE_BALANCE_SHEET_DIRECTION_AVAILABLE"}
    pair = (assets["direction"], equity["direction"])
    states = {
        ("INCREASED", "INCREASED"): "ASSETS_AND_EQUITY_EXPANDING",
        ("INCREASED", "DECREASED"): "ASSETS_EXPANDING_EQUITY_CONTRACTING",
        ("DECREASED", "INCREASED"): "ASSETS_CONTRACTING_EQUITY_EXPANDING",
        ("DECREASED", "DECREASED"): "ASSETS_AND_EQUITY_CONTRACTING",
    }
    return {"status": states.get(pair, "UNCHANGED_OR_MIXED"), "reason": None}


def _provider_trajectory_context(record: Mapping[str, Any]) -> dict[str, Any]:
    metrics = record.get("provider_series_trends", {}).get("metrics", {})
    revenue = _growth_trajectory_dimension(metrics.get("revenue_growth", {}))
    earnings = _growth_trajectory_dimension(metrics.get("earnings_growth", {}))
    assets = _direction_trajectory_dimension(metrics.get("assets_direction", {}))
    equity = _direction_trajectory_dimension(metrics.get("equity_direction", {}))
    operating_cash_flow = _direction_trajectory_dimension(metrics.get("operating_cash_flow_direction", {}))
    alignment = _revenue_earnings_alignment(revenue, earnings)
    balance_sheet = _balance_sheet_expansion_pattern(assets, equity)
    income_available = revenue["status"] == "AVAILABLE" or earnings["status"] == "AVAILABLE"
    balance_available = assets["status"] == "AVAILABLE" or equity["status"] == "AVAILABLE"
    ocf_available = operating_cash_flow["status"] == "AVAILABLE"
    dimensions = sum((income_available, balance_available, ocf_available))
    unavailable_or_partial = [
        value["unavailable_reason"] for value in (revenue, earnings, assets, equity, operating_cash_flow)
        if value.get("unavailable_reason")
    ]
    unavailable_or_partial.extend(
        value["reason"] for value in (alignment, balance_sheet) if value.get("reason")
    )
    return {
        "version": TRAJECTORY_CONTEXT_VERSION,
        "trajectory_status": "AVAILABLE" if dimensions else "UNAVAILABLE",
        "authority_tier": PROVIDER_TIER,
        "entity_class": record["entity_class"],
        "revenue_direction": revenue["direction"], "revenue_growth_basis": revenue["growth_basis"],
        "earnings_direction": earnings["direction"], "earnings_growth_basis": earnings["growth_basis"],
        "revenue_vs_earnings_alignment": alignment,
        "assets_direction": assets["direction"], "equity_direction": equity["direction"],
        "balance_sheet_expansion_pattern": balance_sheet,
        "operating_cash_flow_direction": operating_cash_flow["direction"],
        "period_coverage": {
            "retained_reporting_periods": list(record.get("reporting_periods") or []),
            "income_trajectory_available": income_available,
            "balance_sheet_trajectory_available": balance_available,
            "operating_cash_flow_trajectory_available": ocf_available,
        },
        "available_dimension_count": dimensions,
        "multi_dimensional_trajectory": dimensions >= 2,
        "acceleration": {
            "status": "UNAVAILABLE",
            "reason": "PRIOR_COMPARABLE_DIRECTION_NOT_EMITTED_BY_EXISTING_PROVIDER_SERIES_ENVELOPE",
        },
        "official_metric_context": None,
        "data_limitations": list(record.get("provider_series_trends", {}).get("data_limitations") or []) + [
            "trajectory_is_descriptive_provider_research_only_not_a_score_or_official_calculation_grade",
            "balance_sheet_movement_has_no_intrinsic_good_bad_interpretation",
        ],
        "unavailable_or_partial_reasons": sorted(set(unavailable_or_partial)),
    }


def _official_trajectory_context(record: Mapping[str, Any]) -> dict[str, Any]:
    metrics = [{"metric_id": metric.get("metric_id"), "status": metric.get("status"),
                "periods_used": list(metric.get("periods_used") or []), "blocked_reason": metric.get("blocked_reason")}
               for metric in record.get("metrics", [])]
    return {
        "version": TRAJECTORY_CONTEXT_VERSION,
        "trajectory_status": "OFFICIAL_METRIC_CONTEXT_ONLY",
        "authority_tier": OFFICIAL_TIER,
        "entity_class": record["entity_class"],
        "revenue_direction": None, "revenue_growth_basis": None,
        "earnings_direction": None, "earnings_growth_basis": None,
        "revenue_vs_earnings_alignment": {"status": "UNAVAILABLE", "reason": "NO_PROVIDER_TRAJECTORY_PROMOTION_TO_OFFICIAL"},
        "assets_direction": None, "equity_direction": None,
        "balance_sheet_expansion_pattern": {"status": "UNAVAILABLE", "reason": "NO_OFFICIAL_DIRECTION_RECALCULATION_IN_TRAJECTORY_CONTEXT"},
        "operating_cash_flow_direction": None,
        "period_coverage": {"authoritative_periods_available": list(record.get("authoritative_periods_available") or [])},
        "available_dimension_count": 0, "multi_dimensional_trajectory": False,
        "acceleration": {"status": "UNAVAILABLE", "reason": "NO_OFFICIAL_DIRECTION_RECALCULATION_IN_TRAJECTORY_CONTEXT"},
        "official_metric_context": {"fundamental_research_readiness": record.get("fundamental_research_readiness"), "metrics": metrics},
        "data_limitations": ["official_metric_context_is_distinct_from_provider_research_trajectory",
                             "no_new_official_trend_or_direction_calculation"],
        "unavailable_or_partial_reasons": ["NO_OFFICIAL_DIRECTION_RECALCULATION_IN_TRAJECTORY_CONTEXT"],
    }


def _blocked_trajectory_context(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": TRAJECTORY_CONTEXT_VERSION, "trajectory_status": "UNAVAILABLE",
        "authority_tier": BLOCKED_TIER, "entity_class": record["entity_class"],
        "revenue_direction": None, "revenue_growth_basis": None, "earnings_direction": None,
        "earnings_growth_basis": None,
        "revenue_vs_earnings_alignment": {"status": "UNAVAILABLE", "reason": "NO_RETAINED_PROVIDER_OR_OFFICIAL_TRAJECTORY_SOURCE"},
        "assets_direction": None, "equity_direction": None,
        "balance_sheet_expansion_pattern": {"status": "UNAVAILABLE", "reason": "NO_RETAINED_PROVIDER_OR_OFFICIAL_TRAJECTORY_SOURCE"},
        "operating_cash_flow_direction": None, "period_coverage": {}, "available_dimension_count": 0,
        "multi_dimensional_trajectory": False,
        "acceleration": {"status": "UNAVAILABLE", "reason": "NO_RETAINED_PROVIDER_OR_OFFICIAL_TRAJECTORY_SOURCE"},
        "official_metric_context": None,
        "data_limitations": ["no_retained_fundamental_source"],
        "unavailable_or_partial_reasons": ["NO_RETAINED_PROVIDER_OR_OFFICIAL_TRAJECTORY_SOURCE"],
    }


def _trajectory_context(record: Mapping[str, Any]) -> dict[str, Any]:
    if record["authority_tier"] == PROVIDER_TIER:
        return _provider_trajectory_context(record)
    if record["authority_tier"] == OFFICIAL_TIER:
        return _official_trajectory_context(record)
    return _blocked_trajectory_context(record)


def _official_ticker_record(readiness_row: Mapping[str, Any], frozen_row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Full per-ticker detail for one officially-qualified issuer, reused verbatim from
    fundamental_research_readiness.py's own per-issuer result. Nothing is recalculated here."""
    identity = readiness_row["issuer_identity"]
    record: dict[str, Any] = {
        "ticker": identity["ticker"],
        "authority_tier": OFFICIAL_TIER,
        "entity_class": identity["entity_class"],
        "sector": identity["entity_class"],
        "fundamental_research_readiness": readiness_row["fundamental_research_readiness"],
        "authoritative_periods_available": list(readiness_row["authoritative_periods_available"]),
        "metrics": readiness_row["metrics"],
        "metric_family_states": readiness_row["metric_family_states"],
        "history_readiness": readiness_row["history_readiness"],
        "evidence_completeness": readiness_row["evidence_completeness"],
        "blocked_metrics": [
            {"metric_id": metric["metric_id"], "status": metric["status"],
             "blocked_reason": metric["blocked_reason"], "periods_used": metric["periods_used"]}
            for metric in readiness_row["metrics"] if metric["status"] in BLOCKED_METRIC_STATUSES
        ],
    }
    if frozen_row is not None and frozen_row.get("disposition") != "EVIDENCE_QUALIFIED":
        # PNJ/FPT today: the frozen 2026-08-20 P3-F10 checkpoint predates their P3-F13
        # promotion. Recorded for lineage, never hidden.
        record["supersedes_frozen_p3f10_disposition"] = frozen_row.get("disposition")
    return record


def _period_key(period: Any) -> tuple[int, int] | None:
    """Return a sortable quarterly key, rejecting annual/opaque retained periods."""
    text = str(period)
    if len(text) != 7 or text[4:6] != "-Q" or text[6] not in "1234" or not text[:4].isdigit():
        return None
    return int(text[:4]), int(text[6])


def _is_consecutive_quarter(previous: str, current: str) -> bool:
    old, new = _period_key(previous), _period_key(current)
    return old is not None and new is not None and (new[0] * 4 + new[1]) == (old[0] * 4 + old[1] + 1)


def _comparison_record(*, previous: Mapping[str, Any], current: Mapping[str, Any],
                       source_metric: str, mode: str, comparison_type: str) -> dict[str, Any]:
    """Calculate one bounded comparison while exposing basis and source lineage, never values."""
    record: dict[str, Any] = {
        "comparison_type": comparison_type,
        "status": "BLOCKED",
        "provider": str(current["provider"]),
        "periods": [str(previous["reporting_period"]), str(current["reporting_period"])],
        "lineage": [
            {"fact_id": previous.get("fact_id"), "source_observation_ids": list(previous.get("source_observation_ids") or []),
             "source_sha256": previous.get("source_sha256"), "status": previous.get("status")},
            {"fact_id": current.get("fact_id"), "source_observation_ids": list(current.get("source_observation_ids") or []),
             "source_sha256": current.get("source_sha256"), "status": current.get("status")},
        ],
        "metric_family_classification": METRIC_FAMILY_CLASSIFICATION[source_metric],
        "blocked_reason": None,
    }
    eligible, blocker, bases = _pair_basis_eligibility(previous, current, source_metric)
    record["period_basis"] = bases
    if not eligible:
        record["blocked_reason"] = blocker
        return record
    previous_value, current_value = float(previous["value"]), float(current["value"])
    if mode == "growth":
        if previous_value <= 0:
            record["blocked_reason"] = "GROWTH_BASE_NON_POSITIVE"
            return record
        record["growth_fraction"] = (current_value - previous_value) / previous_value
    else:
        record["direction"] = "INCREASED" if current_value > previous_value else (
            "DECREASED" if current_value < previous_value else "UNCHANGED"
        )
    record["status"] = "AVAILABLE"
    return record


def _latest_comparison(*, candidates: list[Mapping[str, Any]], source_metric: str,
                       mode: str, comparison_type: str, prefer_available: bool = False) -> dict[str, Any] | None:
    """Prefer the newest eligible same-provider comparison; a newer unusable provider cannot
    hide an older valid provider-series trend.  If none are eligible, retain the newest block."""
    results = [_comparison_record(
        previous=previous, current=current, source_metric=source_metric, mode=mode,
        comparison_type=comparison_type,
    ) for previous, current in candidates]
    available = [record for record in results if record["status"] == "AVAILABLE"]
    pool = available if prefer_available and available else results
    return max(pool, key=lambda record: (_period_key(record["periods"][1]), record["provider"])) if pool else None


def _provider_series_metric(*, ticker: str, metric_id: str, source_metric: str,
                            family: str, mode: str, facts: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive one permitted provider-series trend from retained canonical provider facts only."""
    base = {
        "ticker": ticker,
        "metric_id": metric_id,
        "metric_family": family,
        "method": "same_provider_comparable_quarter_provider_series_trend/v2",
        "authority_tier": PROVIDER_TIER,
        "status": "BLOCKED",
        "provider": None,
        "periods": [],
        "lineage": [],
        "data_limitations": list(PROVIDER_SERIES_LIMITATIONS),
        "comparability_scope": PROVIDER_SERIES_COMPARABILITY_SCOPE,
        "blocked_reason": "NO_RETAINED_PROVIDER_REPORTED_SERIES",
        "metric_family_classification": METRIC_FAMILY_CLASSIFICATION[source_metric],
        "period_basis": [],
    }
    candidates = [
        fact for fact in facts
        if fact.get("canonical_metric") == source_metric
        and fact.get("status") == "provider_reported"
        and fact.get("provider")
        and _period_key(fact.get("reporting_period")) is not None
        and isinstance(fact.get("value"), (int, float))
        and not isinstance(fact.get("value"), bool)
    ]
    if not candidates:
        return base
    candidates.sort(key=lambda fact: (_period_key(fact["reporting_period"]), str(fact["provider"]), str(fact["fact_id"])))
    by_provider: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fact in candidates:
        by_provider[str(fact["provider"])].append(fact)
    qoq_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    yoy_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for provider_facts in by_provider.values():
        for previous, current in zip(provider_facts, provider_facts[1:]):
            if _is_consecutive_quarter(str(previous["reporting_period"]), str(current["reporting_period"])):
                qoq_pairs.append((previous, current))
        by_period = {_period_key(fact["reporting_period"]): fact for fact in provider_facts}
        for current in provider_facts:
            year, quarter = _period_key(current["reporting_period"])
            previous = by_period.get((year - 1, quarter))
            if previous is not None:
                yoy_pairs.append((previous, current))
    if not qoq_pairs:
        base["blocked_reason"] = "NO_SAME_PROVIDER_CONSECUTIVE_QUARTER_PAIR"
        return base
    qoq = _latest_comparison(
        candidates=qoq_pairs, source_metric=source_metric, mode=mode, comparison_type="QoQ",
        prefer_available=source_metric in {"revenue", "net_income"},
    )
    # Same-quarter YoY is meaningful only for the newly evidenced income-statement flow series.
    comparisons = {"qoq": qoq}
    if source_metric in {"revenue", "net_income"}:
        comparisons["yoy"] = _latest_comparison(
            candidates=yoy_pairs, source_metric=source_metric, mode=mode, comparison_type="YoY", prefer_available=True,
        ) or {"comparison_type": "YoY", "status": "BLOCKED", "provider": None, "periods": [],
              "lineage": [], "metric_family_classification": METRIC_FAMILY_CLASSIFICATION[source_metric],
              "period_basis": [], "blocked_reason": "NO_SAME_PROVIDER_SAME_QUARTER_PRIOR_YEAR_PAIR"}
        base["comparisons"] = comparisons
    selected = qoq if qoq and qoq["status"] == "AVAILABLE" else next(
        (record for record in comparisons.values() if record and record["status"] == "AVAILABLE"), qoq
    )
    if selected is None:
        base["blocked_reason"] = "NO_SAME_PROVIDER_CONSECUTIVE_QUARTER_PAIR"
        return base
    base.update({key: value for key, value in selected.items() if key != "comparison_type"})
    if selected["status"] == "AVAILABLE":
        base["status"] = "AVAILABLE"
        base["blocked_reason"] = None
    return base


def provider_series_trends_for_ticker(*, ticker: str, facts: list[Mapping[str, Any]],
                                      retained_periods: list[str] | None = None) -> dict[str, Any]:
    """Return the allowed provider-series trend envelope for one PROVIDER_RESEARCH ticker."""
    retained_set = set(retained_periods or [])
    scoped_facts = [fact for fact in facts if not retained_set or fact.get("reporting_period") in retained_set]
    metrics = {
        metric_id: _provider_series_metric(
            ticker=ticker, metric_id=metric_id, source_metric=source_metric,
            family=family, mode=mode, facts=scoped_facts,
        )
        for metric_id, source_metric, family, mode in PROVIDER_SERIES_METRICS
    }
    available = sum(metric["status"] == "AVAILABLE" for metric in metrics.values())
    return {
        "authority_tier": PROVIDER_TIER,
        "status": "AVAILABLE" if available else "BLOCKED",
        "usable_metric_count": available,
        "metric_family_coverage": dict(sorted(Counter(
            metric["metric_family"] for metric in metrics.values() if metric["status"] == "AVAILABLE"
        ).items())),
        "metrics": metrics,
        "data_limitations": list(PROVIDER_SERIES_LIMITATIONS),
        "comparability_scope": PROVIDER_SERIES_COMPARABILITY_SCOPE,
        "retained_period_scope": sorted(retained_set),
    }


@lru_cache(maxsize=2)
def load_retained_provider_series(canonical_facts_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Read immutable retained canonical-fact shards; this function makes no provider call."""
    records: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(Path(canonical_facts_root).glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            records[path.name.removesuffix(".jsonl.gz")] = [json.loads(line) for line in handle if line.strip()]
    return records


def _provider_ticker_record(frozen_row: Mapping[str, Any], acquisition_row: Mapping[str, Any] | None,
                            provider_facts: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """One non-officially-qualified candidate. Reuses P3-F10's own disposition row and
    P3-F15/P3-F16's PROVIDER_RESEARCH/BLOCKED authority vocabulary. Zero metric values: scope,
    currency, and unit scale stay UNKNOWN by design -- see module docstring."""
    has_raw = frozen_row["raw_observation_state"] == "RAW_OBSERVED"
    record: dict[str, Any] = {
        "ticker": frozen_row["ticker"],
        "authority_tier": PROVIDER_TIER if has_raw else BLOCKED_TIER,
        "sector": frozen_row["sector"],
        "disposition": frozen_row["disposition"],
        "provider_tier_blocked_reason": frozen_row["blocker"],
        "raw_observation_count": frozen_row["raw_observation_count"],
        "raw_statement_families": list(frozen_row["raw_statement_families"]),
        "raw_providers": list(frozen_row["raw_providers"]),
        "reporting_periods": list(frozen_row["reporting_periods"]),
        "scope_currency_scale_status": "UNKNOWN_FAIL_CLOSED" if has_raw else "NOT_APPLICABLE_NO_SOURCE",
        "allowed_uses": list(PROVIDER_ALLOWED_USES) if has_raw else [],
        "forbidden_uses": list(PROVIDER_FORBIDDEN_USES),
    }
    if acquisition_row is not None:
        record["official_tier_blocked_reason"] = acquisition_row.get("disposition")
        record["official_tier_blocked_detail"] = acquisition_row.get("reason")
    if has_raw:
        record["provider_series_trends"] = provider_series_trends_for_ticker(
            ticker=str(frozen_row["ticker"]), facts=list(provider_facts or []),
            retained_periods=list(frozen_row.get("reporting_periods") or []),
        )
    return record


def _metric_family_coverage(official_records: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, Counter[str]] = defaultdict(Counter)
    for record in official_records:
        for family, state in record["metric_family_states"].items():
            coverage[family][state] += 1
    return {family: dict(sorted(counter.items())) for family, counter in sorted(coverage.items())}


def _sector_coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    broad = Counter(record["sector"] for record in records.values())
    official_entity_class = Counter(
        record["entity_class"] for record in records.values() if record["authority_tier"] == OFFICIAL_TIER
    )
    return {
        "broad_sector_distribution_all_candidates": dict(sorted(broad.items())),
        "entity_class_distribution_officially_qualified": dict(sorted(official_entity_class.items())),
    }


def _entity_class_scaleout_coverage(records: Mapping[str, Mapping[str, Any]],
                                    before_counts: Counter[str]) -> dict[str, Any]:
    after_counts = Counter(str(record["entity_class"]) for record in records.values())
    source_coverage = Counter(
        str(record["entity_class_provenance"]["selected_sources"][0]["source_type"])
        if record["entity_class_provenance"]["selected_sources"] else "UNRESOLVED"
        for record in records.values()
    )
    return {
        "before_entity_class_distribution": dict(sorted(before_counts.items())),
        "after_entity_class_distribution": dict(sorted(after_counts.items())),
        "resolved_unknown_count": max(0, before_counts.get("unknown", 0) - after_counts.get("unknown", 0)),
        "remaining_unknown_count": after_counts.get("unknown", 0),
        "conflicting_count": sum(record["entity_class_provenance"]["conflict"] for record in records.values()),
        "selected_source_coverage": dict(sorted(source_coverage.items())),
        "evidence_hierarchy": [
            "OFFICIAL_CURRENT_FUNDAMENTAL_READINESS",
            "QUALIFIED_ENTITY_CLASS",
            "RETAINED_P3F10_EXISTING_CLASS",
            "VCI_PROVIDER_INDUSTRY_RESEARCH_ONLY",
            "UNKNOWN_OR_CONFLICT_FAIL_CLOSED",
        ],
    }


def _metric_applicability_coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for record in records.values():
        entity_class = str(record["entity_class"])
        for metric, evaluation in record["entity_class_applicability"]["sector_metric_applicability"].items():
            coverage[entity_class][metric][evaluation["applicability"]] += 1
    return {
        entity_class: {metric: dict(sorted(states.items())) for metric, states in sorted(metrics.items())}
        for entity_class, metrics in sorted(coverage.items())
    }


def _provider_trend_coverage_by_class(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records.values():
        if record.get("authority_tier") != PROVIDER_TIER:
            continue
        entity_class = str(record["entity_class"])
        for metric in record.get("provider_series_trends", {}).get("metrics", {}).values():
            coverage[entity_class][f"{metric['metric_id']}:{metric['status']}"] += 1
    return {entity_class: dict(sorted(counts.items())) for entity_class, counts in sorted(coverage.items())}


def _official_coverage_by_class(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records.values():
        if record.get("authority_tier") == OFFICIAL_TIER:
            coverage[str(record["entity_class"])]["issuer_count"] += 1
            for metric in record.get("metrics", []):
                coverage[str(record["entity_class"])][f"metric:{metric['status']}"] += 1
    return {entity_class: dict(sorted(counts.items())) for entity_class, counts in sorted(coverage.items())}


def _trajectory_context_coverage(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_entity_class: dict[str, Counter[str]] = defaultdict(Counter)
    alignment = Counter()
    unavailable_or_partial = Counter()
    summary = Counter()
    for record in records.values():
        context = record["fundamental_trajectory_context"]
        entity_class = str(context["entity_class"])
        by_entity_class[entity_class][f"trajectory_status:{context['trajectory_status']}"] += 1
        if context["trajectory_status"] != "UNAVAILABLE":
            summary["issuers_with_any_trajectory_context"] += 1
            by_entity_class[entity_class]["any_trajectory_context"] += 1
        period_coverage = context["period_coverage"]
        if period_coverage.get("income_trajectory_available"):
            summary["issuers_with_income_trajectory"] += 1
            by_entity_class[entity_class]["income_trajectory"] += 1
        if period_coverage.get("balance_sheet_trajectory_available"):
            summary["issuers_with_balance_sheet_trajectory"] += 1
            by_entity_class[entity_class]["balance_sheet_trajectory"] += 1
        if period_coverage.get("operating_cash_flow_trajectory_available"):
            summary["issuers_with_ocf_trajectory"] += 1
            by_entity_class[entity_class]["ocf_trajectory"] += 1
        if context["multi_dimensional_trajectory"]:
            summary["issuers_with_multi_dimensional_trajectory"] += 1
            by_entity_class[entity_class]["multi_dimensional_trajectory"] += 1
        alignment[str(context["revenue_vs_earnings_alignment"]["status"])] += 1
        unavailable_or_partial.update(context["unavailable_or_partial_reasons"])
    summary["acceleration_available_count"] = 0
    return {
        **dict(sorted(summary.items())),
        "revenue_earnings_alignment": dict(sorted(alignment.items())),
        "coverage_by_entity_class": {entity: dict(sorted(counts.items())) for entity, counts in sorted(by_entity_class.items())},
        "unavailable_or_partial_reasons": dict(sorted(unavailable_or_partial.items())),
    }


def _income_statement_period_semantic_coverage(
    records: Mapping[str, Mapping[str, Any]], provider_series_by_ticker: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Coverage accounting for the endpoint-semantic decision, without emitting provider values."""
    direct = Counter()
    blocked = Counter()
    by_provider = defaultdict(Counter)
    by_entity_class = defaultdict(Counter)
    for ticker, record in records.items():
        if record.get("authority_tier") != PROVIDER_TIER:
            continue
        retained_periods = set(record.get("reporting_periods") or [])
        for fact in provider_series_by_ticker.get(ticker, []):
            metric = fact.get("canonical_metric")
            if metric not in {"revenue", "net_income"} or fact.get("status") != "provider_reported":
                continue
            if retained_periods and fact.get("reporting_period") not in retained_periods:
                continue
            if _period_key(fact.get("reporting_period")) is None or not isinstance(fact.get("value"), (int, float)):
                continue
            if fact.get("provider") == "KBS":
                direct[metric] += 1
                by_provider["KBS"][metric] += 1
                by_entity_class[str(record.get("sector") or "unknown")][metric] += 1
            elif fact.get("provider") == "VCI":
                blocked["VCI_DURATION_BASIS_UNEVIDENCED"] += 1
                by_provider["VCI"]["blocked_periods"] += 1
    qoq = Counter()
    yoy = Counter()
    blocked_trends = Counter()
    for record in records.values():
        if record.get("authority_tier") != PROVIDER_TIER:
            continue
        for metric_id in ("revenue_growth", "earnings_growth"):
            metric = record.get("provider_series_trends", {}).get("metrics", {}).get(metric_id, {})
            if metric.get("status") == "BLOCKED":
                blocked_trends[str(metric.get("blocked_reason"))] += 1
            comparisons = metric.get("comparisons", {})
            if comparisons.get("qoq", {}).get("status") == "AVAILABLE":
                qoq[metric_id] += 1
            if comparisons.get("yoy", {}).get("status") == "AVAILABLE":
                yoy[metric_id] += 1
    return {
        "direct_single_quarter_periods": dict(sorted(direct.items())),
        "transformed_single_quarter_periods": 0,
        "blocked_periods": dict(sorted(blocked.items())),
        "qoq_trends": dict(sorted(qoq.items())),
        "yoy_trends": dict(sorted(yoy.items())),
        "blocked_trends": dict(sorted(blocked_trends.items())),
        "direct_period_coverage_by_provider": {provider: dict(sorted(counts.items())) for provider, counts in sorted(by_provider.items())},
        "direct_period_coverage_by_entity_class": {entity: dict(sorted(counts.items())) for entity, counts in sorted(by_entity_class.items())},
    }


def build_artifact(*, p3f10_frozen: Mapping[str, Any], p3f13_current: Mapping[str, Any],
                   requested_at: str,
                   provider_series_by_ticker: Mapping[str, list[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Build the complete market-wide current fundamental-research artifact from two already
    -computed inputs. Raises if p3f13_current was not derived from exactly this p3f10_frozen
    checkpoint (a cross-repository content-identity guard, not a recomputation)."""
    if p3f13_current.get("source_artifacts", {}).get("p3f10") != p3f10_frozen.get("artifact_identity"):
        raise ValueError("P3F10_ARTIFACT_IDENTITY_MISMATCH")

    frozen_rows = {str(row["ticker"]): row for row in p3f10_frozen["instrument_dispositions"]}
    official_rows = {
        str(row["issuer_identity"]["ticker"]): row
        for row in p3f13_current["refreshed_fundamental_readiness"]["issuer_research_readiness"]
    }
    acquisition_by_ticker = {str(row["ticker"]): row for row in p3f13_current["acquisition_dispositions"]}

    all_tickers = sorted(frozen_rows)
    if len(all_tickers) != int(p3f13_current["cohort_identity"]["total_cohort_count"]):
        raise ValueError("COHORT_SIZE_MISMATCH")

    records: dict[str, dict[str, Any]] = {}
    entity_class_evidence = load_entity_classification_evidence()
    before_entity_class_counts: Counter[str] = Counter()
    for ticker in all_tickers:
        if ticker in official_rows:
            records[ticker] = _official_ticker_record(official_rows[ticker], frozen_rows.get(ticker))
        else:
            records[ticker] = _provider_ticker_record(
                frozen_rows[ticker], acquisition_by_ticker.get(ticker),
                (provider_series_by_ticker or {}).get(ticker),
            )
        record = records[ticker]
        before_entity_class = str(record.get("entity_class", record.get("sector", "unknown")))
        before_entity_class_counts[before_entity_class] += 1
        resolution = _entity_class_resolution(
            ticker=ticker, frozen_row=frozen_rows.get(ticker),
            official_entity_class=record.get("entity_class") if record["authority_tier"] == OFFICIAL_TIER else None,
            evidence=entity_class_evidence,
        )
        record["entity_class"] = resolution["entity_class"]
        # `sector` is retained as the legacy consumer field, now tied exactly to the explicit
        # entity-class provenance rather than a second independently-derived classification.
        record["sector"] = resolution["entity_class"]
        record["entity_class_provenance"] = resolution
        record["entity_class_applicability"] = _entity_class_metric_applicability(resolution["entity_class"])
        record["fundamental_trajectory_context"] = _trajectory_context(record)

    official_tickers = sorted(official_rows)
    official_records = [records[ticker] for ticker in official_tickers]
    metric_status_counts = p3f13_current["refreshed_fundamental_readiness"]["coverage_summary"]["metric_status_counts"]
    tier_counts = Counter(record["authority_tier"] for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "cohort_identity": p3f10_frozen["cohort_identity"],
        "source_artifacts": {
            "p3f10_frozen": p3f10_frozen.get("artifact_identity"),
            "p3f13_current": p3f13_current.get("artifact_identity"),
            "provider_series_canonical_store_state": (
                p3f10_frozen.get("source_artifacts", {}).get("canonical_store_state")
            ),
        },
        "provider_financial_period_basis_contract": {
            "version": "provider_financial_period_basis_and_trend_integrity/v1+provider_income_statement_period_semantics_and_trend_recovery/v1",
            "metric_family_classification": dict(METRIC_FAMILY_CLASSIFICATION),
            "point_in_time_stock_rule": "same-provider same-source-payload same-scope consecutive reporting-date direction only",
            "period_flow_rule": "direct comparison requires evidenced comparable duration; KBS KQKD termtype=2 is endpoint-evidenced SINGLE_QUARTER, VCI income-statement duration remains UNKNOWN, and cash-flow SINGLE_QUARTER requires retained beginning-cash resolver evidence",
            "income_statement_provider_semantics": {"KBS": KBS_KQKD_QUARTER_SEMANTICS, "VCI": VCI_INCOME_STATEMENT_SEMANTICS},
            "prohibited": ["quarter_label_duration_inference", "ytd_as_single_quarter", "full_year_to_q1_direct_growth", "cross_provider_comparison", "numeric_behavior_duration_inference"],
            "transformation_contract": {
                "version": "provider_income_statement_standalone_quarter_transform/v1",
                "status": "NOT_ENABLED_NO_EVIDENCED_YTD_PROVIDER_ENDPOINT",
                "permitted_only_if": ["same_provider", "same_ticker", "same_fiscal_year", "same_metric_identity", "same_statement_scope", "same_currency", "same_scale", "evidenced_cumulative_basis", "both_required_periods_retained"],
                "methods": {"Q2": "Q2_YTD_MINUS_Q1_YTD", "Q3": "Q3_YTD_MINUS_Q2_YTD", "Q4": "FY_MINUS_Q3_YTD"},
            },
        },
        "coverage": {
            "candidate_count": len(all_tickers),
            "issuers_with_official_facts": len(official_tickers),
            "issuers_with_usable_deterministic_metrics": sum(
                1 for ticker in official_tickers
                if records[ticker]["fundamental_research_readiness"] in AVAILABLE_READINESS_STATES
            ),
            "provider_research_tier_count": int(tier_counts.get(PROVIDER_TIER, 0)),
            "blocked_no_source_count": int(tier_counts.get(BLOCKED_TIER, 0)),
            "exact_qualified_metrics": int(metric_status_counts.get("EXACT_QUALIFIED", 0)),
            "derived_proxy_metrics": int(metric_status_counts.get("DERIVED_PROXY", 0)),
            "missing_or_blocked_metrics": (
                int(metric_status_counts.get("MISSING", 0))
                + int(metric_status_counts.get("BLOCKED", 0))
                + int(metric_status_counts.get("CONFLICT", 0))
            ),
            "not_applicable_metrics": int(metric_status_counts.get("NOT_APPLICABLE", 0)),
            "provider_research_usable_for_series_trends_count": sum(
                record.get("provider_series_trends", {}).get("usable_metric_count", 0) > 0
                for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            ),
        },
        "metric_family_coverage": _metric_family_coverage(official_records),
        "provider_series_metric_family_coverage": dict(sorted(Counter(
            metric["metric_family"]
            for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            for metric in record.get("provider_series_trends", {}).get("metrics", {}).values()
            if metric.get("status") == "AVAILABLE"
        ).items())),
        "provider_series_period_coverage": dict(sorted(Counter(
            "->".join(metric["periods"])
            for record in records.values() if record["authority_tier"] == PROVIDER_TIER
            for metric in record.get("provider_series_trends", {}).get("metrics", {}).values()
            if metric.get("status") == "AVAILABLE"
        ).items())),
        "income_statement_period_semantic_coverage": _income_statement_period_semantic_coverage(
            records, provider_series_by_ticker or {}
        ),
        "sector_coverage": _sector_coverage(records),
        "entity_class_scaleout_coverage": _entity_class_scaleout_coverage(records, before_entity_class_counts),
        "entity_class_metric_applicability_coverage": _metric_applicability_coverage(records),
        "provider_series_trend_coverage_by_entity_class": _provider_trend_coverage_by_class(records),
        "official_coverage_by_entity_class": _official_coverage_by_class(records),
        "fundamental_trajectory_context_coverage": _trajectory_context_coverage(records),
        "data_gap_summary": {
            "official_tier_blocked_reasons": dict(sorted(Counter(
                record["official_tier_blocked_reason"] for record in records.values()
                if record["authority_tier"] != OFFICIAL_TIER and record.get("official_tier_blocked_reason")
            ).items())),
            "provider_tier_blocked_reasons": dict(sorted(Counter(
                record["provider_tier_blocked_reason"] for record in records.values()
                if record["authority_tier"] == PROVIDER_TIER and record.get("provider_tier_blocked_reason")
            ).items())),
            "no_source_available_count": int(tier_counts.get(BLOCKED_TIER, 0)),
        },
        "non_authorized_downstream_uses": list(NON_AUTHORIZED_DOWNSTREAM_USES),
        "provider_tier_allowed_uses": list(PROVIDER_ALLOWED_USES),
        "provider_tier_forbidden_uses": list(PROVIDER_FORBIDDEN_USES),
        "authority_boundary": {
            "official_qualified_is_calculation_grade": True,
            "provider_research_is_descriptive_only": True,
            "provider_research_never_official_label": True,
            "provider_industry_entity_class_mapping_is_research_only": True,
            "provider_industry_entity_class_mapping_promoted_to_global_authority": False,
            "new_evidence_acquired": True,
            "new_evidence_scope": "bounded provider-owned endpoint-schema semantic evidence; no provider absolute fact or authority promotion",
            "new_source_route_approved": False,
            "authority_promoted": False,
            "valuation_or_ranking_or_recommendation_produced": False,
        },
        "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": []},
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"] = identity["artifact_sha256"]
    artifact["artifact_identity"] = identity["artifact_identity"]
    return artifact


def execute(*, p3f10_frozen_path: Path = DEFAULT_P3F10_FROZEN, requested_at: str | None = None) -> dict[str, Any]:
    """Recompute the full artifact live from already-retained bytes: no network call, no new
    evidence, no re-run of P3-F9B/P3-F10's own acquisition (only P3-F13's pure recomputation,
    exactly as its own test suite already does on every run)."""
    p3f10_frozen = json.loads(p3f10_frozen_path.read_text(encoding="utf-8"))
    p3f13_current = execute_p3f13()
    return build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current,
        requested_at=requested_at or datetime.now(timezone.utc).isoformat(),
        provider_series_by_ticker=load_retained_provider_series(DEFAULT_CANONICAL_FACTS_ROOT),
    )
