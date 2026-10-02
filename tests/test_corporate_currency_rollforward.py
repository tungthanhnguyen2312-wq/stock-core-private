from datetime import datetime
from pathlib import Path
import json
import pytest
import corporate_currency_rollforward as r

NOW = datetime.fromisoformat("2026-10-02T12:00:00+07:00")


def seams(tmp_path, monkeypatch, *, retained=True, failure=None, prior=None, materialized=True):
    attempt = dict(disposition="SUCCESS", acquisition_session="2026-10-02", acquired_at="2026-10-02T05:38:59+07:00")
    monkeypatch.setattr(r.acquisition, "_load", lambda path: attempt if retained else None)
    monkeypatch.setattr(r.acquisition, "latest_successful_session", lambda root: prior)
    calls = []
    def acquire(root, **kwargs):
        calls.append(kwargs)
        return dict(attempt) if not failure else dict(disposition="FAILURE", error_message=failure)
    def verify(root, session):
        chosen = attempt if session == "2026-10-02" else prior
        return dict(attempt=chosen, attempt_identity="attempt:"+session)
    def materialize(root, acquisition_session):
        path = root / (acquisition_session+".json")
        path.write_text(json.dumps(dict(artifact_identity="context:"+acquisition_session)), encoding="utf-8")
        return dict(output_path=path.name, artifact_identity="context:"+acquisition_session, materialization_reused=materialized)
    import current_official_event_context
    monkeypatch.setattr(current_official_event_context, "replay", lambda value: None)
    return dict(acquire_fn=acquire, materialize_fn=materialize, verify_fn=verify), calls


def run(root, kwargs, **extra):
    return r.rollforward(root, target_market_session="2026-10-01", observed_at=NOW, allow_acquisition=True, **kwargs, **extra)


def test_missing_success_makes_exactly_one_bounded_call(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch, retained=False)
    result = run(tmp_path, kwargs)
    assert len(calls) == 1
    assert calls[0]["session"] == "2026-10-02"
    assert calls[0]["budget"].limits.max_requests == 64
    assert calls[0]["hnx_rights_window"] == ("2026-09-02", "2026-10-16")
    assert result.receipt()["refresh_action"] == "ACQUIRED_CURRENT_SUCCESS"


def test_retained_success_zero_acquisition_and_separate_lanes(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch)
    frozen = dict(path="old.json", artifact_identity="historical")
    result = run(tmp_path, kwargs, frozen_market_selection=frozen)
    receipt = result.receipt()
    assert calls == []
    assert receipt["refresh_action"] == "REUSED_CURRENT_SUCCESS"
    assert receipt["historical_use_allowed"] is False
    assert receipt["target_market_session"] == "2026-10-01"
    assert receipt["acquisition_civil_date"] == "2026-10-02"
    assert receipt["frozen_market_context"] == frozen
    frozen["artifact_identity"] = "changed externally"
    assert result.receipt()["frozen_market_context"]["artifact_identity"] == "historical"


def test_missing_materialization_recovers_without_acquiring(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch, materialized=False)
    assert run(tmp_path, kwargs).receipt()["refresh_action"] == "RECOVERED_MATERIALIZATION_FROM_RETAINED_SUCCESS"
    assert not calls


@pytest.mark.parametrize("reason", ["REQUEST_BUDGET_EXHAUSTED", "TOTAL_BYTE_BUDGET_EXHAUSTED", "RESPONSE_BYTE_LIMIT_EXCEEDED", "WALL_CLOCK_BUDGET_EXHAUSTED", "PAGE_BUDGET_EXHAUSTED", "SOURCE_FETCH_FAILED", "PARSE_FAILURE"])
def test_failures_are_local_and_never_retry(tmp_path, monkeypatch, reason):
    kwargs, calls = seams(tmp_path, monkeypatch, retained=False, failure=reason)
    result = run(tmp_path, kwargs)
    assert len(calls) == 1
    assert result.current_context() is None
    receipt = result.receipt()
    assert receipt["failure_reason"] == reason
    assert receipt["refresh_action"] == "REFRESH_FAILED_NO_USABLE_CURRENT_CONTEXT"
    assert "research_action_posture" not in receipt


def test_prior_fallback_requires_explicit_age_policy(tmp_path, monkeypatch):
    prior = dict(disposition="SUCCESS", acquisition_session="2026-10-01", acquired_at="2026-10-01T12:00:00+07:00")
    kwargs, calls = seams(tmp_path, monkeypatch, retained=False, failure="outage", prior=prior)
    assert run(tmp_path, kwargs).current_context() is None
    allowed = run(tmp_path, kwargs, prior_descriptive_max_age_days=2)
    assert allowed.receipt()["freshness_state"] == "PRIOR_DESCRIPTIVE_STALE"
    assert allowed.receipt()["refresh_action"] == "REFRESH_FAILED_REUSED_PRIOR_CURRENT_RESEARCH"
    assert run(tmp_path, kwargs, prior_descriptive_max_age_days=0).current_context() is None


def test_corrupt_success_no_refetch_or_prior_switch(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch)
    def corrupt(*args):
        raise ValueError("CAPTURE_SHA256_MISMATCH")
    kwargs["verify_fn"] = corrupt
    result = run(tmp_path, kwargs)
    assert result.current_context() is None
    assert result.receipt()["integrity_verification"] == "FAILED"
    assert not calls


def test_captured_selection_survives_later_path_changes(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch)
    result = run(tmp_path, kwargs)
    (tmp_path / "2026-10-02.json").write_text("corrupt", encoding="utf-8")
    assert result.current_context()["artifact_identity"] == "context:2026-10-02"
    returned = result.receipt()
    returned["refresh_action"] = "tamper"
    assert result.receipt()["refresh_action"] == "REUSED_CURRENT_SUCCESS"


def test_naive_knowledge_time_rejected(tmp_path):
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        r.rollforward(tmp_path, target_market_session="2026-10-01", observed_at=datetime(2026,10,2), allow_acquisition=False)


def test_historical_discovery_never_selects_later_context(tmp_path):
    import daily_session_level2_package as level2
    ops = tmp_path / "operations-review"
    for day in ("20261001", "20261002"):
        path = ops / ("current-official-event-context-integration-v1-"+day)
        path.mkdir(parents=True)
        (path / "current_official_event_context_artifact.json").write_text("{}", encoding="utf-8")
    assert level2.session_artifact_paths(tmp_path, "2026-10-01")["official_event_context"].parent.name.endswith("20261001")
    assert level2.session_artifact_paths(tmp_path, "2026-09-30")["official_event_context"].parent.name.endswith("UNAVAILABLE")
    assert level2._latest_official_event_context_dir(ops).endswith("20261002")


def test_malformed_retained_manifest_fails_locally_without_acquisition(tmp_path, monkeypatch):
    kwargs, calls = seams(tmp_path, monkeypatch)
    def broken(path):
        raise ValueError("MALFORMED_RETAINED_MANIFEST")
    monkeypatch.setattr(r.acquisition, "_load", broken)
    result = run(tmp_path, kwargs)
    assert result.current_context() is None
    assert result.receipt()["failure_reason"] == "MALFORMED_RETAINED_MANIFEST"
    assert not calls
