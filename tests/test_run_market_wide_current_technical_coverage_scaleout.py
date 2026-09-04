"""DAILY_LIVE_ACQUISITION_FAIL_FAST_AND_ZERO_RECOVERY_CORRECTIVE_V1 defect 1: consolidate() must
not crash with FileNotFoundError when recovery_candidates() returns zero candidates. run_batch()
is the only thing that previously created the ``out`` directory (as a side effect of mkdir(parents
=True) for its sibling batches/ subdirectory); with zero candidates it never runs, so ``out``
never existed before consolidate() tried to write into it -- exactly the live 2026-09-03 failure
(P3F9B exact coverage 17/1683)."""
import json

import pytest

from field_temporal_contract import stable_id
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
