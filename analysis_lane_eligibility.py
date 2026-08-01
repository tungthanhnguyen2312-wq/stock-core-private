"""Phase 4B — Analysis Lane Schema and Eligibility Gates (MVP).

Pure, deterministic eligibility evaluation for the five Phase 4A analytical lanes
(quality_growth, income_defensive, structural_catalyst, distressed_high_risk,
blocked_avoid), gated exclusively on existing Producer data-truth contracts, per:
operations-review/phase_4a_analysis_engine_market_scan_v2_design_20260801T072613Z.md

Scope discipline (Phase 4B task): this module implements ONLY the schema and
eligibility-gate layer. It does not rank tickers, generate facts/catalysts/
scenarios, compute scores, read or write analysis_bundle.json or any database,
or call into export_ai_bundle.py. Callers pass already-extracted per-contract
dicts in; nothing here parses a raw bundle or touches I/O. `is_actionable` is
hardcoded False on every result -- this milestone produces eligibility gating,
never an investment signal.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

LANES: tuple[str, ...] = (
    "quality_growth",
    "income_defensive",
    "structural_catalyst",
    "distressed_high_risk",
    "blocked_avoid",
)

STATUSES: tuple[str, ...] = (
    "eligible_for_analysis",
    "insufficient_evidence",
    "blocked",
    "not_applicable",
)

# entity_type values confirmed to exist in stock-core-private/financial_mapping.py
# (ENTITY_TYPES = {"*", "unknown", "corporate", "bank", "securities", "insurance",
# "finance_company"}) that are NOT the generic corporate archetype. quality_growth's
# revenue/margin framing does not structurally apply to these without a dedicated
# sector-specific evidence contract (Phase 4A Section 7; out of scope here).
_NON_GENERIC_CORPORATE_ENTITY_TYPES = frozenset({"bank", "securities", "insurance", "finance_company"})

# earnings_anomaly.explanation_status values that count as a *resolved* explanation.
# Left empty on purpose: as of export_ai_bundle.py::build_earnings_anomaly_contract,
# every real explanation_status value ("insufficient_statement_detail", "not_applicable",
# "decomposition_available_unreconciled") is unresolved or not-yet-applicable -- there is
# currently no "explained" value. Any anomaly_observed ticker therefore blocks
# quality_growth today. This set exists so a future Producer-side resolved status can be
# recognized without changing this module's gate logic.
_RESOLVED_EARNINGS_EXPLANATION_STATUSES: frozenset[str] = frozenset()

# opportunity_ranking.dimensions.<dim>.state allowed values, per
# stock-core-private/... build_ticker_context.py::opportunity_ranking_contract validation.
_DIMENSION_STATE_ALLOWED = frozenset({
    "available", "limited", "partial", "unavailable", "unknown", "incomparable", "inapplicable", "blocked",
})

_SHARE_BASIS_BLOCKING_STATUSES = frozenset({"incomparable", "insufficient_identity", "not_available"})


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _lane_result(
    lane: str,
    status: str,
    *,
    blocking_reasons: Sequence[str] = (),
    data_warnings: Sequence[str] = (),
    required_evidence: Sequence[str] = (),
    supporting_paths: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    if lane not in LANES:
        raise ValueError(f"Unknown lane: {lane!r}")
    if status not in STATUSES:
        raise ValueError(f"Unknown lane status: {status!r}")
    return {
        "lane": lane,
        "status": status,
        "eligible": status == "eligible_for_analysis",
        "blocking_reasons": list(blocking_reasons),
        "data_warnings": list(data_warnings),
        "required_evidence": list(required_evidence),
        "supporting_paths": list(supporting_paths),
        "limitations": list(limitations),
        "is_actionable": False,
    }


def _dimension_state(opportunity_ranking: Mapping[str, Any] | None, dimension: str) -> str | None:
    if not _is_mapping(opportunity_ranking):
        return None
    dimensions = opportunity_ranking.get("dimensions")
    if not _is_mapping(dimensions):
        return None
    dim = dimensions.get(dimension)
    if not _is_mapping(dim):
        return None
    state = dim.get("state")
    return state if state in _DIMENSION_STATE_ALLOWED else None


def _status_from_dimension_state(state: str | None) -> tuple[str, str]:
    """Map an opportunity_ranking dimension state to a lane status and blocking reason.
    Reason is '' for eligible_for_analysis/not_applicable (nothing is "blocking" there)."""
    if state is None:
        return "insufficient_evidence", "opportunity_ranking_dimension_state_unavailable"
    if state in ("available", "limited"):
        return "eligible_for_analysis", ""
    if state in ("partial", "unavailable", "unknown"):
        return "insufficient_evidence", f"opportunity_ranking_dimension_state:{state}"
    if state in ("blocked", "incomparable"):
        return "blocked", f"opportunity_ranking_dimension_state:{state}"
    if state == "inapplicable":
        return "not_applicable", ""
    return "insufficient_evidence", f"opportunity_ranking_dimension_state_unrecognized:{state}"


# ---------------------------------------------------------------------------
# Cross-cutting gates (Gate 1, 3, 7, 8, 6/9) -- shared across all five lanes
# ---------------------------------------------------------------------------

def _price_volume_basis_warnings(price_basis_provenance: Mapping[str, Any] | None, ticker: str) -> list[str]:
    """Gate 1: unknown/unverified price or volume basis blocks adjusted-return,
    liquidity, and backtest-style claims. price_basis_provenance is the single
    combined contract Producer's build_price_basis_contract already emits (one
    contract carries both price_basis and volume_basis, not two independent ones)."""
    path = f"tickers.{ticker}.price_basis_provenance"
    if not _is_mapping(price_basis_provenance):
        return [
            f"adjusted_return_claims_blocked:price_basis_provenance_missing:{path}",
            f"liquidity_claims_blocked:price_basis_provenance_missing:{path}",
            f"backtest_claims_blocked:price_basis_provenance_missing:{path}",
        ]
    price_basis = price_basis_provenance.get("price_basis")
    price_verified = price_basis_provenance.get("price_basis_verified") is True
    volume_basis = price_basis_provenance.get("volume_basis")
    volume_verified = price_basis_provenance.get("volume_basis_verified") is True

    warnings: list[str] = []
    if not price_verified or price_basis in (None, "unknown"):
        warnings.append(f"adjusted_return_claims_blocked:price_basis={price_basis!r}:{path}.price_basis")
    if not volume_verified or volume_basis in (None, "unknown"):
        warnings.append(f"liquidity_claims_blocked:volume_basis={volume_basis!r}:{path}.volume_basis")
    if warnings:
        warnings.append(f"backtest_claims_blocked:price_or_volume_basis_unverified:{path}")
    return warnings


def _valuation_comparability_warnings(valuation_namespaces: Mapping[str, Any] | None, ticker: str) -> list[str]:
    """Gate 3: incomparable valuation namespaces block direct valuation-change conclusions."""
    path = f"tickers.{ticker}.valuation_namespaces.comparability.metrics"
    if not _is_mapping(valuation_namespaces):
        return ["valuation_change_claims_blocked:valuation_namespaces_not_provided_to_evaluator"]
    comparability = valuation_namespaces.get("comparability")
    metrics = comparability.get("metrics") if _is_mapping(comparability) else None
    if not _is_mapping(metrics):
        return ["valuation_change_claims_blocked:comparability_metrics_not_provided_to_evaluator"]
    warnings: list[str] = []
    for metric_name, metric in metrics.items():
        if _is_mapping(metric) and metric.get("status") != "comparable":
            warnings.append(f"valuation_change_claims_blocked:{metric_name}:{metric.get('status')}:{path}.{metric_name}")
    return warnings


def _ta_signal_warning(ta_signal_semantics: Mapping[str, Any] | None) -> str:
    """Gate 8: a missing TA result must not become a neutral or no-signal claim."""
    if not _is_mapping(ta_signal_semantics):
        return "ta_signal_semantics_not_provided_to_evaluator"
    if ta_signal_semantics.get("coverage_status") == "missing":
        return "ta_signal_missing:" + str(
            ta_signal_semantics.get("null_interpretation")
            or "null indicates absence from TA scan output, not a confirmed no-signal claim."
        )
    return "ta_signal_present_not_a_signal:" + str(
        ta_signal_semantics.get("presence_interpretation")
        or "presence indicates availability only, not an investment action."
    )


def _news_window_warning(news_window_semantics: Mapping[str, Any] | None) -> str:
    """Gate 7: zero mapped news must not become a confirmed no-news claim."""
    if not _is_mapping(news_window_semantics):
        return "news_window_semantics_not_provided_to_evaluator"
    if news_window_semantics.get("is_no_relevant_news_claim") is False:
        return "zero_or_partial_news_mapping_is_not_a_no_news_claim"
    return "news_window_semantics_present"


_STANDING_LIMITATIONS: tuple[str, ...] = (
    "risk_semantics, opportunity_ranking, ta_signal_semantics, and news_window_semantics are "
    "evidence-availability / fail-closed metadata, not investment signals; this evaluator's "
    "evidence-availability ordering must not be read as investment attractiveness "
    "(Phase 4A Principles 1 and 5; Phase 4B gates 6 and 9).",
)


# ---------------------------------------------------------------------------
# Per-lane evaluators
# ---------------------------------------------------------------------------

def evaluate_quality_growth(
    ticker: str,
    *,
    entity_type: str | None,
    financial_period_coverage: Mapping[str, Any] | None,
    earnings_anomaly: Mapping[str, Any] | None,
    opportunity_ranking: Mapping[str, Any] | None,
) -> dict[str, Any]:
    lane = "quality_growth"
    et_path = f"tickers.{ticker}.entity_type"
    fpc_path = f"tickers.{ticker}.financial_period_coverage"
    ea_path = f"tickers.{ticker}.earnings_anomaly"
    orank_path = f"tickers.{ticker}.opportunity_ranking.dimensions.financial_quality"

    if entity_type in (None, "unknown"):
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=["entity_type_unknown"],
            required_evidence=["confirmed corporate entity_type"],
            supporting_paths=[et_path],
            limitations=["entity_type is unknown/unclassified; corporate quality/growth framing is not confirmed applicable."],
        )
    if entity_type in _NON_GENERIC_CORPORATE_ENTITY_TYPES:
        return _lane_result(
            lane, "not_applicable",
            supporting_paths=[et_path],
            limitations=[
                f"entity_type={entity_type!r} is not the generic corporate archetype; revenue/margin "
                "quality-growth framing requires a sector-specific evidence contract not yet modeled "
                "(Phase 4A Section 7).",
            ],
        )

    if not _is_mapping(financial_period_coverage):
        return _lane_result(
            lane, "blocked",
            blocking_reasons=["financial_period_coverage_missing"],
            required_evidence=["financial_period_coverage"],
            supporting_paths=[fpc_path],
        )

    coverage_status = financial_period_coverage.get("coverage_status")
    if coverage_status == "incomparable":
        return _lane_result(
            lane, "blocked",
            blocking_reasons=["financial_period_coverage_incomparable"],
            supporting_paths=[f"{fpc_path}.coverage_status"],
            limitations=list(financial_period_coverage.get("limitations") or []),
        )
    if financial_period_coverage.get("latest_verified_period") is None:
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=["no_verified_financial_period"],
            required_evidence=["financial_period_coverage.latest_verified_period"],
            supporting_paths=[f"{fpc_path}.latest_verified_period", f"{fpc_path}.coverage_status"],
            limitations=list(financial_period_coverage.get("limitations") or []),
        )

    if not _is_mapping(earnings_anomaly):
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=["earnings_anomaly_data_missing"],
            required_evidence=["earnings_anomaly"],
            supporting_paths=[ea_path],
        )
    ea_status = earnings_anomaly.get("status")
    if ea_status == "anomaly_observed":
        explanation_status = earnings_anomaly.get("explanation_status")
        if explanation_status not in _RESOLVED_EARNINGS_EXPLANATION_STATUSES:
            return _lane_result(
                lane, "blocked",
                blocking_reasons=[f"unexplained_earnings_anomaly:{explanation_status}"],
                supporting_paths=[f"{ea_path}.status", f"{ea_path}.explanation_status"],
                limitations=list(earnings_anomaly.get("limitations") or []),
            )
    elif ea_status != "not_observed":
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=[f"earnings_anomaly_status_inconclusive:{ea_status}"],
            supporting_paths=[f"{ea_path}.status"],
        )

    state = _dimension_state(opportunity_ranking, "financial_quality")
    status, reason = _status_from_dimension_state(state)
    return _lane_result(
        lane, status,
        blocking_reasons=[reason] if reason else [],
        required_evidence=[] if status == "eligible_for_analysis" else ["opportunity_ranking.dimensions.financial_quality"],
        supporting_paths=[fpc_path, ea_path, orank_path],
    )


def evaluate_income_defensive(
    ticker: str,
    *,
    entity_type: str | None,
    risk_semantics: Mapping[str, Any] | None,
    share_basis_identities: Mapping[str, Any] | None,
    financial_period_coverage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Distribution/dividend evidence is not among the ten named Phase 4B input
    contracts, and this lane's purpose is fundamentally distribution-evidence-based
    (Phase 4A Section 3.2). It therefore can never reach eligible_for_analysis in this
    milestone; it always reports insufficient_evidence, while still surfacing the
    currently-available risk/share-basis/coverage gates for a future integration."""
    lane = "income_defensive"
    et_path = f"tickers.{ticker}.entity_type"
    rs_path = f"tickers.{ticker}.risk_semantics"
    sbi_path = f"tickers.{ticker}.share_basis_identities"
    fpc_path = f"tickers.{ticker}.financial_period_coverage"

    blocking_reasons = ["distribution_evidence_contract_not_available_to_this_evaluator"]
    data_warnings: list[str] = []
    limitations = [
        "income_defensive eligibility fundamentally requires distribution/dividend evidence, which "
        "is not among the ten Phase 4A/4B named input contracts; this result never reaches "
        "eligible_for_analysis in this milestone.",
    ]

    if entity_type in (None, "unknown"):
        data_warnings.append("entity_type_unknown")

    if risk_semantics is None:
        data_warnings.append("risk_semantics_unavailable")
    elif not _is_mapping(risk_semantics):
        data_warnings.append("risk_semantics_malformed")
    else:
        data_warnings.append("risk_semantics_present_no_safety_threshold_defined_yet")
        limitations.append(
            "risk_semantics.score_value polarity is higher_is_safer (legacy field name 'risk' must "
            "not be read as higher-means-more-risk); no safety threshold is defined yet, so this "
            "evaluator does not classify the numeric value.",
        )

    if not _is_mapping(share_basis_identities):
        data_warnings.append("share_basis_identities_missing")
    else:
        pairs = (share_basis_identities.get("comparability") or {}).get("pairs") or {}
        if _is_mapping(pairs):
            for pair_name, pair in pairs.items():
                if _is_mapping(pair) and pair.get("status") in _SHARE_BASIS_BLOCKING_STATUSES:
                    blocking_reasons.append(f"share_basis_identity_{pair.get('status')}:{pair_name}")

    if not _is_mapping(financial_period_coverage):
        data_warnings.append("financial_period_coverage_missing")

    return _lane_result(
        lane, "insufficient_evidence",
        blocking_reasons=blocking_reasons,
        data_warnings=data_warnings,
        required_evidence=["corporate_action_distribution_evidence (not a named input to this milestone)"],
        supporting_paths=[et_path, rs_path, sbi_path, fpc_path],
        limitations=limitations,
    )


def evaluate_structural_catalyst(
    ticker: str,
    *,
    opportunity_ranking: Mapping[str, Any] | None,
) -> dict[str, Any]:
    lane = "structural_catalyst"
    orank_path = f"tickers.{ticker}.opportunity_ranking"
    dim_path = f"{orank_path}.dimensions.catalyst_evidence"

    if not _is_mapping(opportunity_ranking):
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=["opportunity_ranking_unavailable"],
            required_evidence=["opportunity_ranking"],
            supporting_paths=[orank_path],
        )
    if opportunity_ranking.get("status") == "unknown":
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=[f"opportunity_ranking_status_unknown:{opportunity_ranking.get('reason')}"],
            required_evidence=["opportunity_ranking"],
            supporting_paths=[f"{orank_path}.status"],
        )

    state = _dimension_state(opportunity_ranking, "catalyst_evidence")
    status, reason = _status_from_dimension_state(state)
    return _lane_result(
        lane, status,
        blocking_reasons=[reason] if reason else [],
        required_evidence=[] if status == "eligible_for_analysis" else ["opportunity_ranking.dimensions.catalyst_evidence"],
        supporting_paths=[dim_path],
        limitations=[
            "Catalyst *evidence-availability* only; naming or tagging an actual catalyst against "
            "the Phase 4A Section 5 taxonomy is a separate, not-yet-implemented step.",
        ],
    )


def evaluate_distressed_high_risk(
    ticker: str,
    *,
    earnings_anomaly: Mapping[str, Any] | None,
    financial_period_coverage: Mapping[str, Any] | None,
    risk_semantics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    lane = "distressed_high_risk"
    ea_path = f"tickers.{ticker}.earnings_anomaly"
    fpc_path = f"tickers.{ticker}.financial_period_coverage"
    rs_path = f"tickers.{ticker}.risk_semantics"

    triggers: list[str] = []
    paths: list[str] = []

    if _is_mapping(earnings_anomaly) and earnings_anomaly.get("status") == "anomaly_observed":
        triggers.append("unresolved_earnings_anomaly")
        paths.append(f"{ea_path}.status")

    if _is_mapping(financial_period_coverage):
        cs = financial_period_coverage.get("coverage_status")
        if cs in ("unavailable", "incomparable"):
            triggers.append(f"financial_period_coverage_status:{cs}")
            paths.append(f"{fpc_path}.coverage_status")

    data_warnings: list[str] = []
    limitations: list[str] = []
    if risk_semantics is None:
        data_warnings.append("risk_semantics_unavailable_not_used_as_trigger")
    elif _is_mapping(risk_semantics):
        paths.append(f"{rs_path}.score_value")
        data_warnings.append(
            "risk_semantics present but no safety threshold is defined in this milestone; not used "
            "to trigger or exclude this lane.",
        )
        limitations.append(
            "risk_semantics.score_value polarity is higher_is_safer (legacy field name 'risk' must "
            "not be read as higher-means-more-risk).",
        )

    if triggers:
        return _lane_result(
            lane, "eligible_for_analysis",
            supporting_paths=paths,
            data_warnings=data_warnings,
            limitations=limitations,
        )

    if not _is_mapping(earnings_anomaly) and not _is_mapping(financial_period_coverage):
        return _lane_result(
            lane, "insufficient_evidence",
            blocking_reasons=["earnings_anomaly_and_financial_period_coverage_both_missing"],
            required_evidence=["earnings_anomaly", "financial_period_coverage"],
            supporting_paths=[ea_path, fpc_path],
            data_warnings=data_warnings,
        )

    return _lane_result(
        lane, "insufficient_evidence",
        blocking_reasons=["no_evidenced_stress_signal_found"],
        supporting_paths=paths or [ea_path, fpc_path],
        data_warnings=data_warnings,
        limitations=limitations,
    )


def evaluate_blocked_avoid(
    ticker: str,
    *,
    entity_type: str | None,
    financial_period_coverage: Mapping[str, Any] | None,
    share_basis_identities: Mapping[str, Any] | None,
    valuation_namespaces: Mapping[str, Any] | None,
    opportunity_ranking: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fail-closed routing lane: triggers only on evidence insufficiency, never on a
    judgment about the company. `eligible=True` here means "correctly routed to
    blocked_avoid", not "this ticker is bad"."""
    lane = "blocked_avoid"
    triggers: list[str] = []
    paths: list[str] = []

    if entity_type in (None, "unknown"):
        triggers.append("entity_type_unknown")
        paths.append(f"tickers.{ticker}.entity_type")

    if not _is_mapping(financial_period_coverage) or financial_period_coverage.get("coverage_status") == "unavailable":
        triggers.append("financial_period_coverage_absent")
        paths.append(f"tickers.{ticker}.financial_period_coverage")

    if _is_mapping(share_basis_identities):
        values = [
            (share_basis_identities.get(k) or {}).get("value")
            for k in ("current_market", "financial_period_end", "weighted_average")
        ]
        sbi_all_null = all(v is None for v in values)
    else:
        sbi_all_null = True

    if _is_mapping(valuation_namespaces):
        live_metrics = (valuation_namespaces.get("live_vendor") or {}).get("metrics") or {}
        hist_metrics = (valuation_namespaces.get("historical_calculated") or {}).get("metrics") or {}
        all_values = [
            m.get("value") for m in list(live_metrics.values()) + list(hist_metrics.values())
            if _is_mapping(m)
        ]
        vns_unavailable = len(all_values) == 0 or all(v is None for v in all_values)
    else:
        vns_unavailable = True

    if sbi_all_null and vns_unavailable:
        triggers.append("share_basis_and_valuation_namespaces_both_unavailable")
        paths.append(f"tickers.{ticker}.share_basis_identities")
        paths.append(f"tickers.{ticker}.valuation_namespaces")

    if not _is_mapping(opportunity_ranking) or opportunity_ranking.get("status") == "unknown":
        triggers.append("opportunity_ranking_status_unknown_or_missing")
        paths.append(f"tickers.{ticker}.opportunity_ranking")

    if triggers:
        return _lane_result(
            lane, "eligible_for_analysis",
            supporting_paths=paths,
            data_warnings=[f"blocked_avoid_trigger:{t}" for t in triggers],
            limitations=[
                "blocked_avoid membership reflects evidence insufficiency, not a judgment on the "
                "underlying company; a caller integrating this evaluator should treat blocked_avoid "
                "eligibility as overriding membership in the other four lanes for the same "
                "ticker/cutoff -- this pure per-lane evaluator does not enforce that override itself.",
            ],
        )
    return _lane_result(lane, "not_applicable", supporting_paths=paths)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def evaluate_ticker_lanes(
    ticker: str,
    *,
    entity_type: str | None = None,
    financial_period_coverage: Mapping[str, Any] | None = None,
    valuation_namespaces: Mapping[str, Any] | None = None,
    share_basis_identities: Mapping[str, Any] | None = None,
    earnings_anomaly: Mapping[str, Any] | None = None,
    risk_semantics: Mapping[str, Any] | None = None,
    opportunity_ranking: Mapping[str, Any] | None = None,
    ta_signal_semantics: Mapping[str, Any] | None = None,
    news_window_semantics: Mapping[str, Any] | None = None,
    price_basis_provenance: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate all five Phase 4A analytical lanes for one ticker at one cutoff.

    Every keyword argument is an already-extracted contract dict (or None) matching
    the ten named Producer contracts: financial_period_coverage, valuation_namespaces,
    share_basis_identities, earnings_anomaly, risk_semantics, opportunity_ranking,
    ta_signal_semantics, news_window_semantics (the object nested at
    tickers[ticker].news_related.news_window_semantics), and price_basis_provenance
    (the single combined price/volume-basis contract Producer's build_price_basis_contract
    already emits). entity_type is the existing per-ticker classification field.

    This function does not parse a raw bundle, read any file, or perform I/O -- callers
    are responsible for extracting these values from wherever they live in an actual
    analysis_bundle.json (out of scope for this schema/gates-only milestone).

    Returns a list of five lane-result dicts (see LANES), each with: lane, status,
    eligible, blocking_reasons, data_warnings, required_evidence, supporting_paths,
    limitations, is_actionable (always False).

    Deterministic: identical inputs always produce identical output; no randomness,
    clock, or I/O of any kind.
    """
    cross_cutting_warnings = list(_price_volume_basis_warnings(price_basis_provenance, ticker))
    cross_cutting_warnings.extend(_valuation_comparability_warnings(valuation_namespaces, ticker))
    cross_cutting_warnings.append(_ta_signal_warning(ta_signal_semantics))
    cross_cutting_warnings.append(_news_window_warning(news_window_semantics))

    results = [
        evaluate_quality_growth(
            ticker,
            entity_type=entity_type,
            financial_period_coverage=financial_period_coverage,
            earnings_anomaly=earnings_anomaly,
            opportunity_ranking=opportunity_ranking,
        ),
        evaluate_income_defensive(
            ticker,
            entity_type=entity_type,
            risk_semantics=risk_semantics,
            share_basis_identities=share_basis_identities,
            financial_period_coverage=financial_period_coverage,
        ),
        evaluate_structural_catalyst(
            ticker,
            opportunity_ranking=opportunity_ranking,
        ),
        evaluate_distressed_high_risk(
            ticker,
            earnings_anomaly=earnings_anomaly,
            financial_period_coverage=financial_period_coverage,
            risk_semantics=risk_semantics,
        ),
        evaluate_blocked_avoid(
            ticker,
            entity_type=entity_type,
            financial_period_coverage=financial_period_coverage,
            share_basis_identities=share_basis_identities,
            valuation_namespaces=valuation_namespaces,
            opportunity_ranking=opportunity_ranking,
        ),
    ]

    for result in results:
        result["data_warnings"] = list(result["data_warnings"]) + cross_cutting_warnings
        result["limitations"] = list(result["limitations"]) + list(_STANDING_LIMITATIONS)
        result["is_actionable"] = False

    return results
