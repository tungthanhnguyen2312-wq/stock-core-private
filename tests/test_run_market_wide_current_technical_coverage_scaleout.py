"""DAILY_LIVE_ACQUISITION_FAIL_FAST_AND_ZERO_RECOVERY_CORRECTIVE_V1 defect 1: consolidate() must
not crash with FileNotFoundError when recovery_candidates() returns zero candidates. run_batch()
is the only thing that previously created the ``out`` directory (as a side effect of mkdir(parents
=True) for its sibling batches/ subdirectory); with zero candidates it never runs, so ``out``
never existed before consolidate() tried to write into it -- exactly the live 2026-09-03 failure
(P3F9B exact coverage 17/1683)."""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from field_temporal_contract import stable_id
from market_wide_current_descriptive_research import (
    MarketWideCurrentDescriptiveResearchError,
    build_artifact,
)
from market_wide_current_liquidity_research import content_identity as liquidity_content_identity
from market_wide_current_technical_coverage_scaleout import content_identity
from tools import run_market_wide_current_technical_coverage_scaleout as runner

TARGET = "2026-09-03"


def _snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def _baseline(records):
    artifact = {"records": records}
    identity = content_identity(artifact)
    return {**artifact, **identity}


def _artifact_path(out):
    return out / "market_wide_current_technical_coverage_recovery_artifact.json"


def test_consolidate_zero_candidates_creates_the_missing_output_directory(tmp_path):
    out = tmp_path / "market-wide-current-technical-coverage-scaleout-v1-20260903"
    assert not out.exists()
    baseline = _baseline({})
    snapshot = _snapshot({})

    runner.consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=10)

    assert out.is_dir()
    assert _artifact_path(out).is_file()


def test_consolidate_zero_candidates_artifact_is_semantically_empty(tmp_path):
    out = tmp_path / "out"
    baseline = _baseline({})
    snapshot = _snapshot({})

    runner.consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=10)

    artifact = json.loads(_artifact_path(out).read_text(encoding="utf-8"))
    assert artifact["target_session"] == TARGET
    assert artifact["candidate_selection"]["count"] == 0
    assert artifact["candidate_selection"]["tickers"] == []
    assert artifact["records"] == {}
    assert artifact["recovered_history_overrides"] == {}
    assert artifact["acquisition_results"] == {}


def test_consolidate_zero_candidates_does_not_fabricate_recovered_records(tmp_path):
    # A ticker present in the universe but not itself eligible for recovery (already has a
    # complete technical window, tonight and at baseline) still yields a zero-candidate cohort.
    # Zero candidates is not the same as zero tickers, and consolidate() must never invent a
    # recovered record for it.
    out = tmp_path / "out"
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "SHADOW_ONLY"}},
    })
    snapshot = _snapshot({
        "AAA": {
            "disposition": "EXACT_SESSION_RETAINED",
            "observations": [{"session": f"2026-08-{index + 1:02d}", "close": 10.0 + index, "volume": 1000 + index} for index in range(20)],
        },
    })

    runner.consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=10)

    artifact = json.loads(_artifact_path(out).read_text(encoding="utf-8"))
    assert artifact["candidate_selection"]["count"] == 0
    assert artifact["records"] == {}
    assert "AAA" not in artifact["recovered_history_overrides"]


def test_ordinary_nonzero_batch_consolidation_still_works(tmp_path):
    out = tmp_path / "out"
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
    })
    snapshot = _snapshot({
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]},
    })
    batch_dir = out / "batches"
    batch_dir.mkdir(parents=True)
    record = {
        "ticker": "AAA", "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "attempt_count": 1,
        "observations": [{"session": TARGET}],
    }
    (batch_dir / "batch-000.json").write_text(json.dumps({"batch": 0, "records": [record]}), encoding="utf-8")

    runner.consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=10)

    artifact = json.loads(_artifact_path(out).read_text(encoding="utf-8"))
    assert artifact["candidate_selection"]["count"] == 1
    assert artifact["records"]["AAA"]["state"] == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
    assert artifact["recovered_history_overrides"]["AAA"]["state"] == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"


def test_consolidate_missing_batch_for_a_nonzero_cohort_still_raises(tmp_path):
    # Regression guard: the new mkdir must not paper over a genuinely missing (non-zero-candidate)
    # batch -- only the zero-candidate case is legitimate.
    out = tmp_path / "out"
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
    })
    snapshot = _snapshot({
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET}]},
    })

    with pytest.raises(ValueError, match="MISSING_RECOVERY_BATCH"):
        runner.consolidate(baseline=baseline, snapshot=snapshot, out=out, batch_size=10)
    assert not _artifact_path(out).exists()


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _run_all_ohlc_body(*, count=20):
    """20 daily closes ending exactly on TARGET (2026-09-03), in DNSE's raw epoch/VN-session shape."""
    target_epoch = int(datetime(2026, 9, 2, 17, tzinfo=timezone.utc).timestamp())  # 2026-09-03T00:00 VN
    body = {key: [] for key in ("t", "o", "h", "l", "c", "v")}
    for index in range(count):
        body["t"].append(target_epoch - (count - index - 1) * 86400)
        body["o"].append(10 + index)
        body["h"].append(10 + index)
        body["l"].append(10 + index)
        body["c"].append(10 + index)
        body["v"].append(100 + index)
    return body


def _universe_resolution(records, *, denominator, observed):
    payload = {
        "records": records,
        "current_active_equity_denominator": {"count": denominator},
        "observed_session_cohort": {"count": observed},
        "input_candidates": {"resolved_completed_session": TARGET},
    }
    digest = _hash(payload)
    return {**payload, "artifact_sha256": digest, "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{digest}"}


def _liquidity_artifact(records, *, snapshot_identity):
    payload = {
        "records": records, "resolved_completed_session": TARGET,
        "universe": {"canonical_candidate_count": len(records), "source_snapshot_identity": snapshot_identity},
        "coverage": {"disposition_counts": {}},
        "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": False},
    }
    identity = liquidity_content_identity(payload)
    return {**payload, **identity}


def test_run_all_produces_a_self_consistent_artifact_that_downstream_accepts_and_rejects_when_mutated(tmp_path, monkeypatch):
    """Regression for the orchestration-boundary defect: run_all() used to finalize the artifact's
    canonical identity *before* stamping operational_summary.HISTORY_RECOVERY_RUNTIME onto it, so
    the stored artifact_sha256 never matched a fresh recomputation over the actual persisted
    payload -- market_wide_current_descriptive_research.build_artifact() correctly rejected every
    such artifact with TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH. The fix threads the runtime
    diagnostic into build_recovery_artifact() before it computes content_identity(), so identity is
    computed exactly once over the complete, final payload."""
    baseline = _baseline({
        "AAA": {"in_current_descriptive_scope": True, "technical_features": {"status": "MISSING"}},
    })
    snapshot = _snapshot({
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": TARGET, "close": 29.0, "volume": 129}]},
    })
    body = _run_all_ohlc_body()

    monkeypatch.setattr(runner, "ensure_credentials_loaded", lambda: None)
    monkeypatch.setattr(runner, "credentials_for_request", lambda: ("key", "secret"))
    monkeypatch.setattr(runner, "fetch_capability_raw", lambda *args, **kwargs: {"ok": True, "body": body, "provider": "DNSE", "endpoint": "/price/ohlc"})

    out = tmp_path / "out"
    runner.run_all(baseline=baseline, snapshot=snapshot, out=out)

    artifact = json.loads(_artifact_path(out).read_text(encoding="utf-8"))

    # 1) artifact is produced.
    assert artifact["target_session"] == TARGET

    # 2) HISTORY_RECOVERY_RUNTIME is present where the --all contract expects it, and the actual
    #    recovery it summarizes really happened.
    assert "HISTORY_RECOVERY_RUNTIME" in artifact["operational_summary"]
    assert artifact["recovered_history_overrides"]["AAA"]["state"] == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"

    # 3) stored canonical identity equals fresh deterministic recomputation over the final payload
    #    -- this is the line that failed before the fix (stored 07cbc638... vs recomputed b26c5723...
    #    in the live handoff evidence).
    recomputed = content_identity(artifact)
    assert artifact["artifact_sha256"] == recomputed["artifact_sha256"]
    assert artifact["artifact_identity"] == recomputed["artifact_identity"]

    # 4) downstream descriptive research accepts the valid finalized artifact.
    ur = _universe_resolution({"AAA": {"activity_and_session_state": "ACTIVE_LISTED_OBSERVED", "membership_state": "INCLUDED"}}, denominator=1, observed=1)
    liq = _liquidity_artifact({"AAA": {"ticker": "AAA", "disposition": "MISSING", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}}, snapshot_identity=snapshot["snapshot_identity"])
    downstream = build_artifact(
        universe_resolution_artifact=ur, p3f9b_snapshot=snapshot, liquidity_artifact=liq,
        entity_classifications={}, technical_history_recovery_artifact=artifact,
    )
    assert downstream["records"]["AAA"]["technical_features"]["technical_history_provenance"]["source"] == "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY"

    # 5) a post-identity mutation of the artifact -- exactly the class of defect that was fixed --
    #    still causes downstream identity rejection. Fail-closed behavior must be preserved.
    mutated = json.loads(json.dumps(artifact))
    mutated["operational_summary"]["HISTORY_RECOVERY_RUNTIME"] = dict(mutated["operational_summary"]["HISTORY_RECOVERY_RUNTIME"], tampered=True)
    with pytest.raises(MarketWideCurrentDescriptiveResearchError, match="TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH"):
        build_artifact(
            universe_resolution_artifact=ur, p3f9b_snapshot=snapshot, liquidity_artifact=liq,
            entity_classifications={}, technical_history_recovery_artifact=mutated,
        )
