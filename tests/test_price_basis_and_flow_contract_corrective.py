"""Synthetic contract proofs; prior-chat numeric examples are not retained T0 authority."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

import canonical_market_bars as bars
import flow_price_divergence_shadow as flow
import stocklookup_core.tactical.market_structure_breakout_product_projection as projection
import market_wide_current_descriptive_research as descriptive
import multi_session_signal_velocity as velocity
import mva_daily_research_bundle as features
import stocklookup_core.tactical.tactical_confirmation_invalidation_boundaries as boundaries
import technical_structure_context as structure

SESSION = "2026-10-08"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"


def rows():
    # Numerical examples reproduced synthetically, never relabelled as retained evidence.
    closes = [(30.38 * 20 - 18.25) / 19] * 19 + [18.25]
    return [{"session": (date(2026, 9, 19) + timedelta(days=i)).isoformat(),
        "open": c, "high": c, "low": c, "close": c, "volume": 1000,
        "price_basis": BASIS, "transformation_identity": "identity_provider_numeric_ohlc/v1",
        "source_identity": "synthetic:pnj", "provider": "DNSE"} for i, c in enumerate(closes)]


def artifact(version="v1.3"):
    axes = {n: {"state": next(iter(velocity.RANK[n])), "source_identity": "synthetic:technical"}
            for n in velocity.AXES}
    axes["structural_repair"]["state"] = "REPAIRING"
    axes["setup_maturation"]["state"] = "EARLY"
    axes["fundamental_trajectory"]["trajectory"] = {"latest_transition": "UNCHANGED",
        "recent_direction": "UNCHANGED", "policy_epoch_excluded_observation_count": 0}
    return velocity._identity({"schema_version": "1.2.0", "contract_version": "multi_session_signal_velocity/" + version,
        "source_inventory": [{"session": SESSION, "snapshot_identity": "synthetic:t0", "classification": "QUALIFIED"}],
        "records": [{"ticker": "PNJ", "session": SESSION, "source_snapshot_identity": "synthetic:t0",
            "overall_transition_state": "EARLY_IMPROVEMENT", "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"},
            "axes": axes, "is_actionable": False}]})


def test_price_numeric_parity_and_source_window_qualification():
    source = rows()
    before = deepcopy(source)
    result = features.market_features(source)
    values = result["values"]
    assert values["close"] == 18.25
    assert values["ma_20"] == pytest.approx(30.38)
    assert values["momentum_20d"] == source[-1]["close"] / source[0]["close"] - 1
    q = result["price_basis_qualification"]
    assert result["price_basis"] == "ADJUSTED_RETROSPECTIVE"
    assert q["observed_price_basis"] == BASIS and q["price_basis_verified"] is False
    assert q["comparability"] == "NOT_ESTABLISHED" and not q["historical_pit_eligible"]
    assert len(q["window_evidence"]) == 20 and q["window_evidence"][0]["source_identity"] == "synthetic:pnj"
    assert "IDENTITY_TRANSFORM_IS_NOT_AN_ADJUSTMENT" in q["limitations"]
    assert source == before
    projected = descriptive._technical_features({"observations": source}, target_session=SESSION)
    assert projected["price_basis_qualification"] == q and projected["values"] == values


@pytest.mark.parametrize("claim", [{"event_type": "STOCK_DIVIDEND", "status": "ANNOUNCED"},
    {"status": "QUALIFIED", "official_execution_status": "EXECUTED", "ex_date_status": "EXPLICIT_OFFICIAL",
     "factor_chain_identity": "synthetic:spoof", "adjustment_factor": 0.5}])
def test_event_and_synthetic_factor_claims_cannot_promote_or_reprice(claim):
    source = rows()
    baseline = features.market_features(source)
    for row in source:
        row["factor_chain"] = [claim]
        row["price_basis_verified"] = True
    result = features.market_features(source)
    assert result["values"] == baseline["values"]
    assert result["price_basis_qualification"]["price_basis_verified"] is False


def test_missing_and_mixed_basis_keep_fail_closed_contract():
    source = rows()
    for row in source: row.pop("price_basis")
    result = features.market_features(source)
    assert result["price_basis"] == "unknown" and result["values"]["close"] == 18.25
    source[0]["price_basis"] = BASIS
    result = features.market_features(source)
    assert result["status"] == "MISSING" and result["values"] == {}
    assert "REFERENCE_WINDOW_PRICE_BASIS_INCOMPATIBLE" in result["blockers"]


def test_builder_preserves_sealed_synthetic_fixture_bytes(tmp_path):
    path = tmp_path / "sealed_synthetic_t0.json"
    path.write_text(json.dumps(rows(), ensure_ascii=False, indent=2), encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    features.market_features(json.loads(path.read_text(encoding="utf-8")))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_long_dnse_stamp_stays_research_and_not_pit():
    row = {**rows()[-1], "dataset": "DNSE_OHLC_1D", "retrieved_at": "2026-10-08T10:00:00Z"}
    result = bars.project_daily(row, ticker="PNJ", source_identity="synthetic:sealed")
    assert result["close"] == 18.25 and result["price_basis"] == "RETROSPECTIVE_ADJUSTED"
    assert result["corporate_action_crossing"]["comparability"] == "NOT_ESTABLISHED"
    assert not result["fitness"]["historical_pit_eligible"] and result["price_basis_verified"] is False


@pytest.mark.parametrize("version", ["v1.2", "v1.3"])
def test_valid_versions_native_identity_and_tampered_digest(version):
    source = artifact(version)
    assert set(flow.accept_velocity_for_flow(source, reference_session=SESSION)) == {"PNJ"}
    source["records"][0]["overall_transition_state"] = "STABLE"
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        flow.accept_velocity_for_flow(source, reference_session=SESSION)


@pytest.mark.parametrize("field,value", [("schema_version", "2.0.0"), ("contract_version", "multi_session_signal_velocity/v9"),
    ("supersedes", {"contract_version": "multi_session_signal_velocity/v1.2", "old_artifacts_immutable": True})])
def test_global_compatibility_gates_precede_hash(field, value):
    source = artifact(); source[field] = value
    with pytest.raises(ValueError, match="INCOMPATIBLE"):
        flow.accept_velocity_for_flow(source, reference_session=SESSION)


@pytest.mark.parametrize("defect", ["vocabulary", "missing_axis", "epoch_transition", "epoch_direction", "epoch_exclusion"])
def test_incompatible_record_is_withheld_without_recomputing_overall(defect):
    source = artifact()
    other = deepcopy(source["records"][0]); other["ticker"] = "PAN"
    source["records"].append(other)
    record = source["records"][0]
    trajectory = record["axes"]["fundamental_trajectory"]["trajectory"]
    if defect == "vocabulary": record["axes"]["structural_repair"]["state"] = "NEW_SEMANTICS"
    elif defect == "missing_axis": record["axes"].pop("market_support")
    elif defect == "epoch_transition": trajectory["latest_transition"] = "NOT_COMPARABLE_POLICY_CHANGE"
    elif defect == "epoch_direction": trajectory["recent_direction"] = "NOT_COMPARABLE_POLICY_CHANGE"
    else: trajectory["policy_epoch_excluded_observation_count"] = 1
    source = velocity._identity(source)
    sealed = deepcopy(source)
    refusals = {}
    accepted = flow.accept_velocity_for_flow(source, reference_session=SESSION, exclusions=refusals)
    assert set(accepted) == {"PAN"} and refusals["PNJ"].endswith("INCOMPATIBLE")
    output = flow.build_artifact(reference_session=SESSION, flow_series={}, velocity_artifact=source)
    pnj = next(r for r in output["records"] if r["ticker"] == "PNJ")
    assert pnj["relationship"] == "PRICE_EVIDENCE_INSUFFICIENT" and not pnj["is_actionable"]
    assert "VELOCITY_RECORD_SEMANTICS_INCOMPATIBLE" in pnj["price"]["reason_codes"]
    assert source == sealed


def test_session_source_binding_and_non_voting():
    source = artifact()
    assert flow.accept_velocity_for_flow(source, reference_session="2026-10-07") == {}
    source["records"][0]["source_snapshot_identity"] = "unbound:other"
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        flow.accept_velocity_for_flow(velocity._identity(source), reference_session=SESSION)
    output = flow.build_artifact(reference_session=SESSION, flow_series={}, velocity_artifact=artifact())
    assert output["authority_boundary"]["is_actionable"] is False
    assert output == flow.build_artifact(reference_session=SESSION, flow_series={}, velocity_artifact=artifact())


def test_current_native_producer_output_passes_without_version_rewriting(tmp_path):
    from test_multi_session_signal_velocity import _fixture, _decision
    _fixture(tmp_path, [(SESSION, _decision(SESSION))])
    native = velocity.build_from_retained_root(tmp_path)
    sealed = deepcopy(native)
    assert native["contract_version"] == "multi_session_signal_velocity/v1.3"
    accepted = flow.accept_velocity_for_flow(native, reference_session=SESSION)
    assert set(accepted) == {"FPT"}
    assert native == sealed


@pytest.mark.parametrize("invalid,shared", [(18.75, True), (17.0, False), (None, False)])
def test_pan_horizons_do_not_change_levels_operators_or_verdict(invalid, shared):
    source = {"eligibility": {"status": "ELIGIBLE"}, "trend_context": {"close": 19.0},
        "pivot_context": {"pivot_price": 18.75}, "bos_context": {"broken_level": 35.9},
        "trigger_context": {"status": "AVAILABLE", "trigger_type": "PIVOT_BREAKOUT_TRIGGER", "trigger_level": 18.75, "trigger_state": "UNCHANGED"},
        "invalidation_context": {"status": "AVAILABLE", "invalidation_level": invalid,
        "invalidation_method": "CONFIRMED_SWING_LOW_BY_RULE_OR_V1_SUPPORT_FALLBACK"}}
    result = projection._project_ticker("PAN", source, SESSION)
    assert result["trigger_level"] == 18.75 and result["invalidation_level"] == invalid
    assert result["trigger_close_comparison_operator"] == ">" and result["invalidation_close_comparison_operator"] == "<"
    assert result["trigger_state"] == "UNCHANGED" and result["broken_level"] == 35.9
    assert result["trigger_horizon"] == "PIVOT_BREAKOUT_MEASUREMENT"
    assert result["invalidation_horizon"] == "SWING_STRUCTURE_ANALYTICAL_CONTEXT"
    assert ("SHARED_LEVEL_DISTINCT_HORIZONS" in result["warnings"]) is shared
    assert result["shared_level_status"] == ("SHARED_BOUNDARY" if shared else "DISTINCT_BOUNDARIES" if invalid is not None else "UNAVAILABLE_BOUNDARIES")
    assert not result["authority"]["is_actionable"]


def test_boundary_numeric_and_operator_parity_with_unverified_lineage():
    tech = features.market_features(rows())
    ctx = boundaries._context(tactical_record={"entry_state": "BREAKOUT_READY", "rule_id": "synthetic:rule"},
        descriptive_record={"technical_features": tech}, structure_record={"structure_context": {
            "status": "AVAILABLE", "resistance": {"value": 36.9}, "support": {"value": 35.9}}})
    level = boundaries._level_boundary(boundary_type="TEST", direction="ABOVE_TO_CONFIRM", operator="FUTURE_CLOSE_GT_RESISTANCE_LEVEL",
        level_name="resistance", ctx=ctx, reason="test", fallback_reason="test")
    ma = boundaries._ma_boundary(boundary_type="TEST", direction="ABOVE_TO_CONFIRM", operator="FUTURE_CLOSE_GT_FUTURE_MA20", ctx=ctx, reason="test")
    assert level["value"] == 36.9 and ma["value"] == pytest.approx(30.38)
    for result in (level, ma):
        assert result["unit"] == "UNVERIFIED_RESEARCH_PRICE"
        assert result["evidence_lineage"]["price_basis_qualification"]["price_basis_verified"] is False


def test_baseline_golden_structure_states_levels_and_lineage_are_unchanged():
    path = Path(__file__).parent / "fixtures" / "price_basis_corrective_synthetic_golden.json"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    fixture = json.loads(path.read_text(encoding="utf-8"))
    source = fixture["rows"]
    record = structure._classify_ticker("PNJ", descriptive_record=fixture["descriptive"],
        pf_record={"observations": source}, target_session=source[-1]["session"])
    qualification = record["price_basis_qualification"]
    for name in ("trend_context", "structure_context", "swing_structure", "bos_context", "pivot_context", "trigger_context", "invalidation_context"):
        assert record[name]["price_basis_qualification"] == qualification
    def legacy(value):
        if isinstance(value, dict): return {k: legacy(v) for k, v in value.items() if k != "price_basis_qualification"}
        if isinstance(value, list): return [legacy(v) for v in value]
        return value
    record.pop("warnings")
    assert legacy(record) == fixture["expected_structure"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    source[0]["transformation_identity"] = "mixed:other"
    refused = structure._classify_ticker("PNJ", descriptive_record=fixture["descriptive"],
        pf_record={"observations": source}, target_session=source[-1]["session"])
    assert "REFERENCE_WINDOW_PRICE_BASIS_INCOMPATIBLE" in refused["blockers"]


@pytest.mark.parametrize("adapter_version", ["v1", "v2"])
@pytest.mark.parametrize("epoch_break", [False, True])
def test_retained_adapters_share_gate_and_preserve_source_bytes(tmp_path, monkeypatch, adapter_version, epoch_break):
    from test_volume_and_flow_retained import fixture, ASOF
    from bounded_artifact_stream import source_hash
    import volume_and_flow_retained as v1
    import volume_and_flow_retained_v2 as v2
    import volume_and_flow_context as context
    adapter = v1 if adapter_version == "v1" else v2
    root, runtime, batch = fixture(tmp_path, monkeypatch)
    source = artifact()
    row = source["records"][0]
    row.update(ticker="VNM", session=ASOF)
    source["source_inventory"][0]["session"] = ASOF
    if epoch_break: row["axes"]["fundamental_trajectory"]["trajectory"]["policy_epoch_excluded_observation_count"] = 1
    source = velocity._identity(source)
    before = {str(p): source_hash(p) for p in root.rglob("*.json")}
    result, audit = adapter.collect(source_root=root, runtime_root=runtime, session=ASOF,
        feature_batch=batch, feature_batch_sha256=source_hash(batch), velocity_artifact=source)
    assert audit["source_bytes_unchanged"] and before == {str(p): source_hash(p) for p in root.rglob("*.json")}
    expected = {"VNM": "VELOCITY_RECORD_SEMANTICS_INCOMPATIBLE"} if epoch_break else {}
    assert audit["velocity_record_exclusions"] == result["velocity_compatibility"]["record_exclusions"] == expected
    assert result["velocity_compatibility"]["non_voting"] is True
    context.verify(result, context.CONTRACT_VERSION)
    assert result["authority_effect"] == context.AUTHORITY_EFFECT
    source["artifact_sha256"] = "tampered"
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        adapter.collect(source_root=root, runtime_root=runtime, session=ASOF,
            feature_batch=batch, feature_batch_sha256=source_hash(batch), velocity_artifact=source)
