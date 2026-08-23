from market_wide_current_valuation_input_scaleout import build_current_valuation_artifact, content_identity


def _inputs():
    prices = {"resolved_completed_session": "2026-08-21", "source": "DNSE", "snapshot_identity": "price:1", "records": {
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"close": 10_000}]},
        "VCB": {"disposition": "SESSION_MISSING", "observations": []},
    }}
    fundamentals = {"artifact_identity": "fund:1", "records": {
        "AAA": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "revenue"}]},
        "VCB": {"entity_class": "bank", "authority_tier": "PROVIDER_RESEARCH"},
    }}
    shares = {"artifact_identity": "shares:1", "projected_coverage_impact": {"cohort_rows": [
        {"ticker": "AAA", "resolver_authority": "provider_reported_lagged", "freshness_state": "PROVIDER_REPORTED_STALE", "provider_value": 100},
    ]}}
    return prices, fundamentals, shares


def test_deterministic_and_stale_shares_block_every_dependent_metric():
    first = build_current_valuation_artifact(price_snapshot=_inputs()[0], fundamental_artifact=_inputs()[1], share_promotion_artifact=_inputs()[2])
    second = build_current_valuation_artifact(price_snapshot=_inputs()[0], fundamental_artifact=_inputs()[1], share_promotion_artifact=_inputs()[2])
    assert first["artifact_identity"] == second["artifact_identity"]
    assert content_identity(first)["artifact_sha256"] == first["artifact_sha256"]
    assert first["coverage"]["price_ready"] == 1
    assert first["coverage"]["share_ready"] == 0
    assert first["records"]["AAA"]["metrics"]["market_cap"]["status"] == "BLOCKED"
    assert "CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION" in first["records"]["AAA"]["metrics"]["P/E"]["blocked_reasons"]


def test_bank_industrial_metrics_remain_not_applicable_without_synthesizing_financials():
    prices, fundamentals, shares = _inputs()
    artifact = build_current_valuation_artifact(price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares)
    bank = artifact["records"]["VCB"]
    assert bank["metrics"]["P/E"]["status"] == "BLOCKED"
    assert bank["metrics"]["EV/Sales"]["status"] == "NOT_APPLICABLE"
    assert bank["financial_input"]["authority"] == "PROVIDER_RESEARCH"
    assert bank["financial_input"]["calculation_grade"] is False
