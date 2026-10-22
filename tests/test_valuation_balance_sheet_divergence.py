import copy

import pytest

import canonical_daily_financial_v2_materialization as material
from stocklookup_core.financial import financial_analysis_product_projection as projection
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.decision import integrated_investment_decision_product as decision
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery, _decision_card


SESSION = "2026-10-16"


def fixture(*, deterioration=False, sector=True, issuer="corporate"):
    records, values, sectors = {}, {}, {}
    for i in range(6):
        ticker = f"T{i}"
        features = {}
        source_values = {"cash_to_assets": .6-i*.1, "debt_to_assets": .1+i*.1,
            "debt_to_equity": .2+i*.1, "pbt_margin": .1, "net_margin": .1,
            "gross_margin": .2, "debt_to_equity_direction": .1 if deterioration and i == 0 else -.1,
            "equity_to_assets_direction": .02}
        for fid,value in source_values.items():
            flow = fid in {"pbt_margin", "net_margin", "gross_margin"}
            provider, sha = ("KBS", "income:sha") if flow else ("VCI", "balance:sha")
            periods = ["2026-Q1", "2026-Q1"]
            if fid.endswith("direction"):
                periods = ["2025-Q1", "2025-Q1"] + periods
            features[fid] = {"feature_id": fid, "value": value, "fitness": "READY", "method": fid+"/fixture",
                "growth_basis": "POINT_IN_TIME_YOY" if fid.endswith("direction") else None,
                "period_identity": periods, "scope": ["consolidated"], "currency": None, "scale": None,
                "period_semantics": ["STANDALONE_QUARTER" if flow else "POINT_IN_TIME_BALANCE_SHEET"],
                "provider_source_provenance": [{"provider": provider, "source_sha256": sha,
                    "fact_id": f"{ticker}:{fid}:{n}", "source_file": "fixture"} for n in range(len(periods))],
                "reason_codes": [], "warnings": []}
        records[ticker] = {"ticker": ticker, "issuer_type": issuer, "features": features, "states": {},
            "history_context": {}, "current_research_ready": True, "source_identities": {}}
        basis = {"contract_version": "monetary_basis_contract/v1", "currency": "VND", "native_scale": "units",
            "normalized_unit": "VND", "multiplier_to_vnd": 1, "basis_status": "RESEARCH_CONTRACT_QUALIFIED", "basis_source": "fixture"}
        pb = {"method_id": valuation.PB_CURRENT_RESEARCH, "status": "RESEARCH_USABLE", "value": .5+i*.3,
            "applicability": "APPLICABLE", "statement_scope": "consolidated", "share_basis": valuation.CURRENT_SHARE_RESEARCH_PROXY,
            "period_basis": "POINT_IN_TIME_BALANCE_SHEET", "book_period": "2026-Q1", "input_periods": ["2026-Q1"],
            "equity_definition": "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
            "equity_monetary_basis": basis, "market_cap_monetary_basis": basis,
            "equity_lineage": {"provider": "VCI", "source_sha256": "balance:sha", "source_file": "fixture"},
            "ttm_compatibility_class": "fixture:consolidated", "limitations": ["NCI_NOT_DEDUCTED"]}
        values[ticker] = {"entity_class": issuer, "methods": {valuation.PB_CURRENT_RESEARCH: pb},
            "share_basis": valuation.CURRENT_SHARE_RESEARCH_PROXY}
        if sector:
            sectors[ticker] = "Retained sector"
    engine = {"contract_version": projection.ENGINE_CONTRACT, "records": records}
    engine.update(projection._identity(engine))
    product = projection.build_product_projection(financial_context=engine, product_tickers=list(records), requested_at="fixed")
    wrapper = {"contract_version": material.CONTRACT_VERSION, "decision_session": SESSION,
        "financial_analysis_product": product, "financial_content_identity": product["artifact_identity"],
        "financial_v2_engine_identity": engine["artifact_identity"],
        "engine_fundamental_peer_context": valuation.attach_engine_fundamental_peers(records, industry_by_ticker=sectors)}
    wrapper.update(material._identity(wrapper))
    evaluated = {"contract_version": material.CONTRACT_VERSION, "records": values,
        "source_valuation_identity": "raw:fixture", "source_financial_v2_identity": engine["artifact_identity"]}
    evaluated.update(material._identity(evaluated))
    raw = {"artifact_identity": "raw:fixture", "valuation_session": SESSION}
    return evaluated, wrapper, sectors, raw


def run(evaluated, wrapper, sectors, raw):
    return material.attach_balance_sheet_divergence(evaluated, financial_materialization=wrapper,
        industry_by_ticker=sectors, decision_session=SESSION, raw_valuation_artifact=raw)[valuation.DIVERGENCE_MEMBER]


def test_financially_supported_discount_and_real_delivery_without_policy_change():
    evaluated, wrapper, sectors, raw = fixture()
    saved = copy.deepcopy(evaluated["records"])
    before = decision.build_artifact(session=SESSION, requested_at=SESSION+"T16:00:00+07:00",
        technical_structure_artifact={"records": {}}, current_valuation_artifact=evaluated,
        financial_analysis_artifact=wrapper["financial_analysis_product"], financial_peer_materialization_artifact=wrapper)
    context = run(evaluated, wrapper, sectors, raw)
    assert evaluated["records"] == saved
    subject = context["records"]["T0"]
    assert subject["assessment"] == "LOW_PB_WITH_FINANCIAL_SUPPORT"
    assert subject["valuation"]["peer_context"]["peer_count"] == 6
    assert subject["valid_paired_comparisons"] == 8
    assert subject["valuation"]["history"]["status"] == "UNKNOWN"
    assert subject["financial_measures"]["same_provider_roe_avg_equity"]["status"] == "UNKNOWN"
    after = decision.build_artifact(session=SESSION, requested_at=SESSION+"T16:00:00+07:00",
        technical_structure_artifact={"records": {}}, current_valuation_artifact=evaluated,
        financial_analysis_artifact=wrapper["financial_analysis_product"], financial_peer_materialization_artifact=wrapper)
    record = after["records"]["T0"]
    for key in ("research_action_posture", "fundamental_state", "fundamental_decision_policy_version", "evidence_axis_coherence"):
        assert record[key] == before["records"]["T0"][key]
    delivered = project_integrated_decision_for_ai_delivery(record)
    expected = record["valuation_balance_sheet_divergence"]
    assert delivered["valuation_balance_sheet_divergence"] == expected
    assert delivered["current_research_decision_input"]["dimensions"]["VALUATION"]["balance_sheet_divergence"] == expected
    assert delivered["evidence_axes"]["VALUATION"]["context"]["balance_sheet_divergence"] == expected
    assert _decision_card("T0", record, None, source_session=SESSION)["valuation"]["balance_sheet_divergence"] == expected
    from stocklookup_core.decision import current_research_decision_packet as packet
    from stocklookup_core.decision.current_opportunity_prioritization import content_identity as opportunity_identity
    opportunity = {"contract_version": "current_opportunity_prioritization/v1", "research_session": SESSION,
        "records": {"T0": {"ticker": "T0", "entry_action": "WAIT", "priority_tier": "MONITOR"}}}
    opportunity.update(opportunity_identity(opportunity))
    built_packet = packet.build_artifact(opportunity=opportunity, integrated_decision=after)
    assert built_packet["records"]["T0"]["components"]["valuation_balance_sheet_divergence"] == expected
    assert "NCI_NOT_DEDUCTED" in expected["limitations"] and not expected["is_actionable"]


def test_low_valuation_with_deterioration_is_warning_not_proof():
    result = run(*fixture(deterioration=True))["records"]["T0"]
    assert result["assessment"] == "LOW_PB_WITH_VALUE_TRAP_WARNINGS"
    assert any(e["observation"] == "BALANCE_SHEET_DETERIORATION_YOY" for e in result["contradicting_evidence"])
    assert result["conditions_to_reassess"] and result["supporting_evidence"]
    assert not result["is_actionable"]


@pytest.mark.parametrize("change,reason", [("period", "FINANCIAL_PERIOD_DIFFERS_FROM_PB_BOOK_PERIOD"),
    ("scope", "FINANCIAL_SCOPE_DIFFERS_FROM_PB_OR_UNKNOWN"),
    ("source", "BALANCE_SHEET_SOURCE_NOT_BOUND_TO_PB_EQUITY"),
    ("currency", "KNOWN_REPORTING_CURRENCY_DIFFERS"),
    ("semantics", "FINANCIAL_METHOD_OR_PERIOD_SEMANTICS_UNPROVEN")])
def test_independent_invalid_measure_is_excluded_without_erasing_other_methods(change, reason):
    evaluated, wrapper, sectors, raw = fixture()
    compact = wrapper["financial_analysis_product"]["records"]["T0"]
    source = compact["feature_fitness"]["cash_to_assets"]["source_feature_context"]
    if change == "period": source["period_identity"] = ["2026-Q2"]
    if change == "scope": source["scope"] = ["unknown"]
    if change == "source": source["source_fact_refs"][0]["source_sha256"] = "other"
    if change == "currency": source["currency"] = "USD"
    if change == "semantics": source["period_semantics"] = ["UNKNOWN_DURATION"]
    product = wrapper["financial_analysis_product"]
    product.update(projection._identity(product))
    wrapper["financial_content_identity"] = product["artifact_identity"]
    wrapper.update(material._identity(wrapper))
    result = run(evaluated, wrapper, sectors, raw)["records"]["T0"]
    assert reason in result["financial_measures"]["cash_to_assets"]["reason_codes"]
    assert result["financial_measures"]["cash_to_assets"]["status"] == "UNKNOWN"
    assert result["financial_measures"]["debt_to_assets"]["status"] == "AVAILABLE"
    assert result["valid_paired_comparisons"] == 7


@pytest.mark.parametrize("issuer", ["bank", "securities", "insurance", "finance_company", "unknown"])
def test_no_corporate_inference_for_specialist_or_unknown_issuer(issuer):
    result = run(*fixture(issuer=issuer))["records"]["T0"]
    assert result["status"] == ("UNKNOWN" if issuer == "unknown" else "NOT_APPLICABLE")
    assert result["valid_paired_comparisons"] == 0


def test_missing_sector_never_falls_back_to_whole_market_pb():
    result = run(*fixture(sector=False))["records"]["T0"]
    assert result["status"] == "UNKNOWN"
    assert "RETAINED_SECTOR_LABEL_ABSENT" in result["material_gaps"]["valuation"]


@pytest.mark.parametrize("change", ["tamper", "session", "source", "financial", "financial_content"])
def test_source_binding_fails_closed_without_promoting_or_recomputing(change):
    evaluated, wrapper, sectors, raw = fixture()
    run(evaluated, wrapper, sectors, raw)
    product = wrapper["financial_analysis_product"]
    if change == "tamper": evaluated[valuation.DIVERGENCE_MEMBER]["records"]["T0"]["assessment"] = "fake"
    if change == "source": evaluated["source_valuation_identity"] = "other"
    if change == "financial": product = {**product, "artifact_identity": "other"}
    if change == "financial_content":
        product = copy.deepcopy(product)
        product["records"]["T0"]["current_research_ready"] = False
    result = valuation.verified_divergence_records(evaluated, product, "2026-10-15" if change == "session" else SESSION)
    assert result["T0"]["assessment"] == "UNKNOWN"
    assert result["T0"]["reason_codes"] == ["DIVERGENCE_SOURCE_BINDING_INVALID"]


def test_session_binding_refuses_cross_session_relabel():
    evaluated, wrapper, sectors, raw = fixture()
    with pytest.raises(ValueError, match="SESSION_BINDING"):
        run(evaluated, wrapper, sectors, {**raw, "valuation_session": "2026-10-15"})


@pytest.mark.parametrize("field,value", [("statement_scope", "unknown"), ("book_period", "2026-Q4"),
    ("share_basis", "UNAVAILABLE"), ("equity_definition", None), ("equity_definition", "UNKNOWN"), ("value", -1)])
def test_unqualified_pb_cannot_become_a_discount_hypothesis(field, value):
    evaluated, wrapper, sectors, raw = fixture()
    evaluated["records"]["T0"]["methods"][valuation.PB_CURRENT_RESEARCH][field] = value
    result = run(evaluated, wrapper, sectors, raw)["records"]["T0"]
    assert result["status"] == "UNKNOWN" and result["assessment"] == "UNKNOWN"
    assert result["valid_paired_comparisons"] == 0


@pytest.mark.parametrize("field,value", [("share_basis", valuation.EXACT_OR_QUALIFIED),
    ("equity_definition", "PARENT_ATTRIBUTABLE_EQUITY"), ("book_period", "2026-Q2")])
def test_distinct_pb_identities_never_enter_one_cohort(field, value):
    evaluated, wrapper, sectors, raw = fixture()
    evaluated["records"]["T0"]["methods"][valuation.PB_CURRENT_RESEARCH][field] = value
    if field == "book_period":
        evaluated["records"]["T0"]["methods"][valuation.PB_CURRENT_RESEARCH]["input_periods"] = [value]
    result = run(evaluated, wrapper, sectors, raw)["records"]["T0"]
    assert result["valuation"]["peer_context"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert result["valuation"]["peer_context"]["peer_count"] == 1
    assert result["assessment"] == "UNKNOWN"


def test_optional_missing_valuation_leg_does_not_block_financial_current_research():
    _, wrapper, sectors, _ = fixture()
    result = material.build_evaluated_valuation_artifact(engine_artifact={"records": {},
        "artifact_identity": wrapper["financial_v2_engine_identity"]}, raw_valuation_artifact=None,
        product_tickers=["T0"], requested_at=SESSION+"T16:00:00+07:00", decision_session=SESSION,
        divergence_financial_materialization=wrapper, divergence_industry_by_ticker=sectors)
    assert "T0" in result["records"]
    assert result[valuation.DIVERGENCE_MEMBER]["status"] == "UNKNOWN"
    record = valuation.verified_divergence_records(result, wrapper["financial_analysis_product"], SESSION)["T0"]
    assert record["assessment"] == "UNKNOWN"
    assert "DIVERGENCE_INPUT_BINDING_UNAVAILABLE" in record["reason_codes"]
