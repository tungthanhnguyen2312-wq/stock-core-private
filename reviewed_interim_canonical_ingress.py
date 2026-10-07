"""Reviewed-interim official facts -> the existing official overlay (factual authority only).

FACT AUTHORITY: a reviewed interim fact whose document, period, scope, unit, currency,
row/column and citation evidence all qualified may be a QUALIFIED official fact for its
exact ticker/metric/period/scope.  RESEARCH AUTHORITY is untouched: the canonical
qualification policy still marks a non-annual fact ``RESEARCH_PERIOD_NOT_ANNUAL``, no Q2 or
annual alias is created for a duration metric, and nothing here derives a TTM.

The rows produced here are consumed by the *existing* overlay loader
(``financial_evidence_currency_refresh.load_public_official_fact_rows``).  No parallel store
is created and no legacy provider row is touched.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from canonical_financial_qualification_policy import evaluate_fact
from financial_evidence_currency_contract import CONTRACT_VERSION as OVERLAY_CONTRACT
from official_financial_assurance_evidence import REVIEWED, assurance_status_is_qualified
from official_legacy_precedence import compare_official_and_legacy

MILESTONE_ID = "FINANCIAL_EVIDENCE_REVIEWED_INTERIM_CANONICAL_INGRESS_V1"
CONTRACT_VERSION = "reviewed_interim_canonical_ingress/v2"
OVERLAY_CURRENCY = "VND"
CONTEXT_CURRENCIES = frozenset({"VND", "USD"})
FOREIGN_CONTEXT_METRICS = frozenset({"revenue", "net_income", "attributable_net_income"})
EARNINGS_COMPONENT_METRIC = "investment_property_disposal_result"
EARNINGS_COMPONENT_CONTRACT = "reported_earnings_component_context/v1"
ANNUAL_CONTEXT_CONTRACT = "audited_annual_exact_field_context/v1"


def earnings_component_is_admitted(row: Mapping[str, Any]) -> bool:
    from official_financial_ocr_table_evidence import row_label_supports_metric
    evidence = row.get("reported_component_evidence") or {}
    return (row.get("canonical_metric") == EARNINGS_COMPONENT_METRIC
            and row.get("context_kind") == "EARNINGS_QUALITY_COMPONENT"
            and row.get("component_contract") == EARNINGS_COMPONENT_CONTRACT
            and row.get("ingress_contract") == CONTRACT_VERSION
            and row.get("projection_currency_policy") == "VND_EXISTING_CONTRACT"
            and row.get("currency") == "VND" and row.get("period_type") == "interim"
            and row.get("statement_family") == "income_statement"
            and str(row.get("line_code")) == "21"
            and evidence.get("citation_id") == row.get("citation_id")
            and row_label_supports_metric(EARNINGS_COMPONENT_METRIC, str(evidence.get("literal_label") or "")))
PROVIDER_LABEL = "official_issuer_ir"
# Circular-200 income statement: line 60 total profit after tax (net_income); line 61 profit
# attributable to the parent (attributable_net_income).  Crossed pairs are never emitted.
LINE_CODE_IDENTITY_CONFLICTS = frozenset({("net_income", "61"), ("attributable_net_income", "60")})


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def overlay_rows_from_panel_facts(panel_facts: Sequence[Mapping[str, Any]], *,
        allow_audited_annual_context: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Adapt already-qualified panel facts to overlay rows; refuse anything the overlay cannot carry.

    USD income fields retain their native currency as context only. The legacy
    VND citation lane excludes them; no FX conversion is invented here.
    """
    rows: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for fact in panel_facts:
        lineage = dict(fact.get("source_lineage") or {})
        assurance = lineage.get("assurance_evidence")
        reasons: list[str] = []
        if fact.get("qualification_state") != "QUALIFIED":
            reasons.append("VALUE_NOT_QUALIFIED")
        if not assurance_status_is_qualified(fact.get("audit_or_review_status")):
            reasons.append("ASSURANCE_STATUS_NOT_ALLOWED")
        if fact.get("audit_or_review_status") == REVIEWED and not (assurance or {}).get("evidence_id"):
            reasons.append("REVIEWED_STATUS_WITHOUT_EVIDENCE")
        annual_context = (allow_audited_annual_context and fact.get("period_type") == "annual"
                          and fact.get("reporting_period") == "2025"
                          and fact.get("audit_or_review_status") == "audited"
                          and fact.get("currency") == "VND"
                          and bool((assurance or {}).get("evidence_id")))
        if fact.get("period_type") != "interim" and not annual_context:
            reasons.append("PERIOD_NOT_INTERIM")
        if fact.get("statement_scope") != "consolidated":
            reasons.append("SCOPE_NOT_CONSOLIDATED")
        if fact.get("currency") not in CONTEXT_CURRENCIES:
            reasons.append("CURRENCY_NOT_ADMITTED_FOR_CONTEXT")
        elif fact.get("currency") != OVERLAY_CURRENCY and (
                fact.get("canonical_metric") not in FOREIGN_CONTEXT_METRICS
                or fact.get("statement_family") != "income_statement"):
            reasons.append("FOREIGN_CURRENCY_METRIC_NOT_ADMITTED")
        if not (lineage.get("document_sha256") and lineage.get("citation_id")):
            reasons.append("CITATION_MISSING")
        if (fact.get("canonical_metric"), str(lineage.get("line_code"))) in LINE_CODE_IDENTITY_CONFLICTS:
            reasons.append("METRIC_LINE_CODE_IDENTITY_CONFLICT")
        component = fact.get("canonical_metric") == EARNINGS_COMPONENT_METRIC
        if component:
            from official_financial_ocr_table_evidence import row_label_supports_metric
            if (fact.get("currency") != "VND" or fact.get("statement_family") != "income_statement"
                    or str(lineage.get("line_code")) != "21"
                    or not row_label_supports_metric(EARNINGS_COMPONENT_METRIC,
                        str((lineage.get("row_object") or {}).get("reconstructed_label") or ""))):
                reasons.append("EARNINGS_COMPONENT_IDENTITY_NOT_QUALIFIED")
        identity = {"ticker": fact.get("issuer_identity"), "metric": fact.get("canonical_metric"),
                    "period": fact.get("reporting_period"), "currency": fact.get("currency"),
                    "value": fact.get("value")}
        if reasons:
            blocked.append({"key": identity, "state": "BLOCKED", "reasons": sorted(set(reasons))})
            continue
        rows.append({
            "ticker": fact["issuer_identity"], "canonical_metric": fact["canonical_metric"],
            "reporting_period": fact["reporting_period"], "period_type": fact["period_type"],
            "period_start": fact["period_start"], "period_end": fact["period_end"],
            "statement_scope": fact["statement_scope"], "statement_family": fact["statement_family"],
            "temporal_nature": fact["temporal_nature"],
            # ``value`` is the absolute source-currency amount; declared scale is kept apart so the
            # existing citation loader (scale "units") cannot rescale it a second time.
            "currency": fact["currency"], "normalized_value": fact["value"], "value": fact["value"],
            "projection_currency_policy": "VND_EXISTING_CONTRACT" if fact["currency"] == "VND" else "SOURCE_CURRENCY_CONTEXT_ONLY",
            "already_normalized": True, "unit_scale": 1,
            "source_unit_scale": (lineage.get("unit_evidence") or {}).get("unit_scale"),
            "qualification_state": "QUALIFIED", "blockers": [],
            "document_sha256": lineage["document_sha256"], "citation_id": lineage["citation_id"],
            "source_page": lineage.get("source_page"), "line_code": lineage.get("line_code"),
            "audit_or_review_status": fact["audit_or_review_status"], "assurance_evidence": assurance,
            "observed_at": fact["observed_at"], "knowledge_available_at": fact["knowledge_available_at"],
            "publication_date": None, "source_family": "issuer_ir", "restatement": None,
            "extraction_method": lineage.get("extraction_method"), "reason_codes": list(fact.get("reason_codes") or []),
            "ingress_contract": CONTRACT_VERSION, "overlay_contract": OVERLAY_CONTRACT,
            **({"context_kind": "AUDITED_ANNUAL_FIELD", "annual_context_contract": ANNUAL_CONTEXT_CONTRACT,
                "projection_period_policy": "AUDITED_ANNUAL_CONTEXT_ONLY"} if annual_context else {}),
            **({"context_kind": "EARNINGS_QUALITY_COMPONENT", "component_contract": EARNINGS_COMPONENT_CONTRACT,
                "reported_component_evidence": {"literal_label": lineage["row_object"]["reconstructed_label"],
                    "citation_id": lineage["citation_id"]}} if component else {}),
        })
    rows.sort(key=lambda row: (row["ticker"], row["reporting_period"], row["canonical_metric"]))
    blocked.sort(key=lambda item: json.dumps(item["key"], sort_keys=True))
    return rows, blocked


def policy_fact(row: Mapping[str, Any]) -> dict[str, Any]:
    """The canonical-fact-shaped view the qualification policy evaluates (no new authority)."""
    return {
        "fact_id": _hash({"ticker": row["ticker"], "metric": row["canonical_metric"],
                          "period": row["reporting_period"], "scope": row["statement_scope"],
                          "document_sha256": row["document_sha256"]}),
        "ticker": row["ticker"], "canonical_metric": row["canonical_metric"],
        "reporting_period": row["reporting_period"], "period_type": row["period_type"],
        "period_start": row["period_start"], "period_end": row["period_end"],
        "statement_family": row["statement_family"], "statement_scope": row["statement_scope"],
        "provider": PROVIDER_LABEL, "source_sha256": row["document_sha256"],
        "source_observation_ids": [f"official-document:{row['document_sha256']}"],
        "citation_id": row["citation_id"], "evidence_id": row["document_sha256"],
        "currency": row["currency"], "scale": "units", "value": row["normalized_value"],
        "status": "qualified", "conflicts": [],
    }


def authority_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    """Fact qualification and research admissibility, kept separate by the existing policy."""
    result = evaluate_fact(policy_fact(row))
    return {"factual_status": result["status"], "factual_reason_codes": result["reason_codes"],
            "research_status": result["research_status"],
            "research_reason_codes": result["research_reason_codes"]}


def precedence_row(row: Mapping[str, Any], legacy: Mapping[str, Any] | None) -> dict[str, Any]:
    """Official-vs-legacy comparison for one exact ticker/metric/period/scope key only."""
    key = {"ticker": row["ticker"], "metric": row["canonical_metric"],
           "period": row["reporting_period"], "scope": row["statement_scope"]}
    if row.get("context_kind") == "AUDITED_ANNUAL_FIELD":
        return {"key": key, "status": "NOT_COMPARABLE", "reason": "AUDITED_ANNUAL_CONTEXT_ONLY",
                "official_factual_status": authority_projection(row)["factual_status"],
                "allowed_uses": ["EXACT_FIELD_CURRENT_RESEARCH_CONTEXT"], "legacy_modified": False}
    if row.get("context_kind") == "EARNINGS_QUALITY_COMPONENT":
        return {"key": key, "status": "NOT_COMPARABLE", "reason": "EARNINGS_COMPONENT_CONTEXT_ONLY",
                "official_factual_status": authority_projection(row)["factual_status"],
                "allowed_uses": ["DESCRIPTIVE_EARNINGS_QUALITY_CONTEXT"], "legacy_modified": False}
    if row.get("projection_currency_policy") == "SOURCE_CURRENCY_CONTEXT_ONLY":
        return {"key": key, "status": "NOT_COMPARABLE",
                "reason": "SOURCE_CURRENCY_CONTEXT_ONLY_VND_COMPARISON_NOT_ADMITTED",
                "official_factual_status": authority_projection(row)["factual_status"],
                "currency": row["currency"], "allowed_uses": ["EXACT_FIELD_CURRENT_RESEARCH_CONTEXT"],
                "legacy_modified": False}
    return {"key": key, **compare_official_and_legacy(row, legacy)}
