"""Completed-market-session gate: provider evidence primary, 15:30 is a post-close acquisition
attempt floor (2026-09-03 rebaseline, was 18:00 -- see DEFAULT_POST_CLOSE_ATTEMPT_FLOOR)."""
from __future__ import annotations

from datetime import datetime
import inspect
from pathlib import Path

import pytest

import completed_market_session_gate as gate
from vn_time import VN_TZ

SESSION = "2026-08-26"
BEFORE = datetime(2026, 8, 26, 15, 29, tzinfo=VN_TZ)
AFTER = datetime(2026, 8, 26, 15, 35, tzinfo=VN_TZ)
POST_CLOSE = datetime(2026, 8, 26, 19, 19, tzinfo=VN_TZ)


def _working_dates(*dates: str) -> dict:
    return {"workingDates": list(dates)}


def _p3f9b(session: str, *, requested_at: str, exact: int = 889, total: int = 1683, **extra) -> dict:
    payload = {
        "resolved_completed_session": session,
        "retained_snapshot_session": session,
        "snapshot_sha256": "a" * 64,
        "snapshot_identity": "p3f9_exact_session_snapshot:" + "a" * 64,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "attempted_candidate_count": total,
        "exact_session_observed_count": exact,
        "requested_at": requested_at,
    }
    payload.update(extra)
    return payload


def test_before_safety_floor_is_too_early():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=BEFORE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T17:30:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_TOO_EARLY
    assert result["safety_floor_pass"] is False
    assert "BEFORE_SAFETY_FLOOR" in result["reason_codes"]
    assert result["authority_statement"]["provider_confirmed_completed"] is False


def test_after_floor_time_alone_never_ready():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
    )
    assert result["completion_gate_status"] != gate.STATUS_READY
    assert result["safety_floor_pass"] is True
    assert result["completion_gate_status"] == gate.STATUS_PROVIDER_EVIDENCE_UNAVAILABLE
    assert result["ready_semantic"] is None


def test_after_floor_without_exact_session_is_insufficient():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
    )
    assert result["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT
    assert result["safety_floor_pass"] is True


def test_phase_a_after_floor_valid_working_date_is_attempt_eligible_not_ready():
    result = gate.evaluate_attempt_eligibility(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
    )
    assert result["attempt_gate_status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert result["completion_gate_status"] is None
    assert result["ready_semantic"] is None
    assert result["resolved_session"] == SESSION
    assert result["authority_statement"]["provider_confirmed_completed"] is False
    assert "exact_session_data_proven" in result["authority_statement"]["attempt_eligible_does_not_mean"]


def test_phase_a_time_alone_never_attempt_eligible():
    result = gate.evaluate_attempt_eligibility(
        requested_at=AFTER,
        requested_session=SESSION,
    )
    assert result["attempt_gate_status"] != gate.STATUS_ATTEMPT_ELIGIBLE
    assert result["attempt_gate_status"] == gate.STATUS_PROVIDER_EVIDENCE_UNAVAILABLE


def test_phase_a_before_floor_is_too_early_and_not_attempt_eligible():
    result = gate.evaluate_attempt_eligibility(
        requested_at=BEFORE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
    )
    assert result["attempt_gate_status"] == gate.STATUS_TOO_EARLY
    assert result["attempt_gate_status"] != gate.STATUS_ATTEMPT_ELIGIBLE


def test_phase_a_historical_completed_session_outside_current_window_is_eligible():
    result = gate.evaluate_attempt_eligibility(
        requested_at=datetime(2026, 8, 30, 20, 5, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    assert result["attempt_gate_status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert result["resolved_session"] == SESSION
    assert "RETAINED_HISTORICAL_EXACT_SESSION_IDENTITY_CONFIRMED" in result["reason_codes"]


def test_phase_a_historical_session_without_qualified_evidence_fails_closed():
    result = gate.evaluate_attempt_eligibility(
        requested_at=datetime(2026, 8, 30, 20, 5, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
    )
    assert result["attempt_gate_status"] == gate.STATUS_PROVIDER_EVIDENCE_UNAVAILABLE
    assert "WORKING_DATES_WINDOW_DOES_NOT_COVER_SESSION" in result["reason_codes"]
    assert "EXACT_SESSION_EVIDENCE_ABSENT" in result["reason_codes"]


def test_phase_a_historical_target_acquisition_is_explicitly_opt_in():
    result = gate.evaluate_attempt_eligibility(
        requested_at=datetime(2026, 8, 30, 20, 5, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
        allow_historical_target_session_acquisition=True,
    )
    assert result["attempt_gate_status"] == gate.STATUS_ATTEMPT_ELIGIBLE
    assert "ATTEMPT_ELIGIBLE_HISTORICAL_TARGET_SESSION_ACQUISITION" in result["reason_codes"]


def test_valid_working_date_exact_session_after_floor_is_ready():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=POST_CLOSE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00.376043+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_READY
    assert result["resolved_session"] == SESSION
    assert result["ready_semantic"] == gate.READY_SEMANTIC
    assert result["provider_semantic_strength"] == gate.PROVIDER_SEMANTIC_STRENGTH
    assert result["provider_evidence_type"] == gate.PROVIDER_EVIDENCE_TYPE
    assert result["authority_statement"]["provider_confirmed_completed"] is False
    assert result["authority_statement"]["safety_floor_is_not_session_authority"] is True
    assert "market_session_completed" in result["authority_statement"]["working_dates_does_not_prove"]


def test_phase_b_historical_completed_session_outside_current_window_is_ready():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 30, 20, 5, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_READY
    assert result["resolved_session"] == SESSION


def test_working_date_mismatch_fails_closed():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates("2026-08-27", "2026-08-28"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T18:05:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_NON_WORKING_DATE
    assert "NOT_IN_WORKING_DATES" in result["reason_codes"]


def test_explicit_future_session_is_blocked():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session="2026-08-27",
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        exact_session_evidence=_p3f9b("2026-08-27", requested_at="2026-08-27T18:05:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_BLOCKED
    assert "FUTURE_SESSION" in result["reason_codes"]


def test_weekend_explicit_session_fails():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 29, 20, 5, tzinfo=VN_TZ),
        requested_session="2026-08-29",
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
    )
    assert result["completion_gate_status"] == gate.STATUS_NON_WORKING_DATE
    assert "WEEKEND_SESSION" in result["reason_codes"]


def test_holiday_in_observed_window_fails():
    # 2026-09-02 is inside a forward window but omitted from workingDates.
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 9, 2, 20, 5, tzinfo=VN_TZ),
        requested_session="2026-09-02",
        working_dates_evidence=_working_dates("2026-09-01", "2026-09-03"),
    )
    assert result["completion_gate_status"] == gate.STATUS_NON_WORKING_DATE
    assert "NOT_IN_WORKING_DATES" in result["reason_codes"]


def test_omitted_session_resolves_latest_defensible_completed_session():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=POST_CLOSE,
        requested_session=None,
        working_dates_evidence=_working_dates("2026-08-25", SESSION, "2026-08-27"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_READY
    assert result["resolved_session"] == SESSION
    assert result["resolution_method"] == "LATEST_DEFENSIBLE_COMPLETED_WORKING_SESSION"


def test_omitted_session_on_weekend_uses_retained_exact_session_not_weekday_calendar():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 29, 20, 5, tzinfo=VN_TZ),
        requested_session=None,
        working_dates_evidence=_working_dates("2026-08-31", "2026-09-01"),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_READY
    assert result["resolved_session"] == SESSION


def test_stale_prior_session_packet_cannot_satisfy_current_session():
    packet = {
        "contract_version": "capability_first_eod_collector/v1",
        "session_date": "2026-08-21",
        "created_at": "2026-08-21T18:05:00+07:00",
        "packet_identity": "packet:" + "b" * 64,
        "packet_sha256": "b" * 64,
        "observations": [
            {"session": "2026-08-21", "provider_session_date": "2026-08-21", "status": "ACQUIRED"},
        ],
    }
    result = gate.evaluate_completed_market_session_gate(
        requested_at=POST_CLOSE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=packet,
    )
    assert result["completion_gate_status"] == gate.STATUS_SESSION_MISMATCH


def test_pre_cutoff_exact_session_is_insufficient():
    # 15:20 is before the 15:30 floor: must not satisfy the same-day post-close stabilization
    # requirement, even though it is well after the market-wide ~15:00 activity boundary.
    result = gate.evaluate_completed_market_session_gate(
        requested_at=POST_CLOSE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T15:20:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT
    assert "EXACT_SESSION_ACQUIRED_BEFORE_SAFETY_FLOOR" in result["reason_codes"]


def test_provider_evidence_unavailable_is_deterministic():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=None,
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T18:05:00+07:00"),
        allow_provider_probe=False,
    )
    assert result["completion_gate_status"] == gate.STATUS_PROVIDER_EVIDENCE_UNAVAILABLE
    assert result["provider_semantic_strength"] == gate.PROVIDER_SEMANTIC_STRENGTH_UNAVAILABLE
    assert result["authority_statement"]["provider_confirmed_completed"] is False


def test_thin_p3f9b_coverage_is_insufficient():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=AFTER,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T18:05:00+07:00", exact=10, total=1683),
    )
    assert result["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT


def test_gate_does_not_claim_provider_confirmed_completed():
    source = inspect.getsource(gate)
    assert "PROVIDER_CONFIRMED_COMPLETED" not in source or "never claims PROVIDER_CONFIRMED_COMPLETED" in source
    result = gate.evaluate_completed_market_session_gate(
        requested_at=POST_CLOSE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    assert result["authority_statement"]["provider_confirmed_completed"] is False


def test_no_sleep_or_poll_in_gate_module():
    source = inspect.getsource(gate)
    assert "sleep(" not in source
    assert "time.sleep" not in source
    assert "sched" not in source
    assert "BackgroundScheduler" not in source
    assert inspect.getsource(gate.evaluate_completed_market_session_gate).count("while ") == 0
    assert inspect.getsource(gate.evaluate_attempt_eligibility).count("while ") == 0


def test_gate_identity_is_deterministic():
    kwargs = dict(
        requested_at=POST_CLOSE,
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T19:19:00+07:00"),
    )
    first = gate.evaluate_completed_market_session_gate(**kwargs)
    second = gate.evaluate_completed_market_session_gate(**kwargs)
    assert first["gate_identity"] == second["gate_identity"]
    assert first["schema_version"] == gate.SCHEMA_VERSION


def test_load_exact_session_from_scaleout_artifact(tmp_path: Path):
    session = SESSION
    nodash = session.replace("-", "")
    path = (
        tmp_path / "operations-review" / "canonical-post-close-v1" / session
        / "post-close-attempt-191900" / "operations-review"
        / f"p3f9b-market-wide-exact-session-scaleout-{nodash}"
        / "p3f9b_market_wide_exact_session_scaleout_artifact.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        gate.canonical_dump({
            "artifact_identity": "p3f9b_market_wide_exact_session_scaleout:" + "c" * 64,
            "artifact_sha256": "c" * 64,
            "contract_version": "p3f9b_market_wide_exact_session_scaleout/v1",
            "execution_timestamp": "2026-08-26T19:19:00.376043+07:00",
            "exact_session_coverage": {
                "attempted_candidate_count": 1683,
                "exact_session_observed_count": 889,
            },
            "resolved_session": {
                "resolved_completed_session": session,
                "retained_snapshot_session": session,
                "execution_timestamp": "2026-08-26T19:19:00.376043+07:00",
            },
            "snapshot_identity": "p3f9_exact_session_snapshot:" + "c" * 64,
        }),
        encoding="utf-8",
    )
    loaded = gate.load_exact_session_evidence_from_root(tmp_path, session)
    normalized = gate.normalize_exact_session_evidence(loaded)
    assert normalized["resolved_completed_session"] == session
    assert normalized["exact_session_observed_count"] == 889


def test_loader_prefers_later_post_floor_scaleout_over_pre_floor_default(tmp_path: Path):
    session = SESSION
    nodash = session.replace("-", "")
    scaleout_file = "p3f9b_market_wide_exact_session_scaleout_artifact.json"

    def write(path: Path, requested_at: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            gate.canonical_dump({
                "artifact_identity": "p3f9b:" + requested_at,
                "execution_timestamp": requested_at,
                "exact_session_coverage": {"attempted_candidate_count": 1683, "exact_session_observed_count": 889},
                "resolved_session": {
                    "resolved_completed_session": session,
                    "retained_snapshot_session": session,
                    "execution_timestamp": requested_at,
                },
            }),
            encoding="utf-8",
        )

    write(tmp_path / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / scaleout_file, "2026-08-26T16:07:09+07:00")
    write(
        tmp_path / "operations-review" / "canonical-post-close-v1" / session / "post-close-attempt-191900"
        / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / scaleout_file,
        "2026-08-26T19:19:00.376043+07:00",
    )
    loaded = gate.load_exact_session_evidence_from_root(tmp_path, session)
    assert loaded is not None
    assert "19:19:00" in str(loaded.get("execution_timestamp"))


# =====================================================================================
# 2026-09-03 post-close stabilization gate rebaseline: floor moved 18:00 -> 15:30.
# Required test matrix (DAILY_OWNER_FLOW_POST_CLOSE_STABILIZATION_GATE_V1).
# =====================================================================================


def test_default_floor_constant_is_15_30_not_18_00():
    assert gate.DEFAULT_POST_CLOSE_ATTEMPT_FLOOR == gate.time(15, 30)
    # Compatibility alias: any existing importer of the old name still gets the new value.
    assert gate.DEFAULT_SAFETY_FLOOR == gate.DEFAULT_POST_CLOSE_ATTEMPT_FLOOR


@pytest.mark.parametrize(
    "hour,minute,second,expected_status",
    [
        (14, 59, 0, gate.STATUS_TOO_EARLY),
        (15, 0, 0, gate.STATUS_TOO_EARLY),
        (15, 15, 0, gate.STATUS_TOO_EARLY),
        (15, 29, 59, gate.STATUS_TOO_EARLY),
        (15, 30, 0, gate.STATUS_ATTEMPT_ELIGIBLE),
        (15, 35, 0, gate.STATUS_ATTEMPT_ELIGIBLE),
        (17, 0, 0, gate.STATUS_ATTEMPT_ELIGIBLE),
    ],
)
def test_omitted_session_current_day_floor_boundary_sweep(hour, minute, second, expected_status):
    """Owner flow (`stocklookup.ps1 daily`, no --session) on its own qualified working date.
    14:59/15:00/15:15/15:29:59 stay TOO_EARLY (current-session stabilizing, no attempt). 15:30:00
    becomes Phase-A attempt eligible for TODAY, and 15:35/17:00 keep the same eligible behavior --
    17:00 must never regress to TOO_EARLY merely because the old rule required 18:00."""
    requested_at = datetime(2026, 8, 26, hour, minute, second, tzinfo=VN_TZ)
    result = gate.evaluate_attempt_eligibility(
        requested_at=requested_at,
        requested_session=None,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
    )
    assert result["attempt_gate_status"] == expected_status
    if expected_status == gate.STATUS_ATTEMPT_ELIGIBLE:
        assert result["resolved_session"] == SESSION
    else:
        assert "BEFORE_SAFETY_FLOOR" in result["reason_codes"]
        # Not eligible means no session is surfaced as ready to acquire/publish.
        assert result["resolved_session"] is None


def test_explicit_session_today_floor_boundary_sweep():
    """Same boundary, but with an explicit --session equal to today's qualified working date."""
    for hour, minute, expected in ((15, 29, gate.STATUS_TOO_EARLY), (15, 30, gate.STATUS_ATTEMPT_ELIGIBLE)):
        result = gate.evaluate_attempt_eligibility(
            requested_at=datetime(2026, 8, 26, hour, minute, tzinfo=VN_TZ),
            requested_session=SESSION,
            working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        )
        assert result["attempt_gate_status"] == expected


def test_exact_session_evidence_at_or_after_floor_satisfies_time_component():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 26, 15, 40, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T15:30:00+07:00"),
    )
    assert result["completion_gate_status"] == gate.STATUS_READY
    assert result["ready_semantic"] == gate.READY_SEMANTIC


def test_exact_session_evidence_before_floor_does_not_satisfy_time_component():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 26, 15, 40, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T15:20:00+07:00"),
    )
    assert result["completion_gate_status"] != gate.STATUS_READY
    assert "EXACT_SESSION_ACQUIRED_BEFORE_SAFETY_FLOOR" in result["reason_codes"]


def test_at_floor_with_no_exact_evidence_is_not_ready():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 26, 15, 30, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
    )
    assert result["completion_gate_status"] != gate.STATUS_READY
    assert result["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT


def test_at_floor_with_insufficient_coverage_fails_closed():
    result = gate.evaluate_completed_market_session_gate(
        requested_at=datetime(2026, 8, 26, 15, 30, tzinfo=VN_TZ),
        requested_session=SESSION,
        working_dates_evidence=_working_dates(SESSION),
        exact_session_evidence=_p3f9b(SESSION, requested_at="2026-08-26T15:30:00+07:00", exact=10, total=1683),
    )
    assert result["completion_gate_status"] == gate.STATUS_EXACT_SESSION_EVIDENCE_INSUFFICIENT


def test_no_test_requires_the_old_18_00_rule():
    """No fixture in this module may depend on 18:00 -- the gate's own source is the only
    place the retired value name may still appear, purely as a historical/compat comment."""
    import re

    assert "time(18, 0)" not in inspect.getsource(gate)
    this_module_source = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(r"datetime\(2026, \d+, \d+, 18,", this_module_source)
