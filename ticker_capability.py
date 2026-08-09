"""Ticker Capability Matrix (P1.5): pure, deterministic eligibility across five
capability tiers, gated exclusively on already-computed Producer contracts.

Scope discipline, matching analysis_lane_eligibility.py: this module never re-resolves a
source identity, never fetches or recomputes evidence, never infers a tier from mere
availability, and never grants a market-dependent capability because a technical field is
merely present. Every input must already be the output of an existing qualified contract
(build_price_basis_contract(), build_distribution_evidence_for_ticker(),
build_historical_fundamental_brief(), or the current-share transition resolver).

Tiers (independently evaluated -- not assumed cumulative in this implementation):
  T0_informational          -- always eligible; profile/news/sector context only.
  T1_technical_display      -- OHLCV/technical coverage exists. Display and single-series
                                pattern reading only -- no return, no adjusted comparison,
                                no cross-corporate-action comparison, no liquidity claim,
                                regardless of price/volume basis state.
  T2_historical_fundamental -- an available historical_fundamental_brief with at least one
                                qualified fact for this ticker.
  T3_distribution_event     -- distribution_evidence.coverage_status == "available" with at
                                least one qualified cash or non-cash distribution event.
  T4_market_dependent       -- price basis is_actionable AND volume basis verified AND
                                current shares proven through the trusted session. All three
                                required; missing any one blocks the tier entirely.

is_actionable is hardcoded False everywhere in this module's output -- it produces
capability gating only, never an investment signal, matching Phase 4B's
analysis_lane_eligibility.py convention exactly.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "1.1.0"

# This is a projection schema, not a new eligibility engine.  The only decisions it
# makes are how to render a missing or malformed upstream contract safely.  Every
# positive/negative business decision is retained from the named Producer contract.
MATRIX_SCHEMA_VERSION = "1.0.0"
SEMANTIC_STATUSES = frozenset({
    "available", "descriptive_only", "partial", "blocked", "blocked_input",
    "unavailable", "not_applicable", "unknown",
})


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item is not None and str(item)})
    if value is None or value == "":
        return []
    return [str(value)]


def _reason_codes(record: Mapping[str, Any]) -> list[str]:
    """Retain reason-code fields exactly; do not replace them with prose."""
    values: list[str] = []
    for key in ("reason_codes", "blocking_reasons", "missing_evidence", "required_inputs",
                "missing_or_unqualified_inputs"):
        values.extend(_string_list(record.get(key)))
    if record.get("reason"):
        values.append(str(record["reason"]))
    return sorted(set(values))


def _semantic_status(source_status: Any, *, absent: bool = False,
                     descriptive_only: bool = False) -> str:
    """Map existing source vocabulary to the compact matrix vocabulary.

    ``authority_status`` always retains the original value, so ``partial`` is never
    mistaken for a full result and statuses such as ``eligible_for_analysis`` remain
    inspectable.  This helper does not inspect evidence or calculate an analysis.
    """
    if absent:
        return "unavailable"
    if descriptive_only:
        return "descriptive_only"
    state = str(source_status or "unknown").lower()
    mapping = {
        "available": "available", "eligible": "available",
        "eligible_for_analysis": "available", "partially_eligible": "partial",
        "partial": "partial", "partially_qualified": "partial",
        "provider_reported": "partial", "provider_reported_only": "partial",
        "blocked": "blocked", "allocation_blocked": "blocked",
        "blocked_input": "blocked_input", "unavailable": "unavailable",
        "missing": "unavailable", "insufficient_evidence": "unavailable",
        "not_applicable": "not_applicable", "inapplicable": "not_applicable",
        "unknown": "unknown", "conflict": "blocked", "incomparable": "blocked",
    }
    return mapping.get(state, "unknown")


def _capability(*, authority: str, record: Mapping[str, Any] | None,
                status: Any = None, descriptive_only: bool = False,
                dependencies: Any = None, absent_reason: str | None = None,
                trust_tier: Any = None) -> dict[str, Any]:
    """Project one existing authority without copying or interpreting its result."""
    source = _as_mapping(record)
    absent = record is None
    source_status = status if status is not None else source.get("status")
    reasons = _reason_codes(source)
    if absent and absent_reason:
        reasons = [absent_reason]
    return {
        "status": _semantic_status(source_status, absent=absent,
                                   descriptive_only=descriptive_only),
        "authority_status": source_status if source_status is not None else ("missing" if absent else "unknown"),
        "reason_codes": reasons,
        "authority": authority,
        "trust_tier": trust_tier if trust_tier is not None else source.get("trust_tier"),
        "descriptive_only": bool(descriptive_only),
        "is_actionable": False,
        "dependencies": _string_list(dependencies),
    }


def _financial_quality_capability(entry: Mapping[str, Any]) -> dict[str, Any]:
    qualified_evidence = entry.get("fundamental_quality_evidence")
    if isinstance(qualified_evidence, Mapping):
        return _capability(
            authority="fundamental_quality_evidence", record=qualified_evidence,
            dependencies=["canonical_financial_facts"],
        )
    quality = _as_mapping(entry.get("fundamental_quality"))
    models = _as_mapping(quality.get("models"))
    if not models:
        return _capability(authority="fundamental_quality", record=None,
                           absent_reason="fundamental_quality_contract_not_attached")
    source_states = sorted({str(_as_mapping(model).get("status") or
                                _as_mapping(model).get("result_state") or "unknown")
                            for model in models.values() if isinstance(model, Mapping)})
    # Mixed model outcomes are explicitly partial.  This does not score models; it prevents
    # one available submodel from hiding an unavailable or inapplicable one.
    preferred = source_states[0] if len(source_states) == 1 else "partial"
    result = _capability(authority="fundamental_quality", record=quality, status=preferred,
                         dependencies=["financial_canonical"])
    result["authority_statuses"] = source_states
    return result


def _identity(entry: Mapping[str, Any], ticker: str) -> tuple[dict[str, Any], list[str]]:
    entity_type = entry.get("entity_type")
    source = {"status": "unknown" if entity_type in (None, "unknown") else "available"}
    result = _capability(authority="financial_mapping.ticker_entity_profiles", record=source,
                         status=source["status"],
                         dependencies=["tickers.%s.entity_type" % ticker],
                         absent_reason="entity_type_missing")
    result["entity_type"] = entity_type if entity_type is not None else "unknown"
    if entity_type in (None, "unknown"):
        result["reason_codes"] = ["entity_type_unknown"]
    conflicts: list[str] = []
    brief = _as_mapping(entry.get("qualified_research_brief"))
    brief_type = brief.get("entity_type")
    if entity_type and brief_type and entity_type != brief_type:
        result["status"] = "blocked"
        result["reason_codes"] = sorted(set(result["reason_codes"] + ["entity_type_authority_conflict"]))
        conflicts.append("entity_type_authority_conflict")
    lanes = entry.get("analysis_lane_eligibility")
    quality_growth = next(
        (lane for lane in lanes if isinstance(lane, Mapping) and lane.get("lane") == "quality_growth"),
        None,
    ) if isinstance(lanes, list) else None
    result["analysis_archetype_qualification"] = _capability(
        authority="analysis_lane_eligibility.quality_growth", record=quality_growth,
        status=_as_mapping(quality_growth).get("status"), dependencies=["entity_type"],
        absent_reason="analysis_lane_eligibility_not_attached",
    )
    return result, conflicts


def build_ticker_capability_matrix(
    ticker: str,
    entry: Mapping[str, Any] | None,
    *,
    market_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the retained Producer decisions for one ticker, with no I/O or analysis.

    An absent optional contract is a valid fail-closed answer: it becomes explicitly
    unavailable rather than being recomputed by this attachment.  The projection is
    therefore deterministic for equal entry and authority inputs.
    """
    item = _as_mapping(entry)
    authority = _as_mapping(market_authority)
    ticker = str(ticker).upper()
    identity, conflicts = _identity(item, ticker)

    canonical = item.get("canonical_financial_facts")
    if canonical is None:
        canonical = item.get("financial_canonical")
    historical_decision = _as_mapping(item.get("historical_decision_analysis"))
    historical_eligibility = _as_mapping(historical_decision.get("eligibility"))
    qmo = item.get("qualified_market_observations")
    qmo_record = _as_mapping(qmo)
    qmo_available = qmo_record.get("status") == "available"
    qmo_descriptive = qmo_available and qmo_record.get("descriptive_only") is True
    research = item.get("qualified_research_brief")
    pillar_projection = item.get("research_financial_fact_projection")
    pillar_projection_record = _as_mapping(pillar_projection)
    portfolio_raw = item.get("portfolio_risk_analysis")
    portfolio = _as_mapping(portfolio_raw)
    allocation_raw = portfolio.get("allocation_eligibility") if isinstance(portfolio_raw, Mapping) else None
    portfolio_fit_raw = (_as_mapping(portfolio.get("portfolio_considerations")).get("actual_portfolio_fit")
                         if isinstance(portfolio_raw, Mapping) else None)
    allocation = _as_mapping(allocation_raw)
    portfolio_fit = _as_mapping(portfolio_fit_raw)

    # Market gates are deliberately read from the global authority selection, never from
    # a provider-adjusted observation.  That keeps the two namespaces visibly separate.
    raw_state = authority.get("raw_price_authority_after_selection", authority.get("raw_price_authority"))
    raw_reasons = {
        "status": raw_state,
        "reason_codes": [authority.get("fiingroup_access_state"), authority.get("license_authority")],
    }
    generic_price = {
        "status": authority.get("generic_actionable_price_basis", "BLOCKED"),
        "reason_codes": ["generic_actionable_price_basis", authority.get("fiingroup_access_state")],
    }
    generic_volume = {
        "status": authority.get("generic_actionable_volume_basis", "BLOCKED"),
        "reason_codes": ["generic_actionable_volume_basis", authority.get("fiingroup_access_state")],
    }
    valuation = {
        "status": authority.get("historical_valuation_unlock", "BLOCKED"),
        "reason_codes": ["historical_valuation_unlock", authority.get("fiingroup_access_state")],
    }

    matrix = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "ticker": ticker,
        "identity": identity,
        "fundamental_data": {
            "canonical_financial_facts": _capability(
                authority="canonical_financial_facts", record=canonical,
                dependencies=["financial_canonical"], absent_reason="canonical_financial_facts_missing"),
            "financial_quality_analysis": _financial_quality_capability(item),
            "historical_fundamental_analysis": _capability(
                authority="historical_fundamental_brief", record=item.get("historical_fundamental_brief"),
                dependencies=["canonical_financial_facts"], absent_reason="historical_fundamental_brief_not_attached"),
            "historical_decision_analysis": _capability(
                authority="historical_decision_analysis", record=item.get("historical_decision_analysis"),
                status=historical_eligibility.get("status"), dependencies=["fundamental_quality", "historical_fundamental_brief"],
                absent_reason="historical_decision_analysis_not_attached"),
            "pillar_a_research_projection": _capability(
                authority="research_financial_fact_projection", record=pillar_projection,
                status=pillar_projection_record.get("status"),
                dependencies=["canonical_financial_facts", "entity_archetype"],
                absent_reason="pillar_a_research_projection_not_attached"),
        },
        "market_descriptive": {
            "provider_scoped_price_observations": _capability(
                authority="qualified_market_observations", record=qmo, status=qmo_record.get("status"),
                descriptive_only=qmo_descriptive, dependencies=["single_provider_ohlcv_window"],
                absent_reason="qualified_market_observations_not_attached"),
            "provider_scoped_adjusted_price_analytics": _capability(
                authority="qualified_market_observations", record=qmo, status=qmo_record.get("status"),
                descriptive_only=qmo_descriptive, dependencies=["provider_scoped_price_basis"],
                absent_reason="qualified_market_observations_not_attached"),
            "provider_scoped_volume_observations": _capability(
                authority="qualified_market_observations", record=qmo, status=qmo_record.get("status"),
                descriptive_only=qmo_descriptive, dependencies=["provider_scoped_volume_basis"],
                absent_reason="qualified_market_observations_not_attached"),
            "qualified_market_observations": _capability(
                authority="qualified_market_observations", record=qmo, status=qmo_record.get("status"),
                descriptive_only=qmo_descriptive, dependencies=["provider_scoped"],
                absent_reason="qualified_market_observations_not_attached"),
        },
        "market_actionable": {
            "raw_as_traded_price": _capability(authority="market_data_source_authority", record=raw_reasons,
                                                 status=raw_state, dependencies=["raw_ticker_session_history"]),
            "current_market_cap": _capability(authority="market_basis_capability_registry", record=generic_price,
                                                status=generic_price["status"], dependencies=["qualified_raw_price", "current_shares"]),
            "current_valuation": _capability(authority="market_basis_capability_registry", record=valuation,
                                               status=valuation["status"], dependencies=["qualified_raw_price", "valuation_identity"]),
            "generic_liquidity": _capability(authority="market_basis_capability_registry", record=generic_volume,
                                               status=generic_volume["status"], dependencies=["qualified_volume_scope"]),
            "tradability": _capability(authority="market_basis_capability_registry", record=generic_volume,
                                         status=generic_volume["status"], dependencies=["qualified_market_composition"]),
            "sizing": _capability(authority="portfolio_risk_analysis", record=allocation_raw,
                                   status=allocation.get("status"), dependencies=["generic_liquidity", "portfolio_context"],
                                   absent_reason="portfolio_risk_analysis_not_attached"),
            "execution_backtest_price_basis": _capability(authority="market_basis_capability_registry", record=generic_price,
                                                            status=generic_price["status"], dependencies=["qualified_raw_price", "qualified_volume_scope"]),
        },
        "research": {
            "pillar_a_historical_research_eligibility": _capability(
                authority="research_financial_fact_projection", record=pillar_projection,
                status=pillar_projection_record.get("status"),
                dependencies=["fully_qualified_corporate_metric_set"],
                absent_reason="pillar_a_research_projection_not_attached"),
            "qualified_research_brief": _capability(authority="qualified_research_brief", record=research,
                                                      status="available" if isinstance(research, Mapping) else None,
                                                      dependencies=["historical_decision_analysis"],
                                                      absent_reason="qualified_research_brief_not_attached"),
            "ai_grounded_research": _capability(authority="qualified_research_brief", record=research,
                                                  status="available" if isinstance(research, Mapping) else None,
                                                  dependencies=["qualified_research_brief", "ticker_capability_matrix"],
                                                  absent_reason="qualified_research_brief_not_attached"),
            "dashboard_research_presentation": _capability(authority="dashboard_research_panel", record=None,
                                                              dependencies=["dashboard_matrix_rendering"],
                                                              absent_reason="dashboard_matrix_rendering_deferred"),
        },
        "portfolio": {
            "portfolio_fit": _capability(authority="portfolio_risk_analysis", record=portfolio_fit_raw,
                                           status=portfolio_fit.get("status"), dependencies=["portfolio_context"],
                                           absent_reason="portfolio_risk_analysis_not_attached"),
            "allocation_eligibility": _capability(authority="portfolio_risk_analysis", record=allocation_raw,
                                                    status=allocation.get("status"), dependencies=["portfolio_context", "generic_liquidity"],
                                                    absent_reason="portfolio_risk_analysis_not_attached"),
        },
        "market_data_authority": {
            "market_data_track": authority.get("market_data_track", "WAITING_EXTERNAL_ACCESS"),
            "selected_source_id": authority.get("selected_source_id"),
            "fiingroup_access_state": authority.get("fiingroup_access_state"),
            "license_authority": authority.get("license_authority"),
            "dnse_market_data_access": authority.get("dnse_market_data_access"),
            "dnse_next_qualification_candidate": authority.get("dnse_next_qualification_candidate"),
            "fiingroup_fallback_candidate": authority.get("fiingroup_fallback_candidate"),
        },
        "conflicts": conflicts,
        "summary": {
            "trust_is_capability_specific": True,
            "overall_status": "mixed_capability",
            "is_actionable": False,
        },
        "is_actionable": False,
    }
    return matrix

TIERS: tuple[str, ...] = (
    "T0_informational",
    "T1_technical_display",
    "T2_historical_fundamental",
    "T3_distribution_event",
    "T4_market_dependent",
)


def _tier(eligible: bool, reason: str) -> dict[str, Any]:
    return {"eligible": bool(eligible), "reason": reason, "is_actionable": False}


def evaluate_ticker_capability(
    ticker: str,
    *,
    has_technical_coverage: bool,
    historical_fundamental_brief: Mapping[str, Any] | None,
    distribution_evidence: Mapping[str, Any] | None,
    price_basis_provenance: Mapping[str, Any] | None,
    current_shares_proven: bool,
) -> dict[str, Any]:
    """Pure. No I/O, no network, no database access. Returns
    {"schema_version", "ticker", "tiers": {tier_name: {"eligible", "reason",
    "is_actionable": False}}, "is_actionable": False}.
    """
    price_basis_provenance = price_basis_provenance if isinstance(price_basis_provenance, Mapping) else {}
    tiers: dict[str, dict[str, Any]] = {
        "T0_informational": _tier(True, "always eligible: profile/news/sector context only"),
        "T1_technical_display": _tier(
            has_technical_coverage,
            "OHLCV/technical coverage present; display and single-series pattern reading only, "
            "regardless of price or volume basis state" if has_technical_coverage
            else "no technical coverage retained for this ticker",
        ),
    }

    brief = historical_fundamental_brief if isinstance(historical_fundamental_brief, Mapping) else None
    brief_ok = bool(brief) and brief.get("status") == "available" and bool(brief.get("facts"))
    tiers["T2_historical_fundamental"] = _tier(
        brief_ok,
        "available historical_fundamental_brief with at least one qualified fact" if brief_ok
        else "no available historical_fundamental_brief with qualified facts for this ticker",
    )

    dist = distribution_evidence if isinstance(distribution_evidence, Mapping) else None
    event_count = 0
    if dist is not None:
        event_count = len(dist.get("cash_distributions") or []) + len(dist.get("non_cash_distributions") or [])
    dist_ok = bool(dist) and dist.get("coverage_status") == "available" and event_count > 0
    tiers["T3_distribution_event"] = _tier(
        dist_ok,
        f"{event_count} qualified distribution event(s), coverage_status=available" if dist_ok
        else "no qualified distribution event for this ticker",
    )

    price_ok = price_basis_provenance.get("is_actionable") is True
    volume_ok = price_basis_provenance.get("volume_basis_verified") is True
    shares_ok = current_shares_proven is True
    market_ok = price_ok and volume_ok and shares_ok
    blocking = [name for name, ok in (
        ("price_basis", price_ok), ("volume_basis", volume_ok), ("current_shares", shares_ok),
    ) if not ok]
    tiers["T4_market_dependent"] = _tier(
        market_ok,
        "price basis, volume basis, and current shares are all qualified through the trusted session" if market_ok
        else f"blocked on: {', '.join(blocking)}",
    )

    return {"schema_version": VERSION, "ticker": ticker, "tiers": tiers, "is_actionable": False}
