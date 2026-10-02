from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import prospective_decision_outcome_feedback as feedback
import prospective_decision_retention as retention


def _axis(state: str = "AVAILABLE") -> dict:
    return {
        "state": state, "fitness": "AVAILABLE", "supporting_reason_codes": ["SUPPORT"],
        "contradicting_reason_codes": [], "blocker_reason_codes": [], "method": "existing/v1",
        "lineage": {"source_artifact_identity": "source:1"},
    }


def _condition(role: str, *, operator: str = "FUTURE_CLOSE_GT_RESISTANCE_LEVEL") -> dict:
    return retention.serialize_boundary_condition({
        "status": "READY", "boundary_type": "BREAKOUT", "comparison_operator": operator,
        "source_metric": "resistance" if "GT" in operator else "support", "baseline_value": 100.0,
        "source_rule": "R1", "method": "watchlist_tactical_entry_classifier/v1",
        "evidence_lineage": {"technical": "retained"}, "warnings": [], "reason": "Existing rule.",
    }, role=role, source_strategy_identity="tactical-boundaries:1")


def _decision(session: str, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return {
        "ticker": "FPT", "as_of_session": session, "decision_identity": decision_identity,
        "research_action_posture": "WAIT_FOR_CONFIRMATION", "why_now": "Retained T0 rationale.",
        "priority_posture_reconciliation": {"research_priority_tier": "PRIORITY_NOW"},
        "evidence_axis_coherence": {"state": "ALIGNED"},
        "evidence_axes": {name: _axis() for name in retention.REQUIRED_AXES} if axes else {},
        "trigger": {"trigger_state": "APPROACHING", "condition": _condition("trigger")},
        "invalidation": {"invalidation_level": 90.0, "condition": _condition("invalidation", operator="FUTURE_CLOSE_LT_SUPPORT_LEVEL")},
        "source_identities": {"technical_structure_identity": "structure:1"},
    }


def _price_snapshot(session: str, close: float) -> dict:
    return {
        "resolved_completed_session": session, "snapshot_identity": f"price:{session}",
        "records": {"FPT": {"observations": [{
            "session": session, "close": close, "provider": "DNSE", "dataset": "OHLC",
            "price_basis": "CURRENT_DESCRIPTIVE", "transformation_identity": "normalization/v1",
            "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
        }]}},
    }


def _integrated(session: str, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return {
        "contract_version": "integrated_investment_decision_product/v1", "session": session,
        "artifact_identity": f"integrated:{session}:{decision_identity}", "artifact_sha256": "x" * 64,
        "records": {"FPT": _decision(session, decision_identity=decision_identity, axes=axes)},
    }


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _bind(root: Path, snapshot: dict) -> None:
    session = snapshot["session"]
    operation_identity = snapshot["daily_session_operation_identity"]
    _write(root / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
        "market_session": session, "operation_identity": operation_identity,
        "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
    })
    _write(root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
        "session": session, "daily_session_operation_identity": operation_identity,
        "integrated_investment_decision_product_identity": snapshot["source_integrated_decision_artifact"]["artifact_identity"],
        "prospective_decision_snapshot": {"identity": snapshot["snapshot_identity"]},
    })


def _snapshot(session: str, close: float, *, decision_identity: str = "decision:FPT:one", axes: bool = True) -> dict:
    return retention.build_snapshot(
        session=session, operation_identity=f"daily-operation:{session}", producer_run_identity=f"daily-run:{session}",
        integrated_artifact=_integrated(session, decision_identity=decision_identity, axes=axes),
        exact_session_snapshot=_price_snapshot(session, close),
    )


def test_deterministic_identity_and_warm_rerun_are_append_only(tmp_path: Path):
    first = _snapshot("2026-01-02", 100.0)
    again = _snapshot("2026-01-02", 100.0)
    source_before = copy.deepcopy(_integrated("2026-01-02"))
    assert first == again
    path = retention.write_immutable_snapshot(tmp_path, first)
    assert retention.write_immutable_snapshot(tmp_path, again) == path
    assert retention.validate_snapshot(first)
    assert _integrated("2026-01-02") == source_before


def test_distinct_decision_gets_distinct_snapshot_without_overwriting_t0(tmp_path: Path):
    original = _snapshot("2026-01-02", 100.0, decision_identity="decision:FPT:original")
    changed = _snapshot("2026-01-02", 100.0, decision_identity="decision:FPT:changed")
    assert original["snapshot_identity"] != changed["snapshot_identity"]
    assert retention.write_immutable_snapshot(tmp_path, original) != retention.write_immutable_snapshot(tmp_path, changed)


def test_legacy_missing_axis_stays_field_not_retained_at_t0():
    integrated = _integrated("2026-01-02", axes=False)
    del integrated["records"]["FPT"]["evidence_axes"]
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["status"] == retention.FIELD_NOT_RETAINED
    # The record itself is retained unchanged, so a later evaluator can tell
    # this apart from an unavailable current-market field.
    assert "evidence_axes" not in snapshot["records"]["FPT"]["integrated_decision_at_t0"]


def test_narrative_or_dynamic_condition_remains_explicitly_non_evaluable():
    condition = retention.serialize_boundary_condition({
        "status": "CONDITIONAL", "boundary_type": "BASE_RESOLUTION",
        "source_metric": "ma_20_or_momentum_20d", "warnings": ["DISJUNCTIVE"],
        "reason": "Existing disjunctive rule.",
    }, role="trigger", source_strategy_identity="tactical-boundaries:1")
    assert condition["status"] == "NOT_MACHINE_EVALUABLE"
    assert "EXISTING_BOUNDARY_NOT_REDUCED_TO_NEW_TRIGGER_ENGINE" in condition["reason_codes"]


def test_modern_snapshot_is_the_t0_source_and_t_plus_one_matures_by_trading_session(tmp_path: Path):
    first = _snapshot("2026-01-02", 100.0)
    second = _snapshot("2026-01-05", 104.0)
    for snapshot in (first, second):
        retention.write_immutable_snapshot(tmp_path, snapshot)
        _bind(tmp_path, snapshot)

    # Recreate the Sep-04 regression shape: a mutable working path has a
    # different content identity than the handoff's original source.  It must
    # not replace the sealed T0 snapshot in a later feedback artifact.
    _write(tmp_path / "operations-review" / "integrated-artifacts" / "2026-01-02" / "integrated_investment_decision_product_artifact.json", {
        **_integrated("2026-01-02", decision_identity="decision:FPT:rewritten"),
        "artifact_identity": "integrated:rewritten-after-handoff",
        "requested_at": "2026-01-02T15:00:00+07:00",
    })

    artifact = feedback.build_feedback_artifact(tmp_path)
    row = next(item for item in artifact["feedback_records"] if item["decision_session"] == "2026-01-02")
    horizon = row["forward_outcomes"]["horizons"]["forward_close_return_1"]
    assert row["t0_snapshot_identity"] == first["snapshot_identity"]
    assert row["decision_identity"] == "decision:FPT:one"
    assert horizon["status"] == "MATURE" and horizon["maturation_state"] == "MATURED"
    assert horizon["return"] == pytest.approx(0.04)
    assert row["trigger_invalidation_outcome"]["trigger"]["status"] == "SATISFIED"
    assert artifact["prospective_corpus"]["genuine_immutable_snapshot_count"] == 2


def test_corporate_intelligence_axis_is_retained_and_tracked_when_present():
    """CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1: a FUTURE modern T0
    snapshot must retain the new axis (mission Section 21) with zero code change to the
    verbatim `integrated_decision_at_t0` copy, and _axis_completeness must track it."""
    integrated = _integrated("2026-01-02", axes=True)
    integrated["records"]["FPT"]["evidence_axes"]["CORPORATE_INTELLIGENCE"] = _axis(state="CATALYST_PRESENT")
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is True
    assert item["status"] == "COMPLETE"
    assert "CORPORATE_INTELLIGENCE" not in item["missing_axes"]
    # Verbatim capture requires no producer-side code change: the T0 copy already carries it.
    assert snapshot["records"]["FPT"]["integrated_decision_at_t0"]["evidence_axes"]["CORPORATE_INTELLIGENCE"]["state"] == "CATALYST_PRESENT"


def test_no_qualified_corporate_event_state_is_still_a_complete_retained_axis():
    """A definitive NO_QUALIFIED_CORPORATE_EVENT read is a resolved result, not an incomplete
    one -- it must not be conflated with the axis never having been attempted (NOT_PROVIDED)."""
    integrated = _integrated("2026-01-02", axes=True)
    integrated["records"]["FPT"]["evidence_axes"]["CORPORATE_INTELLIGENCE"] = _axis(state="NO_QUALIFIED_CORPORATE_EVENT")
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is True
    assert item["status"] == "COMPLETE"


def test_legacy_snapshot_without_corporate_intelligence_axis_is_not_retrofitted():
    """A legacy (pre-milestone) integrated decision that never had a CORPORATE_INTELLIGENCE
    axis at all must not be penalized as incomplete, and must not be silently backfilled --
    mission Section 21: legacy snapshots are not reconstructed."""
    integrated = _integrated("2026-01-02", axes=True)
    assert "CORPORATE_INTELLIGENCE" not in integrated["records"]["FPT"]["evidence_axes"]
    snapshot = retention.build_snapshot(
        session="2026-01-02", operation_identity="daily-operation:2026-01-02", producer_run_identity="daily-run:2026-01-02",
        integrated_artifact=integrated, exact_session_snapshot=_price_snapshot("2026-01-02", 100.0),
    )
    item = snapshot["records"]["FPT"]["evidence_axis_snapshot"]
    assert item["corporate_intelligence_retained"] is False
    assert item["status"] == "COMPLETE"
    assert "CORPORATE_INTELLIGENCE" not in snapshot["records"]["FPT"]["integrated_decision_at_t0"]["evidence_axes"]


def test_pending_and_insufficient_depth_are_distinct():
    assert retention.maturity_state(horizon_status="PENDING_NOT_ENOUGH_FUTURE_SESSIONS", later_completed_sessions=0, required_sessions=1) == "PENDING"
    assert retention.maturity_state(horizon_status="PENDING_NOT_ENOUGH_FUTURE_SESSIONS", later_completed_sessions=1, required_sessions=5) == "INSUFFICIENT_FUTURE_DEPTH"
    assert retention.maturity_state(horizon_status="PRICE_BASIS_INCOMPATIBLE", later_completed_sessions=5, required_sessions=5) == "PRICE_SERIES_UNQUALIFIED"


@pytest.mark.parametrize('status,fitness,diagnosis', [
    ('CLOSE_PRICE_NOT_RETAINED', 'T0_CLOSE_NOT_RETAINED', 'T0_CLOSE_NOT_RETAINED'),
    ('CLOSE_PRICE_NOT_RETAINED', 'T0_CLOSE_VALUE_INVALID', 'T0_CLOSE_INVALID'),
    ('PENDING_NOT_ENOUGH_FUTURE_SESSIONS', 'PENDING_FUTURE_SESSION', 'PENDING_COMPLETED_SESSION_DEPTH'),
    ('CLOSE_PRICE_NOT_RETAINED', 'EXACT_CLOSE_MISSING', 'FUTURE_CLOSE_NOT_RETAINED'),
    ('CLOSE_PRICE_NOT_RETAINED', 'CLOSE_VALUE_INVALID', 'FUTURE_CLOSE_INVALID'),
    ('PRICE_BASIS_INCOMPATIBLE', 'INCOMPATIBLE_PRICE_SERIES', 'PRICE_SERIES_INCOMPATIBLE'),
    ('T0_SESSION_NOT_IN_GOVERNED_CHAIN', None, 'T0_SESSION_NOT_QUALIFIED'),
    ('T0_SESSION_NOT_IN_GOVERNED_CHAIN', 'START_CLOSE_NOT_RETAINED', 'T0_SESSION_NOT_QUALIFIED'),
    ('MATURE', 'COMPATIBLE_RETAINED_CLOSE_SERIES', 'MATURE_ENDPOINT_RETURN'),
    ('CLOSE_PRICE_NOT_RETAINED', None, 'UNRESOLVED_CLOSE_GAP'),
    ('UNKNOWN', None, 'UNKNOWN_OUTCOME_FITNESS'),
])
def test_health_preserves_distinct_outcome_gap_causes(status, fitness, diagnosis):
    assert retention._maturity_diagnosis({'status': status, 'series_fitness': fitness}) == diagnosis


def _health_record(ticker='FPT', session='2026-01-02', identity='decision:FPT:1'):
    return {'ticker': ticker, 'decision_session': session, 'decision_identity': identity,
            'temporal_qualification': {'status': retention.GENUINE},
            'forward_outcomes': {'horizons': {'forward_close_return_5': {
                'status': 'CLOSE_PRICE_NOT_RETAINED', 'series_fitness': 'EXACT_CLOSE_MISSING',
                'future_session': '2026-01-09', 'maturation_state': 'PRICE_SERIES_UNQUALIFIED'}}}}


def test_health_reconciles_horizon_denominators_and_exact_future_gaps_without_mutation():
    records = [_health_record(), _health_record('HPG', identity='decision:HPG:1')]
    before = copy.deepcopy(records)
    health = retention.build_corpus_health(snapshot_inventory={}, feedback_artifact={'feedback_records': records})
    maturity = health['outcome_maturity']
    assert maturity['admitted_decision_count'] == 2
    assert maturity['sessions'][0]['horizons']['forward_close_return_5']['affected_future_sessions'] == {'2026-01-09': 2}
    for horizon in maturity['sessions'][0]['horizons'].values():
        assert sum(horizon['diagnosis_counts'].values()) == horizon['decision_count'] == 2
    assert health == retention.build_corpus_health(snapshot_inventory={}, feedback_artifact={'feedback_records': records[::-1]})
    assert records == before
    assert maturity['no_historical_t0_backfill'] is True


def test_health_keeps_unqualified_snapshot_and_legacy_outcome_scopes_separate():
    inventory = {'inventory': [{'session': '2026-01-02', 'classification': 'ORPHAN', 'snapshot_identity': 'orphan:1', 'decision_count': 10}],
                 'handoff_snapshot_inventory': [{'session': '2026-01-05', 'snapshot_status': 'NOT_RETAINED'}]}
    health = retention.build_corpus_health(snapshot_inventory=inventory, feedback_artifact={'feedback_records': [_health_record()]})
    assert len(health['sessions']) == 2
    assert all(not row['identity_qualified'] for row in health['sessions'])
    assert health['outcome_maturity']['admitted_decision_count'] == 1
    assert health['outcome_maturity']['sessions'][0]['decision_count'] == 1


def test_health_excludes_rebuilt_t0_and_rejects_duplicate_decisions():
    row = _health_record(); excluded = copy.deepcopy(row)
    excluded['temporal_qualification']['status'] = 'RETROSPECTIVELY_REBUILT'
    out = retention._maturity_health([excluded])
    assert out['admitted_decision_count'] == 0 and out['excluded_temporal_record_count'] == 1
    with pytest.raises(ValueError, match='DUPLICATE_DECISION'):
        retention._maturity_health([row, copy.deepcopy(row)])
    row['decision_identity'] = None
    with pytest.raises(ValueError, match='DECISION_BINDING_REQUIRED'):
        retention._maturity_health([row])


def test_health_consumer_reuses_canonical_verdict_and_malformed_horizon_is_unknown():
    from tools.run_prospective_decision_retention_outcome_maturation import _health
    row = _health_record(); row['forward_outcomes']['horizons']['forward_close_return_5'] = ['malformed']
    health = retention.build_corpus_health(snapshot_inventory={}, feedback_artifact={'feedback_records': [row]})
    assert health['outcome_maturity']['horizon_diagnosis_counts']['forward_close_return_5'] == {'UNKNOWN_OUTCOME_FITNESS': 1}
    consumer = _health({'prospective_corpus_health': health})
    assert consumer == health
    consumer['outcome_maturity']['sessions'].clear()
    assert health['outcome_maturity']['sessions']


@pytest.mark.parametrize("value", [None, True, False, 0, -3, 1.25, "Tiếng Việt 😀", {"z": [1, None, True, {"á": "☃"}], "a": -0.0}, {str(n): {"nested": [n, "đ" * 20]} for n in range(10000)}])
def test_streaming_hash_exact_canonical_oracle(value):
    import hashlib
    original = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert retention._hash(value) == hashlib.sha256(original.encode("utf-8")).hexdigest()


def test_streaming_hash_nan_still_rejected():
    with pytest.raises(ValueError):
        retention._hash({"nested": [float("nan")]})


def test_streamed_snapshot_bytes_and_identities_equal_original(tmp_path, monkeypatch):
    import hashlib
    snapshot = _snapshot("2026-01-01", 100)
    snapshot["unicode"] = "Tiếng Việt 😀"
    snapshot.pop("snapshot_identity")
    snapshot["snapshot_identity"] = retention.SNAPSHOT_PREFIX + retention._hash(snapshot)
    unsigned = {k: v for k, v in snapshot.items() if k != "snapshot_identity"}
    assert snapshot["snapshot_identity"] == retention.SNAPSHOT_PREFIX + hashlib.sha256(retention._canon(unsigned).encode("utf-8")).hexdigest()
    for row in snapshot["records"].values():
        body = {k: v for k, v in row.items() if k != "prospective_snapshot_record_identity"}
        assert row["prospective_snapshot_record_identity"] == retention.RECORD_PREFIX + hashlib.sha256(retention._canon(body).encode("utf-8")).hexdigest()
    oracle = tmp_path / "old.json"
    oracle.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    expected = oracle.read_bytes()
    # Guard the actual new path against whole-object dumps/read_text.
    monkeypatch.setattr(retention.json, "dumps", lambda *a, **k: pytest.fail("whole-object dumps"))
    path = retention.write_immutable_snapshot(tmp_path, snapshot)
    assert path.read_bytes() == expected
    stat = path.stat()
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("whole-existing snapshot read"))
    assert retention.write_immutable_snapshot(tmp_path, snapshot) == path
    assert path.stat().st_mtime_ns == stat.st_mtime_ns
    assert retention.validate_snapshot(snapshot)


@pytest.mark.parametrize("failure", ["encode", "fsync", "replace"])
def test_failed_stream_write_leaves_destination_and_cleans_temp(tmp_path, monkeypatch, failure):
    snapshot = _snapshot("2026-01-01", 100)
    path = retention.write_immutable_snapshot(tmp_path, snapshot)
    original = path.read_bytes()
    if failure == "encode":
        def broken(*args, **kwargs):
            yield b"partial"
            raise MemoryError("synthetic encoder failure")
        monkeypatch.setattr(retention, "_json_bytes", broken)
        expected = MemoryError
    elif failure == "fsync":
        def fail(*args):
            raise OSError("fsync failed")
        monkeypatch.setattr(retention.os, "fsync", fail)
        expected = OSError
    else:
        snapshot = _snapshot("2026-01-02", 100)
        def fail(*args):
            raise OSError("replace failed")
        monkeypatch.setattr(retention.os, "replace", fail)
        expected = OSError
    with pytest.raises(expected):
        retention.write_immutable_snapshot(tmp_path, snapshot)
    assert path.read_bytes() == original
    assert not list((tmp_path / "operations-review" / "prospective-decision-retention-v1").glob("*/*/*.tmp"))


def test_large_synthetic_snapshot_uses_bounded_batches_and_no_registration(tmp_path):
    snapshot = _snapshot("2026-01-01", 100)
    snapshot["large_nested_evidence"] = [{"n": n, "evidence": "é" * 1000} for n in range(5000)]
    import hashlib
    digest = hashlib.sha256()
    sizes = []
    for block in retention._json_bytes(snapshot):
        digest.update(block)
        sizes.append(len(block))
    assert max(sizes) <= 64 * 1024
    assert retention._hash(snapshot) == digest.hexdigest()
    retention.write_immutable_snapshot(tmp_path, snapshot)
    assert not (tmp_path / "operations-review" / "canonical-post-close-v1").exists()
    assert not (tmp_path / "operations-review" / "daily-research-session-operations-v1").exists()
