from __future__ import annotations

from pathlib import Path

from governed_trading_session_calendar import (
    TARGET_SESSION_INVALID,
    TARGET_SESSION_VALID,
    load_governed_trading_session_calendar,
)
from market_wide_historical_matched_liquidity import calculate_trailing_feature


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / "config" / "governed_trading_session_calendar_v1.json"


def test_governed_replay_calendar_has_valid_targets_and_deterministic_windows():
    calendar = load_governed_trading_session_calendar(CALENDAR)
    assert len(calendar.sessions) == 65
    assert calendar.is_valid_target("2026-09-04")
    assert calendar.is_valid_target("2026-08-25")
    assert not calendar.is_valid_target("2026-08-30")
    assert not calendar.is_valid_target("2026-09-02")
    sep04_20 = calendar.resolve_window("2026-09-04", 20)
    sep04_60 = calendar.resolve_window("2026-09-04", 60)
    aug25_20 = calendar.resolve_window("2026-08-25", 20)
    aug25_60 = calendar.resolve_window("2026-08-25", 60)
    assert sep04_20["target_session_state"] == TARGET_SESSION_VALID
    assert (sep04_20["sessions"][0], sep04_20["sessions"][-1]) == ("2026-08-05", "2026-09-04")
    assert (sep04_60["sessions"][0], sep04_60["sessions"][-1]) == ("2026-06-10", "2026-09-04")
    assert (aug25_20["sessions"][0], aug25_20["sessions"][-1]) == ("2026-07-29", "2026-08-25")
    assert (aug25_60["sessions"][0], aug25_60["sessions"][-1]) == ("2026-06-03", "2026-08-25")
    assert calendar.resolve_window("2026-08-30", 20)["state"] == TARGET_SESSION_INVALID
    assert calendar.resolve_window("2026-09-02", 20)["state"] == TARGET_SESSION_INVALID


def test_valid_calendar_session_with_missing_trades_is_a_data_blocker_not_calendar_blocker():
    calendar = load_governed_trading_session_calendar(CALENDAR)
    result = calculate_trailing_feature(
        ticker="HPG", feature_id="ADTV20_MATCHED_VND", metric="value", unit="VND",
        target_session="2026-09-04", calendar=calendar, size=20, daily_cells={},
    )
    assert result["target_session_calendar_state"] == TARGET_SESSION_VALID
    assert result["data_availability_state"] == "REQUIRED_SESSION_CANONICAL_DATA_MISSING"
    assert "REQUIRED_SESSION_CANONICAL_DATA_MISSING" in result["blockers"]
    assert "TARGET_SESSION_NOT_IN_GOVERNED_CALENDAR" not in result["blockers"]
    assert all(session <= "2026-09-04" for session in result["window_sessions"])
