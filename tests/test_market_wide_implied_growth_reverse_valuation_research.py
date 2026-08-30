from __future__ import annotations

from market_wide_implied_growth_reverse_valuation_research import build_artifact, solve_fcff_terminal_growth


def _current(*, price=100.0, status="PRICE_READY"):
    return {"valuation_session": "2026-08-28", "artifact_identity": "valuation:source", "records": {
        "CORP": {"price_input": {"value": price, "status": status, "session": "2026-08-28", "source_snapshot_identity": "snapshot:one"}},
        "BANK": {"price_input": {"value": 50.0, "status": "PRICE_READY", "session": "2026-08-28", "source_snapshot_identity": "snapshot:two"}},
        "NONE": {"price_input": {"value": None, "status": "BLOCKED"}},
    }}


def _proxy():
    return {"artifact_identity": "proxy:source", "records": {
        ticker: {"valuation_tier": "VALUATION_RESEARCH_PROXY_RESTRICTED", "metrics": {"proxy_P/E": {"value": 10.0}}, "warnings": ["CURRENT_ONLY_NOT_PIT"]}
        for ticker in ("CORP", "BANK", "NONE")
    }}


def _intrinsic(*, invalid_terminal=False):
    return {"artifact_identity": "intrinsic:source", "records": {
        "CORP": {"methods": {"net_net": {"state": "available", "per_share_value": 150.0, "warnings": ["existing"]}}, "reverse_fcff_inputs": {
            "forecast_fcff": 10.0, "forecast_fcff_source": "retained forecast contract",
            "wacc": 0.10, "wacc_source": "retained discount contract",
            "market_enterprise_value": 200.0, "market_enterprise_value_source": "retained market EV contract",
            "growth_bounds": {"lower": -0.10, "upper": 0.09},
            **({"terminal_growth": 0.10} if invalid_terminal else {}),
        }},
        "BANK": {"methods": {"fcff_dcf": {"state": "inapplicable", "per_share_value": None}}},
    }}


def test_valid_reverse_and_existing_value_gap_preserve_upstream_identity():
    artifact = build_artifact(current_valuation=_current(), valuation_proxy=_proxy(), fundamental={"artifact_identity": "fundamental:source", "records": {"CORP": {"axes": {}}}}, intrinsic=_intrinsic())
    record = artifact["records"]["CORP"]
    reverse = record["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]
    gap = record["methods"]["EXISTING_INTRINSIC_VALUE_GAP_V1"]
    assert reverse["state"] == "READY"
    assert abs(reverse["solved_value"] - 0.05) < 1e-9
    assert reverse["solved_parameter"] == "terminal_growth"
    assert gap["state"] == "READY" and gap["absolute_gap"] == 50.0 and gap["relative_gap"] == 0.5
    assert record["upstream_identities"]["intrinsic"] == "intrinsic:source"
    assert record["research_tier"] == "CURRENT_RESEARCH_ONLY" and record["is_actionable"] is False


def test_sector_inapplicable_and_missing_intrinsic_fail_closed_without_score_forecast():
    artifact = build_artifact(current_valuation=_current(), valuation_proxy=_proxy(), fundamental={"records": {"BANK": {"axes": {"GROWTH_MOMENTUM": {"score": 1.0}}}}}, intrinsic=_intrinsic())
    bank = artifact["records"]["BANK"]
    assert bank["methods"]["EXISTING_INTRINSIC_VALUE_GAP_V1"]["state"] == "UNAVAILABLE"
    assert bank["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]["state"] == "UNAVAILABLE"
    assert bank["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]["used_inputs"] == {}
    assert bank["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]["solved_value"] is None


def test_unusable_price_no_root_and_terminal_constraint_are_blocked():
    no_price = build_artifact(current_valuation=_current(price=None, status="BLOCKED"), valuation_proxy=_proxy(), intrinsic=_intrinsic())
    assert no_price["records"]["CORP"]["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]["reason_codes"] == ["CURRENT_PRICE_UNUSABLE"]
    invalid = build_artifact(current_valuation=_current(), valuation_proxy=_proxy(), intrinsic=_intrinsic(invalid_terminal=True))
    assert invalid["records"]["CORP"]["methods"]["REVERSE_FCFF_TERMINAL_GROWTH_V1"]["reason_codes"] == ["EXISTING_TERMINAL_GROWTH_VIOLATES_DISCOUNT_RATE"]
    assert solve_fcff_terminal_growth(forecast_fcff=10.0, discount_rate=.1, market_enterprise_value=10.0, lower_bound=-.1, upper_bound=.09)["reason"] == "NO_ROOT_WITHIN_ADMISSIBLE_BOUNDS"


def test_determinism_coverage_and_no_action_outputs():
    first = build_artifact(current_valuation=_current(), valuation_proxy=_proxy(), intrinsic=_intrinsic())
    assert first == build_artifact(current_valuation=_current(), valuation_proxy=_proxy(), intrinsic=_intrinsic())
    assert first["universe_denominator"] == 3 and first["residual"] == 0
    assert first["coverage"]["states"]["READY"] == 1
    rendered = str(first)
    for prohibited in ("target_price", "recommendation", "position_size", "probability"):
        assert prohibited not in rendered
