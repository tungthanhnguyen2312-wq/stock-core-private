"""KBS fiscal-period identity: qualified periods may feed arithmetic; raw labels may not."""
from __future__ import annotations

import stocklookup_core.financial.financial_analysis_engine_v2 as engine
import stocklookup_core.financial.financial_flow_semantics_ttm_bridge as bridge
import stocklookup_core.financial.market_wide_financial_analysis_v2_scaleout as scaleout
import stocklookup_core.financial.market_wide_fundamental_feature_store as feature_store
from market_wide_current_fundamental_research import provider_series_trends_for_ticker


def _income(ticker: str, period: str, value: float, *, metric: str = "revenue",
            scale: str = "ONE", scope: str = "consolidated", provider: str = "KBS",
            qualified: str | None = None) -> dict:
    fact = {
        "ticker": ticker, "canonical_metric": metric, "provider": provider,
        "statement_family": "income_statement", "reporting_period": period,
        "period_type": "quarterly", "value": value, "status": "provider_reported",
        "statement_scope": scope, "currency": "VND", "scale": scale,
        "source_sha256": f"{ticker}-{provider}-{scope}", "fact_id": f"{ticker}-{metric}-{period}-{scope}-{provider}",
    }
    if qualified is not None:
        fact["qualified_normalized_period"] = qualified
        fact["period_normalization"] = "FIXTURE_STATED_PERIOD"
    return fact


def _engine_row(metric: str, value: float, native: str, *, qualified: str | None = None,
                provider: str = "KBS", family: str = "income_statement",
                semantic: str = "STANDALONE_QUARTER") -> dict:
    row = {
        "ticker": "HCM", "canonical_metric": metric, "reported_value": value,
        "native_period_label": native, "period_end": native,
        "period_semantic_state": semantic, "source_status": "provider_reported",
        "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
        "statement_family": family,
        "normalized_candidate_unit": {"currency": "VND", "scale": "ONE"},
        "source_lineage": {"provider": provider, "source_file": f"{family}.parquet",
                           "source_sha256": family, "fact_id": f"{metric}-{native}-{qualified or 'raw'}"},
    }
    if qualified is not None:
        row["qualified_normalized_period"] = qualified
    return row


def test_hpg_keeps_the_proven_raw_to_fiscal_map_and_does_not_observe_those_rows() -> None:
    parts = {
        "2025-Q3": 1_000, "2025-Q4": 2_000, "2025-Q4_1": 3_000,
        "2026-Q1": bridge.HPG_KBS_FY2025_ANCHORS["net_income"]["value_vnd"] - 6_000,
    }
    facts = [_income("HPG", label, value, metric="net_income", scale="units") for label, value in parts.items()]
    record = bridge.build_ticker_record(ticker="HPG", entity_type="corporate", facts=facts)
    assert record["ttm"]["net_income"]["source_periods"] == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    assert record["ttm"]["net_income"]["source_raw_periods"] == ["2025-Q4_1", "2025-Q3", "2025-Q4", "2026-Q1"]
    assert facts[3]["reporting_period"] == "2026-Q1"
    assert record["research_observations"] == []


def test_ssi_evf_hcm_dhg_pan_are_not_shifted_by_a_generic_offset() -> None:
    ssi = [_income("SSI", "2026-Q1", 5, scale="MILLION_VND")]
    qualified = bridge.qualify_proven_kbs_income_period(ssi)
    assert qualified[0]["reporting_period"] == "2026-Q1"
    assert "qualified_normalized_period" not in qualified[0]
    ssi_record = bridge.build_ticker_record(ticker="SSI", entity_type="corporate", facts=ssi)
    assert ssi_record["ttm"] == {}
    assert ssi_record["research_observations"][0]["native_period_label"] == "2026-Q1"
    assert ssi_record["research_observations"][0]["scale"] == "MILLION_VND"
    assert ssi_record["research_observations"][0]["is_actionable"] is False
    assert ssi_record["research_observations"][0]["reason_code"] == bridge.KBS_PERIOD_IDENTITY_UNVERIFIED

    evf = [_income("EVF", "2026-Q1", 9, scale="MILLION_VND")]
    evf_record = bridge.build_ticker_record(ticker="EVF", entity_type="finance_company", facts=evf)
    assert evf_record["blocker"] == "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"
    assert evf_record["ttm"] == {}
    assert evf_record["research_observations"][0]["scale"] == "MILLION_VND"
    assert evf_record["research_observations"][0]["native_period_label"] == "2026-Q1"

    hcm = [_income("HCM", "2025-Q4", 7)]
    hcm_out = bridge.qualify_proven_kbs_income_period(hcm)[0]
    assert hcm_out["reporting_period"] == "2025-Q4"
    assert "qualified_normalized_period" not in hcm_out
    hcm_record = bridge.build_ticker_record(ticker="HCM", entity_type="corporate", facts=hcm)
    assert "revenue" not in hcm_record["ttm"]
    assert hcm_record["research_observations"][0]["native_period_label"] == "2025-Q4"

    for ticker in ("DHG", "PAN"):
        raw = [_income(ticker, "2026-Q1", 3)]
        out = bridge.qualify_proven_kbs_income_period(raw)[0]
        assert out["reporting_period"] == "2026-Q1"
        assert "qualified_normalized_period" not in out


def test_proven_matching_period_is_not_false_blocked_and_scopes_do_not_mix() -> None:
    quarters = [_income("FPT", f"2025-Q{q}", 10, qualified=f"2025-Q{q}") for q in range(1, 5)]
    separate = [_income("FPT", f"2025-Q{q}", 10, scope="separate", qualified=f"2025-Q{q}") for q in range(1, 5)]
    record = bridge.build_ticker_record(ticker="FPT", entity_type="corporate", facts=quarters + separate)
    assert record["ttm"]["revenue"]["value"] == 40
    assert record["research_observations"] == []
    other_provider = [_income("FPT", f"2025-Q{q}", 100, provider="VCI") for q in range(1, 5)]
    mixed = bridge.build_ticker_record(ticker="FPT", entity_type="corporate", facts=quarters + other_provider)
    assert mixed["ttm"]["revenue"]["value"] == 40


def test_duplicate_qualified_fiscal_period_is_blocked() -> None:
    facts = [
        _income("AAA", "2025-Q4_1", 10, qualified="2025-Q4"),
        _income("AAA", "2026-Q1", 12, qualified="2025-Q4"),
        _income("AAA", "2025-Q3", 8, qualified="2025-Q3"),
        _income("AAA", "2025-Q2", 6, qualified="2025-Q2"),
        _income("AAA", "2025-Q1", 4, qualified="2025-Q1"),
    ]
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    assert "revenue" not in record["ttm"]
    trends = provider_series_trends_for_ticker(ticker="AAA", facts=[
        {**_income("AAA", "2026-Q1", 12, qualified="2025-Q4"), "source_observation_ids": ["a"]},
        {**_income("AAA", "2025-Q4", 10, qualified="2025-Q4"), "source_observation_ids": ["b"]},
    ])
    assert trends["metrics"]["revenue_growth"]["blocked_reason"] == "SAME_FISCAL_PERIOD_COUNTED_TWICE"


def test_engine_qoq_uses_qualified_period_not_the_raw_kbs_label() -> None:
    rows = [
        _engine_row("net_income", 20, "2025-Q4", qualified="2025-Q3"),
        _engine_row("net_income", 50, "2026-Q1", qualified="2025-Q4"),
        _engine_row("revenue", 100, "2025-Q4", qualified="2025-Q3"),
        _engine_row("revenue", 100, "2026-Q1", qualified="2025-Q4"),
    ]
    features = engine.build_ticker_context("HCM", rows, issuer_type="corporate", source_identities={})["features"]
    qoq = features["net_income_qoq"]
    assert qoq["fitness"] == "READY"
    assert qoq["value"] == 1.5
    assert qoq["period_identity"] == ["2025-Q3", "2025-Q4"]
    assert engine.RAW_PERIOD_LABEL_DIFFERS_FROM_QUALIFIED_PERIOD in qoq["warnings"]
    direction = features["net_margin_direction"]
    assert direction["fitness"] == "READY"
    assert abs(direction["value"] - 0.3) < 1e-9
    raw = [
        _engine_row("net_income", 20, "2025-Q3"),
        _engine_row("net_income", 40, "2025-Q4"),
    ]
    blocked = engine.build_ticker_context("HCM", raw, issuer_type="corporate", source_identities={})["features"]["net_income_qoq"]
    assert blocked["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert engine.KBS_PERIOD_IDENTITY_UNVERIFIED in blocked["reason_codes"]


def test_feature_store_blocks_unverified_kbs_income_and_keeps_a_qualified_period() -> None:
    def row(period: str, value: float, *, qualified: str | None = None) -> dict:
        item = {
            "ticker": "AAA", "canonical_metric": "revenue", "statement_scope": "consolidated",
            "statement_family": "income_statement", "native_period_label": period, "period_end": period,
            "period_semantic_state": "STANDALONE_QUARTER", "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "reported_value": value,
            "source_lineage": {"provider": "KBS", "source_file": "income", "source_sha256": "a", "raw_item_id": "revenue"},
        }
        if qualified is not None:
            item["qualified_normalized_period"] = qualified
        return item
    blocked = feature_store.build_ticker_record("AAA", [row("2025-Q2", 100), row("2026-Q2", 130)], {"AAA": "corporate"})
    assert blocked["features"]["revenue_same_period_yoy"]["blocker_reason_codes"] == [feature_store.KBS_PERIOD_IDENTITY_UNVERIFIED]
    ready = feature_store.build_ticker_record(
        "AAA", [row("2025-Q2", 100, qualified="2025-Q2"), row("2026-Q2", 130, qualified="2026-Q2")],
        {"AAA": "corporate"})
    assert abs(ready["features"]["revenue_same_period_yoy"]["value"] - 0.3) < 1e-9


def test_scaleout_does_not_revive_an_unverified_income_proxy_over_a_ready_balance_sheet() -> None:
    def semantic(metric: str, value: float, period: str, *, family: str, provider: str, semantic_state: str) -> dict:
        return {
            "ticker": "AAA", "canonical_metric": metric, "reported_value": value,
            "native_period_label": period, "period_end": period, "period_semantic_state": semantic_state,
            "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
            "statement_family": family, "statement_scope": "consolidated",
            "normalized_candidate_unit": {"currency": "VND", "scale": "ONE"},
            "source_lineage": {"provider": provider, "source_file": family, "source_sha256": family,
                               "fact_id": f"{metric}-{period}"},
        }
    rows = [semantic("revenue", 100, f"2025-Q{q}", family="income_statement", provider="KBS", semantic_state="STANDALONE_QUARTER")
            for q in range(1, 5)]
    rows += [semantic("net_income", 25, f"2025-Q{q}", family="income_statement", provider="KBS", semantic_state="STANDALONE_QUARTER")
             for q in range(1, 5)]
    rows += [
        semantic("shareholders_equity", 500, "2025-Q4", family="balance_sheet", provider="VCI", semantic_state="POINT_IN_TIME_BALANCE_SHEET"),
        semantic("total_assets", 1000, "2025-Q4", family="balance_sheet", provider="VCI", semantic_state="POINT_IN_TIME_BALANCE_SHEET"),
    ]
    store = {"ticker": "AAA", "entity_type": "corporate", "entity_applicability": "ENTITY_SPECIFIC", "features": {
        "profit_state": {"status": "READY_RESEARCH_PROXY", "value": 10, "categorical_state": "PROFITABLE",
                         "input_periods": ["2026-Q1"], "provider_source_lineage": [], "scope": ["consolidated"],
                         "duration_semantics": ["STANDALONE_QUARTER"]},
        "net_margin": {"status": "READY_RESEARCH_PROXY", "value": 0.1, "categorical_state": None,
                       "input_periods": ["2026-Q1"], "provider_source_lineage": [], "scope": ["consolidated"],
                       "duration_semantics": ["STANDALONE_QUARTER"]},
        "total_assets_pit_trajectory": {"status": "READY_RESEARCH_PROXY", "value": 0.2, "categorical_state": "INCREASING",
                                        "input_periods": ["2024-Q4", "2025-Q4"], "provider_source_lineage": [],
                                        "scope": ["consolidated"], "duration_semantics": ["POINT_IN_TIME_BALANCE_SHEET"]},
    }}
    qualified = scaleout.build_qualified_flow_artifact(semantic_rows=rows, feature_records={"AAA": store}, requested_at="t")
    artifact = scaleout.build_scaleout(
        semantic_rows=rows, feature_records={"AAA": store}, feature_store_artifact={"artifact_identity": "store:1"},
        period_semantics_identity="sem:1", requested_at="t", qualified_flow_artifact=qualified,
    )
    record = artifact["records"]["AAA"]
    # Same-column margin stays a warned ratio. The raw label is not a fiscal period,
    # so the store proxy must not become the sign, and TTM stays blocked.
    assert record["features"]["net_margin"]["fitness"] == "READY"
    assert record["features"]["net_margin"]["value"] == 0.25
    assert bridge.RAW_KBS_PERIOD_LABEL_RETAINED in record["features"]["net_margin"]["warnings"]
    assert record["features"]["net_income_sign"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert bridge.KBS_PERIOD_IDENTITY_UNVERIFIED in record["features"]["net_income_sign"]["reason_codes"]
    assert record["features"]["net_income_ttm"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert record["features"]["net_income_sign"]["fitness"] != "RESEARCH_PROXY"
    assert record["features"]["equity_to_assets"]["fitness"] == "READY"
    assert record["features"]["equity_to_assets"]["value"] == 0.5
    assert record["features"]["assets_yoy"]["fitness"] == "RESEARCH_PROXY"
    assert record["current_research_ready"] is True
    assert record["research_observations"]


def test_explicit_retained_flow_basis_still_builds_ttm() -> None:
    facts = []
    for quarter in range(1, 5):
        fact = _income("CMG", f"2025-Q{quarter}", quarter)
        fact["flow_period_basis"] = "STANDALONE_QUARTER"
        facts.append(fact)
    record = bridge.build_ticker_record(ticker="CMG", entity_type="corporate", facts=facts)
    assert record["ttm"]["revenue"]["value"] == 10
    assert record["research_observations"] == []
