"""Deterministic owner-focus core-financial evidence coverage artifact.

This is a coverage and evidence-prioritisation consumer of the governed P3-F13
panel, retained-PDF inventory, sector taxonomy, and existing provider-research
envelope.  It grants no financial, valuation, or investment authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from owner_research_focus import CONTRACT_VERSION as OWNER_FOCUS_CONTRACT, owner_focus_tickers
from p3f13_official_financial_evidence_scaleout import execute as execute_p3f13
from market_wide_current_fundamental_research import execute as execute_fundamental
from sector_financial_taxonomy import REAL_DATA_VALIDATED_SECTORS


ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "owner_focus_core_financial_panel_coverage/v1"
ARTIFACT_TYPE = "OWNER_FOCUS_CORE_FINANCIAL_PANEL_COVERAGE"
RETAINED_PDF_INVENTORY = ROOT / "operations-review" / "retained-official-financial-pdf-extraction-scaleout-v1-20260827" / "artifact.json"

# Every identity below already exists in the relevant established taxonomy.  The
# finance-company taxonomy is deliberately not operationalised: it has no real-data
# proof corpus and hence cannot be silently treated as an industrial panel.
CORPORATE_CORE = (
    ("revenue", "EARNINGS", "PRIMARY"),
    ("gross_profit", "EARNINGS", "SECONDARY"),
    ("profit_before_tax", "EARNINGS", "SECONDARY"),
    ("net_income", "EARNINGS", "PRIMARY"),
    ("cash_and_equivalents", "BALANCE_SHEET", "PRIMARY"),
    ("total_assets", "BALANCE_SHEET", "PRIMARY"),
    ("shareholders_equity", "BALANCE_SHEET", "PRIMARY"),
    ("total_interest_bearing_debt", "BALANCE_SHEET", "PRIMARY"),
    ("operating_cash_flow", "CASH_FLOW", "CASH_FLOW"),
)
SECURITIES_CORE = (
    ("total_operating_revenue", "EARNINGS", "PRIMARY"),
    ("profit_after_tax_parent", "EARNINGS", "PRIMARY"),
    ("financial_assets_fvtpl", "BALANCE_SHEET", "PRIMARY"),
    ("loans_balance", "BALANCE_SHEET", "PRIMARY"),
    ("total_assets", "BALANCE_SHEET", "PRIMARY"),
    ("total_equity", "BALANCE_SHEET", "PRIMARY"),
    ("short_term_borrowings_and_financial_leases", "BALANCE_SHEET", "SECONDARY"),
    ("operating_cash_flow", "CASH_FLOW", "CASH_FLOW"),
)
FINANCE_COMPANY_CORE = (
    ("interest_income", "EARNINGS", "PRIMARY"),
    ("profit_before_tax", "EARNINGS", "PRIMARY"),
    ("customer_loans_net", "BALANCE_SHEET", "PRIMARY"),
    ("total_assets", "BALANCE_SHEET", "PRIMARY"),
    ("total_equity", "BALANCE_SHEET", "PRIMARY"),
)

PRIORITY_ORDER = {
    "P0_CURRENT_CORE_METRIC_MISSING": 0,
    "P1_CONSECUTIVE_PERIOD_GAP": 1,
    "P2_VALUATION_INPUT_BLOCKED": 2,
    "P3_CASH_FLOW_QUALITY_GAP": 3,
    "P4_SECONDARY_CORE_METRIC": 4,
    "P5_SECTOR_CONTRACT_INCOMPLETE": 5,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def core_panel_contract(entity_type: str) -> dict[str, Any]:
    """Return a sector-aware panel only from pre-existing canonical identities."""
    if entity_type == "corporate":
        metrics, state = CORPORATE_CORE, "COMPLETE"
    elif entity_type == "securities":
        metrics, state = SECURITIES_CORE, "COMPLETE"
    elif entity_type == "finance_company":
        metrics, state = FINANCE_COMPANY_CORE, "SECTOR_CORE_PANEL_CONTRACT_INCOMPLETE"
    else:
        metrics, state = (), "SECTOR_CORE_PANEL_CONTRACT_INCOMPLETE"
    return {
        "entity_type": entity_type,
        "contract_state": state,
        "real_data_validated": entity_type in REAL_DATA_VALIDATED_SECTORS or entity_type == "corporate",
        "metrics": [
            {"canonical_metric": metric, "family": family, "priority_class": priority}
            for metric, family, priority in metrics
        ],
        "no_new_canonical_identities": True,
    }


def _sort_periods(values: Sequence[str]) -> list[str]:
    return sorted({str(value) for value in values}, key=lambda value: tuple(int(part) if part.isdigit() else part for part in value.replace("-Q", "-").split("-")))


def _fact_key(fact: Mapping[str, Any]) -> tuple[str, str, str, str, int | None]:
    return (
        str(fact.get("reporting_period")), str(fact.get("period_type")), str(fact.get("statement_scope")),
        str(fact.get("currency")), fact.get("unit_scale"),
    )


def _compatible_consecutive_annual(facts: Sequence[Mapping[str, Any]]) -> tuple[bool, bool, list[str]]:
    """Return two- and three-period compatibility without scope/type mixing."""
    groups: dict[tuple[str, str, int | None], list[int]] = defaultdict(list)
    periods: list[str] = []
    for fact in facts:
        period = str(fact.get("reporting_period") or "")
        if fact.get("period_type") != "annual" or not period.isdigit():
            continue
        groups[(str(fact.get("statement_scope")), str(fact.get("currency")), fact.get("unit_scale"))].append(int(period))
        periods.append(period)
    has_two = has_three = False
    for years in groups.values():
        years = sorted(set(years))
        for index in range(len(years)):
            if index and years[index] == years[index - 1] + 1:
                has_two = True
            if index >= 2 and years[index] == years[index - 1] + 1 and years[index - 1] == years[index - 2] + 1:
                has_three = True
    return has_two, has_three, _sort_periods(periods)


def _document_rows(inventory: Mapping[str, Any], ticker: str) -> list[dict[str, Any]]:
    rows = []
    for row in inventory.get("inventory", []):
        if str(row.get("ticker")) != ticker:
            continue
        metadata = row.get("source_metadata") or {}
        rows.append({
            "document_sha256": row.get("document_sha256"), "document_class": row.get("document_class"),
            "document_period": metadata.get("reporting_period"), "native_text": row.get("text_layer_status") == "TEXT_AVAILABLE",
            "image_only": row.get("classification") == "IMAGE_ONLY", "layout_family": row.get("layout_family"),
            "scope": "consolidated" if "financial" in str(row.get("document_class")) else "UNKNOWN",
            "audit_review_state": "audited" if "audited" in str(row.get("document_class")) else "UNKNOWN",
            "corpus_classification": row.get("classification"), "extraction_status": metadata.get("extraction_status"),
            "source_locator": metadata.get("canonical_url"),
        })
    return sorted(rows, key=lambda row: (str(row.get("document_period") or ""), str(row.get("document_sha256"))))


def _financial_docs(documents: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in documents if "financial" in str(row.get("document_class") or "") or row.get("document_class") == "annual_report"]


def _opportunity(entity_type: str, documents: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    docs = _financial_docs(documents)
    if not docs:
        return "NO_RETAINED_OFFICIAL_DOCUMENT", "OFFICIAL_DOCUMENT_MISSING"
    if entity_type == "finance_company":
        return "SECTOR_LAYOUT_GAP", "SECTOR_CONTRACT_INCOMPLETE"
    if any(row.get("image_only") for row in docs):
        return "IMAGE_ONLY_OCR_GAP", "OFFICIAL_DOCUMENT_IMAGE_ONLY"
    if any(row.get("native_text") for row in docs):
        if entity_type == "securities":
            return "SECTOR_LAYOUT_GAP", "OFFICIAL_DOCUMENT_RETAINED_PARSER_BLOCKED"
        return "STRUCTURAL_NATIVE_TEXT_GAP", "OFFICIAL_DOCUMENT_RETAINED_PARSER_BLOCKED"
    return "METADATA_GAP", "OFFICIAL_DOCUMENT_METADATA_BLOCKED"


def _provider_facts(record: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not record or record.get("authority_tier") != "PROVIDER_RESEARCH":
        return []
    facts = []
    for metric_id, metric in sorted(((record.get("provider_series_trends") or {}).get("metrics") or {}).items()):
        if metric.get("status") == "AVAILABLE":
            facts.append({"metric_id": metric_id, "periods": list(metric.get("periods") or []), "status": "PROVIDER_RESEARCH_ONLY", "provider": metric.get("provider")})
    return facts


def _status_for_metric(*, metric: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], latest_period: str | None,
                       entity_type: str, documents: Sequence[Mapping[str, Any]], contract_state: str) -> dict[str, Any]:
    name = str(metric["canonical_metric"])
    qualified = [fact for fact in facts if fact.get("canonical_metric") == name and fact.get("qualification_state") == "QUALIFIED" and fact.get("is_positive_authority") is not False]
    periods = _sort_periods([str(fact.get("reporting_period")) for fact in qualified])
    annual_periods = _sort_periods([str(fact.get("reporting_period")) for fact in qualified if fact.get("period_type") == "annual"])
    interim_periods = _sort_periods([str(fact.get("reporting_period")) for fact in qualified if fact.get("period_type") != "annual"])
    opportunity, missing_status = _opportunity(entity_type, documents)
    if contract_state != "COMPLETE":
        status = "SECTOR_CONTRACT_INCOMPLETE"
        opportunity = "SECTOR_LAYOUT_GAP"
    elif qualified and latest_period in periods:
        status = "OFFICIAL_QUALIFIED_CURRENT"
    elif qualified:
        status = "OFFICIAL_QUALIFIED_HISTORICAL"
    else:
        status = missing_status
    yoy, trend, comparable_annual = _compatible_consecutive_annual(qualified)
    return {
        **metric, "status": status, "official_fact_periods": periods,
        "annual_periods": annual_periods, "interim_periods": interim_periods,
        "temporal_sufficiency": {
            "CURRENT_LEVEL": status == "OFFICIAL_QUALIFIED_CURRENT",
            "YOY_2_PERIOD": yoy, "TREND_3_PERIOD": trend,
            "compatible_annual_periods": comparable_annual,
            "annual_and_interim_remain_distinct": True,
        },
        "retained_evidence_opportunity": opportunity,
        "missing_evidence_needed": None if qualified else "OFFICIAL_CONSOLIDATED_PERIOD_SCOPE_CURRENCY_UNIT_AND_PAGE_ROW_CITED_VALUE",
    }


def _priority_rows(ticker: str, metrics: Sequence[Mapping[str, Any]], contract_state: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        status, priority_class, name = metric["status"], metric["priority_class"], metric["canonical_metric"]
        if contract_state != "COMPLETE":
            code, reason = "P5_SECTOR_CONTRACT_INCOMPLETE", "EXISTING_SECTOR_TAXONOMY_IS_SCHEMA_ONLY"
        elif status != "OFFICIAL_QUALIFIED_CURRENT" and priority_class == "PRIMARY":
            code, reason = "P0_CURRENT_CORE_METRIC_MISSING", "CURRENT_PRIMARY_CORE_METRIC_NOT_OFFICIAL_QUALIFIED"
        elif status == "OFFICIAL_QUALIFIED_CURRENT" and not metric["temporal_sufficiency"]["YOY_2_PERIOD"]:
            code, reason = "P1_CONSECUTIVE_PERIOD_GAP", "NO_COMPATIBLE_CONSECUTIVE_ANNUAL_OFFICIAL_PERIODS"
        elif status != "OFFICIAL_QUALIFIED_CURRENT" and priority_class == "CASH_FLOW":
            code, reason = "P3_CASH_FLOW_QUALITY_GAP", "OPERATING_CASH_FLOW_NOT_OFFICIAL_QUALIFIED_CURRENT"
        elif status != "OFFICIAL_QUALIFIED_CURRENT":
            code, reason = "P4_SECONDARY_CORE_METRIC", "SECONDARY_CORE_METRIC_NOT_OFFICIAL_QUALIFIED_CURRENT"
        else:
            continue
        rows.append({"ticker": ticker, "canonical_metric": name, "priority_code": code, "reason_code": reason,
                     "opportunity": metric["retained_evidence_opportunity"], "status": status})
    return sorted(rows, key=lambda row: (PRIORITY_ORDER[row["priority_code"]], ticker, row["canonical_metric"]))


def _downstream(metrics: Sequence[Mapping[str, Any]], entity_type: str, contract_state: str) -> dict[str, str]:
    by_name = {row["canonical_metric"]: row for row in metrics}
    current = lambda *names: all(by_name.get(name, {}).get("temporal_sufficiency", {}).get("CURRENT_LEVEL") for name in names)
    yoy = lambda *names: all(by_name.get(name, {}).get("temporal_sufficiency", {}).get("YOY_2_PERIOD") for name in names)
    if contract_state != "COMPLETE":
        return {name: "BLOCKED_SECTOR_CONTRACT_INCOMPLETE" for name in ("earnings_growth", "margin", "roe_roa", "leverage", "cash_flow_quality", "valuation_input_availability")}
    return {
        "earnings_growth": "SUPPORTABLE" if yoy("net_income" if entity_type == "corporate" else "profit_after_tax_parent") else "BLOCKED_INSUFFICIENT_COMPATIBLE_PERIODS",
        "margin": "SUPPORTABLE" if current("revenue", "net_income") else "BLOCKED_CORE_EARNINGS_OR_REVENUE_MISSING",
        "roe_roa": "SUPPORTABLE" if current("net_income", "shareholders_equity", "total_assets") else "BLOCKED_EARNINGS_EQUITY_OR_ASSETS_MISSING",
        "leverage": "SUPPORTABLE" if entity_type == "corporate" and current("total_interest_bearing_debt", "shareholders_equity") else "NOT_APPLICABLE" if entity_type == "securities" else "BLOCKED_DEBT_OR_EQUITY_MISSING",
        "cash_flow_quality": "SUPPORTABLE" if current("operating_cash_flow", "net_income") else "BLOCKED_OCF_OR_EARNINGS_MISSING",
        "valuation_input_availability": "PARTIAL" if any(row["status"] == "OFFICIAL_QUALIFIED_CURRENT" for row in metrics) else "BLOCKED_NO_CURRENT_OFFICIAL_CORE_FACTS",
    }


def build_artifact(*, p3f13_artifact: Mapping[str, Any], fundamental_artifact: Mapping[str, Any], pdf_inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Build the complete exact-ten cohort artifact from retained repository evidence."""
    focus = list(owner_focus_tickers())
    issuers = {str(row.get("issuer_identity", {}).get("ticker")): row for row in (p3f13_artifact.get("refreshed_panel_data") or {}).get("issuers", [])}
    records: list[dict[str, Any]] = []
    all_priorities: list[dict[str, Any]] = []
    for ticker in focus:
        issuer = issuers.get(ticker, {})
        entity_type = str((issuer.get("issuer_identity") or {}).get("entity_type") or (fundamental_artifact.get("records", {}).get(ticker) or {}).get("entity_class") or "unknown")
        contract = core_panel_contract(entity_type)
        facts = list(issuer.get("facts") or [])
        qualified_periods = _sort_periods([str(row.get("reporting_period")) for row in facts if row.get("qualification_state") == "QUALIFIED"])
        latest = qualified_periods[-1] if qualified_periods else None
        documents = _document_rows(pdf_inventory, ticker)
        metrics = [_status_for_metric(metric=metric, facts=facts, latest_period=latest, entity_type=entity_type, documents=documents, contract_state=contract["contract_state"]) for metric in contract["metrics"]]
        priorities = _priority_rows(ticker, metrics, contract["contract_state"])
        all_priorities.extend(priorities)
        provider = _provider_facts((fundamental_artifact.get("records") or {}).get(ticker))
        primary_blocker = (priorities[0]["reason_code"] if priorities else "NO_CORE_EVIDENCE_BLOCKER")
        records.append({
            "ticker": ticker, "entity_type": entity_type, "core_panel_contract": contract,
            "official_qualified_facts": [{"canonical_metric": row.get("canonical_metric"), "reporting_period": row.get("reporting_period"), "period_type": row.get("period_type"), "statement_scope": row.get("statement_scope"), "value": row.get("value"), "source_lineage": row.get("source_lineage")} for row in facts if row.get("qualification_state") == "QUALIFIED"],
            "official_qualified_periods": qualified_periods, "latest_official_period": latest,
            "provider_research_facts": provider, "retained_official_pdfs": documents,
            "core_metric_statuses": metrics, "evidence_priorities": priorities,
            "primary_blocker": primary_blocker, "downstream_research_usefulness": _downstream(metrics, entity_type, contract["contract_state"]),
        })
    matrix = []
    for row in records:
        metrics, docs = row["core_metric_statuses"], row["retained_official_pdfs"]
        matrix.append({
            "ticker": row["ticker"], "entity_type": row["entity_type"], "latest_official_period": row["latest_official_period"],
            "core_applicable_count": len(metrics) if row["core_panel_contract"]["contract_state"] == "COMPLETE" else 0,
            "official_current_count": sum(metric["status"] == "OFFICIAL_QUALIFIED_CURRENT" for metric in metrics),
            "official_historical_count": sum(metric["status"] == "OFFICIAL_QUALIFIED_HISTORICAL" for metric in metrics),
            "provider_research_only_count": len(row["provider_research_facts"]), "retained_pdf_count": len(docs),
            "native_text_pdf_count": sum(bool(doc["native_text"]) for doc in docs), "image_only_pdf_count": sum(bool(doc["image_only"]) for doc in docs),
            "parser_blocked_count": sum(metric["status"] == "OFFICIAL_DOCUMENT_RETAINED_PARSER_BLOCKED" for metric in metrics),
            "current_level_ready_count": sum(bool(metric["temporal_sufficiency"]["CURRENT_LEVEL"]) for metric in metrics),
            "yoy_ready_count": sum(bool(metric["temporal_sufficiency"]["YOY_2_PERIOD"]) for metric in metrics),
            "trend_ready_count": sum(bool(metric["temporal_sufficiency"]["TREND_3_PERIOD"]) for metric in metrics),
            "first_three_evidence_priorities": [f"{priority['priority_code']}:{priority['canonical_metric']}" for priority in row["evidence_priorities"][:3]],
            "primary_blocker": row["primary_blocker"],
        })
    all_priorities = sorted(all_priorities, key=lambda row: (PRIORITY_ORDER[row["priority_code"]], focus.index(row["ticker"]), row["canonical_metric"]))
    next_target: dict[str, Any] | None = None
    if all_priorities:
        selected = all_priorities[0]
        selected_record = next(row for row in records if row["ticker"] == selected["ticker"])
        period = selected_record["latest_official_period"]
        retained = [row for row in selected_record["retained_official_pdfs"] if row.get("document_period") == period]
        document = (retained or selected_record["retained_official_pdfs"] or [None])[0]
        capability = {
            "STRUCTURAL_NATIVE_TEXT_GAP": "EXISTING_NATIVE_TEXT_EXTRACTION",
            "IMAGE_ONLY_OCR_GAP": "IMAGE_ONLY_TABLE_OCR",
            "SECTOR_LAYOUT_GAP": "SECTOR_LAYOUT_MAPPING",
            "METADATA_GAP": "METADATA_QUALIFICATION",
            "NO_RETAINED_OFFICIAL_DOCUMENT": "NEW_OFFICIAL_DOCUMENT_ACQUISITION",
        }[selected["opportunity"]]
        next_target = {
            "ticker": selected["ticker"], "canonical_metric": selected["canonical_metric"], "period": period,
            "existing_retained_document_sha256": document.get("document_sha256") if document else None,
            "blocker_type": selected["opportunity"], "recommended_capability_action": capability,
            "not_automatically_executed": True,
        }
    residual = len(focus) - len(records)
    artifact = {
        "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "generated_from": {"official_financial_panel": p3f13_artifact.get("artifact_identity"), "provider_research": fundamental_artifact.get("artifact_identity"), "retained_pdf_corpus": pdf_inventory.get("artifact_identity")},
        "owner_focus_config_identity": OWNER_FOCUS_CONTRACT, "panel_identity": "sector_aware_existing_canonical_identities/v1",
        "document_corpus_identity": pdf_inventory.get("artifact_identity"), "owner_focus_tickers": focus,
        "is_investment_ranking": False, "prohibited_outputs": ["buy_sell_recommendation", "investment_ranking", "target", "probability", "position_size"],
        "records": records, "watchlist_coverage_matrix": matrix, "evidence_priority_order": all_priorities,
        "next_evidence_targets": all_priorities[:10], "next_milestone_recommendation": next_target,
        "residual_checks": {"required_ticker_count": 10, "actual_ticker_count": len(records), "residual": residual, "residual_zero": residual == 0, "exact_owner_focus_order": [row["ticker"] for row in records] == focus, "no_acquisition_route_substitution": set(row["ticker"] for row in records) == set(focus)},
        "authority_boundary": {"network_called": False, "ocr_called": False, "database_mutated": False, "dashboard_mutated": False, "provider_promoted": False, "valuation_or_value_authority_promoted": False},
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"owner_focus_core_financial_panel_coverage:{artifact['artifact_sha256']}"
    return artifact


def execute() -> dict[str, Any]:
    return build_artifact(p3f13_artifact=execute_p3f13(), fundamental_artifact=execute_fundamental(requested_at="2026-08-27T00:00:00Z"), pdf_inventory=_read_json(RETAINED_PDF_INVENTORY))
