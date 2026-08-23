from datetime import datetime, timezone

from field_temporal_contract import stable_id
from market_wide_current_technical_coverage_scaleout import (
    build_recovery_artifact,
    content_identity,
    recovery_candidates,
    recovery_record,
)


TARGET = "2026-08-21"


def _snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def _baseline(records):
    artifact = {"records": records}
    identity = content_identity(artifact)
    return {**artifact, **identity}


def test_selects_only_observed_current_session_records_missing_technical_history():
    snapshot = _snapshot({
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]},
        "BBB": {"disposition": "SESSION_MISSING", "observations": []},
        "CCC": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]},
    })
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
        "BBB": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
        "CCC": {"in_current_descriptive_scope": True, "technical_features": {"status": "SHADOW_ONLY"}},
    })
    assert recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot) == ["AAA"]


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


def test_terminal_recovery_artifact_is_complete_and_deterministic():
    snapshot = _snapshot({"AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]}})
    baseline = _baseline({"AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}}})
    record = {"ticker": "AAA", "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "observations": [{"session": TARGET}]}
    first = build_recovery_artifact(baseline_artifact=baseline, p3f9b_snapshot=snapshot, batch_records=[{"records": [record]}])
    second = build_recovery_artifact(baseline_artifact=baseline, p3f9b_snapshot=snapshot, batch_records=[{"records": [record]}])
    assert first["acquisition_results"] == {"RECOVERED_COMPLETE_TECHNICAL_HISTORY": 1}
    assert first["artifact_identity"] == second["artifact_identity"]
