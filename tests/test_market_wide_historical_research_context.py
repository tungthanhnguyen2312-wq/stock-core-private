"""Focused tests for market-wide retrospective historical research context."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from field_temporal_contract import stable_id as p3f9b_stable_id
from market_wide_current_technical_coverage_scaleout import content_identity as recovery_content_identity
from market_wide_historical_research_context import (
    BLOCKED_OUTPUTS,
    FORBIDDEN_PAYLOAD_TOKENS,
    PRICE_BASIS,
    build_artifact,
    content_identity,
    evaluate_historical_context,
)
from polymorphic_current_strategy_classification import content_identity as strategy_content_identity


TARGET = "2026-08-24"
ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"

PROTECTED_DESCRIPTIVE_ID = "market_wide_current_descriptive_research:ab08cf56fa4678b86296fc5c1f4cbaf108ec66b2e776d6d4070880bbc0b77ce1"
PROTECTED_TACTICAL_ID = "watchlist_tactical_entry_classifier:3fc4ed10d487a543887ddd66dc70cd8b5df4907654b302b25f604707e16f75f1"
PROTECTED_OFFICIAL_ID = "current_official_market_universe:d77e16f82893df419689b24356d066d6a6431bd3c27e09190e3c319e004abb55"
PROTECTED_SNAPSHOT_ID = "p3f9_exact_session_snapshot:8f1d762c5fb4d1cbdd9a26dc415b318aafefa630799c38fd74076ca166d8f25c"
PROTECTED_QUEUE_ID = "daily_opportunity_decision_queue:0b8158b4775cbc2b2497a61e4f98c9b0a3046350a3cdd41e727a02c42c17ab22"
PROTECTED_OPERATION_ID = "daily_research_session_operation:4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa"
PROTECTED_FREEZE_21_ID = "prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1"
PROTECTED_FREEZE_24_ID = "prospective_research_snapshot:d8195a5d3715b662159a01f3dc5f409ac90500643eb5323a0b28f5ec5908ff78"


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _trading_days(end: str, count: int) -> list[str]:
    day = date.fromisoformat(end)
    days = []
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    return list(reversed(days))


def _bars(end: str, closes: list[float], *, volume: float = 1000.0, high_low: bool = True) -> list[dict]:
    days = _trading_days(end, len(closes))
    rows = []
    for index, close in enumerate(closes):
        row = {
            "session": days[index],
            "open": close,
            "close": close,
            "volume": volume + index,
            "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
            "provider": "DNSE",
        }
        if high_low:
            row["high"] = close * 1.01
            row["low"] = close * 0.99
        rows.append(row)
    return rows


def _rising(count: int, start: float = 10.0, step: float = 0.1) -> list[float]:
    return [start + step * index for index in range(count)]


def _falling(count: int, start: float = 20.0, step: float = 0.1) -> list[float]:
    return [start - step * index for index in range(count)]


def universe_resolution(records, *, denominator, observed):
    payload = {
        "records": records,
        "current_active_equity_denominator": {"count": denominator},
        "observed_session_cohort": {"count": observed},
        "input_candidates": {"resolved_completed_session": TARGET},
    }
    digest = _hash(payload)
    return {
        **payload,
        "artifact_sha256": digest,
        "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{digest}",
    }


def p3f9b_snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = p3f9b_stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def recovery_artifact(overrides, *, snapshot_identity):
    payload = {
        "target_session": TARGET,
        "source_lineage": {"p3f9b_snapshot_identity": snapshot_identity},
        "recovered_history_overrides": overrides,
        "records": overrides,
    }
    return {**payload, **recovery_content_identity(payload)}


def _ur(ticker, state="ACTIVE_LISTED_OBSERVED"):
    return {"ticker": ticker, "activity_and_session_state": state, "membership_state": "INCLUDED"}


def test_missing_history_is_explicit_not_synthetic():
    result = evaluate_historical_context([], target_session=TARGET)
    assert result["context_status"] == "MISSING"
    assert result["trailing_range"]["status"] == "MISSING"
    assert result["fifty_two_week_range"]["status"] == "MISSING"
    assert result["trailing_range"]["value"] is None
    assert result["history"]["raw_as_traded"] == "NOT_PROMOTED"
    assert result["history"]["historical_pit_eligible"] is False
    assert result["history"]["price_basis"] == PRICE_BASIS


def test_short_history_is_insufficient_never_filled():
    result = evaluate_historical_context(_bars(TARGET, _rising(8)), target_session=TARGET)
    assert result["context_status"] == "INSUFFICIENT_HISTORY"
    assert result["trailing_range"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["fifty_two_week_range"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["fifty_two_week_range"]["reason"] == "RETAINED_OBSERVED_SESSIONS_BELOW_252"
    assert result["current_feature_window"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["structural_state"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["cross_sectional_historical_comparison"]["status"] == "BLOCKED"


def test_rising_series_is_trend_continuation_not_performance():
    result = evaluate_historical_context(_bars(TARGET, _rising(28)), target_session=TARGET)
    assert result["context_status"] in {"AVAILABLE", "PARTIAL"}
    assert result["is_current_session"] is True
    assert result["ma_alignment"]["trend_state"] == "ABOVE_MA20"
    assert result["momentum"]["sign"] == "POSITIVE"
    assert result["structural_state"]["value"] == "TREND_CONTINUATION"
    assert result["trailing_range"]["status"] == "AVAILABLE"
    assert result["fifty_two_week_range"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["history"]["price_basis"] == PRICE_BASIS
    assert result["history"]["raw_as_traded"] == "NOT_PROMOTED"
    assert result["structural_state"]["not_strategy_eligibility"] is True


def test_long_rising_series_is_mature_trend():
    result = evaluate_historical_context(_bars(TARGET, _rising(45)), target_session=TARGET)
    assert result["structural_state"]["value"] == "MATURE_TREND"
    assert result["ma_alignment"]["persistence_windows"] >= 10


def test_falling_series_is_deterioration():
    result = evaluate_historical_context(_bars(TARGET, _falling(28)), target_session=TARGET)
    assert result["ma_alignment"]["trend_state"] == "AT_OR_BELOW_MA20"
    assert result["momentum"]["sign"] == "NEGATIVE"
    assert result["structural_state"]["value"] == "DETERIORATION"
    assert result["drawdown"]["current_drawdown"] < 0


def test_flat_series_is_base():
    result = evaluate_historical_context(_bars(TARGET, [10.0] * 28), target_session=TARGET)
    assert result["ma_alignment"]["near_ma20"] is True
    assert result["structural_state"]["value"] == "BASE"


def test_early_reversal_uses_existing_momentum_and_ma_primitives():
    # Last 20: first well below last, but a mid-window high keeps close below MA20.
    closes = [7.0, 7.2, 7.4, 7.6, 8.0] + [12.0] * 14 + [10.4, 10.6, 10.8, 11.0, 11.1]
    result = evaluate_historical_context(_bars(TARGET, closes), target_session=TARGET)
    assert result["ma_alignment"]["trend_state"] == "AT_OR_BELOW_MA20"
    assert result["momentum"]["sign"] == "POSITIVE"
    assert result["structural_state"]["value"] == "EARLY_REVERSAL"


def test_no_calendar_imputation_uses_observation_count_not_weekday_span():
    bars = _bars(TARGET, _rising(20))
    bars[5]["session"] = "2026-06-01"
    bars = sorted(bars, key=lambda row: row["session"])
    result = evaluate_historical_context(bars, target_session=TARGET)
    assert result["history"]["observation_count"] == 20
    assert result["history"]["window_rule"] == "ACTUAL_RETAINED_TRADING_OBSERVATIONS_NO_CALENDAR_IMPUTATION"
    assert result["trailing_range"]["observation_count"] == 20


def test_cross_sectional_historical_comparison_stays_blocked():
    result = evaluate_historical_context(_bars(TARGET, _rising(28)), target_session=TARGET)
    assert result["cross_sectional_historical_comparison"]["status"] == "BLOCKED"
    assert result["cross_sectional_historical_comparison"]["reason"] == "HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE"


def test_stale_last_bar_is_labelled_not_current_session():
    bars = _bars("2026-08-21", _rising(28))
    result = evaluate_historical_context(bars, target_session=TARGET)
    assert result["is_current_session"] is False
    assert result["as_of_session"] == "2026-08-21"


def test_build_artifact_replay_and_authority_envelope():
    ur = {
        "RIS1": _ur("RIS1"),
        "THIN1": _ur("THIN1"),
        "OLD1": _ur("OLD1", "INACTIVE_OR_DELISTED"),
    }
    pf = {
        "RIS1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(28))},
        "THIN1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(5))},
        "OLD1": {"disposition": "PROVIDER_REJECTED", "observations": []},
    }
    snapshot = p3f9b_snapshot(pf)
    artifact = build_artifact(
        universe_resolution_artifact=universe_resolution(ur, denominator=2, observed=2),
        p3f9b_snapshot=snapshot,
    )
    replayed = content_identity(artifact)
    assert replayed["artifact_sha256"] == artifact["artifact_sha256"]
    assert replayed["artifact_identity"] == artifact["artifact_identity"]
    again = build_artifact(
        universe_resolution_artifact=universe_resolution(ur, denominator=2, observed=2),
        p3f9b_snapshot=snapshot,
    )
    assert again["artifact_sha256"] == artifact["artifact_sha256"]
    assert artifact["records"]["RIS1"]["structural_state"]["value"] == "TREND_CONTINUATION"
    assert artifact["records"]["THIN1"]["context_status"] == "INSUFFICIENT_HISTORY"
    assert artifact["records"]["OLD1"]["context_status"] == "NOT_APPLICABLE"
    assert artifact["authority_boundary"]["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert artifact["authority_boundary"]["PIT"] == "BLOCKED"
    assert artifact["authority_boundary"]["research_priority_entry_action_strategy_eligibility"] == "NOT_MODIFIED"
    assert artifact["blocked_outputs"]["historical_strategy_performance_win_rate_alpha"] == "HISTORICAL_PERFORMANCE_PROHIBITED"
    payload = _canonical_json(artifact["records"])
    for token in FORBIDDEN_PAYLOAD_TOKENS:
        assert f'"{token}"' not in payload
        assert f":{token}" not in payload
    assert artifact["records"]["RIS1"]["history"]["price_basis"] == PRICE_BASIS
    assert artifact["records"]["RIS1"]["history"]["raw_as_traded"] == "NOT_PROMOTED"
    assert "RAW_AS_TRADED" not in str(artifact["records"]["RIS1"]["history"]["price_basis"])


def test_recovery_override_is_used_and_keeps_adjusted_label():
    ur = {"REC1": _ur("REC1")}
    pf = {"REC1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(8))}}
    snapshot = p3f9b_snapshot(pf)
    recovery = recovery_artifact(
        {
            "REC1": {
                "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY",
                "payload_sha256": "abc",
                "observations": _bars(TARGET, _falling(40)),
            }
        },
        snapshot_identity=snapshot["snapshot_identity"],
    )
    artifact = build_artifact(
        universe_resolution_artifact=universe_resolution(ur, denominator=1, observed=1),
        p3f9b_snapshot=snapshot,
        technical_history_recovery_artifact=recovery,
    )
    record = artifact["records"]["REC1"]
    assert record["history"]["source"] == "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY"
    assert record["history"]["observation_count"] == 40
    assert record["structural_state"]["value"] == "DETERIORATION"
    assert record["history"]["price_basis"] == PRICE_BASIS
    assert record["history"]["historical_pit_eligible"] is False


def test_strategy_session_mismatch_is_rejected():
    ur = {"RIS1": _ur("RIS1")}
    pf = {"RIS1": {"disposition": "EXACT_SESSION_RETAINED", "observations": _bars(TARGET, _rising(28))}}
    snapshot = p3f9b_snapshot(pf)
    strategy_payload = {"session": "2026-08-21", "records": {}}
    strategy = {**strategy_payload, **strategy_content_identity(strategy_payload)}
    with pytest.raises(Exception):
        build_artifact(
            universe_resolution_artifact=universe_resolution(ur, denominator=1, observed=1),
            p3f9b_snapshot=snapshot,
            strategy_artifact=strategy,
        )


def test_real_retained_snapshot_pilot_and_representative_structural_states():
    snapshot = json.loads(
        (OPS / "p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json").read_text(encoding="utf-8")
    )
    recovery = json.loads(
        (
            OPS
            / "market-wide-current-technical-coverage-scaleout-v1-20260824"
            / "market_wide_current_technical_coverage_recovery_artifact.json"
        ).read_text(encoding="utf-8")
    )
    hpg = evaluate_historical_context(snapshot["records"]["HPG"]["observations"], target_session=TARGET)
    assert hpg["history"]["observation_count"] >= 20
    assert hpg["history"]["price_basis"] == PRICE_BASIS
    assert hpg["history"]["raw_as_traded"] == "NOT_PROMOTED"
    assert hpg["fifty_two_week_range"]["status"] == "INSUFFICIENT_HISTORY"
    assert hpg["cross_sectional_historical_comparison"]["status"] == "BLOCKED"
    recovered = recovery["recovered_history_overrides"]["CCC"]["observations"]
    ccc = evaluate_historical_context(
        recovered,
        target_session=TARGET,
        provenance={"source": "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY"},
    )
    assert ccc["history"]["observation_count"] >= 200
    assert ccc["fifty_two_week_range"]["status"] == "INSUFFICIENT_HISTORY"
    assert ccc["history"]["price_basis"] == PRICE_BASIS

    seen = {}
    for ticker, record in snapshot["records"].items():
        context = evaluate_historical_context(record.get("observations") or [], target_session=TARGET)
        value = (context.get("structural_state") or {}).get("value")
        if value and value not in seen:
            seen[value] = ticker
        if len(seen) >= 4:
            break
    for ticker, record in recovery["recovered_history_overrides"].items():
        context = evaluate_historical_context(record.get("observations") or [], target_session=TARGET)
        value = (context.get("structural_state") or {}).get("value")
        if value and value not in seen:
            seen[value] = ticker
    assert "TREND_CONTINUATION" in seen or "MATURE_TREND" in seen
    assert "DETERIORATION" in seen
    assert "BASE" in seen or "EARLY_REVERSAL" in seen


def test_real_market_wide_artifact_replays_and_keeps_authority_closed():
    path = (
        OPS
        / "market-wide-historical-research-context-v1-20260824"
        / "market_wide_historical_research_context_artifact.json"
    )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    replayed = content_identity(artifact)
    assert replayed["artifact_sha256"] == artifact["artifact_sha256"]
    assert replayed["artifact_identity"] == artifact["artifact_identity"]
    assert artifact["artifact_identity"] == (
        "market_wide_historical_research_context:bf25da2fc89f82b168b624fa5bfe4a4d3ec4ff4a6e3aa4f91cd7ae00d2ba1787"
    )
    assert artifact["session"] == TARGET
    assert artifact["authority_boundary"]["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert artifact["authority_boundary"]["PIT"] == "BLOCKED"
    assert artifact["coverage"]["fifty_two_week_available_count"] == 0
    assert artifact["coverage"]["current_session_context_count"] == 881
    payload = json.dumps(artifact["records"])
    for token in FORBIDDEN_PAYLOAD_TOKENS:
        assert f'"{token}"' not in payload
    am = artifact["records"]["AAM"]
    assert am["history"]["price_basis"] == PRICE_BASIS
    assert am["history"]["raw_as_traded"] == "NOT_PROMOTED"
    assert am["history"]["historical_pit_eligible"] is False
    assert am["cross_sectional_historical_comparison"]["status"] == "BLOCKED"


def test_governed_2026_08_24_and_2026_08_21_identities_unchanged():
    descriptive = json.loads(
        (OPS / "market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json").read_text(encoding="utf-8")
    )
    tactical = json.loads(
        (OPS / "watchlist-tactical-entry-decision-v1-20260824/watchlist_tactical_entry_classifier_artifact.json").read_text(encoding="utf-8")
    )
    official = json.loads(
        (OPS / "current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json").read_text(encoding="utf-8")
    )
    snapshot = json.loads(
        (OPS / "p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json").read_text(encoding="utf-8")
    )
    queue = json.loads(
        (
            OPS
            / "daily-research-session-operations-v1/2026-08-24"
            / "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa"
            / "daily_opportunity_decision_queue_artifact.json"
        ).read_text(encoding="utf-8")
    )
    freeze_21 = json.loads(
        (OPS / "current-decision-prospective-learning-v1-20260824/current_decision_prospective_snapshot_20260821.json").read_text(encoding="utf-8")
    )
    freeze_24 = json.loads(
        (
            OPS
            / "opportunity-decision-prospective-freeze-v1/2026-08-24"
            / "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa"
            / "opportunity_decision_prospective_freeze.json"
        ).read_text(encoding="utf-8")
    )
    assert descriptive["artifact_identity"] == PROTECTED_DESCRIPTIVE_ID
    assert tactical["artifact_identity"] == PROTECTED_TACTICAL_ID
    assert official["artifact_identity"] == PROTECTED_OFFICIAL_ID
    assert snapshot["snapshot_identity"] == PROTECTED_SNAPSHOT_ID
    assert queue["artifact_identity"] == PROTECTED_QUEUE_ID
    assert freeze_21["snapshot_id"] == PROTECTED_FREEZE_21_ID
    assert freeze_24["snapshot_id"] == PROTECTED_FREEZE_24_ID
    assert PROTECTED_OPERATION_ID.split(":")[1] in str(
        OPS / "daily-research-session-operations-v1/2026-08-24/4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa"
    )
    assert BLOCKED_OUTPUTS["historical_raw_as_traded_or_pit"] == "RAW_AS_TRADED_NOT_PROMOTED"
