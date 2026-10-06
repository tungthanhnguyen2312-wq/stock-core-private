"""Population-separated outcome review. Fixtures are not ticker branches."""
from __future__ import annotations

import json
from pathlib import Path

import decision_outcome_calibration_review as review


def _row(**overrides):
    base = {
        "population": review.PROSPECTIVE_GENUINE,
        "population_reason": "SOURCE_TYPE",
        "source_type": "QUALIFIED_LEGACY_INTEGRATED_T0",
        "session": "2026-09-03",
        "ticker": "AAA",
        "posture": "EARLY_REVERSAL",
        "tactical_state": "EARLY_REVERSAL_CANDIDATE",
        "regime": "MIXED_BREADTH",
        "horizon": 5,
        "status": review.MATURE,
        "forward_return": 0.02,
        "mfe": 0.04,
        "mae": -0.01,
        "outcome_label": "INSUFFICIENT_OUTCOME_EVIDENCE",
        "warnings": None,
        "supportive_features_present": None,
        "refused_horizons": [],
    }
    base.update(overrides)
    return base


def test_populations_are_not_pooled():
    rows = [
        _row(forward_return=0.05),
        _row(population=review.RECONSTRUCTED_RESEARCH, source_type="PANEL", session="2026-09-04", forward_return=-0.02),
    ]
    built = review.review_observations(rows)
    assert built["population_mixing"] is False
    assert built["populations_present"] == [review.PROSPECTIVE_GENUINE, review.RECONSTRUCTED_RESEARCH]
    assert built["mature_counts"]["T5"]["rows"] == 2
    identities = {(item["population"], item["mature_count"]) for item in built["cohorts"]}
    assert (review.PROSPECTIVE_GENUINE, 1) in identities
    assert (review.RECONSTRUCTED_RESEARCH, 1) in identities
    assert built["probability"] is None
    assert built["automatic_threshold_change"] is False


def test_live_sessions_stay_pending_and_t60_is_refused():
    pending = _row(session="2026-10-05", status="PENDING_FUTURE_SESSIONS", forward_return=None, mfe=None, mae=None)
    refused = _row(refused_horizons=["T60"])
    built = review.review_observations([pending, refused])
    assert built["mature_counts"]["T5"]["rows"] == 1
    assert built["pending_live_horizon_rows"] == 1
    assert "2026-10-05" not in built["mature_counts"]["T5"]["decision_sessions"]
    assert built["t60_engine_horizon"] is False
    assert built["refused_t60_fields"] == 1


def test_small_sample_has_no_matched_edge():
    built = review.review_observations([
        _row(),
        _row(posture="WAIT", tactical_state="UNCLASSIFIED", forward_return=-0.01),
    ])
    setup = next(item for item in built["cohorts"] if item["posture"] == "EARLY_REVERSAL")
    assert setup["sample_quality"] == review.INSUFFICIENT
    assert setup["matched_control"]["status"] == review.UNQUALIFIED_SAMPLE


def test_qualified_same_regime_control_reports_edge():
    setup_rows = [
        _row(session=f"2026-09-{day:02d}", ticker=f"S{index}", forward_return=0.04)
        for index, day in enumerate(range(1, 9), start=1)
    ]
    # 300 mature observations across 8 sessions.
    setup_rows = []
    for session_index in range(8):
        for item in range(40):
            setup_rows.append(_row(session=f"2026-08-{session_index+1:02d}", ticker=f"S{session_index}-{item}", forward_return=0.04))
    control_rows = []
    for session_index in range(8):
        for item in range(40):
            control_rows.append(_row(
                session=f"2026-08-{session_index+1:02d}", ticker=f"C{session_index}-{item}",
                posture="WAIT", tactical_state="UNCLASSIFIED", forward_return=0.01,
            ))
    built = review.review_observations(setup_rows + control_rows)
    setup = next(item for item in built["cohorts"] if item["posture"] == "EARLY_REVERSAL")
    assert setup["sample_quality"] == review.CALIBRATION_CANDIDATE
    assert setup["matched_control"]["status"] == "COMPUTED"
    assert setup["matched_control"]["edge"] == 0.03
    assert setup["probability"] is None


def test_missing_warnings_and_features_stay_explicit():
    built = review.review_observations([_row(forward_return=-0.02, posture="AVOID", tactical_state="UNCLASSIFIED")])
    cohort = built["cohorts"][0]
    assert cohort["false_positive_review"]["status"] == "WARNINGS_NOT_RETAINED"
    assert cohort["false_negative_review"]["status"] == "FEATURES_NOT_RETAINED"
    assert cohort["false_reversal_rate"]["status"] == "LABEL_NOT_RETAINED"
    assert cohort["maximum_drawdown"]["status"] == "MISSING"


def test_supportive_wait_is_a_false_negative_candidate_without_a_threshold_change():
    built = review.review_observations([_row(posture="AVOID", tactical_state="UNCLASSIFIED", supportive_features_present=True)])
    cohort = built["cohorts"][0]
    assert cohort["false_negative_review"]["supportive_features_while_wait_or_avoid"] == 1
    assert cohort["automatic_threshold_change"] is False


def test_compact_projection_keeps_horizon_5_and_drops_t60():
    record = {
        "source_type": "IMMUTABLE_INTEGRATED_T0",
        "decision_session": "2026-10-06",
        "ticker": "HPG",
        "research_action_posture": "WAIT",
        "tactical_structure_state": "BASE_BUILDING",
        "market_sector_state": "MIXED_BREADTH",
        "feedback_taxonomy": {"label": "INSUFFICIENT_OUTCOME_EVIDENCE"},
        "evidence_axes": {"axis_states": {}, "status": "FIELD_NOT_RETAINED_AT_T0"},
        "forward_outcomes": {
            "horizons": {
                "forward_close_return_5": {"status": "PENDING_FUTURE_SESSIONS", "return": None},
                "T60": {"status": "MATURE", "return": 0.5},
            },
            "close_path_by_horizon": {"close_excursion_5": {"CLOSE_MFE": None, "CLOSE_MAE": None}},
        },
    }
    rows = review.compact_horizons(record)
    assert [row["horizon"] for row in rows] == [5]
    assert rows[0]["population"] == review.PROSPECTIVE_GENUINE
    assert rows[0]["refused_horizons"] == ["T60"]
    built = review.review_observations(rows)
    assert built["mature_counts"]["T5"]["rows"] == 0
    assert built["pending_live_horizon_rows"] == 1


def test_stream_reads_one_array_and_does_not_require_the_retained_artifact(tmp_path: Path):
    payload = {
        "artifact_identity": "test",
        "feedback_records": [
            {
                "source_type": "QUALIFIED_LEGACY_INTEGRATED_T0",
                "decision_session": "2026-09-03",
                "ticker": "QNS",
                "research_action_posture": "EARLY_REVERSAL",
                "tactical_structure_state": "BREAKOUT_READY",
                "market_sector_state": "MIXED_BREADTH",
                "forward_outcomes": {"horizons": {"forward_close_return_20": {"status": "MATURE", "return": 0.01}}, "close_path_by_horizon": {}},
            }
        ],
    }
    path = tmp_path / "feedback.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    built = review.review_feedback_artifact(path)
    assert built["mature_counts"]["T20"]["rows"] == 1
    assert built["mature_counts"]["T20"]["decision_sessions"] == ["2026-09-03"]
    assert built["storage_footprint"]["persisted"] is False
    assert path.read_text(encoding="utf-8").startswith("{")


def test_conflicting_tier_and_source_are_unclassified():
    record = {
        "source_type": "IMMUTABLE_INTEGRATED_T0",
        "semantic_tier": review.RECONSTRUCTED_RESEARCH,
        "decision_session": "2026-09-03",
        "forward_outcomes": {"horizons": {"forward_close_return_5": {"status": "MATURE", "return": 0.01}}},
    }
    rows = review.compact_horizons(record)
    built = review.review_observations(rows)
    assert built["unclassified_rows"] == 1
    assert built["mature_counts"]["T5"]["rows"] == 0
