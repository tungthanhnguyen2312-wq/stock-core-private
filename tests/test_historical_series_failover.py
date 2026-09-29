from __future__ import annotations

from datetime import date, timedelta

import pytest

import historical_series_failover as history
from tools import run_market_wide_current_technical_coverage_scaleout as runner


TARGET = "2026-08-28"


def _rows(*, close: float = 100.0, count: int = 20) -> list[dict]:
    current = date.fromisoformat(TARGET)
    days = []
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return [
        {"session": day.isoformat(), "open": close - 1, "high": close + 1, "low": close - 2,
         "close": close if day.isoformat() == TARGET else close - (count - index), "volume": 1000 + index}
        for index, day in enumerate(reversed(days))
    ]


def _series(provider: str, *, close: float = 100.0, count: int = 20, **kwargs) -> dict:
    return history.build_provider_series(
        ticker="HPG", provider=provider, target_session=TARGET, requested_at="2026-09-05T10:00:00+07:00",
        requested_start="2026-07-01", requested_end=TARGET, rows=_rows(close=close, count=count), **kwargs,
    )


def _snapshot(close: float = 100.0) -> dict:
    return {"observations": [{"session": TARGET, "close": close, "provider": "KBS"}]}


def test_dnse_complete_history_is_selected_and_preserves_closed_authority():
    dnse = _series("DNSE")
    selected = history.select_feature_safe_series(
        ticker="HPG", target_session=TARGET, feature_family="TECHNICAL_CLOSE_HISTORY",
        snapshot_record=_snapshot(), provider_series={"DNSE": dnse},
    )
    assert selected["selected_provider"] == "DNSE"
    assert selected["compatibility_with_exact_session"] == "EXACT_TARGET_CLOSE_MATCH"
    assert dnse["fitness"]["PIT_BACKTEST"] == "BLOCKED"
    assert dnse["fitness"]["EXECUTION_LIQUIDITY"] == "BLOCKED"


def test_kbs_is_close_history_fallback_but_its_volume_family_stays_blocked():
    dnse = _series("DNSE", count=19)
    kbs = _series("KBS")
    selected = history.select_feature_safe_series(
        ticker="HPG", target_session=TARGET, feature_family="TECHNICAL_CLOSE_HISTORY",
        snapshot_record=_snapshot(), provider_series={"DNSE": dnse, "KBS": kbs},
    )
    assert selected["selected_provider"] == "KBS"
    assert kbs["fitness"]["MOMENTUM"] == "READY"
    assert kbs["fitness"]["TACTICAL_STRUCTURE"] == "READY"
    assert kbs["fitness"]["TECHNICAL_VOLUME_HISTORY"] == "BLOCKED"
    assert kbs["fitness"]["PARTICIPATION"] == "BLOCKED"


def test_vci_can_follow_a_kbs_target_close_mismatch_without_splicing_histories():
    series = {"DNSE": _series("DNSE", count=19), "KBS": _series("KBS", close=99.0), "VCI": _series("VCI")}
    selected = history.select_feature_safe_series(
        ticker="HPG", target_session=TARGET, feature_family="TACTICAL_STRUCTURE",
        snapshot_record=_snapshot(), provider_series=series,
    )
    assert selected["selected_provider"] == "VCI"
    assert selected["history_depth"] == 20
    assert any(row["reason"] == "TARGET_SESSION_CLOSE_MISMATCH" for row in selected["attempted_providers"])
    record = history.recovery_record_from_selection(selection=selected, provider_series=series)
    assert record["provider"] == "VCI"
    assert {row["session"] for row in record["observations"]} == {row["session"] for row in series["VCI"]["observations"]}


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        (_rows() + [{"session": "2026-08-29", "close": 101.0, "volume": 1}], "FUTURE_SESSION_ROW_PROHIBITED"),
        (_rows() + [_rows()[-1]], "DUPLICATE_SESSION_ROW"),
    ],
)
def test_future_and_duplicate_provider_observations_fail_closed(rows, reason):
    series = history.build_provider_series(
        ticker="HPG", provider="KBS", target_session=TARGET, requested_at="test",
        requested_start="2026-07-01", requested_end=TARGET, rows=rows,
    )
    assert series["status"] == "BLOCKED"
    assert series["reason"] == reason
    assert series["fitness"]["TECHNICAL_CLOSE_HISTORY"] == "BLOCKED"


def test_dnse_missing_does_not_attempt_a_retired_provider():
    dnse_record = {"ticker": "HPG", "state": "FETCH_FAILED", "reason": "DNSE_TIMEOUT", "attempt_count": 1}
    record = runner._feature_safe_record(
        ticker="HPG", dnse_record=dnse_record, snapshot_record=_snapshot(), target_session=TARGET,
        retrieved_at="test", start="2026-07-01", end=TARGET,
    )
    assert record["state"] == "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK"
    assert record["reason"] == "DNSE_HISTORY_UNAVAILABLE_NO_ACTIVE_FAILOVER"


def test_provider_fitness_matrix_keeps_method_level_limits_explicit():
    matrix = history.provider_fitness_matrix({"DNSE": _series("DNSE"), "KBS": _series("KBS")})
    assert matrix["providers"]["DNSE"]["fitness"]["TECHNICAL_CLOSE_HISTORY"] == "READY"
    assert matrix["providers"]["KBS"]["fitness"]["PARTICIPATION"] == "BLOCKED"
    assert matrix["authority_boundary"]["PIT_BACKTEST"] == "BLOCKED"
