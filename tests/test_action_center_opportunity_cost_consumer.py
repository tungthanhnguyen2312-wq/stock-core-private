"""Offline synthetic consumer acceptance; no real portfolio or retained artifacts."""
import ast
import copy
import json
from pathlib import Path

import pytest

import personal_investment_decision_action_center as ac
from canonical_daily_financial_v2_materialization import _identity as valuation_identity
from stocklookup_core.portfolio import action_center_opportunity_cost as consumer
from stocklookup_core.portfolio import portfolio_opportunity_cost_research as engine
from stocklookup_core.decision import integrated_investment_decision_product as iid
from stocklookup_core.tactical import market_structure_breakout_product_projection as structural
from _integrated_decision_fixture import disposition_artifact, disposition_record
from test_integrated_investment_decision_product import _sample_financial_record
from test_research_posture_v2_policy import tactical, FIRED, BEAR
from test_portfolio_opportunity_cost_research import _state, _no_capital_decision

SESSION = "2026-08-28"
TICKERS = ("AAA", "BBB", "CCC", "DDD", "EEE")


def fixtures(*, financial=True, valuation=True, changes=None):
    rows = {}
    for ticker in TICKERS:
        row = tactical(**(changes or FIRED))
        row.update(ticker=ticker, as_of_session=SESSION, trigger_close_comparison_operator=">",
                   invalidation_close_comparison_operator="<", trigger_horizon="PIVOT_BREAKOUT_MEASUREMENT",
                   invalidation_horizon="SWING_STRUCTURE_ANALYTICAL_CONTEXT",
                   price_basis_qualification={"price_basis_verified": False, "basis": "PROVIDER_SCOPED", "historical_pit_eligible": False})
        rows[ticker] = row
    ta = {"contract_version": structural.CONTRACT_VERSION, "session": SESSION, "records": rows}
    ta.update(structural.content_identity(ta))
    val = {"contract_version": "current_research_valuation_context/v1", "requested_at": SESSION + "T15:00:00+07:00",
           "source_valuation_identity": "raw:synthetic", "source_financial_v2_identity": "financial:synthetic", "records": {}}
    for ticker in TICKERS:
        expensive = ticker == "BBB"
        val["records"][ticker] = {"ticker": ticker, "status": "AVAILABLE", "research_usable": True,
            "relative_research_state": "EXPENSIVE_RELATIVE_RESEARCH" if expensive else "ATTRACTIVE_RELATIVE_RESEARCH",
            "share_basis": "PROVIDER_VALUATION_PROXY", "earnings_state": "PROFITABLE",
            "peer_relative": {"P/B": {"status": "READY_RESEARCH_ONLY", "percentile": .9 if expensive else .1,
                                     "peer_count": 12, "basis": {"method_id": "P/B", "provider": "SYNTHETIC", "period": "2026-Q2"}}},
            "methods": {"P/B": {"status": "RESEARCH_USABLE", "value": 1.8, "period_basis": "2026-Q2"}},
            "limitations": ["Synthetic provider research; no strict valuation or PIT authority."]}
    val.update(valuation_identity(val))
    artifact = iid.build_artifact(session=SESSION, requested_at=SESSION + "T15:00:00+07:00", technical_structure_artifact=ta,
        technical_coverage_disposition_artifact=disposition_artifact({t: disposition_record(t, session=SESSION, currency="CURRENT_SESSION") for t in TICKERS}, session=SESSION),
        financial_analysis_artifact={"artifact_identity": "financial:synthetic", "records": {t: _sample_financial_record() for t in TICKERS}} if financial else None,
        current_valuation_artifact=val if valuation else None)
    state = _state({"AAA": "materials", "BBB": "materials"}, sector_weights={"materials": .4}, unresolved=("DDD",))
    state["as_of_date"] = SESSION
    state["positions"]["CCC"] = {"ticker": "CCC", "is_active": True, "current_quantity": 0, "current_position_status": "CLOSED", "current_weight": 0, "sector": "other"}
    frames = [{"ticker": t, "horizon": "STRUCTURAL", "portfolio_role": "CORE", "thesis_id": "synthetic:" + t,
               "thesis_status": "INTACT", "thesis_source": "owner-note:synthetic"} for t in TICKERS]
    request = {"contract_version": consumer.INPUT_CONTRACT, "session": SESSION, "research_frames": frames,
               "owner_portfolio_state": state, "valuation_artifact": val if valuation else None}
    return artifact, request


def build(artifact, request):
    return ac.build_artifact(session=SESSION, requested_at=SESSION + "T17:00:00+07:00",
                             integrated_decision_artifact=artifact, opportunity_cost_input=request)


def cases(result, ticker):
    return {c["case"] for c in result["opportunity_cost_research"]["comparison"]["research_cases"] if c["ticker"] == ticker}


def test_useful_cases_position_truth_independent_lenses_and_human_readable_output():
    artifact, request = fixtures()
    before = copy.deepcopy((artifact, request))
    result = build(artifact, request)
    view = result["opportunity_cost_research"]
    assert {engine.HOLD_CORE_REVIEW, engine.ADD_CORE_REVIEW} <= cases(result, "AAA")
    assert engine.VALUATION_TRIM_REVIEW in cases(result, "BBB")
    assert engine.ALTERNATIVE_INVESTMENT_REVIEW in cases(result, "CCC")
    assert cases(result, "DDD") == set()
    assert engine.ALTERNATIVE_INVESTMENT_REVIEW in cases(result, "EEE")
    units = {u["comparison_unit"]["ticker"]: u for u in view["comparison"]["comparison_units"]}
    assert units["AAA"]["holding_fact"] == engine.HELD_CONFIRMED
    assert units["CCC"]["holding_fact"] == engine.NOT_HELD_CONFIRMED
    assert units["DDD"]["holding_fact"] == units["EEE"]["holding_fact"] == engine.POSITION_UNRESOLVED
    assert engine.CASH_OPTIONALITY_REVIEW in view["comparison"]["case_counts"]
    assert units["AAA"]["lenses"]["tactical"]["confirmation"] == "ENTRY_ADMITTED"
    assert view["evidence_by_ticker"]["AAA"]["evidence_axes"] == artifact["records"]["AAA"]["evidence_axes"]
    assert view["evidence_by_ticker"]["AAA"]["valuation_source_record"] == request["valuation_artifact"]["records"]["AAA"]
    text = ac.markdown(result)
    assert "existing portfolio decision artifact was not supplied" in text
    assert "import a workbook" not in text
    for name in (engine.HELD_CONFIRMED, engine.NOT_HELD_CONFIRMED, engine.POSITION_UNRESOLVED, engine.HOLD_CORE_REVIEW,
                 engine.ADD_CORE_REVIEW, engine.VALUATION_TRIM_REVIEW, engine.ALTERNATIVE_INVESTMENT_REVIEW, engine.CASH_OPTIONALITY_REVIEW, "Decision changers", "COMPARABLE"):
        assert name in text
    _no_capital_decision(view["comparison"])
    assert (artifact, request) == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("state,status", [(None, "PRIVATE_PORTFOLIO_NOT_SUPPLIED"),
    ({"contract_version": "portfolio_state/v1", "status": "NOT_PROVIDED"}, "PRIVATE_PORTFOLIO_UNAVAILABLE"),
    ({"contract_version": "portfolio_state/v9", "status": "AVAILABLE"}, "UNSUPPORTED_PORTFOLIO_STATE")])
def test_absent_unavailable_and_unsupported_owner_never_synthetic_empty(state, status):
    artifact, request = fixtures()
    request["owner_portfolio_state"] = state
    view = build(artifact, request)["opportunity_cost_research"]
    assert view["status"] == status and view["comparison"] is None


@pytest.mark.parametrize("quantity", [None, True, -1, float("nan"), float("inf"), "unknown"])
def test_unresolved_or_invalid_quantity_never_held_or_flat(quantity):
    artifact, request = fixtures()
    request["owner_portfolio_state"]["positions"]["AAA"]["current_quantity"] = quantity
    result = build(artifact, request)
    assert not cases(result, "AAA")
    assert result["opportunity_cost_research"]["comparison"]["comparison_units"][0]["holding_fact"] == engine.POSITION_UNRESOLVED
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("key,value", [("cash_available", float("nan")), ("effective_nav", True),
                                       ("positions", []), ("as_of_date", "2026-08-29"), ("source_identities", {})])
def test_invalid_owner_state_fails_closed(key, value):
    artifact, request = fixtures()
    request["owner_portfolio_state"][key] = value
    with pytest.raises(engine.OpportunityCostResearchError):
        build(artifact, request)


def test_partial_and_stale_owner_state_remain_uncertain_and_limits_only_narrow():
    artifact, request = fixtures()
    state = request["owner_portfolio_state"]
    state.update(as_of_date="2026-08-27", cash_available=None, effective_nav=None)
    state["positions"]["AAA"]["current_weight"] = None
    state["effective_policy"] = {"max_sector_weight": .3}
    result = build(artifact, request)
    view = result["opportunity_cost_research"]
    assert view["owner_state_status"] == "STALE_OWNER_SNAPSHOT_RESEARCH_ONLY"
    assert view["comparison"]["owner_exposure"]["status"] == "PARTIAL_UNCERTAIN"
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    assert engine.HOLD_CORE_REVIEW in cases(result, "AAA")
    assert view["comparison"]["research_cases"][-1]["cash_fact"]["cash_to_nav"] is None


def test_thesis_break_never_trim_and_tactical_weakness_never_relabels_core():
    artifact, request = fixtures(changes=BEAR)
    request["research_frames"][1]["thesis_status"] = "BROKEN"
    result = build(artifact, request)
    assert engine.VALUATION_TRIM_REVIEW not in cases(result, "BBB")
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    unit = result["opportunity_cost_research"]["comparison"]["comparison_units"][0]
    assert unit["lenses"]["core_structural"]["fundamental_state"] == artifact["records"]["AAA"]["fundamental_state"]
    assert unit["lenses"]["tactical"]["confirmation"] == "ADVERSE"


def test_missing_financial_and_valuation_cannot_create_positive_qualification():
    artifact, request = fixtures(financial=False, valuation=False)
    for frame in request["research_frames"]:
        frame.update(thesis_status="UNKNOWN", thesis_source=None)
    result = build(artifact, request)
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    assert engine.VALUATION_TRIM_REVIEW not in cases(result, "BBB")
    assert cases(result, "CCC") == {engine.INSUFFICIENT_COMPARABLE_EVIDENCE}
    assert all(p["comparability"]["status"] == engine.NOT_COMPARABLE for p in result["opportunity_cost_research"]["comparison"]["pairwise"])


@pytest.mark.parametrize("mutation", ["input_session", "iid_session", "iid_content", "valuation_content", "valuation_source", "valuation_session", "duplicate", "false_method"])
def test_source_session_and_qualified_method_corruption_fail_closed(mutation):
    artifact, request = fixtures()
    val = request["valuation_artifact"]
    if mutation == "input_session": request["session"] = "2026-08-27"
    if mutation == "iid_session": artifact["session"] = "2026-08-27"
    if mutation == "iid_content": artifact["records"]["AAA"]["fundamental_state"] = "STABLE"
    if mutation == "valuation_content": val["records"]["AAA"]["peer_relative"]["P/B"]["percentile"] = .9
    if mutation == "valuation_source": val["artifact_identity"] = "another:source"
    if mutation == "valuation_session": val["session"] = "2026-08-27"
    if mutation == "duplicate": request["research_frames"].append(copy.deepcopy(request["research_frames"][0]))
    if mutation == "false_method":
        val["records"]["AAA"]["peer_relative"]["P/B"]["percentile"] = 2
    if mutation in {"valuation_session", "false_method"}:
        val.update(valuation_identity(val))
        artifact["source_artifacts"]["current_valuation"] = val["artifact_identity"]
        artifact.update(iid.content_identity(artifact))
    with pytest.raises(ValueError):
        build(artifact, request)


@pytest.mark.parametrize("bad_dates", [False, True])
def test_pr118_invalid_measurements_do_not_reenter(bad_dates):
    artifact, request = fixtures()
    for frame in request["research_frames"]:
        frame.update(current_returns=[.01, .02, .03], current_return_dates=["2026-08-24", "2026-08-25", "2026-08-26"])
    if bad_dates:
        request["research_frames"][2]["current_return_dates"] = ["x", "y", "z"]
    else:
        request["research_frames"][2]["current_returns"][0] = float("nan")
    result = build(artifact, request)
    pairs = result["opportunity_cost_research"]["comparison"]["pairwise"]
    correlation = next(p for p in pairs if p["candidate_ticker"] == "CCC")["redundancy"]["current_correlation"]
    assert correlation["value"] is None and not correlation["comparable"]
    json.dumps(result, allow_nan=False)


def test_no_opt_in_is_identical_and_no_production_or_public_consumer():
    artifact, request = fixtures()
    kwargs = dict(session=SESSION, requested_at=SESSION, integrated_decision_artifact=artifact)
    baseline = ac.build_artifact(**kwargs)
    assert ac.build_artifact(**kwargs, opportunity_cost_input=None) == baseline
    assert "opportunity_cost_research" not in baseline
    assert "OPPORTUNITY COST" not in ac.markdown(baseline)
    opt_in = build(artifact, request)
    stripped = {k: v for k, v in opt_in.items() if k not in {"opportunity_cost_research", "artifact_identity", "artifact_sha256", "requested_at"}}
    assert all(stripped[k] == v for k, v in baseline.items() if k not in {"artifact_identity", "artifact_sha256", "requested_at"})
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "personal_investment_decision_action_center.py").read_text(encoding="utf-8"))
    resolver = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate_from_retained_artifacts")
    assert "opportunity_cost_input" not in ast.unparse(resolver)
    for filename in ("canonical_post_close_pipeline.py", "tools/release_orchestrator.py", "ai_handoff_publication.py", "tools/run_owner_daily.py"):
        assert "action_center_opportunity_cost" not in (root / filename).read_text(encoding="utf-8")


@pytest.mark.parametrize("field", ["winner", "target_weight", "buy", "position_size", "expected_return", "valuation", "structural"])
def test_no_injected_rank_decision_or_numerical_lens(field):
    artifact, request = fixtures()
    request["research_frames"][0][field] = 1
    with pytest.raises(engine.OpportunityCostResearchError, match="UNSUPPORTED_RESEARCH_FRAME_FIELD"):
        build(artifact, request)


@pytest.mark.parametrize("writer", [ac.write_private_artifact, ac.write_markdown])
def test_optional_writer_enforces_existing_private_boundary(tmp_path, monkeypatch, writer):
    artifact, request = fixtures()
    result = build(artifact, request)
    private = tmp_path / "private"
    monkeypatch.setattr(ac, "default_action_center_root", lambda: private)
    with pytest.raises(ac.ActionCenterError, match="REQUIRES_PRIVATE"):
        writer(result, root=tmp_path / "public")
    assert not (tmp_path / "public").exists()
    path = writer(result, root=private / "research")
    assert path.is_file() and path.is_relative_to(private)
    result["session"] = "../../public"
    with pytest.raises(ac.ActionCenterError, match="SESSION_INVALID"):
        writer(result)


def test_missing_valuation_with_financial_evidence_and_thesis_is_narrowed():
    artifact, request = fixtures(valuation=False)
    result = build(artifact, request)
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    assert engine.HOLD_CORE_REVIEW in cases(result, "AAA")
    comparison = result["opportunity_cost_research"]["comparison"]
    assert comparison["source_engine_comparison_identity"].startswith(engine.V2_CONTRACT_VERSION)
    assert any(c["reason"] == "CONSUMER_REQUIRES_STRUCTURAL_AND_QUALIFIED_VALUATION_EVIDENCE" for c in comparison["narrowed_by_owner_constraints_or_evidence"])


def test_missing_financial_even_with_reported_intact_thesis_never_adds():
    artifact, request = fixtures(financial=False)
    result = build(artifact, request)
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    assert result["opportunity_cost_research"]["comparison"]["comparison_units"][0]["lenses"]["core_structural"]["thesis_status"] == "INTACT"


def test_distinct_valuation_basis_narrows_comparison_without_losing_source():
    artifact, request = fixtures()
    val = request["valuation_artifact"]
    val["records"]["CCC"]["peer_relative"]["P/B"]["basis"]["provider"] = "OTHER_SYNTHETIC"
    val.update(valuation_identity(val))
    artifact["source_artifacts"]["current_valuation"] = val["artifact_identity"]
    artifact.update(iid.content_identity(artifact))
    result = build(artifact, request)
    pair = next(p for p in result["opportunity_cost_research"]["comparison"]["pairwise"] if p["candidate_ticker"] == "CCC")
    assert pair["comparability"]["status"] == engine.PARTIALLY_COMPARABLE
    assert pair["comparability"]["axes"]["strategic"] == engine.NOT_COMPARABLE


def test_existing_portfolio_artifacts_must_share_the_owner_snapshot_and_session():
    artifact, request = fixtures()
    kwargs = dict(session=SESSION, requested_at=SESSION, integrated_decision_artifact=artifact, opportunity_cost_input=request)
    with pytest.raises(ac.ActionCenterError, match="OWNER_SNAPSHOT_MISMATCH"):
        ac.build_artifact(**kwargs, portfolio_snapshot={"artifact_identity": "other"})
    for portfolio, reason in [({"session": "2026-08-27"}, "SESSION_MISMATCH"),
                              ({"session": SESSION, "records": {}}, "SOURCE_MISMATCH")]:
        with pytest.raises(ac.ActionCenterError, match=reason):
            ac.build_artifact(**kwargs, portfolio_aware_decision_artifact=portfolio)


def test_consumer_projection_identity_is_deterministic_and_distinct_from_engine():
    artifact, request = fixtures()
    result = build(artifact, request)
    comparison = result["opportunity_cost_research"]["comparison"]
    payload = {k: v for k, v in comparison.items() if k != "comparison_identity"}
    assert comparison["comparison_identity"] == consumer.CONTRACT_VERSION + ":" + engine._sha(payload)
    reversed_request = copy.deepcopy(request)
    reversed_request["research_frames"].reverse()
    assert build(artifact, reversed_request)["artifact_identity"] == result["artifact_identity"]


def test_narrowed_pair_basis_is_preserved_in_alternative_cases():
    artifact, request = fixtures()
    val = request["valuation_artifact"]
    val["records"]["CCC"]["peer_relative"]["P/B"]["basis"]["period"] = "2025-FY"
    val.update(valuation_identity(val))
    artifact["source_artifacts"]["current_valuation"] = val["artifact_identity"]
    artifact.update(iid.content_identity(artifact))
    result = build(artifact, request)
    comparison = result["opportunity_cost_research"]["comparison"]
    alternative = next(c for c in comparison["research_cases"] if c["ticker"] == "CCC")
    assert all(p["comparability"]["status"] == engine.PARTIALLY_COMPARABLE for p in alternative["comparisons"])
    assert any("CCC" in code for code in comparison["research_cases"][-1]["supporting_evidence"])


def test_return_observation_after_comparison_session_fails_closed():
    artifact, request = fixtures()
    request["research_frames"][0].update(current_returns=[.01, .02, .03], current_return_dates=["2026-08-24", "2026-08-25", "2026-08-31"])
    with pytest.raises(engine.OpportunityCostResearchError, match="RETURN_DATE_FUTURE_INFORMATION"):
        build(artifact, request)


def test_unsupported_owner_state_with_malformed_lineage_stays_unavailable():
    artifact, request = fixtures()
    request["owner_portfolio_state"] = {"contract_version": "portfolio_state/v9", "source_identities": "unsupported"}
    assert build(artifact, request)["opportunity_cost_research"]["status"] == "UNSUPPORTED_PORTFOLIO_STATE"


def test_intrinsic_model_surface_does_not_enter_optional_consumer():
    artifact, request = fixtures()
    val = request["valuation_artifact"]
    val["records"]["AAA"]["intrinsic_scenario_valuation"] = {"target_price": 1, "forecast": "synthetic"}
    val.update(valuation_identity(val))
    artifact["source_artifacts"]["current_valuation"] = val["artifact_identity"]
    artifact["records"]["AAA"]["valuation_context_summary"]["intrinsic_scenario_valuation"] = {"target_price": 1}
    artifact["records"]["AAA"]["decision_identity"] = iid.decision_identity(artifact["records"]["AAA"])
    artifact.update(iid.content_identity(artifact))
    view = build(artifact, request)["opportunity_cost_research"]
    assert "target_price" not in json.dumps(view)
    assert "intrinsic_scenario_valuation" not in json.dumps(view)


@pytest.mark.parametrize("active,quantity,holding", [(True, 0, engine.NOT_HELD_CONFIRMED),
                                                    (False, 100, engine.EXCLUDED_INACTIVE)])
def test_explicit_zero_and_owner_exclusion_remain_distinct(active, quantity, holding):
    artifact, request = fixtures()
    request["owner_portfolio_state"]["positions"]["AAA"].update(is_active=active, current_quantity=quantity)
    result = build(artifact, request)
    unit = result["opportunity_cost_research"]["comparison"]["comparison_units"][0]
    assert unit["holding_fact"] == holding
    assert engine.HOLD_CORE_REVIEW not in cases(result, "AAA")
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")


def test_relative_label_without_ready_method_cannot_support_add_or_trim():
    artifact, request = fixtures()
    val = request["valuation_artifact"]
    for row in val["records"].values():
        row["peer_relative"]["P/B"]["status"] = "REFERENCE_ONLY"
    val.update(valuation_identity(val))
    artifact["source_artifacts"]["current_valuation"] = val["artifact_identity"]
    artifact.update(iid.content_identity(artifact))
    result = build(artifact, request)
    assert engine.ADD_CORE_REVIEW not in cases(result, "AAA")
    assert engine.VALUATION_TRIM_REVIEW not in cases(result, "BBB")


def test_markdown_symlink_cannot_route_optional_private_output_elsewhere(tmp_path, monkeypatch):
    artifact, request = fixtures()
    result = build(artifact, request)
    private = tmp_path / "private"
    monkeypatch.setattr(ac, "default_action_center_root", lambda: private)
    session_dir = private / SESSION
    session_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("preserved", encoding="utf-8")
    try:
        (session_dir / "personal_investment_decision_action_center.md").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not allow creating fixture symlinks; hosted Linux covers this boundary")
    with pytest.raises(ac.ActionCenterError, match="REQUIRES_PRIVATE"):
        ac.write_markdown(result)
    assert outside.read_text(encoding="utf-8") == "preserved"
