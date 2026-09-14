"""Focused regression coverage for HNX_UPCOM_OFFICIAL_SECURITY_STATUS_ENRICHMENT_V1.

Unit-level: exercises hnx_official_issuer_profile_multi_gate.py's normalize_control_status/
normalize_trading_status against real observed raw values (LCD/ART live 2026-09-13 profile
pages) and synthetic edge cases the real cohort didn't happen to produce (temporarily-stopped,
cancelled/delisted, missing status, conflicting evidence). Integration-level: exercises
current_official_market_universe.attach_hnx_upcom_security_status /
build_no_bar_explanation_summary against the real refreshed 2026-09-13 evidence when present.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hnx_official_issuer_profile_multi_gate import (
    CONTROL_CONTROL, CONTROL_MULTIPLE, CONTROL_NORMAL, CONTROL_RESTRICTED, CONTROL_SUSPENSION_RELATED,
    CONTROL_UNKNOWN, CONTROL_WARNING, TRADING_ACTIVE, TRADING_CANCELLED, TRADING_RESTRICTED,
    TRADING_SUSPENDED, TRADING_TEMP_STOPPED, TRADING_UNKNOWN, normalize_control_status, normalize_trading_status,
)
from current_official_market_universe import (
    attach_hnx_upcom_security_status, build_no_bar_explanation_summary, _explanatory_bucket,
)


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"
OFFICIAL_UNIVERSE_PATH = OPS / "current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
STATUS_ENRICHMENT_PATH = OPS / "hnx-upcom-official-security-status-enrichment-v1-20260913/hnx_upcom_official_security_status_artifact.json"
_REQUIRES_REAL_EVIDENCE = pytest.mark.skipif(
    not (OFFICIAL_UNIVERSE_PATH.is_file() and STATUS_ENRICHMENT_PATH.is_file()),
    reason="Real refreshed 2026-09-13 evidence not present in this worktree/checkout.",
)


# 1. Normal/active profile (real: LCD).
def test_normal_active_profile_control_and_trading():
    assert normalize_control_status("Bình thường") == (CONTROL_NORMAL, [CONTROL_NORMAL])
    assert normalize_trading_status("Hoạt động") == TRADING_ACTIVE


# 2. Warning/control.
def test_warning_and_control_are_distinct():
    assert normalize_control_status("Cảnh báo")[0] == CONTROL_WARNING
    assert normalize_control_status("Kiểm soát")[0] == CONTROL_CONTROL
    assert normalize_control_status("Kiểm soát đặc biệt")[0] == CONTROL_CONTROL


# 3. Restricted trading (real: "Giao dịch đặc biệt" -> RESTRICTED, HNX's own special-trading regime).
def test_restricted_trading_status_real_raw_value():
    assert normalize_trading_status("Giao dịch đặc biệt") == TRADING_RESTRICTED
    assert normalize_control_status("Hạn chế giao dịch")[0] == CONTROL_RESTRICTED


# 4. Temporarily stopped (not observed in the real 50-cohort; exercised synthetically).
def test_temporarily_stopped_trading_status():
    assert normalize_trading_status("Tạm ngừng giao dịch") == TRADING_TEMP_STOPPED
    assert normalize_control_status("Tạm ngừng giao dịch")[0] == CONTROL_SUSPENSION_RELATED


# 5. Suspended (real: ART -> "Ngừng giao dịch").
def test_suspended_trading_status_real_raw_value():
    assert normalize_trading_status("Ngừng giao dịch") == TRADING_SUSPENDED
    assert normalize_trading_status("Đình chỉ giao dịch") == TRADING_SUSPENDED


# 6. Cancelled/delisted (not observed in the real 50-cohort; the six residual names have no
#    profile at all rather than an explicit cancellation status -- see test 15).
def test_cancelled_or_delisted_trading_status():
    for raw in ("Hủy giao dịch", "Hủy niêm yết", "Hủy đăng ký giao dịch"):
        assert normalize_trading_status(raw) == TRADING_CANCELLED


# 7. Multiple simultaneous control statuses (real: e.g. "Cảnh báo-Đình chỉ giao dịch -Hạn chế giao dịch").
def test_multiple_simultaneous_control_statuses_real_raw_value():
    status, components = normalize_control_status("Cảnh báo-Đình chỉ giao dịch -Hạn chế giao dịch")
    assert status == CONTROL_MULTIPLE
    assert set(components) == {CONTROL_WARNING, CONTROL_SUSPENSION_RELATED, CONTROL_RESTRICTED}
    # Warning + a single non-normal component must NOT be forced to MULTIPLE.
    single_status, _ = normalize_control_status("Cảnh báo")
    assert single_status == CONTROL_WARNING
    two_component_status, two_components = normalize_control_status("Cảnh báo-Đình chỉ giao dịch")
    assert two_component_status == CONTROL_MULTIPLE
    assert set(two_components) == {CONTROL_WARNING, CONTROL_SUSPENSION_RELATED}


# 8. Profile status missing.
def test_missing_or_blank_status_is_unknown_not_normal():
    assert normalize_control_status(None) == (CONTROL_UNKNOWN, [])
    assert normalize_control_status("") == (CONTROL_UNKNOWN, [])
    assert normalize_trading_status(None) == TRADING_UNKNOWN
    assert normalize_trading_status("") == TRADING_UNKNOWN


# 9. Current status observed after target session cannot backdate.
@_REQUIRES_REAL_EVIDENCE
def test_current_status_never_asserted_qualified_for_target_session():
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    summary = build_no_bar_explanation_summary(status_artifact)
    for row in summary["cohort_50_classified"].values():
        if row["outcome"] == "CURRENT_PROFILE_FOUND":
            assert row["target_session_applicability"] == "CURRENT_STATUS_OBSERVED_AFTER_TARGET_SESSION"
            assert row["target_session_applicability"] != "QUALIFIED_FOR_TARGET_SESSION"


# 10. A dated pre-target status notice MAY qualify for the target session when still effective --
#     unit-level check of the bucket/qualification independence itself, since no real dated
#     notice was acquired this milestone (disclosed, not fabricated).
def test_bucket_assignment_is_independent_of_temporal_qualification():
    bucket = _explanatory_bucket(outcome="CURRENT_PROFILE_FOUND", trading_status="SUSPENDED", control_status="WARNING")
    assert bucket == "OFFICIALLY_SUSPENDED"
    # The bucket function itself takes no temporal argument -- qualification is computed and
    # reported entirely separately (see build_no_bar_explanation_summary), so a future dated
    # notice would change target_session_applicability without altering this classification.


# 11. No-bar does not cause a status inference (a bar-having ticker is never touched by this
#     enrichment; the function only ever reads the two supplied cohorts).
@_REQUIRES_REAL_EVIDENCE
def test_enrichment_never_touches_tickers_outside_its_two_cohorts():
    official_artifact = json.loads(OFFICIAL_UNIVERSE_PATH.read_text(encoding="utf-8"))
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    enriched = attach_hnx_upcom_security_status(official_artifact, status_artifact)
    cohort_tickers = set(status_artifact["cohort_50_no_bar"]) | set(status_artifact["cohort_six_residual"])
    for ticker, record in enriched["records"].items():
        touched = "hnx_upcom_official_control_status" in record
        assert touched == (ticker in cohort_tickers)


# 12. Listed status does not require a price bar (a security is current-listed with or without
#     an observed bar; the enrichment leaves current_universe_status/exchange presence untouched).
@_REQUIRES_REAL_EVIDENCE
def test_listed_status_unchanged_by_enrichment():
    official_artifact = json.loads(OFFICIAL_UNIVERSE_PATH.read_text(encoding="utf-8"))
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    enriched = attach_hnx_upcom_security_status(official_artifact, status_artifact)
    for ticker in status_artifact["cohort_50_no_bar"]:
        assert enriched["records"][ticker]["current_universe_status"] == official_artifact["records"][ticker]["current_universe_status"]
        assert enriched["records"][ticker]["current_universe_status"] == "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"


# 13. Status enrichment does not change tactical rules (no tactical/strategy artifact is even an
#     input to this function -- structurally impossible for it to alter tactical classification).
def test_attach_function_never_touches_tactical_or_strategy_inputs():
    import inspect
    signature = inspect.signature(attach_hnx_upcom_security_status)
    assert set(signature.parameters) == {"artifact", "status_artifact"}


# 14. Status enrichment does not change the universe denominator by itself.
@_REQUIRES_REAL_EVIDENCE
def test_enrichment_does_not_change_reconciliation_denominator():
    official_artifact = json.loads(OFFICIAL_UNIVERSE_PATH.read_text(encoding="utf-8"))
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    enriched = attach_hnx_upcom_security_status(official_artifact, status_artifact)
    assert enriched["reconciliation"] == official_artifact["reconciliation"]
    assert len(enriched["records"]) == len(official_artifact["records"])


# 15. Six residual names remain fail-closed without explicit evidence.
@_REQUIRES_REAL_EVIDENCE
def test_six_residual_names_remain_fail_closed():
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    summary = build_no_bar_explanation_summary(status_artifact)
    six = summary["cohort_six_classified"]
    assert set(six) == {"BCG", "BCR", "DAN", "DVT", "LTG", "VTS"}
    for ticker, row in six.items():
        # No live profile currently resolves for any of the six (consistent with their absence
        # from the refreshed official master lists) -- none may be inferred delisted here.
        assert row["outcome"] == "CURRENT_PROFILE_NOT_FOUND"
        assert row["explanatory_bucket"] == "OFFICIAL_STATUS_UNAVAILABLE"
        assert row["official_control_status"] is None
        assert row["official_trading_status"] is None


@_REQUIRES_REAL_EVIDENCE
def test_no_bar_explanation_counts_reconcile_to_50():
    status_artifact = json.loads(STATUS_ENRICHMENT_PATH.read_text(encoding="utf-8"))
    summary = build_no_bar_explanation_summary(status_artifact)
    total = (summary["no_bar_explained_by_official_status"]
             + summary["no_bar_still_source_coverage_gap"]
             + summary["no_bar_temporally_unresolved"])
    assert total == 50
    assert len(summary["cohort_50_classified"]) == 50
