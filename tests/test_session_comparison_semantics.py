from __future__ import annotations

from session_comparison_semantics import (
    FITNESS_DEGRADED,
    FITNESS_FRESH,
    FITNESS_UNAVAILABLE,
    REASON_NO_PREVIOUS_GOVERNED_SESSION,
    REASON_REGISTRY_GAP,
    ROLE_DISTANT,
    ROLE_IMMEDIATE,
    ROLE_NONE,
    build_comparison_metadata,
)


def _registry(*, completed: dict, attempted: dict | None = None) -> dict:
    return {
        "completed_sessions": {
            session: {"status": "COMPLETED_RETAINED_EVIDENCE", "frozen_input_identities": {}}
            for session in completed
        },
        "sessions": dict(attempted or {}),
    }


# 13. adjacent previous governed session -> FRESH_ADJACENT

def test_adjacent_previous_governed_session_is_fresh_adjacent():
    registry = _registry(completed={"2026-08-25", "2026-08-26"})
    result = build_comparison_metadata(registry=registry, current_session="2026-08-26", comparison_session="2026-08-25")
    assert result["comparison_session"] == "2026-08-25"
    assert result["comparison_session_role"] == ROLE_IMMEDIATE
    assert result["comparison_fitness"] == FITNESS_FRESH
    assert result["is_immediate_previous_completed_session"] is True
    assert result["session_gap_trading_sessions"] == 0
    assert result["comparison_reason_codes"] == []
    assert result["skipped_known_sessions"] == []
    assert result["notice"] is None


# 14. multi-session gap -> DEGRADED_MULTI_SESSION_GAP, and
# 15. PREVIOUS_SESSION_REGISTRY_GAP emitted

def test_multi_session_gap_is_degraded_and_emits_registry_gap_reason():
    registry = _registry(
        completed={"2026-08-26", "2026-09-11"},
        attempted={"2026-09-04": {}, "2026-09-10": {}},
    )
    result = build_comparison_metadata(registry=registry, current_session="2026-09-11", comparison_session="2026-08-26")
    assert result["comparison_session_role"] == ROLE_DISTANT
    assert result["comparison_fitness"] == FITNESS_DEGRADED
    assert result["is_immediate_previous_completed_session"] is False
    assert result["comparison_reason_codes"] == [REASON_REGISTRY_GAP]
    assert result["notice"] is not None
    assert "2026-08-26" in result["notice"] and "2026-09-11" in result["notice"]


# The exact historical shape this milestone was created to fix: current=2026-09-11,
# governed comparator=2026-08-26, with known-but-ungoverned sessions in between (the
# five real registry-promotion-gap dates) must not read as an ordinary adjacent transition.

def test_regression_2026_09_11_vs_2026_08_26_historical_shape_is_not_adjacent():
    registry = _registry(
        completed={"2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-09-11"},
        attempted={"2026-08-27": {}, "2026-08-28": {}, "2026-09-03": {}, "2026-09-04": {}, "2026-09-10": {}},
    )
    result = build_comparison_metadata(registry=registry, current_session="2026-09-11", comparison_session="2026-08-26")
    assert result["comparison_session_role"] == ROLE_DISTANT
    assert result["comparison_fitness"] == FITNESS_DEGRADED
    assert result["is_immediate_previous_completed_session"] is False
    assert result["session_gap_trading_sessions"] == 5
    assert result["skipped_known_sessions"] == [
        "2026-08-27", "2026-08-28", "2026-09-03", "2026-09-04", "2026-09-10",
    ]
    assert result["comparison_reason_codes"] == [REASON_REGISTRY_GAP]


# 16. no previous governed session -> UNAVAILABLE

def test_no_previous_governed_session_is_unavailable():
    registry = _registry(completed={"2026-08-21"})
    result = build_comparison_metadata(registry=registry, current_session="2026-08-21", comparison_session=None)
    assert result["comparison_session"] is None
    assert result["comparison_session_role"] == ROLE_NONE
    assert result["comparison_fitness"] == FITNESS_UNAVAILABLE
    assert result["is_immediate_previous_completed_session"] is False
    assert result["session_gap_trading_sessions"] is None
    assert result["comparison_reason_codes"] == [REASON_NO_PREVIOUS_GOVERNED_SESSION]
    assert result["skipped_known_sessions"] == []


# 17. trading-session gap is not calendar-day gap: a wide calendar gap with no known
# intervening session at all (never registered, never attempted) must still be reported
# as FRESH_ADJACENT with gap=0 -- the registry has no basis to claim otherwise, and this
# module must never fabricate a count from calendar-day subtraction.

def test_gap_reflects_known_registry_sessions_not_calendar_days():
    registry = _registry(completed={"2026-07-01", "2026-09-11"})  # ~10 weeks apart on the calendar
    result = build_comparison_metadata(registry=registry, current_session="2026-09-11", comparison_session="2026-07-01")
    assert result["session_gap_trading_sessions"] == 0
    assert result["comparison_session_role"] == ROLE_IMMEDIATE
    assert result["comparison_fitness"] == FITNESS_FRESH
    assert result["is_immediate_previous_completed_session"] is True


def test_gap_counts_only_sessions_strictly_between_never_the_endpoints():
    registry = _registry(completed={"2026-08-21", "2026-08-26"}, attempted={"2026-08-24": {}, "2026-08-25": {}})
    result = build_comparison_metadata(registry=registry, current_session="2026-08-26", comparison_session="2026-08-21")
    assert result["session_gap_trading_sessions"] == 2
    assert result["skipped_known_sessions"] == ["2026-08-24", "2026-08-25"]


def test_deterministic_repeated_build_produces_identical_metadata():
    registry = _registry(
        completed={"2026-08-26", "2026-09-11"},
        attempted={"2026-08-27": {}, "2026-09-04": {}},
    )
    first = build_comparison_metadata(registry=registry, current_session="2026-09-11", comparison_session="2026-08-26")
    second = build_comparison_metadata(registry=registry, current_session="2026-09-11", comparison_session="2026-08-26")
    assert first == second
