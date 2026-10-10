"""R5 governed model boundary and non-voting production consumption."""
import copy
import json

import pytest
import stocklookup_core.valuation.intrinsic_valuation as model

PERIOD = {"period": "2025", "period_type": "annual", "period_end": "2025-12-31"}
UNIT = {"currency": "VND", "scale": 1}


def assumption(name, value, case, unit=None):
    declared_unit, definition = model.ASSUMPTION_DEFINITIONS[name]
    row = dict(ticker="TEST", entity_family="corporate", valuation_session="2026-10-01",
               case=case, name=name, value=value, unit=declared_unit, semantic_definition=definition,
               forecast_period="2026", horizon="PERPETUITY" if name in {"wacc", "terminal_growth", "forecast_fcff", "growth_lower", "growth_upper"} else "SNAPSHOT_REALIZATION",
               source_class="GOVERNED_CONFIG", source_identity="owner:explicit:" + name,
               source_period="2025", derivation_method=None, fitness="READY", warnings=[], limitations=[], blocker_reason_codes=[])
    if declared_unit.startswith("MONEY"):
        row["monetary_basis"] = UNIT.copy()
    return row


def inputs():
    financial = {metric: dict(canonical_metric=metric, value=value, quality_state="available",
                             statement_scope="consolidated", period_identity=PERIOD.copy(), unit=UNIT.copy(),
                             source_identity="fact:" + metric) for metric, value in {
        "operating_cash_flow":100, "capital_expenditure":20, "total_debt":10, "cash_and_equivalents":5,
        "current_assets":100, "receivables":10, "inventory":20, "total_liabilities":50}.items()}
    sets = {}
    for method in model.IMPLEMENTED:
        sets[method] = {}
        for case, rate, growth, fcff, ratio in [("BEAR", .12, .01, 60, .5), ("BASE", .10, .02, 80, .75), ("BULL", .08, .03, 100, 1)]:
            values = dict(wacc=rate, terminal_growth=growth, forecast_fcff=fcff,
                          cash_realization_ratio=ratio, receivables_realization_ratio=ratio,
                          inventory_realization_ratio=ratio, growth_lower=-.20, growth_upper=.07)
            sets[method][case] = [assumption(name, values[name], case) for name in model.REQUIRED_ASSUMPTIONS[method]]
    return dict(ticker="TEST", entity_family="corporate", valuation_session="2026-10-01", financial=financial,
                share_count={"value":10,"semantics":"period_end","period_identity":PERIOD.copy(),
                             "statement_scope":"consolidated","source_identity":"shares:explicit","fitness":"READY"},
                price_input={"value":100,"session":"2026-10-01","source_identity":"price:retained","unit":UNIT.copy(),
                             "fitness":"READY","share_basis_identity":"shares:explicit"}, assumption_sets=sets)


def test_supported_models_preserve_separate_conditional_cases_and_bridge():
    result = model.build_current_scenario_valuation(inputs())
    fcff = result["methods"]["FCFF_DCF"]
    assert fcff["readiness"] == "READY"
    assert fcff["cases"]["BASE"]["enterprise_value"] == pytest.approx(1000)
    assert fcff["cases"]["BASE"]["equity_value"] == pytest.approx(995)
    assert fcff["cases"]["BASE"]["per_share_model_value"] == pytest.approx(99.5)
    assert result["methods"]["NET_NET"]["cases"]["BASE"]["per_share_model_value"] == pytest.approx(-2.375)
    assert len({c["case_identity"] for c in fcff["cases"].values()}) == 3
    assert len({c["assumption_set_identity"] for c in fcff["cases"].values()}) == 3
    assert fcff["sensitivity"]["state"] == "READY" and len(fcff["sensitivity"]["grid"]) == 27
    assert result["methods"]["REVERSE_FCFF"]["cases"]["BASE"]["readiness"] == "READY"
    assert "MODEL_IMPLICATION_NOT_FORECAST" in result["methods"]["REVERSE_FCFF"]["cases"]["BASE"]["limitations"]
    assert "not most likely" in result["case_definitions"]["BASE"]
    assert "fair_value" not in result and "target_price" not in result and "probability" not in result
    assert set(result["cross_method_dispersion"]) == {"FCFF_DCF", "NET_NET"}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, None, "invalid", {}, []])
def test_bad_assumptions_are_local_blockers_not_exceptions(value):
    data = inputs();data["assumption_sets"]["FCFF_DCF"]["BASE"][0]["value"] = value
    result = model.build_current_scenario_valuation(data)
    assert result["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"
    assert result["methods"]["NET_NET"]["readiness"] == "READY"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("rate", [.02, .01, 0, -.01])
def test_wacc_must_exceed_growth_and_be_positive(rate):
    data = inputs();next(r for r in data["assumption_sets"]["FCFF_DCF"]["BASE"] if r["name"] == "wacc")["value"] = rate
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"


@pytest.mark.parametrize("field", ["source_identity", "source_period", "forecast_period", "horizon", "semantic_definition"])
def test_assumption_provenance_and_semantics_are_mandatory(field):
    data = inputs();data["assumption_sets"]["FCFF_DCF"]["BASE"][0].pop(field)
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"


@pytest.mark.parametrize("fault", ["period", "scope", "unit", "lineage", "capex", "assets", "zero_shares", "weighted_shares", "share_period", "future_period"])
def test_financial_compatibility_and_denominator_economics(fault):
    data = inputs()
    if fault == "period":data["financial"]["operating_cash_flow"]["period_identity"]["period"] = "2024"
    if fault == "scope":data["financial"]["operating_cash_flow"]["statement_scope"] = "separate"
    if fault == "unit":data["financial"]["operating_cash_flow"]["unit"]["scale"] = "unknown"
    if fault == "lineage":data["financial"]["operating_cash_flow"].pop("source_identity")
    if fault == "capex":data["financial"]["capital_expenditure"]["value"] = -20
    if fault == "assets":data["financial"]["current_assets"]["value"] = 1
    if fault == "zero_shares":data["share_count"]["value"] = 0
    if fault == "weighted_shares":data["share_count"]["semantics"] = "basic"
    if fault == "share_period":data["share_count"]["period_identity"]["period"] = "2024"
    if fault == "future_period":data["financial"]["operating_cash_flow"]["period_identity"]["period_end"] = "2027-12-31"
    method = "NET_NET" if fault == "assets" else "FCFF_DCF"
    assert model.build_current_scenario_valuation(data)["methods"][method]["readiness"] == "BLOCKED"


@pytest.mark.parametrize("family", ["bank", "securities", "insurance", "finance_company"])
def test_financial_families_are_not_forced_through_ordinary_corporate_methods(family):
    data = inputs();data["entity_family"] = family
    result = model.build_current_scenario_valuation(data)
    assert all(result["methods"][m]["readiness"] == "NOT_APPLICABLE" for m in ("FCFF_DCF", "NET_NET", "RNAV", "SOTP", "REVERSE_FCFF"))
    assert result["methods"]["DDM"]["readiness"] == "BLOCKED"


def test_qualified_unimplemented_method_is_distinct_from_missing_evidence():
    data = inputs();metric = "qualified_equity_cash_flow"
    data["financial"][metric] = {**copy.deepcopy(data["financial"]["operating_cash_flow"]), "canonical_metric":metric}
    data["assumption_sets"]["FCFE"] = {case:[assumption("cost_of_equity", .1, case), assumption("forecast_fcfe", 60, case)] for case in model.CASES}
    result = model.build_current_scenario_valuation(data)
    assert result["methods"]["FCFE"]["readiness"] == "NOT_IMPLEMENTED_FOR_QUALIFIED_INPUTS"
    assert result["methods"]["FCFE"]["cases"]["BASE"]["per_share_model_value"] is None


def test_input_order_stability_and_no_input_mutation():
    data = inputs();frozen = copy.deepcopy(data)
    first = model.build_current_scenario_valuation(data)
    data["financial"] = dict(reversed(list(data["financial"].items())))
    for cases in data["assumption_sets"].values():
        for rows in cases.values():rows.reverse()
    assert first == model.build_current_scenario_valuation(data)
    assert frozen == inputs()


def test_planned_driver_cannot_adjust_forecasts_or_model_values():
    projection = model.build_current_scenario_valuation(inputs())
    context = {"context_identity":"driver:bound", "drivers":[{"event_identity":"event:planned", "event_type":"PROJECT_ANNOUNCEMENT",
               "status":"PLANNED", "known_dates":{"record_date":"2026-10-02","ex_date":None}, "direction":"UNKNOWN"}]}
    bound = model.bind_forward_driver_explanation(projection, context)
    assert bound["methods"] == projection["methods"]
    assert bound["forward_driver_explanation"]["numeric_adjustment"] == "NONE"
    assert bound["forward_driver_explanation"]["evidence"][0]["known_dates"]["ex_date"] is None


def test_prohibited_probability_field_cannot_become_a_claim():
    data = inputs();data["assumption_sets"]["FCFF_DCF"]["BASE"][0]["probability"] = .9
    result = model.build_current_scenario_valuation(data)
    assert result["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"
    assert '"probability"' not in json.dumps(result)



def test_derived_assumption_requires_formula_and_input_lineage():
    data = inputs();row = data["assumption_sets"]["FCFF_DCF"]["BASE"][0]
    row["source_class"] = "DERIVED_QUALIFIED_EVIDENCE"
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"


def test_price_share_mismatch_blocks_comparison_and_reverse_only():
    data = inputs();data["price_input"]["share_basis_identity"] = "another-share-basis"
    result = model.build_current_scenario_valuation(data)
    assert result["methods"]["FCFF_DCF"]["readiness"] == "READY"
    assert result["methods"]["FCFF_DCF"]["cases"]["BASE"]["current_price_comparison"]["state"] == "BLOCKED"
    assert result["methods"]["REVERSE_FCFF"]["readiness"] == "BLOCKED"


def test_canonical_producer_attach_preserves_every_relative_verdict():
    import canonical_daily_financial_v2_materialization as material
    kwargs = dict(engine_artifact={"records":{}}, raw_valuation_artifact={"records":{}},
                  product_tickers=["TEST"], requested_at="2026-10-01T16:00:00+07:00",
                  entity_applicability_artifact={"records":{"TEST":{"entity_class":"corporate","applicability_status":"RESOLVED"}}})
    before = material.build_evaluated_valuation_artifact(**kwargs)
    after = material.build_evaluated_valuation_artifact(**kwargs, decision_session="2026-10-01")
    projection = after["records"]["TEST"]["intrinsic_scenario_valuation"]
    assert projection["methods"]["FCFF_DCF"]["readiness"] == "BLOCKED"
    assert projection["assumption_config_identity"]
    stripped = {k:v for k,v in after["records"]["TEST"].items() if k != "intrinsic_scenario_valuation"}
    assert stripped == before["records"]["TEST"]
    assert before["artifact_identity"] != after["artifact_identity"]


def test_integrated_projection_does_not_vote_or_mutate_posture():
    import stocklookup_core.decision.integrated_investment_decision_product as integrated
    kwargs = dict(ticker="TEST", as_of_session="2026-10-01", tactical_record=None, financial_record=None,
                  relative_volume_record=None, market_sector_record=None)
    projection = model.build_current_scenario_valuation(inputs())
    before = integrated.build_ticker_integrated_decision(**kwargs, valuation_record={"methods":{}})
    after = integrated.build_ticker_integrated_decision(**kwargs, valuation_record={"methods":{},"intrinsic_scenario_valuation":projection})
    assert before["research_action_posture"] == after["research_action_posture"]
    assert before["decision_identity"] == after["decision_identity"]
    assert before["valuation_context_summary"] == after["valuation_context_summary"]
    cell = after["current_research_decision_input"]["dimensions"]["VALUATION"]
    assert cell["state"] == before["current_research_decision_input"]["dimensions"]["VALUATION"]["state"]
    assert cell["intrinsic_scenario_valuation"] == after["intrinsic_scenario_valuation"]
    assert after["evidence_axes"]["VALUATION"]["context"]["intrinsic_scenario_valuation"] == after["intrinsic_scenario_valuation"]



@pytest.mark.parametrize("field,value", [("source_class", {}), ("horizon", []), ("forecast_period", {}),
                                        ("limitations", 2), ("warnings", {}), ("unit", {})])
def test_malformed_assumption_metadata_is_a_blocker(field, value):
    data = inputs();data["assumption_sets"]["FCFF_DCF"]["BASE"][0][field] = value
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"



def test_retained_assumption_source_cannot_be_asserted_from_an_event_identity():
    data = inputs();row = data["assumption_sets"]["FCFF_DCF"]["BASE"][0]
    row["source_class"] = "QUALIFIED_RETAINED_EVIDENCE";row["source_identity"] = "event:planned"
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"


def test_identity_derivation_reuses_only_an_explicit_qualified_value_with_matching_semantics():
    data = inputs();row = data["assumption_sets"]["FCFF_DCF"]["BASE"][0]
    source = {k:v for k,v in row.items() if k in {"source_identity","ticker","entity_family","value","unit","semantic_definition","forecast_period","horizon","source_period","monetary_basis","fitness"}}
    source["source_identity"] = "qualified:forward-input"
    data["qualified_assumption_sources"] = {source["source_identity"]:source}
    row.update(source_class="DERIVED_QUALIFIED_EVIDENCE", derivation_method="QUALIFIED_VALUE_IDENTITY_V1", input_identities=[source["source_identity"]])
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "READY"
    row["value"] *= 2
    assert model.build_current_scenario_valuation(data)["methods"]["FCFF_DCF"]["cases"]["BASE"]["readiness"] == "BLOCKED"


def test_re_evaluated_valuation_consumer_preserves_verified_projection_locally():
    import stocklookup_core.valuation.current_research_valuation_context as valuation
    projection = model.build_current_scenario_valuation(inputs())
    kwargs = dict(ticker="TEST", feature_record=None, decision_session="2026-10-01")
    before = valuation.evaluate_ticker_valuation(**kwargs, valuation_record=None)
    after = valuation.evaluate_ticker_valuation(**kwargs, valuation_record={"intrinsic_scenario_valuation": projection})
    assert after.pop("intrinsic_scenario_valuation") == projection
    assert after == before
    projection["methods"]["FCFF_DCF"]["cases"]["BASE"]["per_share_model_value"] = 999
    invalid = valuation.evaluate_ticker_valuation(**kwargs, valuation_record={"intrinsic_scenario_valuation": projection})
    blocked = invalid.pop("intrinsic_scenario_valuation")
    assert "INTRINSIC_PROJECTION_IDENTITY_OR_BINDING_INVALID" in blocked["limitations"]
    assert all(m["conditional_per_share_range"] is None for m in blocked["methods"].values())
    assert invalid == before


def test_cross_ticker_or_session_projection_cannot_be_consumed():
    projection = model.build_current_scenario_valuation(inputs())
    for kwargs in ({"ticker":"OTHER"}, {"session":"2026-10-02"}):
        blocked = model.consume_current_projection(projection, **kwargs)
        assert not blocked["cross_method_dispersion"]
        assert "INTRINSIC_PROJECTION_IDENTITY_OR_BINDING_INVALID" in blocked["limitations"]


def test_declared_native_monetary_scale_is_retained_without_inference():
    data = inputs()
    for row in data["financial"].values():
        row["unit"]["scale"] = 1000000
    data["price_input"]["unit"]["scale"] = 1000000
    for cases in data["assumption_sets"].values():
        for rows in cases.values():
            for row in rows:
                if "monetary_basis" in row:
                    row["monetary_basis"]["scale"] = 1000000
    result = model.build_current_scenario_valuation(data)
    case = result["methods"]["FCFF_DCF"]["cases"]["BASE"]
    assert case["per_share_model_value"] == pytest.approx(99.5)
    assert case["monetary_basis"] == {"currency":"VND", "scale":1000000}
    assert case["output_unit"] == "DECLARED_NATIVE_MONETARY_BASIS_PER_SHARE"
    assert case["current_price_comparison"]["state"] == "READY"


def test_irrelevant_financial_units_and_order_do_not_change_price_comparison():
    data = inputs()
    before = model.build_current_scenario_valuation(data)
    data["financial"] = {"irrelevant": {"unit":{"currency":"USD", "scale":1}}, **data["financial"]}
    assert before == model.build_current_scenario_valuation(data)


@pytest.mark.parametrize("content", [None, "{bad-json", '{"contract_version":"wrong","assumption_sets":{}}'])
def test_missing_or_invalid_config_blocks_only_intrinsic_context(tmp_path, monkeypatch, content):
    import canonical_daily_financial_v2_materialization as material
    path = tmp_path / "governed.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    original = model.load_governed_assumption_config
    monkeypatch.setattr(model, "load_governed_assumption_config", lambda _:original(path))
    kwargs = dict(engine_artifact={"records":{}}, raw_valuation_artifact={"records":{}},
                  product_tickers=["TEST"], requested_at="2026-10-01T16:00:00+07:00",
                  entity_applicability_artifact={"records":{"TEST":{"entity_class":"corporate","applicability_status":"RESOLVED"}}})
    before = material.build_evaluated_valuation_artifact(**kwargs)
    after = material.build_evaluated_valuation_artifact(**kwargs, decision_session="2026-10-01")
    projection = after["records"]["TEST"].pop("intrinsic_scenario_valuation")
    assert after["records"] == before["records"]
    assert projection["methods"]["FCFF_DCF"]["readiness"] == "BLOCKED"
    assert "GOVERNED_ASSUMPTION_CONFIG_UNAVAILABLE_OR_INVALID" in projection["methods"]["FCFF_DCF"]["cases"]["BASE"]["reason_codes"]


def test_tampered_projection_with_malformed_family_fails_locally():
    projection = model.build_current_scenario_valuation(inputs())
    projection["entity_family"] = []
    assert not model.consume_current_projection(projection)["cross_method_dispersion"]


def test_invalid_config_identity_cannot_preserve_numeric_assumptions():
    import stocklookup_core.valuation.current_research_valuation_context as valuation
    result = valuation.attach_intrinsic_scenario_valuation({"TEST":{}}, {"TEST":inputs()},
        assumption_config_identity=model.ASSUMPTION_CONTRACT + ":INVALID:proof")
    projection = result["TEST"]["intrinsic_scenario_valuation"]
    assert not projection["cross_method_dispersion"]
    assert projection["methods"]["FCFF_DCF"]["readiness"] == "BLOCKED"


@pytest.mark.parametrize("conflict", ["different_value", "source_flag"])
def test_semantic_share_conflicts_never_select_a_denominator(conflict):
    row = dict(ticker="TEST", canonical_metric="shares_outstanding", period_end="2025-12-31",
               share_basis="PERIOD_END_OUTSTANDING", lineage_complete=True,
               research_semantic_state="RESEARCH_SEMANTIC_READY", normalized_candidate_value=10,
               native_period_label="2025", native_period_type="annual", statement_scope="consolidated",
               source_lineage={"fact_id": "shares:qualified"})
    entities = {"TEST": {"entity_class": "corporate", "applicability_status": "RESOLVED"}}
    def adapt(rows):
        return model.inputs_from_semantic_rows(rows, tickers={"TEST"}, session="2026-10-01", entities=entities)["TEST"]
    assert adapt([row, copy.deepcopy(row)])["share_count"]["value"] == 10
    other = copy.deepcopy(row)
    if conflict == "different_value":
        other["normalized_candidate_value"] = 20
    else:
        other["source_conflicts"] = ["SOURCE_CONFLICT"]
    assert adapt([row, other])["share_count"] == {}
    assert adapt([row, other]) == adapt([other, row])
