from __future__ import annotations

import json
from pathlib import Path

import pytest

import daily_producer_pipeline as producer
import daily_session_shadow_recommendation as daily_shadow


SESSION = "2026-08-28"


def _inputs(session: str = SESSION) -> dict:
    return {
        "descriptive": {"session": session, "artifact_identity": f"market:{session}"},
        "tactical": {"session": session, "artifact_identity": f"tactical:{session}"},
    }


def _chain(inputs: dict, *, session: str = SESSION) -> dict:
    sources = {
        "market": inputs["descriptive"]["artifact_identity"],
        "tactical": inputs["tactical"]["artifact_identity"],
        "fundamental": "fundamental:retained",
    }
    result = {
        "contract_version": daily_shadow.CONTRACT_VERSION,
        "session": session,
        "source_artifact_identities": sources,
        "fundamental_thesis_invalidation_precision": {"artifact_identity": "invalidation:retained"},
        "shadow_security_recommendation": {
            "artifact_identity": "shadow:" + inputs["descriptive"]["artifact_identity"],
            "metadata": {"as_of_session": session},
            "records": {},
        },
    }
    result.update(daily_shadow._identity(result))
    return result


def _write_contexts(root: Path) -> None:
    for relative in daily_shadow.SHARED_CONTEXT_RELATIVE_PATHS.values():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


def test_resolver_builds_then_reuses_exact_same_session_artifact(monkeypatch, tmp_path):
    _write_contexts(tmp_path)
    inputs = _inputs()
    monkeypatch.setattr(daily_shadow, "build", lambda **_: _chain(inputs))
    first = daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=inputs)
    second = daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=inputs)
    assert first["status"] == "BUILT"
    assert second["status"] == "REUSED"
    assert second["chain"]["session"] == SESSION
    assert second["chain"]["shadow_security_recommendation"]["metadata"]["as_of_session"] == SESSION
    assert first["chain"]["artifact_identity"] == second["chain"]["artifact_identity"]


def test_resolver_rejects_wrong_session_corruption_and_changed_same_session_lineage(monkeypatch, tmp_path):
    _write_contexts(tmp_path)
    inputs = _inputs()
    monkeypatch.setattr(daily_shadow, "build", lambda **_: _chain(inputs))
    built = daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=inputs)
    with pytest.raises(daily_shadow.DailySessionShadowRecommendationError, match="SESSION_RESEARCH_INPUTS_MISMATCH"):
        daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=_inputs("2026-08-27"))
    changed = _inputs()
    changed["descriptive"]["artifact_identity"] = "market:changed"
    monkeypatch.setattr(daily_shadow, "build", lambda **_: _chain(changed))
    with pytest.raises(daily_shadow.DailySessionShadowRecommendationError, match="IMMUTABLE_DAILY_SESSION_SHADOW_RECOMMENDATION_CONFLICT"):
        daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=changed)
    built["path"].write_text("{not-json", encoding="utf-8")
    with pytest.raises(daily_shadow.DailySessionShadowRecommendationError, match="RETAINED_DAILY_SHADOW_ARTIFACT_CORRUPT"):
        daily_shadow.resolve_or_build(tmp_path, session=SESSION, inputs=inputs)


def test_daily_producer_autosources_without_manual_parameter_and_threads_exact_packet(monkeypatch, tmp_path):
    inputs = _inputs()
    entries = {name: {"artifact_identity": value["artifact_identity"], "path": name} for name, value in inputs.items()}
    automatic = _chain(inputs)
    calls = {"autosource": 0, "session_operation": 0}
    operation_dir = tmp_path / "operation"
    operation_dir.mkdir()
    for filename in producer.OWNER_FILENAMES:
        (operation_dir / filename).write_bytes(b"{}")
    (operation_dir / "current_decision_cockpit_projection.json").write_text(json.dumps({"projection_identity": "projection:test"}), encoding="utf-8")
    operation = {
        "manifest": {"operation_identity": "operation:test", "input_artifacts": {}, "coverage_summary": {}, "warnings": [], "authority_boundary": {}},
        "product": {"artifact_identity": "product:test"},
    }
    monkeypatch.setattr(producer, "load_registry", lambda *a, **k: {})
    monkeypatch.setattr(producer, "completed_session_gate", lambda *a, **k: {"status": "PASS"})
    monkeypatch.setattr(producer, "resolve_inputs", lambda *a, **k: (inputs, entries))
    monkeypatch.setattr(producer, "validate_coherence", lambda *a, **k: {"session": SESSION})
    monkeypatch.setattr(producer, "build_acquisition_plan", lambda *a, **k: {"items": []})
    monkeypatch.setattr(producer, "_verify_delivery", lambda *a, **k: {"status": "PASS"})

    def autosource(*_args, **kwargs):
        calls["autosource"] += 1
        assert kwargs["session"] == SESSION and kwargs["inputs"] is inputs
        return {"status": "BUILT", "path": tmp_path / "shadow.json", "chain": automatic}

    def session_operation(*_args, **kwargs):
        calls["session_operation"] += 1
        assert kwargs["shadow_security_recommendation"] is automatic["shadow_security_recommendation"]
        return operation, operation_dir

    monkeypatch.setattr(producer, "resolve_or_build_daily_session_shadow_recommendation", autosource)
    monkeypatch.setattr(producer, "run_session_operation", session_operation)
    result = producer.run_daily_producer(
        tmp_path, session=SESSION, latest_completed_session=False,
        producer_head="producer", consumer_head="consumer", now=None,
    )
    assert calls == {"autosource": 1, "session_operation": 1}
    assert result["manifest"]["daily_session_shadow_recommendation"]["status"] == "BUILT"
    assert result["manifest"]["daily_session_shadow_recommendation"]["session"] == SESSION


def test_explicit_override_must_be_same_auto_resolved_artifact():
    automatic = _chain(_inputs())
    resolved = {"chain": automatic}
    assert producer._same_session_shadow_recommendation(
        automatic["shadow_security_recommendation"], resolved, session=SESSION,
    ) == automatic["shadow_security_recommendation"]
    conflicting = dict(automatic["shadow_security_recommendation"])
    conflicting["artifact_identity"] = "shadow:conflict"
    with pytest.raises(producer.DailyProducerError, match="DAILY_SHADOW_EXPLICIT_AUTOSOURCE_CONFLICT"):
        producer._same_session_shadow_recommendation(conflicting, resolved, session=SESSION)
