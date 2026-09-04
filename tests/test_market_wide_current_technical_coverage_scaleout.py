import json
from datetime import datetime, timezone

import pytest

from field_temporal_contract import stable_id
from market_wide_current_technical_coverage_scaleout import (
    build_recovery_artifact,
    content_identity,
    recovery_candidates,
    recovery_record,
)
from tools import run_market_wide_current_technical_coverage_scaleout as runner


TARGET = "2026-08-21"


def _snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def _baseline(records):
    artifact = {"records": records}
    identity = content_identity(artifact)
    return {**artifact, **identity}


def _full_window_observations(count=20):
    return [{"session": f"2026-07-{index + 1:02d}", "close": 10.0 + index, "volume": 1000 + index} for index in range(count)]


def test_selects_only_observed_current_session_records_missing_technical_history():
    snapshot = _snapshot({
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]},
        "BBB": {"disposition": "SESSION_MISSING", "observations": []},
        "CCC": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET, "close": 10.0, "volume": 1000}]},
        "DDD": {"disposition": "EXACT_SESSION_RETAINED", "observations": _full_window_observations()},
    })
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
        "BBB": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
        # CCC and DDD both looked fine as of the prior baseline (SHADOW_ONLY, not MISSING) --
        # CCC's own tonight-snapshot only carries a single bar (e.g. a KBS/VCI gap-recovery
        # projection, see multi_source_exact_session_resolver._project_to_p3f9_shape) and must
        # still be selected; DDD genuinely has a full window tonight and must not be.
        "CCC": {"in_current_descriptive_scope": True, "technical_features": {"status": "SHADOW_ONLY"}},
        "DDD": {"in_current_descriptive_scope": True, "technical_features": {"status": "SHADOW_ONLY"}},
    })
    assert recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot) == ["AAA", "CCC"]


def test_recovery_record_requires_real_target_bar_and_complete_existing_feature_contract():
    target_epoch = int(datetime(2026, 8, 20, 17, tzinfo=timezone.utc).timestamp())
    body = {key: [] for key in ("t", "o", "h", "l", "c", "v")}
    for index in range(20):
        body["t"].append(target_epoch - (19 - index) * 86400)
        body["o"].append(10 + index)
        body["h"].append(10 + index)
        body["l"].append(10 + index)
        body["c"].append(10 + index)
        body["v"].append(100 + index)
    record = recovery_record(
        ticker="AAA", response={"ok": True, "body": body, "provider": "DNSE", "endpoint": "/price/ohlc"},
        target_session=TARGET, query={"symbol": "AAA"}, retrieved_at="2026-08-23T00:00:00+07:00",
    )
    assert record["state"] == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    assert record["attempt_count"] == 1


def test_terminal_recovery_artifact_is_complete_and_deterministic():
    snapshot = _snapshot({"AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]}})
    baseline = _baseline({"AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}}})
    record = {
        "ticker": "AAA", "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "attempt_count": 2,
        "observations": [{"session": TARGET}],
    }
    first = build_recovery_artifact(baseline_artifact=baseline, p3f9b_snapshot=snapshot, batch_records=[{"records": [record]}])
    second = build_recovery_artifact(baseline_artifact=baseline, p3f9b_snapshot=snapshot, batch_records=[{"records": [record]}])
    assert first["acquisition_results"] == {"RECOVERED_COMPLETE_TECHNICAL_HISTORY": 1}
    assert first["artifact_identity"] == second["artifact_identity"]


def _successful_ohlc_body(*, count=20, include_target=True):
    target_epoch = int(datetime(2026, 8, 20, 17, tzinfo=timezone.utc).timestamp())
    latest = target_epoch if include_target else target_epoch - 86400
    body = {key: [] for key in ("t", "o", "h", "l", "c", "v")}
    for index in range(count):
        body["t"].append(latest - (count - index - 1) * 86400)
        body["o"].append(10 + index)
        body["h"].append(10 + index)
        body["l"].append(10 + index)
        body["c"].append(10 + index)
        body["v"].append(100 + index)
    return body


def _run_batch(tmp_path, monkeypatch, responses):
    snapshot = _snapshot({"AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]}})
    baseline = _baseline({"AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}}})
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(runner, "ensure_credentials_loaded", lambda: None)
    monkeypatch.setattr(runner, "credentials_for_request", lambda: ("key", "secret"))
    monkeypatch.setattr(runner, "fetch_capability_raw", fake_fetch)
    runner.run_batch(baseline=baseline, snapshot=snapshot, out=tmp_path, batch=0, batch_size=10)
    batch = json.loads((tmp_path / "batches" / "batch-000.json").read_text(encoding="utf-8"))
    return batch["records"][0], calls


def _response(*, ok, body=None, error_code=None):
    response = {"ok": ok, "provider": "DNSE", "endpoint": "/price/ohlc"}
    if ok:
        response["body"] = body
    else:
        response["error_code"] = error_code
    return response


def test_transient_connection_failure_retries_once_then_recovers(tmp_path, monkeypatch):
    record, calls = _run_batch(tmp_path, monkeypatch, [
        _response(ok=False, error_code="request_failed_ConnectionError"),
        _response(ok=True, body=_successful_ohlc_body()),
    ])
    assert len(calls) == 2
    assert record["state"] == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    assert record["attempt_count"] == 2


def test_exhausted_transient_transport_retries_remain_fetch_failed(tmp_path, monkeypatch):
    record, calls = _run_batch(tmp_path, monkeypatch, [
        _response(ok=False, error_code="request_failed_ConnectionError"),
        _response(ok=False, error_code="request_failed_ConnectionError"),
        _response(ok=False, error_code="request_failed_ConnectionError"),
    ])
    assert len(calls) == runner.MAX_TRANSIENT_TRANSPORT_ATTEMPTS == 3
    assert record["state"] == "FETCH_FAILED"
    assert record["reason"] == "request_failed_ConnectionError"
    assert record["attempt_count"] == 3


@pytest.mark.parametrize(
    ("response", "expected_state"),
    [
        (_response(ok=False, error_code="rate_limited"), "FETCH_FAILED"),
        (_response(ok=True, body=[]), "MALFORMED_RESPONSE"),
        (_response(ok=True, body=_successful_ohlc_body(include_target=False)), "TARGET_SESSION_NOT_RECOVERED"),
        (_response(ok=True, body=_successful_ohlc_body(count=19)), "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK"),
    ],
)
def test_semantic_or_nontransport_provider_failures_are_not_retried(tmp_path, monkeypatch, response, expected_state):
    record, calls = _run_batch(tmp_path, monkeypatch, [response])
    assert len(calls) == 1
    assert record["state"] == expected_state
    assert record["attempt_count"] == 1
