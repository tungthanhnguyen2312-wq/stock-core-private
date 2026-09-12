"""AI_HANDOFF_FRESHNESS_AND_SOURCE_CONVERGENCE_V1: ai_handoff_source_freshness_matrix.py
classifies already-resolved session evidence for AI-consumer source selection. It must
never emit an investment conclusion and must never assert a domain is current when the
underlying evidence says otherwise (stale market-flow/catalyst must not become current)."""
from __future__ import annotations

from ai_handoff_source_freshness_matrix import (
    FITNESS_CURRENT, FITNESS_PARTIAL, FITNESS_STALE, FITNESS_UNAVAILABLE,
    ENRICHMENT_EXTERNAL_MAY_BE_REQUIRED, ENRICHMENT_SUFFICIENT,
    build_source_freshness_matrix,
)

SESSION = "2026-09-11"


def _inputs(**overrides):
    base = {
        "descriptive": {"artifact_identity": "market_wide_current_descriptive_research:d1", "session": SESSION, "market_breadth": {}},
        "tactical": {"artifact_identity": "watchlist_tactical_entry_classifier:t1"},
        "screening": {"artifact_identity": "current_market_screening_opportunity_comparison_foundation:s1"},
        "fundamental": {"artifact_identity": "market_wide_current_fundamental_research:f1"},
        "valuation": {"artifact_identity": "market_wide_current_valuation:v1", "valuation_session": SESSION},
        "corporate_intelligence": {"artifact_identity": "market_wide_current_corporate_intelligence:c1", "session": SESSION},
        "catalyst": {"artifact_identity": "catalyst_event_research_context:cat1", "research_session": SESSION},
    }
    base.update(overrides)
    return base


def test_no_investment_conclusion_fields_present():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    dumped = str(matrix).lower()
    for forbidden in ("buy", "sell", "target_price", "probability", " sizing", "execution_instruction"):
        assert forbidden not in dumped


def test_exact_session_market_data_is_current():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["market_price_descriptive"]["fitness"] == FITNESS_CURRENT
    assert matrix["domains"]["market_price_descriptive"]["source_artifact_identity"] == "market_wide_current_descriptive_research:d1"


def test_exact_session_tactical_is_current():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["tactical"]["fitness"] == FITNESS_CURRENT


def test_fundamentals_never_falsely_called_exact_session():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    fundamentals = matrix["domains"]["fundamentals"]
    assert fundamentals["freshness"]["freshness_status"] == "historical"
    assert fundamentals["fitness"] == FITNESS_PARTIAL
    assert fundamentals["source_session_or_data_as_of"] is None


def test_catalyst_earlier_retained_state_preserved_as_stale_not_current():
    matrix = build_source_freshness_matrix(
        session=SESSION,
        inputs=_inputs(catalyst={"artifact_identity": "catalyst_event_research_context:cat1", "research_session": "2026-08-20"}),
        macro_context=None, macro_presentation_context=None, flow=None,
    )
    catalyst = matrix["domains"]["catalyst_event"]
    assert catalyst["fitness"] == FITNESS_STALE
    assert "EARLIER_RETAINED_CATALYST_CONTEXT" in catalyst["reason_codes"]
    assert catalyst["source_session_or_data_as_of"] == "2026-08-20"


def test_current_corporate_intelligence_preserved():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["corporate_intelligence"]["fitness"] == FITNESS_CURRENT


def test_stale_market_flow_does_not_become_current_when_absent():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    flow_domain = matrix["domains"]["market_flow_positioning"]
    assert flow_domain["fitness"] == FITNESS_UNAVAILABLE
    assert "NO_COMPATIBLE_CURRENT_MARKET_FLOW_ARTIFACT" in flow_domain["reason_codes"]
    assert flow_domain["qualified_dnse_value_flow"]["status"] == FITNESS_UNAVAILABLE


def test_qualified_same_session_market_flow_is_current_and_distinct_from_macro_foreign_flow():
    flow = {"artifact_identity": "current_market_flow_positioning:mf1", "session": SESSION}
    macro_ctx = {"status": "AVAILABLE", "foreign_flow": {"status": "UNAVAILABLE", "reason": "no data in snapshot"}}
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=macro_ctx, flow=flow,
    )
    flow_domain = matrix["domains"]["market_flow_positioning"]
    assert flow_domain["fitness"] == FITNESS_CURRENT
    assert flow_domain["qualified_dnse_value_flow"]["fitness"] == FITNESS_CURRENT
    assert flow_domain["macro_snapshot_foreign_flow"]["status"] == "UNAVAILABLE"
    assert flow_domain["proprietary_flow"]["status"] == FITNESS_UNAVAILABLE


def test_absent_proprietary_flow_always_reported_unavailable():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["market_flow_positioning"]["proprietary_flow"]["status"] == FITNESS_UNAVAILABLE


def test_macro_unavailable_when_neither_regime_nor_presentation_context_bound():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    macro = matrix["domains"]["macro"]
    assert macro["fitness"] == FITNESS_UNAVAILABLE
    assert macro["regime_evidence"]["status"] == "UNAVAILABLE"
    assert macro["presentation_context"]["status"] == "UNAVAILABLE"


def test_macro_available_from_presentation_context_alone_while_regime_still_unavailable():
    macro_presentation = {"status": "AVAILABLE", "artifact_identity": "macro_presentation_context:mp1", "snapshot_data_as_of": SESSION, "quality": {"current_count": 5}}
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=macro_presentation, flow=None,
    )
    macro = matrix["domains"]["macro"]
    assert macro["fitness"] == FITNESS_CURRENT
    assert macro["regime_evidence"]["status"] == "UNAVAILABLE"
    assert macro["presentation_context"]["status"] == "AVAILABLE"


def test_missing_optional_domain_does_not_raise():
    inputs = _inputs()
    del inputs["catalyst"]
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=inputs, macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["catalyst_event"]["fitness"] == FITNESS_UNAVAILABLE


def test_integrated_decision_current_when_bound():
    integrated_delivery = {"integrated_investment_decision_product": {"artifact_identity": "integrated_investment_decision_product:i1"}}
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
        integrated_delivery=integrated_delivery,
    )
    assert matrix["domains"]["integrated_decision"]["fitness"] == FITNESS_CURRENT


def test_integrated_decision_unavailable_when_absent():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    assert matrix["domains"]["integrated_decision"]["fitness"] == FITNESS_UNAVAILABLE


def test_online_enrichment_guidance_lists_unavailable_domains():
    matrix = build_source_freshness_matrix(
        session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None,
    )
    guidance = matrix["online_enrichment_guidance"]
    assert "macro" in guidance["domains_where_external_context_may_be_required"]
    assert "market_price_descriptive" in guidance["internally_sufficient_domains"]


def test_matrix_deterministic_across_reruns():
    one = build_source_freshness_matrix(session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None)
    two = build_source_freshness_matrix(session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None)
    assert one == two


def test_is_actionable_always_false():
    matrix = build_source_freshness_matrix(session=SESSION, inputs=_inputs(), macro_context=None, macro_presentation_context=None, flow=None)
    assert matrix["is_actionable"] is False
