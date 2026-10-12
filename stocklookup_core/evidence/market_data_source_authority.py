"""Decision-only market-source authority reconciliation.

This module deliberately contains no client, credential lookup, or network call.  It records
the bounded source-authority reconciliation after a 2026-08-09 decision-only comparison
incorrectly promoted an unapproved FiinGroup commercial candidate to a preferred route.
FiinGroup is retained only as a
documented, inactive candidate; no paid-provider acquisition is a roadmap route without a new
explicit owner decision.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "1.1.0"

STATUS_QUALIFIED = "qualified"
STATUS_PARTIAL = "partially_qualified"
STATUS_DOCUMENTED = "documented_but_unverified"
STATUS_UNAVAILABLE = "unavailable"
STATUS_REJECTED = "rejected"

ACTIVE_RAW_PRICE_SOURCE_ID = None
FIINGROUP_CANDIDATE_ID = "fiingroup_api_datafeed_hose_stock_v2"
OWNER_DECISION_REQUIRED = "NEW_EXPLICIT_OWNER_DECISION_REQUIRED_FOR_ANY_PAID_PROVIDER"
FIINGROUP_ACCESS_STATE = "NOT_OWNER_AUTHORIZED_NO_CONFIGURED_ACCESS"
LICENSE_AUTHORITY = "NO_LEGITIMATE_ACCESS_OR_CONTRACTUAL_RIGHTS"
MARKET_DATA_TRACK = "OFFICIAL_PILLAR_B_LINEAGE_EXPANSION"
DNSE_MARKET_DATA_ACCESS = "PARTIALLY_QUALIFIED_EXISTING_DNSE_CONTRACT"
DNSE_NEXT_QUALIFICATION_CANDIDATE = "DNSE_OHLC_PRICE_AND_MARKET_VOLUME_BASIS_BACKLOG"
FIINGROUP_FALLBACK_CANDIDATE = None
DNSE_FOREIGN_FLOW_VALUE_AUTHORITY = "PRODUCTION_ENABLED_HPG_VNM_QNS"
DNSE_OHLC_PRICE_BASIS = "ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME"
DNSE_MARKET_VOLUME_BASIS = "UNQUALIFIED_BACKLOG"
NEXT_PILLAR_B_MILESTONE = "PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION"
NEXT_PILLAR_B_EXECUTION_GATE = "EXPLICIT_TASK_AUTHORIZATION_FOR_BOUNDED_VSDC_SSI_NOTICE_ACQUISITION"
# P1.5 proved that qualification tiers can reach the bundle without promoting partial or
# provider-scoped facts.  The next independent work is therefore the canonical-fact-store
# connection, still bounded by the same fail-closed research rules and independent of access.
PARALLEL_UNBLOCKED_NEXT_MILESTONE = "CONNECT_PILLAR_A_MARKET_WIDE_CANONICAL_FACTS_TO_RESEARCH_ENGINE"

DNSE_QUALIFICATION_ROUTE: dict[str, Any] = {
    "candidate_id": "dnse_openapi_market_history",
    "status": DNSE_MARKET_DATA_ACCESS,
    "source_class": "existing_dnse_provider_contract",
    "documented_capabilities": [
        "historical_ohlc_by_ticker_resolution_from_to",
        "historical_trade_by_ticker_board_date_range",
        "realtime_board_specific_market_data",
        "board_separation_G1_G4_T1_T3_T4_T6",
        "closed_ohlc_candles",
    ],
    "foreign_flow_value_authority": DNSE_FOREIGN_FLOW_VALUE_AUTHORITY,
    "ohlc_price_basis": DNSE_OHLC_PRICE_BASIS,
    "market_volume_basis": DNSE_MARKET_VOLUME_BASIS,
    "next_permitted_action": "no_provider_refresh_without_explicit_contract_authorization",
    "network_called": False,
    "credentials_read_or_logged": False,
    "market_basis_effect": "none_until_retained_qualification_pilot_passes",
    "fiingroup_role": "unapproved_commercial_candidate_not_an_acquisition_path",
}

# Each status is field-specific.  The selection is not a score: a candidate with an
# unavailable hard requirement cannot become the source merely because it has more positives.
AUTHORITY_REQUIREMENTS = (
    "raw_as_traded_price", "adjusted_raw_separation", "ticker_session_identity",
    "historical_depth", "corporate_action_mutability", "volume_unit", "trade_scope",
    "deterministic_retrieval", "provenance_retention", "license_production_usability",
    "coverage", "operational_stability",
)

_FIIN_DOC = "https://datafeed.fiingroup.vn/api-datafeed-en/api-trading/stock/stock/hose-stock-v2"
_HOSE_FEE_SCHEDULE = "https://staticfile.hsx.vn/Uploads/UploadDocuments/2406142/Bieu%20gia%20dich%20vu%20cung%20cap%20tin.pdf"

CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "hose_licensed_market_data_feed",
        "source_class": "official_exchange_licensed_service",
        "product": "HOSE Market Data Feed",
        "source_url": _HOSE_FEE_SCHEDULE,
        "selection_state": "documented_commercial_product_not_schema_qualified",
        "requirements": {
            "raw_as_traded_price": STATUS_DOCUMENTED,
            "adjusted_raw_separation": STATUS_UNAVAILABLE,
            "ticker_session_identity": STATUS_UNAVAILABLE,
            "historical_depth": STATUS_UNAVAILABLE,
            "corporate_action_mutability": STATUS_UNAVAILABLE,
            "volume_unit": STATUS_UNAVAILABLE,
            "trade_scope": STATUS_UNAVAILABLE,
            "deterministic_retrieval": STATUS_DOCUMENTED,
            "provenance_retention": STATUS_DOCUMENTED,
            "license_production_usability": STATUS_DOCUMENTED,
            "coverage": STATUS_DOCUMENTED,
            "operational_stability": STATUS_DOCUMENTED,
        },
        "evidence": "HOSE's public service schedule names a Market Data Feed, but its public description does not specify ticker EOD schema, raw/adjusted namespaces, historical retrieval, or revision policy.",
        "hard_failure": "Public product listing alone cannot qualify the required raw ticker/session contract.",
    },
    {
        "candidate_id": FIINGROUP_CANDIDATE_ID,
        "source_class": "established_market_data_vendor_commercial_api",
        "product": "FiinGroup API Datafeed /Market/GetHoseStockv2",
        "source_url": _FIIN_DOC,
        "selection_state": "documented_commercial_candidate_not_owner_authorized",
        "requirements": {
            "raw_as_traded_price": STATUS_DOCUMENTED,
            "adjusted_raw_separation": STATUS_DOCUMENTED,
            "ticker_session_identity": STATUS_DOCUMENTED,
            "historical_depth": STATUS_PARTIAL,
            "corporate_action_mutability": STATUS_DOCUMENTED,
            "volume_unit": STATUS_DOCUMENTED,
            "trade_scope": STATUS_DOCUMENTED,
            "deterministic_retrieval": STATUS_DOCUMENTED,
            "provenance_retention": STATUS_DOCUMENTED,
            "license_production_usability": STATUS_DOCUMENTED,
            "coverage": STATUS_DOCUMENTED,
            "operational_stability": STATUS_DOCUMENTED,
        },
        "evidence": "The vendor's field documentation separately defines OpenPrice/ClosePrice/HighestPrice/LowestPrice and their *Adjusted counterparts, RateAdjusted, Ticker, TradingDate, total order-matching and put-through volumes/values, Status, CreateDate, and UpdateDate.",
        "hard_failure": None,
    },
    {
        "candidate_id": "existing_integrated_vci_kbs_provider_paths",
        "source_class": "existing_broker_provider_paths",
        "product": "VCI and KBS installed provider series",
        "source_url": None,
        "selection_state": "rejected_existing_adjusted_paths",
        "requirements": {
            "raw_as_traded_price": STATUS_REJECTED,
            "adjusted_raw_separation": STATUS_REJECTED,
            "ticker_session_identity": STATUS_PARTIAL,
            "historical_depth": STATUS_PARTIAL,
            "corporate_action_mutability": STATUS_REJECTED,
            "volume_unit": STATUS_PARTIAL,
            "trade_scope": STATUS_PARTIAL,
            "deterministic_retrieval": STATUS_PARTIAL,
            "provenance_retention": STATUS_PARTIAL,
            "license_production_usability": STATUS_UNAVAILABLE,
            "coverage": STATUS_PARTIAL,
            "operational_stability": STATUS_PARTIAL,
        },
        "evidence": "provider_price_basis_registry.py establishes both as empirically event-adjusted and raw_as_traded_eligible=False; they remain provider-adjusted analytical namespaces only.",
        "hard_failure": "Already closed by the active provider price-basis verdicts; must not be re-tested as raw authority.",
    },
)

UNAPPROVED_COMMERCIAL_CANDIDATE_REVIEW: dict[str, Any] = {
    "candidate_id": FIINGROUP_CANDIDATE_ID,
    "decision": OWNER_DECISION_REQUIRED,
    "product": "FiinGroup API Datafeed /Market/GetHoseStockv2",
    "minimum_data_package": {
        "universe": "HOSE listed equities, beginning with HPG and VNM",
        "history": "Daily historical records from 2024-01-01 through the qualification date: enough for the 2024-12-31 HPG anchor, adjacent sessions, and already-qualified 2025/2026 event windows. Longer backtest history is a later, separately justified acquisition.",
        "endpoint": "/Market/GetHoseStockv2",
        "companion_endpoints": [],
        "identity_fields": ["Ticker", "TradingDate", "HOSE endpoint identity"],
        "price_fields": ["ReferencePrice", "OpenPrice", "ClosePrice", "MatchPrice", "HighestPrice", "LowestPrice", "AveragePrice", "currency_or_price_unit"],
        "raw_adjusted_fields": ["ReferencePriceAdjusted", "OpenPriceAdjusted", "ClosePriceAdjusted", "HighestPriceAdjusted", "LowestPriceAdjusted", "RateAdjusted"],
        "volume_fields": ["TotalMatchVolume", "TotalDealVolume", "TotalVolume", "TotalMatchValue", "TotalDealValue", "TotalValue"],
        "provenance_fields": ["HoseStockId", "Status", "CreateDate", "UpdateDate", "source_version_or_dataset_vintage"],
    },
    "contractual_confirmations_required": [
        "Unadjusted price fields are raw/as-traded and are not retrospectively rewritten for corporate actions.",
        "Historical query semantics, revision policy, dataset vintage/as-of availability, and retention period are documented.",
        "Price unit/currency and volume unit are documented for the contracted product.",
        "TotalVolume treatment of continuous matching, opening/closing auctions, negotiated/put-through, and odd-lot trading is documented.",
        "The agreement permits API access, historical retrieval, local retained evidence/cache, derived analytics, and internal production use.",
        "The agreement specifies allowed Dashboard display and any redistribution/publication restrictions.",
    ],
    "status": "NOT_AN_APPROVED_ACQUISITION_OR_INTEGRATION_PATH",
    "acceptance_tests": [
        "HPG 2024-12-31 raw ClosePrice exactly matches the retained HOSE 26,650 VND/share anchor.",
        "HPG adjacent session and VNM sessions preserve ticker/date/OHLC/unit identity with no nearest-session fallback.",
        "Raw fields and *Adjusted fields coexist and remain separate through storage and selection.",
        "A retained pre-event raw payload remains unchanged after a qualified corporate-action event, or the vendor supplies a documented immutable/as-of history mechanism.",
        "TotalMatchVolume + TotalDealVolume reconciles to TotalVolume only where the vendor documents the relationship; no unlabelled inference.",
        "Auction and odd-lot treatment are explicitly documented or the volume authority stays blocked.",
        "Missing session, conflicting revision, wrong unit, or absent raw field fails closed.",
        "No generic valuation, liquidity, execution, or backtest gate opens until the pilot data and contract both pass.",
    ],
    "requirements_for_any_future_owner_review": [
        "Only adjusted historical prices are supplied, or unadjusted field semantics are not contractually confirmed.",
        "No historical point-in-time/revision semantics are supplied.",
        "Terms prohibit the required evidence retention or intended production use.",
        "Ticker/session identity, price unit, or raw/adjusted distinction changes between documentation and contracted payload.",
    ],
}

FIINGROUP_ACCESS_AUDIT: dict[str, Any] = {
    "access_state": FIINGROUP_ACCESS_STATE,
    "license_authority": LICENSE_AUTHORITY,
    "checked_locations": (
        "project configuration and provider adapters",
        "project credential/configuration naming conventions",
        "environment-variable names matching FIIN or DATAFEED",
        "documented source/license notes",
    ),
    "findings": (
        "No FiinGroup adapter, configured endpoint, credential reference, or FIIN/DATAFEED environment-variable name exists.",
        "The sole .env.example credential convention is the retired EODHD token and is not reusable for FiinGroup.",
        "No retained FiinGroup agreement defines historical API, local retention, derived analytics, production, Dashboard, or redistribution rights.",
    ),
    "credentials_read_or_logged": False,
    "network_called": False,
    "production_adapter_created": False,
}


def candidate(candidate_id: str) -> dict[str, Any]:
    for record in CANDIDATES:
        if record["candidate_id"] == candidate_id:
            return deepcopy(record)
    raise ValueError(f"unknown_market_data_authority_candidate:{candidate_id}")


def decision_snapshot() -> dict[str, Any]:
    """A deterministic, decision-only view; this function performs no acquisition."""
    return {
        "schema_version": VERSION,
        "market_data_source_authority_decision": "PASS",
        "public_hose_summary_route": "CLOSED_NONCONFORMING",
        "raw_price_authority_source_selected": False,
        "selected_source_id": ACTIVE_RAW_PRICE_SOURCE_ID,
        "raw_price_authority": "PARTIAL",  # existing annual-report observation only
        "market_authority_reason": "NO_ACTIVE_QUALIFIED_RAW_PRICE_SOURCE",
        "volume_scope_authority_source_selected": False,
        "volume_scope_authority": "BLOCKED",
        "provider_adjusted_authority": "QUALIFIED",
        "raw_adjusted_namespace_separation": "PASS",
        "generic_actionable_price_basis": "BLOCKED",
        "generic_actionable_volume_basis": "BLOCKED",
        "historical_valuation_unlock": "BLOCKED",
        "next_roadmap_milestone": NEXT_PILLAR_B_MILESTONE,
        "network_or_credentials_used": False,
        "candidates": [candidate(item["candidate_id"]) for item in CANDIDATES],
        "unapproved_commercial_candidate_review": deepcopy(UNAPPROVED_COMMERCIAL_CANDIDATE_REVIEW),
    }


def access_snapshot() -> dict[str, Any]:
    """Report the configured-access state without reading any secret value."""
    return {
        "fiingroup_source_acquisition_milestone": "NOT_AUTHORIZED_NOT_EXECUTED",
        "fiingroup_access_state": FIINGROUP_ACCESS_STATE,
        "license_authority": LICENSE_AUTHORITY,
        "owner_source_acquisition_package": "NOT_ACTIVE",
        "market_data_track": MARKET_DATA_TRACK,
        "dnse_market_data_access": DNSE_MARKET_DATA_ACCESS,
        "dnse_next_qualification_route": deepcopy(DNSE_QUALIFICATION_ROUTE),
        "fiingroup_fallback_candidate": FIINGROUP_FALLBACK_CANDIDATE,
        "parallel_unblocked_next_milestone": PARALLEL_UNBLOCKED_NEXT_MILESTONE,
        "raw_price_authority_source_selected": False,
        "raw_price_authority": "PARTIAL",
        "market_authority_reason": "NO_ACTIVE_QUALIFIED_RAW_PRICE_SOURCE",
        "raw_history_mutability": "UNKNOWN",
        "fiingroup_raw_price_pilot": "NOT_AUTHORIZED_NOT_EXECUTED",
        "hpg_raw_price_anchor_crosscheck": "BLOCKED",
        "fiingroup_adjusted_namespace": "NOT_AUTHORIZED_NOT_EXECUTED",
        "fiingroup_volume_scope_authority": "NOT_AUTHORIZED_NOT_EXECUTED",
        "vci_trade_type_coverage": "BLOCKED_DATA",
        "generic_actionable_price_basis": "BLOCKED",
        "generic_actionable_volume_basis": "BLOCKED",
        "historical_valuation_unlock": "BLOCKED",
        "actionable_liquidity_unlock": "BLOCKED",
        "access_audit": deepcopy(FIINGROUP_ACCESS_AUDIT),
        "unapproved_commercial_candidate_review": deepcopy(UNAPPROVED_COMMERCIAL_CANDIDATE_REVIEW),
        "next_pillar_b_milestone": NEXT_PILLAR_B_MILESTONE,
        "next_pillar_b_execution_gate": NEXT_PILLAR_B_EXECUTION_GATE,
    }


def assert_decision_policy(snapshot: Mapping[str, Any] | None = None) -> None:
    """Reject a decision that silently treats documentation as active source authority."""
    value = decision_snapshot() if snapshot is None else snapshot
    if value.get("selected_source_id") is not ACTIVE_RAW_PRICE_SOURCE_ID:
        raise ValueError("unapproved_candidate_must_not_be_selected_source")
    if value.get("raw_price_authority_source_selected") is not False:
        raise ValueError("unapproved_candidate_must_not_activate_raw_authority")
    if value.get("raw_price_authority") != "PARTIAL":
        raise ValueError("unqualified_commercial_source_must_not_change_existing_raw_authority")
    if value.get("volume_scope_authority") != "BLOCKED":
        raise ValueError("undocumented_odd_lot_scope_must_not_open_volume_authority")
    if value.get("network_or_credentials_used") is not False:
        raise ValueError("decision_only_policy_must_not_claim_network_or_credentials")
    fiingroup = candidate(FIINGROUP_CANDIDATE_ID)
    if fiingroup["selection_state"] != "documented_commercial_candidate_not_owner_authorized":
        raise ValueError("fiingroup_candidate_must_remain_unapproved")
    if value.get("next_roadmap_milestone") != NEXT_PILLAR_B_MILESTONE:
        raise ValueError("next_pillar_b_milestone_must_follow_approved_official_route")


def assert_access_policy(snapshot: Mapping[str, Any] | None = None) -> None:
    """Access absence must block the pilot, not manufacture a raw authority or adapter."""
    value = access_snapshot() if snapshot is None else snapshot
    if value.get("fiingroup_access_state") != FIINGROUP_ACCESS_STATE:
        raise ValueError("fiingroup_access_state_must_reflect_configured_access_only")
    if value.get("license_authority") != LICENSE_AUTHORITY:
        raise ValueError("license_authority_must_not_be_inferred_from_documentation")
    if value.get("fiingroup_raw_price_pilot") != "NOT_AUTHORIZED_NOT_EXECUTED":
        raise ValueError("no_authorization_must_block_live_qualification")
    audit = value.get("access_audit") or {}
    if any(audit.get(key) for key in ("credentials_read_or_logged", "network_called", "production_adapter_created")):
        raise ValueError("access_audit_claims_forbidden_activity")
    dnse = value.get("dnse_next_qualification_route") or {}
    if value.get("dnse_market_data_access") != DNSE_MARKET_DATA_ACCESS:
        raise ValueError("dnse_access_state_must_reflect_existing_contract")
    if dnse.get("market_basis_effect") != "none_until_retained_qualification_pilot_passes":
        raise ValueError("dnse_documentation_must_not_open_market_basis")
    if dnse.get("foreign_flow_value_authority") != DNSE_FOREIGN_FLOW_VALUE_AUTHORITY:
        raise ValueError("dnse_foreign_flow_authority_must_remain_production_enabled")
    if dnse.get("ohlc_price_basis") != DNSE_OHLC_PRICE_BASIS or dnse.get("market_volume_basis") != DNSE_MARKET_VOLUME_BASIS:
        raise ValueError("dnse_price_and_volume_gaps_must_remain_fail_closed")
    if dnse.get("network_called") or dnse.get("credentials_read_or_logged"):
        raise ValueError("dnse_pending_route_must_not_call_network_or_read_credentials")
