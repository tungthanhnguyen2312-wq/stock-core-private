"""Small offline acceptance of the production composition, with synthetic engines.

The real Daily, Producer, session operation, packet, immutable materializer,
AI/cockpit encoder and private handoff packager run. Acquisition, session gate,
security engines and post-Daily observers are injected: no network/live publication.
"""
import copy
import json
import sys
import types
from datetime import datetime

import pytest

import canonical_daily_operation as daily
import daily_producer_pipeline as producer
import daily_research_session_operations as operations
from ai_handoff_publication import build_package
from current_macro_regime import build as macro_build, session_context
from current_research_decision_packet_product import verified_packet
from field_temporal_contract import stable_id
from human_ai_decision_evidence_packet import build_packet as human_packet
from macro_market_regime_decision_context import build_context, validate_context
from vn_time import VN_TZ
from test_ai_research_session_delivery import _scoped_operation, _scoped_inputs, _integrated_delivery_fixture, _daily_brief_fixture
from test_canonical_daily_operation import _patch_downstream, _acquired, _write_runtime
from test_current_research_decision_packet import _opportunity, _decision

SESSION = "2026-10-08"
CUTOFF = "2026-10-08T10:00:00Z"


def macro(*, retrieved="2026-10-08T09:00:00Z", observation="2026-10-07", release=None, row_known=None, stale=False):
    row = {"indicator_id": "us_fed_funds", "source_identity": "FRED:DFF", "source": "FRED", "authority": "OFFICIAL_PUBLIC_SOURCE", "value": 4.1, "previous_value": 4.0, "unit": "percent", "status": "AVAILABLE", "observation_date": observation, "released_at": release, "retrieved_at": row_known or retrieved, "raw_payload_sha256": "retained:fred", "freshness": {"status": "STALE" if stale else "CURRENT_RESEARCH_NOT_HISTORICAL_PIT"}, "limitations": ["Latest vintage has no historical release timestamp."]}
    return macro_build(observations=[row], raw_sources=[], retrieved_at=retrieved)


def sector(session=SESSION):
    row = {"contract_version": "current_market_sector_leadership_context/v1", "session": session, "market": {"current_breadth_state": "BROAD_PARTICIPATION"}, "groups": {"records": {}}, "ticker_contexts": {}, "coverage": {}}
    digest = stable_id(row)
    row.update(artifact_sha256=digest, artifact_identity="current_market_sector_leadership_context:" + digest)
    return row


@pytest.mark.parametrize("session,cutoff,retrieval", [
    ("2026-10-08", CUTOFF, "2026-10-08T09:00:00Z"),
    ("2026-10-09", "2026-10-09T10:00:00Z", "2026-10-09T09:00:00Z"),
    ("2026-10-12", "2026-10-12T10:00:00Z", "2026-10-12T09:00:00Z"),
])
def test_future_sessions_use_actual_cutoff(session, cutoff, retrieval):
    context = build_context(macro=macro(retrieved=retrieval, observation=session), session=session, cutoff=cutoff)
    validate_context(context, session)
    assert context["knowledge_available_at"] == cutoff
    assert context["dimensions"]["GLOBAL_RATES"]["state"] == "TIGHTENING"
    assert context["coverage"]["historical_pit_macro_dimensions"] == []


@pytest.mark.parametrize("kwargs", [
    {"retrieved": "2026-10-08T10:01:00Z"},
    {"row_known": "2026-10-08T10:01:00Z"},
    {"release": "2026-10-08T10:01:00Z"},
    {"retrieved": "2026-10-09T09:00:00Z"},
    {"observation": "2020-01-01"},
    {"stale": True},
])
def test_late_and_stale_observations_narrow_only_macro(kwargs):
    context = build_context(macro=macro(**kwargs), sector_leadership=sector(), session=SESSION, cutoff=CUTOFF)
    assert context["dimensions"]["GLOBAL_RATES"]["state"] == "UNKNOWN"
    assert context["dimensions"]["EXACT_SESSION_BREADTH"]["state"] == "BROAD_PARTICIPATION"


def test_date_only_release_and_same_day_timestamp_are_current_research_only():
    for release in (SESSION, "2026-10-08T08:00:00Z"):
        context = build_context(macro=macro(release=release), session=SESSION, cutoff=CUTOFF)
        evidence = context["dimensions"]["GLOBAL_RATES"]["evidence"][0]
        assert context["dimensions"]["GLOBAL_RATES"]["state"] == "TIGHTENING"
        assert evidence["temporal"]["historical_pit"] == "NOT_PROMOTED"
        assert evidence["temporal"]["release_precision"] == ("DATE_ONLY" if release == SESSION else "TIMESTAMP")


def test_identity_session_and_cutoff_are_required():
    context = build_context(macro=macro(), session=SESSION, cutoff=CUTOFF)
    with pytest.raises(ValueError, match="SESSION_MISMATCH"):
        human_packet(ticker="AAA", regime_context=context, decision_session="2026-10-06")
    broken = copy.deepcopy(context)
    broken["dimensions"]["GLOBAL_RATES"]["state"] = "EASING"
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        validate_context(broken, SESSION)
    with pytest.raises(ValueError, match="SESSION_MISMATCH"):
        build_context(macro=macro(), sector_leadership=sector("2026-10-09"), session=SESSION, cutoff=CUTOFF)
    assert session_context(macro(), SESSION)["status"] == "UNAVAILABLE"
    assert session_context(macro(), SESSION, cutoff="2026-10-09T10:00:00Z")["status"] == "UNAVAILABLE"
    assert session_context(macro(), SESSION, cutoff="2026-10-08T10:00:00")["status"] == "UNAVAILABLE"
    forged = macro()
    forged["observations"]["us_fed_funds"]["value"] = 100
    assert session_context(forged, SESSION, cutoff=CUTOFF)["reason"] == "MACRO_ARTIFACT_IDENTITY_INVALID"


def test_nso_release_calendar_overrides_generic_age_rule():
    row = macro()["observations"]["us_fed_funds"]
    row.update(indicator_id="vn_cpi_yoy", source_identity="NSO:release", observation_date="2026-09", released_at="2026-10-06", freshness={"status": "CURRENT", "next_expected_official_release": "2026-10-09"})
    artifact = macro_build(observations=[row], raw_sources=[], retrieved_at=row["retrieved_at"])
    assert session_context(artifact, SESSION, cutoff=CUTOFF)["state_axes"]["INFLATION_PRESSURE"]["state"] == "ACCELERATING"
    assert session_context(artifact, "2026-10-09", cutoff="2026-10-09T10:00:00Z")["state_axes"]["INFLATION_PRESSURE"]["state"] == "UNKNOWN"


def _install_engines(monkeypatch):
    inputs = _scoped_inputs()
    inputs.pop("market_flow_positioning")
    for name in operations.REQUIRED + ("official_universe", "event_context"):
        inputs.setdefault(name, {"records": {}})
        inputs[name].update(artifact_identity=name + ":fixture", contract_version=name + "/fixture", session=SESSION)
    inputs["corporate_intelligence"]["coverage"] = {}
    inputs["valuation"]["valuation_session"] = SESSION
    entries = {name: {"artifact_identity": value["artifact_identity"], "path": "fixture/" + name} for name, value in inputs.items()}
    registry = {"sessions": {SESSION: entries}}
    monkeypatch.setattr(daily, "load_registry", lambda *a: registry)
    for module in (producer, operations):
        monkeypatch.setattr(module, "load_registry", lambda *a: registry)
        monkeypatch.setattr(module, "resolve_inputs", lambda *a: (inputs, entries))
        monkeypatch.setattr(module, "validate_coherence", lambda *a: {"session": SESSION})
    # Real registry identity selection remains active. Domain/security engines are synthetic.
    for build_name, identity_name in (("build_peer", "peer_identity"), ("build_scenario", "scenario_identity"), ("build_strategy", "strategy_identity")):
        identity = getattr(operations, identity_name)
        def builder(_identity=identity, **kwargs):
            value = {"records": {}, "coverage": {}, "session": SESSION}
            value.update(_identity(value))
            return value
        monkeypatch.setattr(operations, build_name, builder)
    opportunity = _opportunity({"AAA": _decision()}, session=SESSION)
    monkeypatch.setattr(operations, "build_opportunity", lambda **k: copy.deepcopy(opportunity))
    queue = {"entry_relevant_summary": {"PRIORITY_NOW_TOTAL": 0, "PRIORITY_NOW_ENTRY_RELEVANT": 0}, "primary_review_candidates": {"count": 0}}
    queue.update(operations.decision_queue_identity(queue))
    opportunity["coverage"] = {"current_official_universe": 7}
    opportunity.update(operations.opportunity_identity(opportunity))
    monkeypatch.setattr(operations, "build_decision_queue", lambda **k: copy.deepcopy(queue))
    for name in ("freeze_current_decision_surface", "prospective_context", "strategy_prospective_context", "decision_queue_prospective_context"):
        monkeypatch.setattr(operations, name, lambda *a: {"snapshot_id": "snapshot:fixture"})
    product = _scoped_operation()["product"]
    product["watchlist"]["tickers"].append("AAA")  # exercise the real cockpit card on synthetic input
    product["market_brief"]["coverage"]["same_session_technical_feature_available_count"] = 7
    def build_product(**kwargs):
        value = copy.deepcopy(product)
        value["macro_context"] = kwargs["macro_context"]
        value.update(operations.product_identity(value))
        return value
    monkeypatch.setattr(operations, "build_product", build_product)
    monkeypatch.setattr(operations, "markdown", lambda *a: "offline brief")
    monkeypatch.setattr(producer, "completed_session_gate", lambda *a, **k: {"status": "READY"})
    shadow = {"artifact_identity": "shadow:fixture", "metadata": {"as_of_session": SESSION}}
    monkeypatch.setattr(producer, "resolve_or_build_daily_session_shadow_recommendation", lambda *a, **k: {"path": "fixture/shadow", "chain": {"artifact_identity": "chain:fixture", "shadow_security_recommendation": shadow, "fundamental_cohort_selection": {}, "fundamental_thesis_invalidation_precision": {"artifact_identity": "invalidation:fixture"}, "source_artifact_identities": {}}})
    monkeypatch.setattr(producer, "materialize_and_write_current_product_projections", lambda **k: {"status": "UNAVAILABLE"})
    consumer = types.ModuleType("builders.build_ticker_context")
    consumer.current_daily_decision_research_contract = lambda *a: {"status": "AVAILABLE"}
    monkeypatch.setitem(sys.modules, "builders.build_ticker_context", consumer)
    return inputs


@pytest.mark.parametrize("missing", [False, True])
def test_real_daily_to_packet_handoff_and_cockpit(monkeypatch, tmp_path, missing):
    _install_engines(monkeypatch)
    from _integrated_decision_fixture import integrated_decision
    integrated = integrated_decision(SESSION, ["AAA"], currency_by_ticker={"AAA": "CURRENT_SESSION"})
    original = copy.deepcopy(integrated)
    captured = {}
    def produce(root, **kwargs):
        kwargs.pop("runtime_root_override", None)
        result = producer.run_daily_producer(root, **kwargs)
        captured.update(result)
        return result
    def acquire():
        if missing: raise OSError("offline source unavailable")
        return macro()
    paths = __import__('daily_session_level2_package').session_artifact_paths(tmp_path, SESSION)
    paths["sector_leadership"].parent.mkdir(parents=True, exist_ok=True)
    paths["sector_leadership"].write_text(json.dumps(sector()), encoding="utf-8")
    _patch_downstream(monkeypatch, tmp_path)
    import canonical_post_close_pipeline as post_close
    monkeypatch.setattr(daily, "build_decision_packet", post_close.build_decision_packet)
    monkeypatch.setattr(daily, "run_daily_producer", produce)
    monkeypatch.setattr(daily, "build_enrichment_components", lambda *a, **k: {"integrated_investment_decision_product": {"artifact": integrated}})
    monkeypatch.setattr(daily, "_build_preseal_daily_integrated_brief", lambda *a, **k: _daily_brief_fixture(integrated, session=SESSION))
    runtime = tmp_path / "runtime"
    _write_runtime(runtime, SESSION)
    daily.run_canonical_daily_operation(tmp_path, runtime, SESSION, now=datetime(2026, 10, 8, 17, 0, tzinfo=VN_TZ), working_dates_evidence={"workingDates": [SESSION]}, producer_fn=None, acquire_fn=lambda *a, **k: _acquired(tmp_path, SESSION), runtime_fn=lambda *a, **k: {"session": SESSION, "live_count": 7}, trusted_fn=lambda *a, **k: {"session": SESSION, "trusted_subset_ready": True}, macro_regime_acquirer=acquire, macro_cutoff_fn=lambda: CUTOFF, macro_refresh_fn=lambda *a: {"status": "UNAVAILABLE"}, macro_presentation_context_fn=lambda *a, **k: {"status": "UNAVAILABLE"})
    operation = captured["operation"]
    packet = operation["canonical_decision_packet"]
    assert verified_packet(packet) is not None
    security = packet["records"]["AAA"]["security_decision"]
    assert security["posture_condition_class"] == integrated["records"]["AAA"]["posture_condition_class"]
    assert security["research_action_policy_version"] == "v2"
    assert packet["records"]["AAA"]["current_decision_context"]["entry_action"] == "WAIT"
    context = packet["macro_market_regime_context"]
    assert context["dimensions"]["GLOBAL_RATES"]["state"] == ("UNKNOWN" if missing else "TIGHTENING")
    for axis in ("DOMESTIC_RATES", "FX_PRESSURE", "CREDIT_CONTEXT", "DOMESTIC_LIQUIDITY"):
        assert context["dimensions"][axis]["state"] == "UNKNOWN"
    if not missing:
        assert context["conflicts"][0]["winner"] is None
        evidence = context["dimensions"]["GLOBAL_RATES"]["evidence"][0]
        assert all(key in evidence for key in ("source_identity", "indicator_id", "observation_date", "released_at", "retrieved_at", "knowledge_time", "freshness", "authority"))
    bundle = json.loads((captured["operation_dir"] / "ai_research_session_bundle.json").read_text())
    cockpit = json.loads((captured["run_dir"] / "dashboard/current_decision_cockpit_projection.json").read_text())
    assert bundle["macro_market_regime_context"] == cockpit["macro_market_regime_context"] == context
    assert bundle["canonical_decision_packet_identity"] == cockpit["canonical_decision_packet_identity"] == packet["artifact_identity"]
    assert integrated == original
    assert bundle["ticker_research_contexts"]["AAA"]["integrated_decision_v1"]["research_action_posture"] == original["records"]["AAA"]["research_action_posture"]
    assert bundle["ticker_research_contexts"]["AAA"]["integrated_decision_v1"]["posture_condition_class"] == security["posture_condition_class"]
    assert cockpit["decision_card_v1"]["AAA"]["posture_condition_class"] == security["posture_condition_class"]
    files, publication = build_package(captured["operation_dir"], SESSION)
    assert publication["status"] == "READY_FOR_AI"
    assert json.loads(files["ai_research_session_bundle.json"].read_text())["macro_market_regime_context"] == context
    forged = copy.deepcopy(packet)
    forged["macro_market_regime_context"]["dimensions"]["GLOBAL_RATES"]["state"] = "EASING"
    assert verified_packet(forged) is None
    assert not any(key in context for key in ("probability", "target_price", "position_size", "regime_score", "buy_score"))


def test_october7_existing_packet_bytes_and_acquisition_unchanged(tmp_path):
    frozen = human_packet(ticker="AAA", sections={"market": {"note": "sealed"}})
    before = json.dumps(frozen, sort_keys=True)
    context = build_context(macro=macro(), session=SESSION, cutoff=CUTOFF)
    after = human_packet(ticker="AAA", sections={"market": {"note": "sealed"}}, regime_context=context, decision_session="2026-10-07")
    assert json.dumps(after, sort_keys=True) == before
    assert daily.prepare_macro_delivery(tmp_path, "2026-10-07", artifact_root=tmp_path, enrichment={}, acquire_fn=lambda: pytest.fail("must not acquire for completed October7")) == {}
