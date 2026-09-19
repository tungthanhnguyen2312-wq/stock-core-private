from __future__ import annotations

import json
import hashlib

import pytest

import canonical_post_close_pipeline as cpc
import flow_price_divergence_shadow as shadow


SESSION = "2026-09-18"


def _series(*, net: int | None = -10, freshness: str = "current", latest: str = SESSION,
            five: str = "complete", ten: str = "complete", sell_streak: int = 0,
            buy_streak: int = 0, cumulative: int = -50) -> dict:
    return {
        "status": "available", "ticker": "AAA",
        "latest_session": {"foreign_net_value_vnd": net},
        "freshness": {"status": freshness, "reference_session_date": SESSION,
                      "latest_qualified_session_date": latest, "sessions_behind": 0 if freshness == "current" else 1},
        "window_summaries": {
            "5_session": {"coverage": five, "sessions": ["2026-09-12", "2026-09-15", "2026-09-16", "2026-09-17", SESSION], "cumulative_net_value_vnd": cumulative},
            "10_session": {"coverage": ten, "sessions": []},
        },
        "current_consecutive_net_sell_sessions": sell_streak,
        "current_consecutive_net_buy_sessions": buy_streak,
    }


def _velocity(*, overall: str = "EARLY_IMPROVEMENT", structural: str = "REPAIRING",
              setup: str = "EARLY", participation: str = "IMPROVING", session: str = SESSION,
              quality: str = "COMPLETE_RETAINED_EVIDENCE") -> dict:
    value = {
        "contract_version": shadow.VELOCITY_CONTRACT_VERSION,
        "records": [{"ticker": "AAA", "session": session, "overall_transition_state": overall,
                     "source_snapshot_identity": "snapshot:test", "evidence_quality": {"state": quality},
                     "axes": {"structural_repair": {"state": structural, "source_identity": "technical:test"},
                              "setup_maturation": {"state": setup},
                              "participation_confirmation": {"state": participation},
                              "market_support": {"state": "SUPPORTIVE"}, "sector_support": {"state": "SUPPORTIVE"}}}],
    }
    digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    value.update(artifact_sha256=digest, artifact_identity="multi_session_signal_velocity:" + digest)
    return value


def _row(series: dict | None = None, velocity: dict | None = None) -> dict:
    return shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": series or _series()}, velocity_artifact=velocity or _velocity())["records"][0]


def test_qualified_value_only_flow_is_the_only_flow_input_and_is_deterministic():
    series = _series()
    series["latest_session"].update({"foreign_volume": 999999, "foreign_room": 999999})
    first = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": series}, velocity_artifact=_velocity())
    assert first == shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": series}, velocity_artifact=_velocity())
    serialized = json.dumps(first["records"][0]["flow"])
    assert "volume" not in serialized.lower() and "room" not in serialized.lower()


def test_missing_flow_is_not_neutral_or_zero():
    row = _row({"status": "missing", "freshness": {}, "latest_session": {}, "window_summaries": {}})
    assert row["flow"]["state"] == "FLOW_UNAVAILABLE"
    assert row["relationship"] == "FLOW_UNAVAILABLE"


def test_exact_alignment_is_required_and_stale_flow_cannot_claim_current_relationship():
    row = _row(_series(freshness="stale", latest="2026-09-17"))
    assert row["session_alignment"]["state"] == "STALE_NOT_COMPARABLE"
    assert row["relationship"] == "FLOW_UNAVAILABLE"
    assert row["evidence_quality"] == "LIMITED_STALE_FLOW_CONTEXT"


def test_future_flow_fails_closed_as_semantically_blocked():
    row = _row(_series(freshness="unknown", latest="2026-09-19"))
    assert row["flow"]["state"] == "SEMANTICALLY_BLOCKED"
    assert row["session_alignment"]["state"] == "SESSION_MISMATCH"


def test_complete_five_session_streak_enables_persistence_but_incomplete_window_does_not():
    persistent = _row(_series(sell_streak=5))
    incomplete = _row(_series(sell_streak=5, five="incomplete"))
    assert persistent["flow"]["persistence"] == "PERSISTENT_NET_SELL"
    assert persistent["relationship"] == "PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE"
    assert incomplete["flow"]["persistence"] == "INSUFFICIENT_HISTORY"


def test_complete_ten_session_coverage_is_reported_without_claiming_ten_session_persistence():
    artifact = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": _series(ten="complete")}, velocity_artifact=_velocity())
    assert artifact["validation"]["ten_session_complete_count"] == 1
    assert "10" not in artifact["records"][0]["flow"]["persistence"]


def test_recent_reversal_is_explicit_not_hidden_by_window_direction():
    row = _row(_series(net=-10, cumulative=50))
    assert row["flow"]["persistence"] == "RECENT_SELL_REVERSAL"


@pytest.mark.parametrize(("net", "overall", "expected"), [
    (-10, "EARLY_IMPROVEMENT", "FOREIGN_SELLING_PRICE_RESILIENCE"),
    (-10, "DETERIORATING", "FOREIGN_SELLING_PRICE_WEAKNESS"),
    (10, "EARLY_IMPROVEMENT", "FOREIGN_BUYING_PRICE_CONFIRMATION"),
    (10, "DETERIORATING", "FOREIGN_BUYING_PRICE_WEAKNESS"),
    (0, "EARLY_IMPROVEMENT", "FLOW_NEUTRAL_PRICE_IMPROVING"),
])
def test_relationship_taxonomy_is_descriptive(net: int, overall: str, expected: str):
    assert _row(_series(net=net, cumulative=net * 5), _velocity(overall=overall))["relationship"] == expected


def test_flat_stable_session_is_not_mislabeled_as_selling_resilience():
    row = _row(_series(), _velocity(overall="STABLE"))
    assert row["price"]["state"] == "PRICE_RESILIENT_OR_STABLE"
    assert row["relationship"] == "FLOW_PRICE_MIXED"


@pytest.mark.parametrize(("structural", "setup"), [("ADVERSE", "EARLY"), ("REPAIRING", "INVALID")])
def test_technical_veto_overrides_market_sector_context(structural: str, setup: str):
    row = _row(_series(), _velocity(structural=structural, setup=setup))
    assert row["price"]["state"] == "PRICE_INVALID_OR_BREAKDOWN"
    assert row["relationship"] == "FOREIGN_SELLING_PRICE_WEAKNESS"


@pytest.mark.parametrize(("participation", "expected"), [("IMPROVING", "PARTICIPATION_CORROBORATES"), ("DIVERGENT", "PARTICIPATION_CONTRADICTS"), ("UNAVAILABLE", "PARTICIPATION_UNAVAILABLE")])
def test_participation_is_separate_context(participation: str, expected: str):
    assert _row(_series(), _velocity(participation=participation))["price"]["participation_context"] == expected


def test_old_velocity_contract_cannot_substitute_for_v12():
    velocity = _velocity(); velocity["contract_version"] = "multi_session_signal_velocity/v1.1"
    with pytest.raises(ValueError, match="REQUIRE_SIGNAL_VELOCITY_V1_2"):
        shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": _series()}, velocity_artifact=velocity)


def test_future_retained_flow_does_not_change_earlier_artifact():
    before = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": _series()}, velocity_artifact=_velocity())
    with_future = _series(); with_future["future_observation"] = {"session": "2026-09-19", "foreign_net_value_vnd": 99}
    after = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": with_future}, velocity_artifact=_velocity())
    # The explicit store projection does not consume arbitrary future fields.
    assert before["records"][0]["relationship"] == after["records"][0]["relationship"]


def test_public_contract_contains_no_action_or_causal_promotion_fields():
    artifact = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": _series()}, velocity_artifact=_velocity())
    data = json.dumps(artifact["records"]).lower()
    for forbidden in ("smart_money", "smart money", "absorption", "domestic_accumulation", "institutional_intent", "recommendation", "target_price", "probability", "score"):
        assert forbidden not in data
    assert artifact["authority_boundary"]["is_actionable"] is False
    assert artifact["authority_boundary"]["no_score_probability_recommendation_or_execution"] is True


def test_daily_collector_success_is_exact_session_bound_and_compact(tmp_path, monkeypatch):
    velocity = _velocity(); velocity["validation"] = {"latest_session": SESSION}
    body = {key: value for key, value in velocity.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    velocity.update(artifact_sha256=digest, artifact_identity="multi_session_signal_velocity:" + digest)
    path = tmp_path / "operations-review" / "multi-session-signal-velocity-v1.2" / SESSION / "multi_session_signal_velocity_artifact.json"
    path.parent.mkdir(parents=True); path.write_text(json.dumps(velocity), encoding="utf-8")
    artifact = shadow.build_artifact(reference_session=SESSION, flow_series={"AAA": _series()}, velocity_artifact=velocity)
    monkeypatch.setattr(shadow, "collect_from_retained_runtime", lambda **_: artifact)
    # The canonical runner imports the helper at invocation, so patch its source module.
    result = cpc.run_flow_price_divergence_shadow(tmp_path, tmp_path / "runtime", SESSION, {"status": "COLLECTED", "path": path.relative_to(tmp_path).as_posix(), "artifact_identity": velocity["artifact_identity"]})
    assert result["status"] == "COLLECTED"
    assert result["artifact_identity"] == artifact["artifact_identity"]
    assert set(result) == {"status", "session", "contract_version", "path", "artifact_identity", "relationship_evaluable_count", "coverage_status", "authority_boundary"}


def test_daily_collector_failure_is_nonblocking(tmp_path, monkeypatch):
    velocity = _velocity(); velocity["validation"] = {"latest_session": SESSION}
    body = {key: value for key, value in velocity.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    velocity.update(artifact_sha256=digest, artifact_identity="multi_session_signal_velocity:" + digest)
    monkeypatch.setattr(cpc, "_load", lambda _: velocity)
    monkeypatch.setattr(shadow, "collect_from_retained_runtime", lambda **_: (_ for _ in ()).throw(RuntimeError("retained failure")))
    result = cpc.run_flow_price_divergence_shadow(tmp_path, tmp_path / "runtime", SESSION, {"status": "COLLECTED", "path": "velocity.json", "artifact_identity": velocity["artifact_identity"]})
    assert result["status"] == "UNAVAILABLE"
    assert "RETAINED_FLOW_PRICE_DIVERGENCE_FAILED" in result["reason"]
