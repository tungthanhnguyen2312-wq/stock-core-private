"""Deterministic, fail-closed market-wide current valuation snapshot.

This consumes retained current-session price, share-basis, and fundamental
artifacts only. It emits a blocked metric rather than substitute provider
trends, issued shares, or a historical price for a missing compatible input.

CURRENT RESEARCH valuation may use a lower share-authority tier only where an
existing contract already permits that use (owner-approved issued-share MVA
proxy / current descriptive research). Provider-reported shares are never
promoted to official common-outstanding authority. Authoritative READY remains
restricted to an explicit current-common-share coverage that includes the
price session.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from typing import Any, Mapping

from field_temporal_contract import stable_id
import monetary_basis_contract as basis_contract
import mva_provider_share_proxy as issued_share_proxy
import p3f_current_market_valuation as p3f
from polymorphic_current_strategy_classification import _valuation_requirement
from price_representation_contract import RepresentationContractError, to_canonical

CONTRACT_VERSION = "market_wide_current_valuation/v1"
ARTIFACT_TYPE = "MARKET_WIDE_CURRENT_VALUATION"
METRICS = ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales", "EV/EBITDA")
SHADOW_METRICS = ("proxy_market_cap", "proxy_P/E", "proxy_P/B", "proxy_P/S", "proxy_EV", "proxy_EV/Sales", "proxy_EV/EBITDA")
OFFICIAL_CURRENT_STATUSES = frozenset({
    "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
    "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE",
})
SHARE_STATUS_BY_AUTHORITY = {
    "qualified_official": "QUALIFIED_OFFICIAL",
    "qualified_current_common_shares": "QUALIFIED_CURRENT_COMMON_SHARES",
    "qualified_official_anchor_not_current": "QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT",
    "provider_reported_current": "PROVIDER_REPORTED_CURRENT",
    "provider_reported_current_research": "PROVIDER_REPORTED_CURRENT_RESEARCH",
    "provider_reported_lagged": "PROVIDER_REPORTED_LAGGED",
    "provider_reported_stale": "PROVIDER_REPORTED_STALE",
    "provider_reported_unverifiable_freshness": "PROVIDER_REPORTED_UNVERIFIABLE_FRESHNESS",
    "unverifiable_freshness": "UNVERIFIABLE_FRESHNESS",
    "corporate_action_reconciliation_required": "CORPORATE_ACTION_RECONCILIATION_REQUIRED",
    "semantic_identity_unresolved": "SEMANTIC_IDENTITY_UNRESOLVED",
    "unknown_observation_date": "UNKNOWN_OBSERVATION_DATE",
    "unavailable": "UNAVAILABLE",
    "unresolved_error": "UNRESOLVED_ERROR",
}
RESEARCH_SHARE_AUTHORITIES = frozenset({
    "qualified_official",
    "qualified_current_common_shares",
    "qualified_official_anchor_not_current",
    "provider_reported_current",
    "provider_reported_current_research",
    "provider_reported_lagged",
})
STALE_FAIL_CLOSED_AUTHORITIES = frozenset({
    "provider_reported_stale",
    "provider_reported_unverifiable_freshness",
    "unverifiable_freshness",
    "corporate_action_reconciliation_required",
    "semantic_identity_unresolved",
})
#: Share authority tiers backed by an independent, audited/official citation (see
#: `current_common_shares_authority.py`'s `official_common` anchor and
#: `docs/share_basis_qualification.md`'s literal Note-27-style count) -- the share
#: *count* itself is a proven, unscaled number for these tiers. `provider_reported_*`
#: tiers (VCI `issue_share`) are not: `financial_identity.qualify_capital_structure_
#: observation` retains them with `"unit": "unknown"` explicitly, never inferring a
#: basic-share-count identity from an unlabeled provider field.
QUALIFIED_SHARE_COUNT_AUTHORITIES = frozenset({
    "qualified_official",
    "qualified_current_common_shares",
    "qualified_official_anchor_not_current",
})
#: Retained `price_unit` tokens that independently prove the exact absolute scale of a
#: DNSE current-session close (e.g. a documented request/response unit parameter, the
#: way KBS's `unit=1000` is proven in `provider_financial_semantic_basis.py`). Empty
#: today: `mva_exact_session_snapshot.py` retains every observation tagged
#: `SOURCE_PRICE_UNIT_UNDOCUMENTED`, and `docs/DECISIONS.md` records that an earlier
#: empirical thousands-of-VND guess (`P3F9B`) was identified as a
#: `MIXED_SOURCE_REPRESENTATION_DEFECT` and removed -- an empirical cross-provider
#: ratio is evidence, not a unit conversion. This set exists so a future milestone with
#: a real documented unit contract only has to add the token here, not re-plumb this
#: module.
KNOWN_PRICE_SCALE_TOKENS: frozenset[str] = frozenset()
RESEARCH_LABELS = (
    "CURRENT_RESEARCH_ONLY",
    "NOT_AUTHORITATIVE",
    "NOT_PIT",
    "NOT_FOR_TARGET_PRICE",
    "NOT_FOR_SIZING",
    "NOT_FOR_EXECUTION",
    "NOT_FOR_VALUE_STRATEGY",
)
EARNINGS_IDENTITY_BY_ENTITY = {
    "corporate": "net_income",
    "bank": "net_profit_parent",
    "securities": "profit_after_tax_parent",
}
EQUITY_IDENTITY_BY_ENTITY = {
    "corporate": "shareholders_equity",
    "bank": "total_equity",
    "securities": "total_equity",
}
P3F_METHOD_FOR_METRIC = {
    "P/E": "P/E",
    "P/B": "P/B",
    "P/S": "P/S",
    "enterprise_value": "EV/Sales",
    "EV/Sales": "EV/Sales",
    "EV/EBITDA": "EV/EBITDA",
}


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_valuation:{digest}"}


def official_research_universe_tickers(official_universe: Mapping[str, Any] | None) -> list[str] | None:
    if official_universe is None:
        return None
    return sorted(
        ticker for ticker, row in (official_universe.get("records") or {}).items()
        if row.get("stocklookup_candidate") and row.get("current_universe_status") in OFFICIAL_CURRENT_STATUSES
    )


def _share_from_authority_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Consume current_common_shares_authority/v1 without changing valuation formulas."""
    tier = str(record.get("authority_tier") or "UNAVAILABLE")
    authority = tier.lower()
    status = SHARE_STATUS_BY_AUTHORITY.get(authority, tier if tier else "UNAVAILABLE")
    authoritative_ready = tier == "QUALIFIED_CURRENT_COMMON_SHARES"
    research_eligible = (
        record.get("fitness_for_use") in {"AUTHORITATIVE_CURRENT_MARKET_CAP", "RESEARCH_USABLE_NOT_AUTHORITATIVE"}
        and record.get("value") is not None
        and authority not in STALE_FAIL_CLOSED_AUTHORITIES
    )
    blockers = list(record.get("blockers") or [])
    if not authoritative_ready:
        blockers.append("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION")
    if authority in STALE_FAIL_CLOSED_AUTHORITIES:
        blockers.append("STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS")
    return {
        "status": status,
        "authority": authority,
        "value": record.get("value") if research_eligible or authoritative_ready else None,
        "share_concept": record.get("canonical_share_identity") if (research_eligible or authoritative_ready) else "unknown_share_concept",
        "source_artifact_identity": record.get("source_evidence_identity"),
        "freshness": str(record.get("fitness_for_use") or tier),
        "observation_date": record.get("observed_at"),
        "observation_lag_days": None,
        "authoritative_current_market_cap_eligible": authoritative_ready,
        "research_proxy_eligible": research_eligible,
        "blocked_reasons": sorted(set(blockers)),
        "retained_evidence": dict(record),
    }


def _share_from_resolver(resolved: Mapping[str, Any], authoritative: Mapping[str, Any] | None) -> dict[str, Any]:
    authority = str(resolved.get("authority") or "unavailable")
    status = SHARE_STATUS_BY_AUTHORITY.get(authority, "UNAVAILABLE")
    share_concept = resolved.get("share_concept") or (
        "current_common_shares_outstanding" if authority == "qualified_official" else
        issued_share_proxy.SEMANTIC_IDENTITY if authority in RESEARCH_SHARE_AUTHORITIES else
        "unknown_share_concept"
    )
    authoritative_ready = bool(authoritative and authoritative.get("status") == "SHARE_READY")
    research_eligible = (
        authority in RESEARCH_SHARE_AUTHORITIES
        and resolved.get("value") is not None
        and authority not in STALE_FAIL_CLOSED_AUTHORITIES
    )
    blockers = []
    if not authoritative_ready:
        blockers.append("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION")
    if authority in STALE_FAIL_CLOSED_AUTHORITIES:
        blockers.append("STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS")
    if authority == "unavailable":
        blockers.append("NO_TICKER_LEVEL_CURRENT_SHARE_BASIS_EVIDENCE_RETAINED")
    if resolved.get("reason"):
        blockers.append(str(resolved["reason"]))
    return {
        "status": status,
        "authority": authority,
        "value": resolved.get("value") if research_eligible or authoritative_ready else None,
        "share_concept": share_concept if (research_eligible or authoritative_ready) else "unknown_share_concept",
        "source_artifact_identity": resolved.get("source") or resolved.get("resolver_version"),
        "freshness": str(resolved.get("status") or authority),
        "observation_date": resolved.get("observation_date"),
        "observation_lag_days": resolved.get("observation_lag_days"),
        "authoritative_current_market_cap_eligible": authoritative_ready,
        "research_proxy_eligible": research_eligible,
        "blocked_reasons": sorted(set(blockers)),
        "retained_evidence": dict(resolved),
    }


def _share_disposition(
    ticker: str,
    promotion: Mapping[str, Any],
    resolved: Mapping[str, Any] | None = None,
    authoritative: Mapping[str, Any] | None = None,
    authority_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Preserve resolver/P3-F5 share tiers; never promote issued shares to official CSO."""
    if isinstance(authority_record, Mapping) and authority_record:
        return _share_from_authority_record(authority_record)
    if isinstance(resolved, Mapping) and resolved:
        return _share_from_resolver(resolved, authoritative)
    cohort = (promotion.get("projected_coverage_impact") or {}).get("cohort_rows") or []
    row = next((item for item in cohort if item.get("ticker") == ticker), None)
    source = promotion.get("artifact_identity")
    if row is None:
        return {
            "status": "UNAVAILABLE", "authority": "unavailable", "value": None,
            "share_concept": "unknown_share_concept", "source_artifact_identity": source,
            "freshness": "UNKNOWN", "authoritative_current_market_cap_eligible": False,
            "research_proxy_eligible": False,
            "blocked_reasons": ["NO_TICKER_LEVEL_CURRENT_SHARE_BASIS_EVIDENCE_RETAINED"],
        }
    authority = str(row.get("resolver_authority") or "unavailable")
    status = SHARE_STATUS_BY_AUTHORITY.get(authority)
    if status is None:
        freshness = str(row.get("freshness_state") or "UNAVAILABLE")
        status = freshness if freshness in SHARE_STATUS_BY_AUTHORITY.values() else "UNAVAILABLE"
    research_eligible = authority in RESEARCH_SHARE_AUTHORITIES and row.get("provider_value") is not None
    if authority in STALE_FAIL_CLOSED_AUTHORITIES:
        research_eligible = False
    blockers = ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"]
    if authority in STALE_FAIL_CLOSED_AUTHORITIES:
        blockers.append("STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS")
    share_concept = (
        "current_common_shares_outstanding" if authority == "qualified_official" else
        issued_share_proxy.SEMANTIC_IDENTITY if research_eligible else "unknown_share_concept"
    )
    return {
        "status": status or "UNAVAILABLE",
        "authority": authority,
        "value": row.get("provider_value") if research_eligible else None,
        "share_concept": share_concept,
        "source_artifact_identity": source,
        "freshness": str(row.get("freshness_state") or authority),
        "authoritative_current_market_cap_eligible": False,
        "research_proxy_eligible": research_eligible,
        "blocked_reasons": blockers,
        "retained_evidence": dict(row),
    }


def _price_input(record: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Use only the exact snapshot session close. Prior-session lookback never substitutes."""
    session = snapshot.get("resolved_completed_session")
    if not isinstance(record, Mapping):
        record = {"disposition": "NOT_IN_PRICE_SNAPSHOT", "observations": []}
    disposition = record.get("disposition") or "UNAVAILABLE"
    matches = [
        item for item in record.get("observations") or []
        if isinstance(item, Mapping) and item.get("session") == session
    ]
    blocked: list[str] = []
    close = None
    ready = False
    native_price_unit = None
    representation = None
    observation_provider = None
    if disposition != "EXACT_SESSION_RETAINED":
        blocked = [f"PRICE_{disposition}"]
    elif len(matches) != 1:
        blocked = ["PRICE_SESSION_MISSING" if not matches else "PRICE_SESSION_AMBIGUOUS"]
    else:
        close = matches[0].get("close")
        native_price_unit = matches[0].get("price_unit")
        observation_provider = matches[0].get("provider")
        if isinstance(close, bool) or not isinstance(close, (int, float)) or close <= 0:
            close, blocked = None, ["PRICE_CLOSE_INVALID"]
        else:
            source_descriptor = snapshot.get("source")
            representation_source = (
                source_descriptor.get("provider") if isinstance(source_descriptor, Mapping)
                else source_descriptor
            )
            try:
                representation = to_canonical(
                    close, source=str(representation_source or ""), capability_id="ohlc_1D",
                    instrument_class="VN_LISTED_EQUITY", field="close",
                )
                close = float(representation["canonical_value"])
                ready = True
            except RepresentationContractError as exc:
                close = None
                blocked = ["PRICE_REPRESENTATION_CONTRACT_UNAVAILABLE", str(exc)]
    return {
        "status": "PRICE_READY" if ready else "PRICE_UNAVAILABLE",
        "value": close,
        "session": session,
        "source": snapshot.get("source") or "DNSE",
        "observation_provider": observation_provider,
        "basis": "CURRENT_SESSION_DESCRIPTIVE_CURRENT_VALUATION_PRICE_LEG",
        "currency": "VND",
        "price_unit": "vnd_per_share" if ready else "snapshot_native_close",
        "provider_native_value": None if representation is None else representation["provider_native_value"],
        "provider_native_unit": None if representation is None else representation["provider_native_unit"],
        "price_representation": representation,
        # The retained observation's own scale-proof token (e.g. `SOURCE_PRICE_UNIT_
        # UNDOCUMENTED`), distinct from `price_unit` above, which only labels *which
        # field* this leg reads, not whether that field's absolute scale is proven.
        "native_price_scale_token": native_price_unit,
        "raw_as_traded": "NOT_PROMOTED",
        "historical_pit_eligible": False,
        "source_snapshot_identity": snapshot.get("snapshot_identity"),
        "blocked_reasons": blocked,
        "reason_codes": blocked,
    }


def _price_coverage_state(price: Mapping[str, Any]) -> str:
    if price.get("status") == "PRICE_READY":
        return "EXACT_SESSION_READY"
    reasons = " ".join(price.get("blocked_reasons") or [])
    if "PRICE_CLOSE_INVALID" in reasons:
        return "INVALID"
    if any(token in reasons for token in ("PRICE_SESSION_MISSING", "PRICE_SESSION_AMBIGUOUS", "PRICE_SESSION_MISSING", "PRICE_NOT_IN_PRICE_SNAPSHOT")):
        return "MISSING_EXACT_SESSION"
    if "SESSION_MISSING" in reasons:
        return "MISSING_EXACT_SESSION"
    return "OTHER"


def _financial_coverage_state(financial: Mapping[str, Any], entity: str) -> str:
    authority = financial.get("authority")
    if authority == "OFFICIAL_QUALIFIED" and financial.get("calculation_grade") is True:
        return "OFFICIAL_QUALIFIED_USABLE"
    if authority == "PROVIDER_RESEARCH":
        return "PROVIDER_TRENDS_DESCRIPTIVE_NOT_ABSOLUTE"
    if entity in {"finance_company", "insurance"}:
        return "NOT_APPLICABLE_ENTITY_CLASS"
    if authority == "UNAVAILABLE":
        return "MISSING"
    return "INSUFFICIENT_EVIDENCE"


def _first_blocker(metric: Mapping[str, Any], *, price: Mapping[str, Any],
                   share: Mapping[str, Any], financial: Mapping[str, Any], entity: str) -> str | None:
    """Name the first real blocker. Observed READY/RESEARCH_USABLE have none."""
    status = metric.get("status")
    if status in {"READY", "RESEARCH_USABLE"}:
        return None
    if status == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    reasons = [str(item) for item in metric.get("blocked_reasons") or []]
    joined = " ".join(reasons)
    if price.get("status") != "PRICE_READY" or any(item.startswith("PRICE_") for item in reasons):
        return "PRICE_MISSING"
    if share.get("authority") in STALE_FAIL_CLOSED_AUTHORITIES or "STALE_SHARE_FAIL_CLOSED" in joined:
        return "SHARE_STALE_OR_CORPORATE_ACTION_BLOCKED"
    if not share.get("research_proxy_eligible") and not share.get("authoritative_current_market_cap_eligible"):
        return "SHARE_AUTHORITY_OR_PROXY_UNAVAILABLE"
    if "EXACT_EBITDA_COMPARABILITY_NOT_RETAINED" in joined:
        return "EBITDA_NOT_EXACT"
    if any("FINANCIAL_IDENTITY_MISSING:total_interest_bearing_debt" in item or item.endswith(":total_interest_bearing_debt") for item in reasons):
        return "DEBT_COMPONENT_MISSING"
    if any("PERIOD" in item or "period" in item for item in reasons):
        return "FINANCIAL_PERIOD_MISMATCH"
    if entity == "unknown" or "ENTITY_CLASS_UNRESOLVED" in joined:
        return "FINANCIAL_ENTITY_IDENTITY_MISMATCH"
    if any(token in joined for token in (
        "PROVIDER_RESEARCH_NOT_AUTHORIZED", "NO_RETAINED_FINANCIAL_RECORD",
        "OFFICIAL_QUALIFIED_FINANCIAL_INPUT_UNAVAILABLE", "FINANCIAL_IDENTITY_MISSING",
    )):
        return "FINANCIAL_FACT_MISSING"
    return reasons[0] if reasons else "VALUATION_INPUT_BLOCKED"


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
        return {
            "authority": tier, "calculation_grade": False,
            "blocked_reasons": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"],
            "source_artifact_identity": artifact.get("artifact_identity"),
        }
    return {
        "authority": "OFFICIAL_QUALIFIED", "calculation_grade": True,
        "source_artifact_identity": artifact.get("artifact_identity"),
        "metric_count": len(fundamental.get("metrics") or []),
        "period_context": fundamental.get("official_metric_context"),
    }


def _metric_shell(metric: str, *, status: str, applicability: str, value: Any = None,
                  blockers: list[str] | None = None, price: Mapping[str, Any] | None = None,
                  extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "metric_id": metric,
        "status": status,
        "value": value if status in {"READY", "RESEARCH_USABLE"} else None,
        "applicability": applicability,
        "formula_version": CONTRACT_VERSION if status != "RESEARCH_USABLE" else f"{CONTRACT_VERSION}+{p3f.CONTRACT_VERSION}",
        "blocked_reasons": sorted(set(blockers or [])),
        "price_session": (price or {}).get("session"),
        "is_actionable": False,
        "historical_pit_eligible": False,
    }
    if extra:
        row.update(dict(extra))
    if status == "RESEARCH_USABLE":
        labels = list(RESEARCH_LABELS)
        if extra and extra.get("share_identity") == issued_share_proxy.SEMANTIC_IDENTITY:
            labels.append("NOT_COMMON_OUTSTANDING_SHARE_BASIS")
        row["labels"] = labels
        row["allowed_uses"] = ["CURRENT_RESEARCH_ONLY"]
        row["forbidden_uses"] = [
            "AUTHORITATIVE_VALUATION", "VALUE_STRATEGY_ELIGIBILITY", "TARGET_PRICE",
            "INTRINSIC_VALUE", "DCF", "SIZING", "EXECUTION", "RANKING", "RECOMMENDATION", "PIT",
        ]
    elif status == "READY":
        row["labels"] = ["AUTHORITATIVE_CURRENT_RESEARCH"]
        row["allowed_uses"] = ["CURRENT_RESEARCH_ONLY", "AUTHORITATIVE_CURRENT_VALUATION"]
        row["forbidden_uses"] = ["TARGET_PRICE", "INTRINSIC_VALUE", "DCF", "SIZING", "EXECUTION", "RANKING", "RECOMMENDATION", "PIT"]
    return row


def _input_identities(metric: str, entity: str, share: Mapping[str, Any]) -> dict[str, Any]:
    identities: dict[str, Any] = {
        "price": "dnse_current_session_close",
        "share": share.get("share_concept"),
        "share_authority_tier": share.get("status"),
        "weighted_average_shares_not_used_as_current_outstanding": True,
        "liabilities_not_aliased_to_interest_bearing_debt": True,
    }
    if metric == "P/E":
        identities["earnings"] = EARNINGS_IDENTITY_BY_ENTITY.get(entity)
        identities["parent_attributable_vs_total_earnings_kept_distinct"] = True
    if metric == "P/B":
        identities["equity"] = EQUITY_IDENTITY_BY_ENTITY.get(entity)
        identities["parent_equity_vs_total_equity_kept_distinct"] = True
    if metric == "P/S":
        identities["revenue"] = "revenue"
    if metric in {"enterprise_value", "EV/Sales", "EV/EBITDA"}:
        identities["debt"] = "total_interest_bearing_debt"
        identities["cash"] = "cash_and_equivalents"
    if metric == "EV/EBITDA":
        identities["ebitda"] = "ebitda_v1_profit_before_tax_plus_interest_expense_plus_depreciation_and_amortization"
        identities["ebitda_comparability"] = "NOT_A_REPORTED_OR_NORMALIZED_EBITDA"
    return identities


def _p3f_price(price: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "PRICE_READY" if price.get("status") == "PRICE_READY" else "PRICE_BLOCKED",
        "value": price.get("value"),
        "observed_value": price.get("value"),
        "reason_codes": list(price.get("blocked_reasons") or []),
        "session": price.get("session"),
        "valuation_date": price.get("session"),
    }


def _p3f_shares(share: Mapping[str, Any], *, research: bool, authoritative: bool) -> dict[str, Any]:
    ready = (authoritative and share.get("authoritative_current_market_cap_eligible")) or (
        research and share.get("research_proxy_eligible") and share.get("value") is not None
    )
    return {
        "status": "SHARE_BASIS_READY" if ready else "SHARE_BASIS_BLOCKED",
        "value": share.get("value") if ready else None,
        "reason_codes": [] if ready else list(share.get("blocked_reasons") or []),
        "identity": (
            "current_common_shares_outstanding" if authoritative else
            share.get("share_concept") or issued_share_proxy.SEMANTIC_IDENTITY
        ),
    }


def _map_p3f_method(metric: str, method: Mapping[str, Any], *, research: bool, authoritative: bool,
                    applicability: str, price: Mapping[str, Any], share: Mapping[str, Any],
                    entity: str) -> dict[str, Any]:
    p3f_status = method.get("status")
    blockers = list(method.get("blockers") or [])
    if metric == "EV/EBITDA":
        blockers.append("EXACT_EBITDA_COMPARABILITY_NOT_RETAINED")
        p3f_status = "VALUATION_BLOCKED"
    if p3f_status == "NOT_APPLICABLE" or applicability == "NOT_APPLICABLE":
        return _metric_shell(metric, status="NOT_APPLICABLE", applicability="NOT_APPLICABLE",
                             blockers=blockers or ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], price=price,
                             extra={"input_identities": _input_identities(metric, entity, share)})
    value = method.get("enterprise_value") if metric == "enterprise_value" else method.get("value")
    if p3f_status == "VALUATION_READY" and metric == "enterprise_value" and value is None:
        p3f_status = "VALUATION_BLOCKED"
        blockers.append("ENTERPRISE_VALUE_NOT_EMITTED_WITHOUT_EV_SALES_INPUTS")
    financial_inputs = method.get("financial_inputs") or []
    financial_currencies = sorted({
        str(item.get("currency")).upper() for item in financial_inputs
        if isinstance(item, Mapping) and isinstance(item.get("currency"), str) and item.get("currency").strip()
    })
    price_currency = str(price.get("currency") or "").upper() or None
    financial_scales = sorted({
        str(item.get("unit_scale")) for item in financial_inputs
        if isinstance(item, Mapping) and item.get("unit_scale") is not None
    })
    currency_compatible = not financial_currencies or (
        price_currency is not None and all(currency == price_currency for currency in financial_currencies)
    )
    # `p3f_current_market_valuation` divides the retained `value` fields directly.  A
    # non-unit `unit_scale` is therefore only usable when the producer has explicitly
    # established that `value` was already canonicalized.  The legacy p3e leg does not
    # carry that representation proof (VNM 2024 revenue is the retained counterexample),
    # so refuse it rather than guessing whether to multiply it here.
    scale_compatible = not financial_scales or all(scale in {"1", "1.0"} for scale in financial_scales)
    monetary_compatibility = {
        "status": (
            "COMPATIBLE" if currency_compatible and scale_compatible
            else "BLOCKED_CURRENCY_MISMATCH" if not currency_compatible
            else "BLOCKED_FINANCIAL_VALUE_SCALE_UNRESOLVED"
        ),
        "price_currency": price_currency,
        "financial_currencies": financial_currencies,
        "financial_input_unit_scales": financial_scales,
        "price_representation_contract_id": (price.get("price_representation") or {}).get("contract_id"),
        "reason": (
            None if currency_compatible and scale_compatible
            else "PRICE_FINANCIAL_CURRENCY_MISMATCH_NO_FX_CONVERSION_CONTRACT" if not currency_compatible
            else "FINANCIAL_VALUE_SCALE_NOT_CANONICAL_FOR_CURRENT_VALUATION"
        ),
    }
    status = "BLOCKED"
    if p3f_status == "VALUATION_READY":
        if authoritative:
            status = "READY"
        elif research:
            status = "RESEARCH_USABLE"
        else:
            blockers.extend(share.get("blocked_reasons") or [])
    elif not blockers:
        blockers.extend(share.get("blocked_reasons") or method.get("blockers") or ["VALUATION_INPUT_BLOCKED"])
    if not currency_compatible or not scale_compatible:
        status = "BLOCKED"
        value = None
        blockers.append(monetary_compatibility["reason"])
    extra = {
        "input_identities": _input_identities(metric, entity, share),
        "share_identity": share.get("share_concept"),
        "financial_period": method.get("financial_period"),
        "financial_inputs": financial_inputs,
        "formula": method.get("formula") or ("market_cap + total_interest_bearing_debt - cash_and_equivalents" if metric == "enterprise_value" else None),
        "p3f_method_status": p3f_status,
        "price_representation": price.get("price_representation"),
        "monetary_compatibility": monetary_compatibility,
    }
    return _metric_shell(metric, status=status, applicability=applicability, value=value,
                         blockers=blockers, price=price, extra=extra)


def _market_cap_monetary_basis(price: Mapping[str, Any], share: Mapping[str, Any]) -> dict[str, Any]:
    """Honest currency/scale for `current_session_close * share_basis_value`.

    Never inferred from magnitude. Both factors must independently prove their absolute
    scale before their product can: the retained price observation must name a token in
    `KNOWN_PRICE_SCALE_TOKENS` (empty today -- see that constant), and the share count
    must come from an audited/official citation (`QUALIFIED_SHARE_COUNT_AUTHORITIES`),
    not an unlabeled provider field. Currency reuses the price leg's existing VND
    assumption -- a jurisdictional fact about which exchange this instrument trades on,
    unrelated to the unresolved absolute-scale question.
    """
    price_scale_token = price.get("native_price_scale_token")
    price_scale_known = price_scale_token in KNOWN_PRICE_SCALE_TOKENS
    share_authority = str(share.get("authority") or "")
    share_scale_known = share_authority in QUALIFIED_SHARE_COUNT_AUTHORITIES
    both_known = price_scale_known and share_scale_known
    return basis_contract.build_basis(
        currency=price.get("currency"),
        scale=basis_contract.BASE_UNIT_SCALE_LABEL if both_known else None,
        multiplier_to_vnd=1 if both_known else None,
        normalized_unit="VND" if both_known else None,
        basis_source=(
            f"price.native_price_scale_token={price_scale_token!r} (proven={price_scale_known}); "
            f"share.authority={share_authority!r} (audited_citation={share_scale_known})"
        ),
    )


def _build_metrics(*, entity: str, price: Mapping[str, Any], share: Mapping[str, Any],
                   financial: Mapping[str, Any], issuer: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    research = bool(share.get("research_proxy_eligible"))
    authoritative = bool(share.get("authoritative_current_market_cap_eligible"))
    price_ready = price.get("status") == "PRICE_READY"
    cap_value = None
    if price_ready and share.get("value") is not None and (research or authoritative):
        cap_value = price["value"] * share["value"]
    cap_basis = _market_cap_monetary_basis(price, share)
    cap_basis_fields = {
        "currency": cap_basis.get("currency"),
        "scale": cap_basis.get("native_scale"),
        "normalized_currency": cap_basis.get("currency") if cap_basis.get("basis_status") != basis_contract.UNKNOWN else None,
        "normalized_scale": basis_contract.BASE_UNIT_SCALE_LABEL if cap_basis.get("basis_status") != basis_contract.UNKNOWN else None,
        "monetary_basis_status": cap_basis.get("basis_status"),
        "monetary_basis_source": cap_basis.get("basis_source"),
        "monetary_basis": cap_basis,
    }

    for metric in METRICS:
        applicability = _applicability(entity, metric)
        if applicability == "NOT_APPLICABLE":
            metrics[metric] = _metric_shell(
                metric, status="NOT_APPLICABLE", applicability=applicability,
                blockers=["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], price=price,
                extra={"input_identities": _input_identities(metric, entity, share)},
            )
            continue
        if applicability == "BLOCKED_ENTITY_CLASS_UNKNOWN" and metric != "market_cap":
            metrics[metric] = _metric_shell(
                metric, status="BLOCKED", applicability=applicability,
                blockers=["ENTITY_CLASS_UNRESOLVED"], price=price,
                extra={"input_identities": _input_identities(metric, entity, share)},
            )
            continue
        if metric == "market_cap":
            blockers = []
            if not price_ready:
                blockers.extend(price.get("blocked_reasons") or [])
                metrics[metric] = _metric_shell(
                    metric, status="BLOCKED", applicability=applicability, blockers=blockers,
                    price=price, extra={"input_identities": _input_identities(metric, entity, share),
                                        "share_identity": share.get("share_concept"), **cap_basis_fields},
                )
                continue
            if share.get("authority") in STALE_FAIL_CLOSED_AUTHORITIES:
                blockers.extend(share.get("blocked_reasons") or [])
                metrics[metric] = _metric_shell(
                    metric, status="BLOCKED", applicability=applicability, blockers=blockers,
                    price=price, extra={"input_identities": _input_identities(metric, entity, share),
                                        "share_identity": share.get("share_concept"), **cap_basis_fields},
                )
                continue
            if not (research or authoritative) or share.get("value") is None:
                blockers.extend(share.get("blocked_reasons") or ["CURRENT_SHARE_BASIS_UNAVAILABLE"])
                metrics[metric] = _metric_shell(
                    metric, status="BLOCKED", applicability=applicability, blockers=blockers,
                    price=price, extra={"input_identities": _input_identities(metric, entity, share), **cap_basis_fields},
                )
                continue
            status = "READY" if authoritative and price_ready else "RESEARCH_USABLE"
            extra = {
                "input_identities": _input_identities(metric, entity, share),
                "share_identity": share.get("share_concept"),
                "formula": "current_session_close * share_basis_value",
                "price_representation": price.get("price_representation"),
                **cap_basis_fields,
            }
            if status == "RESEARCH_USABLE":
                extra["warnings"] = list(share.get("blocked_reasons") or [])
            metrics[metric] = _metric_shell(
                metric, status=status, applicability=applicability, value=cap_value,
                blockers=[], price=price, extra=extra,
            )
            continue
        if metric == "EV/EBITDA":
            blockers = ["EXACT_EBITDA_COMPARABILITY_NOT_RETAINED"]
            if not financial.get("calculation_grade"):
                blockers.extend(financial.get("blocked_reasons") or [])
            if not price_ready:
                blockers.extend(price.get("blocked_reasons") or [])
            if not (research or authoritative):
                blockers.extend(share.get("blocked_reasons") or [])
            metrics[metric] = _metric_shell(
                metric, status="BLOCKED", applicability=applicability, blockers=blockers,
                price=price, extra={"input_identities": _input_identities(metric, entity, share),
                                    "share_identity": share.get("share_concept")},
            )
            continue
        if not financial.get("calculation_grade") or issuer is None:
            blockers = list(financial.get("blocked_reasons") or ["OFFICIAL_QUALIFIED_FINANCIAL_INPUT_UNAVAILABLE"])
            if not price_ready:
                blockers.extend(price.get("blocked_reasons") or [])
            if share.get("authority") in STALE_FAIL_CLOSED_AUTHORITIES or not (research or authoritative):
                blockers.extend(share.get("blocked_reasons") or [])
            metrics[metric] = _metric_shell(
                metric, status="BLOCKED", applicability=applicability, blockers=blockers,
                price=price, extra={"input_identities": _input_identities(metric, entity, share),
                                    "share_identity": share.get("share_concept")},
            )
            continue

    remaining = [metric for metric in METRICS if metric not in metrics]
    if remaining and issuer is not None and financial.get("calculation_grade"):
        formula_row = p3f._evaluate_issuer(
            issuer, price=_p3f_price(price),
            shares=_p3f_shares(share, research=research, authoritative=authoritative),
        )
        for metric in remaining:
            applicability = _applicability(entity, metric)
            p3f_name = P3F_METHOD_FOR_METRIC[metric]
            metrics[metric] = _map_p3f_method(
                metric, formula_row["methods"][p3f_name], research=research, authoritative=authoritative,
                applicability=applicability, price=price, share=share, entity=entity,
            )
    return metrics


def evaluate_value_strategy_readiness(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse the existing VALUE gate; RESEARCH_USABLE never satisfies it."""
    eligible = 0
    blocked = 0
    records: dict[str, Any] = {}
    for ticker, row in (artifact.get("records") or {}).items():
        requirement = _valuation_requirement(row)
        status = "ELIGIBLE" if requirement["status"] == "SATISFIED" else "BLOCKED"
        if status == "ELIGIBLE":
            eligible += 1
        else:
            blocked += 1
        records[ticker] = {
            "status": status,
            "requirement": requirement,
            "authoritative_metric_ready": any(
                metric.get("status") == "READY" for metric in (row.get("metrics") or {}).values()
            ),
            "research_usable_present": any(
                metric.get("status") == "RESEARCH_USABLE" for metric in (row.get("metrics") or {}).values()
            ),
        }
    return {
        "eligible": eligible,
        "blocked": blocked,
        "universe_count": eligible + blocked,
        "rule": "VALUE requires any strict metrics.status==READY under AUTHORITATIVE_CURRENT_VALUATION",
        "research_usable_does_not_satisfy_value": True,
        "shadow_proxy_does_not_satisfy_value": True,
        "records": records,
    }


def build_current_valuation_artifact(
    *,
    price_snapshot: Mapping[str, Any],
    fundamental_artifact: Mapping[str, Any],
    share_promotion_artifact: Mapping[str, Any],
    share_resolution: Mapping[str, Any] | None = None,
    official_universe: Mapping[str, Any] | None = None,
    p3e_artifact: Mapping[str, Any] | None = None,
    authoritative_share_states: Mapping[str, Mapping[str, Any]] | None = None,
    share_authority_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize one record per research-universe ticker without imputation."""
    records: dict[str, Any] = {}
    fundamentals = fundamental_artifact.get("records") or {}
    resolved_tickers = ((share_resolution or {}).get("tickers") or {})
    authority_records = (share_authority_artifact or {}).get("records") or {}
    issuers = {
        str(item["issuer_identity"]["ticker"]): item
        for item in ((p3e_artifact or {}).get("refreshed_panel_data") or {}).get("issuers", [])
    }
    official_tickers = official_research_universe_tickers(official_universe)
    price_records = price_snapshot.get("records") or {}
    universe = official_tickers if official_tickers is not None else sorted(price_records)
    for ticker in universe:
        fundamental = fundamentals.get(ticker)
        entity = str((fundamental or {}).get("entity_class") or (issuers.get(ticker) or {}).get("issuer_identity", {}).get("entity_type") or "unknown")
        price = _price_input(price_records.get(ticker, {"disposition": "NOT_IN_PRICE_SNAPSHOT"}), price_snapshot)
        share = _share_disposition(
            ticker, share_promotion_artifact,
            resolved=resolved_tickers.get(ticker),
            authoritative=(authoritative_share_states or {}).get(ticker),
            authority_record=authority_records.get(ticker),
        )
        financial = _financial_input(fundamental, fundamental_artifact)
        issuer = issuers.get(ticker)
        metric_rows = _build_metrics(entity=entity, price=price, share=share, financial=financial, issuer=issuer)
        for metric in metric_rows.values():
            metric["first_blocker"] = _first_blocker(
                metric, price=price, share=share, financial=financial, entity=entity,
            )
        warnings = ["CURRENT_DESCRIPTIVE_NOT_HISTORICAL_PIT", "NO_RANKING_OR_RECOMMENDATION", "NO_TARGET_PRICE_OR_DCF"]
        if any(metric["status"] == "RESEARCH_USABLE" for metric in metric_rows.values()):
            warnings.append("RESEARCH_USABLE_IS_NOT_AUTHORITATIVE_AND_DOES_NOT_MAKE_VALUE_ELIGIBLE")
        row = {
            "ticker": ticker,
            "entity_class": entity,
            "entity_class_source": (fundamental or {}).get("entity_class_provenance"),
            "in_official_research_universe": official_tickers is None or ticker in official_tickers,
            "price_input": price,
            "share_basis_input": share,
            "financial_input": financial,
            "metrics": metric_rows,
            "warnings": warnings,
            "is_actionable": False,
        }
        records[ticker] = row

    metric_ready = {metric: sum(row["metrics"][metric]["status"] == "READY" for row in records.values()) for metric in METRICS}
    metric_research_usable = {metric: sum(row["metrics"][metric]["status"] == "RESEARCH_USABLE" for row in records.values()) for metric in METRICS}
    metric_blocked = {metric: sum(row["metrics"][metric]["status"] == "BLOCKED" for row in records.values()) for metric in METRICS}
    metric_na = {metric: sum(row["metrics"][metric]["status"] == "NOT_APPLICABLE" for row in records.values()) for metric in METRICS}
    blocked_reasons: Counter[str] = Counter()
    sector_breakdown: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(Counter))
    first_blocker_by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    first_blocker_by_entity: dict[str, Counter[str]] = defaultdict(Counter)
    first_blocker_total: Counter[str] = Counter()
    for row in records.values():
        for metric_id, metric in row["metrics"].items():
            for reason in metric.get("blocked_reasons") or []:
                blocked_reasons[reason] += 1
            sector_breakdown[row["entity_class"]][metric_id][metric["status"]] += 1
            blocker = metric.get("first_blocker")
            if blocker:
                first_blocker_by_metric[metric_id][blocker] += 1
                first_blocker_by_entity[row["entity_class"]][blocker] += 1
                first_blocker_total[blocker] += 1
    price_states = dict(sorted(Counter(_price_coverage_state(r["price_input"]) for r in records.values()).items()))
    financial_states = dict(sorted(Counter(
        _financial_coverage_state(r["financial_input"], r["entity_class"]) for r in records.values()
    ).items()))
    share_states = dict(sorted(Counter(r["share_basis_input"]["status"] for r in records.values()).items()))
    input_residual = (
        abs(sum(price_states.values()) - len(records))
        + abs(sum(share_states.values()) - len(records))
        + abs(sum(financial_states.values()) - len(records))
    )
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "valuation_session": price_snapshot.get("resolved_completed_session"),
        "source_artifacts": {
            "current_price": price_snapshot.get("snapshot_identity"),
            "fundamental": fundamental_artifact.get("artifact_identity"),
            "share_basis": share_promotion_artifact.get("artifact_identity"),
            "official_universe": (official_universe or {}).get("artifact_identity"),
            "official_financial_panel": (p3e_artifact or {}).get("artifact_identity"),
            "share_resolution": None if share_resolution is None else {
                "resolver_version": share_resolution.get("resolver_version"),
                "session_date": share_resolution.get("session_date"),
                "status": share_resolution.get("status"),
            },
            "share_authority": None if share_authority_artifact is None else share_authority_artifact.get("artifact_identity"),
        },
        "records": records,
        "coverage": {
            "universe_denominator": len(records),
            "price_snapshot_records": len(price_records),
            "price_ready": sum(r["price_input"]["status"] == "PRICE_READY" for r in records.values()),
            "share_ready": sum(r["share_basis_input"].get("authoritative_current_market_cap_eligible") is True for r in records.values()),
            "research_share_eligible": sum(r["share_basis_input"].get("research_proxy_eligible") is True for r in records.values()),
            "both_price_and_share_ready": sum(
                r["price_input"]["status"] == "PRICE_READY" and r["share_basis_input"].get("authoritative_current_market_cap_eligible") is True
                for r in records.values()
            ),
            "metric_ready_counts": metric_ready,
            "metric_research_usable_counts": metric_research_usable,
            "metric_blocked_counts": metric_blocked,
            "metric_not_applicable_counts": metric_na,
            "share_authority_tiers": dict(sorted(Counter(r["share_basis_input"]["status"] for r in records.values()).items())),
            "financial_authority_tiers": dict(sorted(Counter(r["financial_input"]["authority"] for r in records.values()).items())),
            "entity_classes": dict(sorted(Counter(r["entity_class"] for r in records.values()).items())),
            "blocked_or_not_applicable": dict(sorted(Counter(m["status"] for r in records.values() for m in r["metrics"].values()).items())),
            "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
            "sector_archetype_breakdown": {
                entity: {metric: dict(sorted(states.items())) for metric, states in metrics.items()}
                for entity, metrics in sorted(sector_breakdown.items())
            },
            "input_coverage": {
                "price": price_states,
                "shares": share_states,
                "financial": financial_states,
                "residual": input_residual,
            },
            "first_blocker_counts": {
                "overall": dict(sorted(first_blocker_total.items())),
                "by_metric": {metric: dict(sorted(counts.items())) for metric, counts in sorted(first_blocker_by_metric.items())},
                "by_entity_class": {entity: dict(sorted(counts.items())) for entity, counts in sorted(first_blocker_by_entity.items())},
            },
        },
        "authority_boundary": {
            "current_snapshot_only": True, "historical_pit_eligible": False, "raw_as_traded": "NOT_PROMOTED",
            "provider_financial_absolute_inputs": "BLOCKED", "ranking": False, "recommendation": False,
            "target_price": False, "intrinsic_value": False, "dcf": False,
            "research_usable_is_not_authoritative": True,
            "value_strategy_requires_authoritative_ready": True,
        },
        "valuation_context": {"status": "CURRENT_RESEARCH", "reason": "PER_METRIC_FITNESS_FOR_USE"},
        "is_actionable": False,
    }
    value_lane = evaluate_value_strategy_readiness(artifact)
    for ticker, row in records.items():
        lane = value_lane["records"][ticker]
        row["value_strategy"] = {
            "status": lane["status"],
            "authoritative_metric_ready": lane["authoritative_metric_ready"],
            "research_usable_present": lane["research_usable_present"],
            "reason": lane["requirement"]["reason"],
        }
        row["content_identity"] = stable_id(row)
    artifact["value_strategy_readiness"] = {key: value for key, value in value_lane.items() if key != "records"}
    artifact["coverage"]["denominator_reconciles"] = (
        artifact["coverage"]["universe_denominator"] == len(records)
        and sum(artifact["coverage"]["share_authority_tiers"].values()) == len(records)
        and sum(artifact["coverage"]["entity_classes"].values()) == len(records)
        and (official_tickers is None or len(official_tickers) == len(records))
        and artifact["coverage"]["input_coverage"]["residual"] == 0
        and all(
            metric_ready[metric] + metric_research_usable[metric] + metric_blocked[metric] + metric_na[metric] == len(records)
            for metric in METRICS
        )
    )
    artifact["coverage"]["unexplained_denominator_drift"] = 0 if artifact["coverage"]["denominator_reconciles"] else abs(
        artifact["coverage"]["universe_denominator"] - len(records)
    )
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
