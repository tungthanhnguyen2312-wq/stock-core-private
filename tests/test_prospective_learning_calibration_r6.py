"""R6 adversarial contracts; synthetic retained decisions only, never provider/Live Daily."""
import copy
import json

import pytest
import empirical_setup_outcome_calibration as cal
import prospective_decision_outcome_feedback as feedback
import prospective_decision_retention as retention
import prospective_decision_outcome_measurement as measurement
from test_empirical_setup_outcome_calibration import make_chain, make_snapshots, make_feedback_record, make_condition, _mature_observation
from test_prospective_decision_retention import _integrated, _price_snapshot, _bind
from tools.run_empirical_setup_outcome_calibration import retained_acceptance, _write_immutable


def observed(chain=None, prices=None):
    chain = chain or make_chain(22)
    prices = prices or {s: 100 + i for i, s in enumerate(chain)}
    snapshots = make_snapshots(chain, {"AAA": prices})
    record = make_feedback_record(ticker="AAA", t0_session=chain[0], posture="WAIT_FOR_CONFIRMATION", entry=100,
        invalidation_level=90, chain=chain, snapshots=snapshots)
    return record, chain, snapshots


def cohort_rows():
    rows = [_mature_observation(f"T{n}", f"2026-01-{s+1:02d}") for s in range(10) for n in range(5)]
    for row in rows:
        row["feedback_taxonomy"] = {"label": "FALSE_POSITIVE_BREAKOUT"}
    return rows


def t5_cohort(rows):
    return next(c for c in cal.aggregate_cohorts(rows) if c["horizon"] == "T5" and not c["cohort_key"]["regime_stratified"])


def governed(cohort):
    return dict(contract_version="governed_prospective_policy_review_rule/v1", current_policy=cohort["current_policy"],
        horizon="T5", cohort_key_identity=cohort["cohort_key_identity"], declaration_identity="owner:predeclared:1", comparison_policy_identity="existing_policy:review:1",
        predeclared_session="2025-12-31", comparison_rule={"method": "PREDECLARED_TAXONOMY_COUNT_AT_LEAST", "taxonomy_label": "FALSE_POSITIVE_BREAKOUT", "minimum_count": 1})


def test_retained_factory_future_accumulation_immutable_t0_and_replay(tmp_path):
    # Weekends/calendar gaps do not change the number of retained completed sessions.
    chain = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    paths = []
    for n, session in enumerate(chain):
        product = _integrated(session)
        product["research_action_policy_version"] = "v1"
        product["records"]["FPT"]["fundamental_decision_policy_version"] = "test/v1"
        snap = retention.build_snapshot(session=session, operation_identity="daily-operation:" + session, producer_run_identity="run:" + session,
            integrated_artifact=product, exact_session_snapshot=_price_snapshot(session, 100 + n))
        paths.append(retention.write_immutable_snapshot(tmp_path, snap)); _bind(tmp_path, snap)
    before = {p: p.read_bytes() for p in paths}
    artifact, report = retained_acceptance(tmp_path)
    first = next(o for o in artifact["observations"] if o["t0_session"] == chain[0])
    assert first["horizons"]["T5"]["forward_return"] == pytest.approx(.05)
    assert first["horizons"]["T10"]["forward_return"] is None
    assert first["forward_driver_context_at_t0"] == cal.FIELD_NOT_RETAINED
    assert first["intrinsic_scenario_at_t0"] == cal.FIELD_NOT_RETAINED
    assert report["deterministic_replay"]["reversed_input_order_identity_equal"]
    assert report["mutation_check"]["unchanged"]
    assert before == {p: p.read_bytes() for p in paths}
    # A future mutable view never supplies T0 policy/evidence fields.
    rewritten = _integrated(chain[0]); rewritten["research_action_policy_version"] = "future/v9"
    mutable = tmp_path / "operations-review" / "future-replay" / "integrated_investment_decision_product_artifact.json"
    mutable.parent.mkdir(); mutable.write_text(json.dumps(rewritten))
    replay = cal.build_calibration_artifact(root=str(tmp_path))
    assert replay["observations"] == artifact["observations"]
    assert replay["cohorts"] == artifact["cohorts"]  # excluded-input inventory changes only the enclosing report identity


@pytest.mark.parametrize("count", [5, 10, 20])
def test_exact_completed_session_maturity(count):
    chain = [f"2026-01-{i+1:02d}" for i in range(count+1)]
    record, chain, snapshots = observed(chain)
    row = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert row["horizons"][f"T{count}"]["status"] == "MATURE"
    record, shorter, snaps = observed(chain[:-1])
    row = cal.build_observation(record, chain=shorter, snapshots=snaps)
    assert row["horizons"][f"T{count}"]["evidence_state"] == "RETAINED_BUT_NOT_YET_MATURE"
    assert row["horizons"][f"T{count}"]["forward_return"] is None


@pytest.mark.parametrize("value", [None, False, 0, -1, float("nan"), float("inf")])
def test_invalid_t0_close_is_not_pending_or_zero_return(value):
    chain = make_chain(3); record, chain, snapshots = observed(chain, {s: value if i == 0 else 100 for i, s in enumerate(chain)})
    row = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert row["horizons"]["T5"]["evidence_state"] == "NOT_RETAINED_AT_T0"
    assert row["horizons"]["T5"]["forward_return"] is None


def test_price_basis_fails_locally_and_close_path_names_remain_explicit():
    record, chain, snapshots = observed()
    snapshots[chain[5]]["records"]["AAA"]["observations"][0]["transformation_identity"] = "incompatible/v2"
    record = make_feedback_record(ticker="AAA", t0_session=chain[0], posture="AVOID", entry=100, invalidation_level=90, chain=chain, snapshots=snapshots)
    row = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert row["horizons"]["T5"]["evidence_state"] == "SEMANTICALLY_INCOMPATIBLE"
    assert row["horizons"]["T10"]["status"] == "MATURE"  # endpoints qualified; incomplete close path stays unavailable
    assert row["horizons"]["T10"]["mfe_close_proxy"] is None
    assert row["horizons"]["T10"]["favorable_semantics"] == "CLOSE_ONLY_FAVORABLE_EXCURSION"
    assert row["horizons"]["T10"]["adverse_semantics"] == "CLOSE_ONLY_ADVERSE_EXCURSION"


@pytest.mark.parametrize("events,expected", [({1:110,2:90},"CONFIRMED_BEFORE_INVALIDATED"), ({1:90,2:110},"INVALIDATED_BEFORE_CONFIRMED"), ({1:110},"CONFIRMED_ONLY"), ({1:90},"INVALIDATED_ONLY"), ({},"NEITHER_YET")])
def test_serialized_condition_event_order_is_horizon_bounded(events, expected):
    chain = make_chain(12); prices = {s:100 for s in chain}; prices.update({chain[i]:v for i,v in events.items()})
    record, chain, snapshots = observed(chain, prices)
    record["trigger"]["condition"] = make_condition(105, ">", "trigger")
    record["invalidation"]["condition"] = make_condition(95, "<", "invalidation")
    d = feedback.feedback_diagnostics(record, chain=chain, snapshots=snapshots)
    assert d["event_ordering"] == expected
    assert d["basis_horizon"] == "T5"
    assert feedback.feedback_diagnostics(record, chain=chain, snapshots=snapshots, horizon_sessions=10)["basis_horizon"] == "T10"


def test_missing_price_prevents_first_event_order_claim_and_simultaneous_order_not_inferred():
    record, chain, snapshots = observed()
    record["trigger"]["condition"] = make_condition(105, ">", "trigger")
    del snapshots[chain[1]]["records"]["AAA"]
    d = feedback.feedback_diagnostics(record, chain=chain, snapshots=snapshots)
    assert d["event_ordering"] == "NOT_EVALUABLE"
    record, chain, snapshots = observed()
    record["trigger"]["condition"] = make_condition(90, ">", "trigger")
    record["invalidation"]["condition"] = make_condition(110, "<", "invalidation")
    assert feedback.feedback_diagnostics(record, chain=chain, snapshots=snapshots)["event_ordering"] == "SAME_SESSION_ORDER_UNRESOLVED"


def test_posthoc_target_and_tampered_downside_condition_are_not_admitted():
    record, chain, snapshots = observed()
    row = cal.build_observation(record, chain=chain, snapshots=snapshots, target_level=105)
    assert row["target"]["status"] == cal.NOT_EVALUATED
    record["invalidation"]["condition"]["reference_level"] = 80
    assert cal.build_observation(record, chain=chain, snapshots=snapshots)["r_multiple_denominator_status"] != "AVAILABLE"


def test_retained_target_is_not_counted_at_an_earlier_horizon():
    record, chain, snapshots = observed()
    record["target_condition_at_t0"] = make_condition(107, ">", "target")
    row = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert row["horizons"]["T5"]["target"]["status"] == "NOT_SATISFIED_YET"
    assert row["horizons"]["T10"]["target"]["status"] == "SATISFIED"


def test_retained_compatible_benchmark_only():
    record, chain, snapshots = observed()
    unavailable = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert unavailable["horizons"]["T5"]["benchmark_relative"]["return"] is None
    record["benchmark"] = {"identity":"index:1", "t0_close":{"close":200,"price_basis_identity":"index-basis/v1","source_identity":"index:t0"}}
    snapshots[chain[5]]["benchmarks"] = {"index:1":{"close":204,"price_basis_identity":"index-basis/v1","source_identity":"index:t5"}}
    row = cal.build_observation(record, chain=chain, snapshots=snapshots)
    assert row["horizons"]["T5"]["benchmark_relative"]["return"] == pytest.approx(.03)
    snapshots[chain[5]]["benchmarks"]["index:1"]["price_basis_identity"] = "different"
    assert cal.build_observation(record, chain=chain, snapshots=snapshots)["horizons"]["T5"]["benchmark_relative"]["return"] is None


@pytest.mark.parametrize("posture", ["AVOID", "WAIT_FOR_CONFIRMATION", "EARLY_WATCH"])
def test_price_alone_and_generic_invalidation_do_not_prove_wrong_decision(posture):
    outcome = {"research_action_posture_at_t0":posture,"horizons":{"T5":{"status":"MATURE","return":.2}},
        "confirmation":{"status":"BOUNDARY_NOT_EVALUABLE"},"invalidation":{"status":"INVALIDATED"},"event_ordering":"NOT_EVALUABLE"}
    assert measurement.classify_feedback_taxonomy(outcome)["label"] == "INSUFFICIENT_OUTCOME_EVIDENCE"


def test_explicit_qualified_t0_signal_can_support_defensive_diagnostic():
    outcome = {"research_action_posture_at_t0":"WAIT_FOR_CONFIRMATION","horizons":{"T5":{"status":"MATURE","return":.2}},
        "confirmation":{"status":"NOT_CONFIRMED_YET"},"invalidation":{"status":"NOT_INVALIDATED_YET"},"qualified_tactical_signal_at_t0":True}
    assert measurement.classify_feedback_taxonomy(outcome)["label"] == "POLICY_TOO_DEFENSIVE"


@pytest.mark.parametrize("n,sessions,state", [(19,5,cal.INSUFFICIENT_SAMPLE),(20,4,cal.INSUFFICIENT_SAMPLE),(20,5,cal.DESCRIPTIVE_ONLY),(49,10,cal.DESCRIPTIVE_ONLY),(50,9,cal.DESCRIPTIVE_ONLY),(50,10,cal.CALIBRATED_RESEARCH)])
def test_existing_presentation_threshold_boundaries(n,sessions,state):
    assert cal.sample_adequacy(n,sessions) == state


@pytest.mark.parametrize("field", ["policy", "feature"])
def test_incompatible_versions_never_pool(field):
    rows = cohort_rows()
    for r in rows[25:]:
        if field == "policy": r["t0_contract_versions"]["research_action_policy_version"] = "v2"
        else: r["feature_versions_at_t0"]["TACTICAL"] = "test_tactical/v2"
    cohorts = [c for c in cal.aggregate_cohorts(rows) if c["horizon"] == "T5"]
    assert len(cohorts) == 2
    assert all(c["sample_adequacy"] == cal.DESCRIPTIVE_ONLY for c in cohorts)


def test_unknown_policy_stays_missing_and_partitions_by_original_source():
    rows = cohort_rows()
    for r in rows: r["t0_contract_versions"]["research_action_policy_version"] = cal.FIELD_NOT_RETAINED
    cohorts = [c for c in cal.aggregate_cohorts(rows) if c["horizon"] == "T5"]
    assert len(cohorts) == 10
    assert all(c["sample_adequacy"] == cal.INSUFFICIENT_SAMPLE for c in cohorts)
    assert all(c["current_policy"]["research_action_policy_version"] == cal.FIELD_NOT_RETAINED for c in cohorts)


def test_duplicate_packets_do_not_increase_sample_and_order_is_deterministic():
    rows = cohort_rows(); first = cal.aggregate_cohorts(rows)
    assert cal.aggregate_cohorts(list(reversed(rows)) + [rows[0]]) == first
    bad = copy.deepcopy(rows[0]); bad["horizons"]["T5"]["forward_return"] = .99
    with pytest.raises(ValueError, match="CONFLICTING"): cal.aggregate_cohorts(rows + [bad])


@pytest.mark.parametrize("defect,reason", [("price","PRICE_BASIS_INCOMPATIBILITY_PRESENT"),("proof","GENUINE_PROSPECTIVE_T0_PROOF_MISSING"),("feature","FEATURE_VERSIONS_NOT_RETAINED_AT_T0")])
def test_adequacy_alone_does_not_grant_review_eligibility(defect,reason):
    rows = cohort_rows(); cohort = t5_cohort(rows)
    assert cohort["calibration_eligibility"]["state"] == cal.CALIBRATION_REVIEW_ELIGIBLE
    if defect == "price": rows[0]["horizons"]["T5"]["status"] = "PRICE_BASIS_INCOMPATIBLE"
    elif defect == "proof": rows[0]["authority_boundary"]["no_retroactive_t0_reconstruction"] = False
    else: rows[0]["feature_versions_at_t0"]["TACTICAL"] = cal.FIELD_NOT_RETAINED
    eligibility = cal.calibration_eligibility(cohort, rows)
    assert eligibility["state"] == cal.DESCRIPTIVE_EVIDENCE_ONLY
    assert reason in eligibility["reason_codes"]


def test_human_candidate_requires_predeclared_rule_and_never_mutates_policy():
    cohort = t5_cohort(cohort_rows()); rule = governed(cohort); before = copy.deepcopy((cohort,rule))
    absent = cal.build_policy_candidates([cohort])
    assert absent["disposition_distribution"] == {"NO_GOVERNED_POLICY_CANDIDATE_TO_COMPARE":1}
    result = cal.build_policy_candidates([cohort], [rule])
    assert result["human_review_candidate_count"] == 1
    assert result["records"][0]["required_human_approval"]
    assert result["automatic_policy_change"] is False
    assert (cohort,rule) == before
    assert "probability" not in result["records"][0]["empirical_statistics"]
    assert "optimized_threshold" not in json.dumps(result)


@pytest.mark.parametrize("defect", ["future_declaration", "invalid_date", "optimizer", "malformed_rule", "bool_threshold", "multiple"])
def test_parameter_search_and_ungoverned_rules_fail_closed(defect):
    cohort = t5_cohort(cohort_rows()); rule = governed(cohort)
    if defect == "future_declaration": rule["predeclared_session"] = "2026-01-10"
    elif defect == "invalid_date": rule["predeclared_session"] = "0000-00-00"
    elif defect == "optimizer": rule["comparison_rule"]["method"] = "OPTIMIZE_BEST_RETURN"
    elif defect == "malformed_rule": rule["comparison_rule"] = [1,2,3]
    elif defect == "bool_threshold": rule["comparison_rule"]["minimum_count"] = True
    result = cal.build_policy_candidates([cohort], [rule, copy.deepcopy(rule)] if defect == "multiple" else [rule])
    assert result["human_review_candidate_count"] == 0
    assert result["automatic_policy_change"] is False


def test_r4_r5_unavailable_context_retained_without_admission_gate():
    product = _integrated("2026-01-02")
    decision = product["records"]["FPT"]
    decision["corporate_intelligence_context"] = {"forward_driver_context":{"contract_version":"forward/v1", "context_identity":"driver:absent", "drivers":[]}}
    decision["intrinsic_scenario_valuation"] = {"projection_identity":"model:unavailable", "methods":{"FCFF":{"readiness":"BLOCKED"}}, "authority_effect":"NONE"}
    snapshot = retention.build_snapshot(session="2026-01-02",operation_identity="operation:1",producer_run_identity="run:1",
        integrated_artifact=product,exact_session_snapshot=_price_snapshot("2026-01-02",100))
    assert snapshot["records"]["FPT"]["integrated_decision_at_t0"] == decision
    projected = feedback._project_snapshot_for_feedback(snapshot)["records"]["FPT"]["integrated_decision_at_t0"]
    assert projected["forward_driver_context_at_t0"]["context_identity"] == "driver:absent"
    assert projected["intrinsic_scenario_at_t0"]["method_readiness"]["FCFF"] == "BLOCKED"


def test_acceptance_output_is_immutable(tmp_path):
    path = tmp_path / "acceptance.json"; _write_immutable(path, {"a":1}); _write_immutable(path, {"a":1})
    with pytest.raises(ValueError, match="IMMUTABLE_ARTIFACT_CONFLICT"): _write_immutable(path, {"a":2})


def test_completed_daily_market_session_does_not_require_another_t0_case(tmp_path):
    chain = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    import daily_session_level2_package as level2
    from test_prospective_decision_retention import _snapshot, _write
    first = _snapshot(chain[0], 100)
    retention.write_immutable_snapshot(tmp_path, first); _bind(tmp_path, first)
    for n, session in enumerate(chain[1:], 1):
        op = "daily-operation:" + session
        _write(tmp_path / "operations-review/daily-research-session-operations-v1" / session / "run/run_manifest.json",
            {"market_session":session,"operation_identity":op,"generation_context":"DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"})
        _write(tmp_path / "operations-review/canonical-post-close-v1" / session / "session_handoff_bundle.json",
            {"session":session,"daily_session_operation_identity":op,"integrated_investment_decision_product_identity":"product:"+session,
             "deeper_bundles":{"integrated_investment_decision_product":"operations-review/absent-working-view/"+session+".json"},
             "daily_producer":{"status":"COMPLETED"},"market_session_proof":{"resolved_completed_session":session}})
        _write(level2.session_artifact_paths(tmp_path, session)["exact_session_snapshot"], _price_snapshot(session, 100+n))
    artifact = cal.build_calibration_artifact(root=str(tmp_path))
    assert artifact["observation_count"] == 1
    assert artifact["observations"][0]["horizons"]["T5"]["forward_return"] == pytest.approx(.05)
    assert artifact["observations"][0]["t0_contract_versions"]["research_action_policy_version"] == cal.FIELD_NOT_RETAINED
