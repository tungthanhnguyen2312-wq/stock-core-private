"""Focused tests for screener_master_projection/v1."""
from __future__ import annotations

import json

import pytest

from screener_master_projection import (
    CONTRACT_VERSION,
    ENTITY_CLASS_VOCABULARY,
    EXECUTION_BLOCKED,
    LIQUIDITY_PROXY,
    PRICE_UNAVAILABLE,
    ScreenerMasterProjectionError,
    build_projection,
    content_identity,
    display_exchange_for,
    js_fallback,
    load_vci_industry_labels,
)


SESSION = "2026-08-28"


def _row(ticker, *, listing="HOSE", close=22.2, change=0.0135, industry="", observation="EXACT_SESSION_RETAINED",
         basis="CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"):
    return {
        "ticker": ticker, "date": SESSION, "close": "" if close is None else close,
        "chg_today_pct": "" if change is None else change, "gtgd20_ty": "",
        "exchange": "DELISTED" if listing == "HNX_LISTED" else "HSX",
        "industry": industry, "listing_exchange": listing,
        "canonical_observation_status": observation if close is not None else "UNAVAILABLE_NO_EXACT_SESSION_OBSERVATION",
        "canonical_price_basis": basis if close is not None else "",
    }


def _workspace(*tickers, extra=None, stances=None, entries=None, entities=None, financial=None):
    stances = stances or {}
    entries = entries or {}
    entities = entities or {}
    financial = financial or {}
    cards = {}
    for ticker in tickers:
        cards[ticker] = {
            "ticker": ticker,
            "as_of_session": SESSION,
            "research_stance": stances.get(ticker, "WAIT_FOR_CONFIRMATION"),
            "research_stance_readiness": "CONDITIONAL",
            "entry_state": entries.get(ticker, "DOWNTREND"),
            "entry_action": "WATCH",
            "valuation": {"entity_class": entities.get(ticker, "corporate")},
            "liquidity": {
                "readiness": LIQUIDITY_PROXY,
                "descriptive_research_state": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE",
                "exact_execution_capacity_status": EXECUTION_BLOCKED,
                "source_session": SESSION,
            },
            "tactical": {
                "primary_entry_state": entries.get(ticker, "DOWNTREND"),
                "entry_action": "WATCH",
                "freshness_status": "CURRENT",
                "source_session": SESSION,
            },
            "why": {"financial_analysis": financial.get(ticker, {"status": "ABSENT", "compact": None})},
            "lineage": {"per_axis_freshness": {"tactical": "CURRENT", "liquidity": "CURRENT"}},
        }
    if extra:
        cards.update(extra)
    return {
        "contract_version": "investment_decision_workspace_projection/v1",
        "as_of_session": SESSION,
        "artifact_identity": "investment_decision_workspace_projection/v1:fixture",
        "cards": cards,
        "coverage": {"ticker_denominator": len(cards), "zero_silent_ticker_drops": True},
    }


def _financial(*tickers, absent=()):
    records = {}
    for ticker in tickers:
        records[ticker] = {
            "contract_version": "financial_analysis_compact/v1",
            "ticker": ticker, "status": "AVAILABLE", "current_research_ready": True,
            "profitability_state": "PROFITABLE", "cash_conversion_state": "UNAVAILABLE",
            "capital_efficiency_state": "UNAVAILABLE", "working_capital_state": "POSITIVE_NET_WORKING_CAPITAL",
        }
    for ticker in absent:
        records[ticker] = {
            "contract_version": "financial_analysis_compact/v1",
            "ticker": ticker, "status": "ABSENT", "reason": "FA_V2_CONTEXT_ABSENT",
        }
    return {
        "contract_version": "financial_analysis_product_integration/v1",
        "artifact_identity": "financial_analysis_product_integration/v1:fixture",
        "records": records,
    }


def _industry(**labels):
    return {
        ticker: {"label": label, "status": "AVAILABLE", "namespace": "VCI_PROVIDER_INDUSTRY", "as_of": SESSION}
        for ticker, label in labels.items()
    }


def test_display_exchange_hnx_listed_never_falls_through_to_delisted():
    mapped = display_exchange_for("HNX_LISTED")
    assert mapped["listing_exchange"] == "HNX_LISTED"
    assert mapped["display_exchange"] == "HNX"
    assert mapped["display_exchange"] != "DELISTED"
    assert display_exchange_for("HOSE")["display_exchange"] == "HSX"
    assert display_exchange_for("UPCOM")["display_exchange"] == "UPCOM"
    assert display_exchange_for("DELISTED")["display_exchange"] == "DELISTED"
    unknown = display_exchange_for("SOME_NEW_BOARD")
    assert unknown["display_exchange"] is None
    assert unknown["status"] == "UNKNOWN"


def test_denominator_equals_snapshot_with_zero_duplicates_and_no_workspace_extras():
    snapshot = [_row("HPG"), _row("SSI", listing="HNX_LISTED"), _row("AAA")]
    workspace = _workspace("HPG", "SSI", "AAA", extra={"ZZZEXTRA": {
        "ticker": "ZZZEXTRA", "research_stance": "INITIATE_RESEARCH_CANDIDATE",
        "research_stance_readiness": "READY", "entry_state": "BREAKOUT_READY",
        "entry_action": "WATCH", "valuation": {"entity_class": "corporate"},
        "liquidity": {"readiness": LIQUIDITY_PROXY, "descriptive_research_state": "AVAILABLE",
                      "exact_execution_capacity_status": EXECUTION_BLOCKED},
        "tactical": {"primary_entry_state": "BREAKOUT_READY", "freshness_status": "CURRENT"},
        "why": {"financial_analysis": {"status": "ABSENT"}},
        "lineage": {"per_axis_freshness": {}},
    }})
    out = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=workspace)
    assert out["coverage"]["ticker_denominator"] == 3
    assert set(out["cards"]) == {"HPG", "SSI", "AAA"}
    assert "ZZZEXTRA" not in out["cards"]
    assert out["coverage"]["duplicate_count"] == 0
    assert out["zero_silent_drops"] is True
    assert out["coverage"]["workspace_only_extras_excluded"] == 1


def test_duplicate_snapshot_tickers_fail_closed():
    with pytest.raises(ScreenerMasterProjectionError, match="DUPLICATE"):
        build_projection(snapshot_rows=[_row("HPG"), _row("HPG")], requested_at="t")


def test_hnx_listed_display_and_unpriced_retained_with_explicit_status():
    snapshot = [
        _row("SSI", listing="HNX_LISTED", close=18.4, change=0.01),
        _row("AAA", listing="HNX_LISTED", close=None, change=None),
        _row("HPG", close=22.2, change=0.0135),
    ]
    out = build_projection(snapshot_rows=snapshot, requested_at="t")
    assert out["cards"]["SSI"]["display_exchange"] == "HNX"
    assert out["cards"]["AAA"]["display_exchange"] == "HNX"
    assert out["cards"]["AAA"]["price"]["status"] == PRICE_UNAVAILABLE
    assert out["cards"]["AAA"]["price"]["value"] is None
    assert out["cards"]["AAA"]["price"]["reason"]
    assert out["coverage"]["price_available_count"] == 2
    assert out["coverage"]["price_unavailable_explicit_count"] == 1
    assert out["cards"]["HPG"]["price"]["change_pct"] == 0.0135
    assert out["cards"]["HPG"]["price"]["change_pct_unit"] == "FRACTION"


def test_return_remains_fraction_contract_not_multiplied():
    out = build_projection(snapshot_rows=[_row("HPG", change=0.0135)], requested_at="t")
    assert out["cards"]["HPG"]["price"]["change_pct"] == pytest.approx(0.0135)
    assert out["cards"]["HPG"]["price"]["change_pct"] != pytest.approx(1.35)
    assert out["cards"]["HPG"]["price"]["change_pct"] != pytest.approx(0.01)


def test_sector_never_uses_entity_class_and_unknown_is_explicit():
    snapshot = [_row("HPG", industry="corporate"), _row("VCB", industry="bank"), _row("XYZ", industry="")]
    industry = _industry(HPG="Thép và Sản phẩm thép")
    entities = {"HPG": "corporate", "VCB": "bank", "XYZ": "corporate"}
    out = build_projection(
        snapshot_rows=snapshot, requested_at="t", industry_by_ticker=industry, entity_by_ticker=entities,
    )
    assert out["cards"]["HPG"]["sector"]["label"] == "Thép và Sản phẩm thép"
    assert out["cards"]["HPG"]["sector"]["status"] == "AVAILABLE"
    assert out["cards"]["HPG"]["entity_type"]["value"] == "corporate"
    assert out["cards"]["VCB"]["sector"]["label"] is None
    assert out["cards"]["VCB"]["sector"]["status"] == "UNKNOWN"
    assert out["cards"]["VCB"]["entity_type"]["value"] == "bank"
    assert out["cards"]["XYZ"]["sector"]["reason"]
    for card in out["cards"].values():
        assert card["sector"]["label"] not in ENTITY_CLASS_VOCABULARY
        assert card["sector"]["label"] != "Doanh nghiệp chung"


def test_unknown_entity_token_is_explicit_unknown_not_available():
    out = build_projection(
        snapshot_rows=[_row("ADC", listing="HNX_LISTED", close=None, change=None)],
        requested_at="t",
        entity_by_ticker={"ADC": "unknown"},
    )
    assert out["cards"]["ADC"]["entity_type"]["value"] is None
    assert out["cards"]["ADC"]["entity_type"]["status"] == "UNKNOWN"


def test_entity_class_token_rejected_even_if_supplied_as_industry_label():
    out = build_projection(
        snapshot_rows=[_row("HPG")],
        requested_at="t",
        industry_by_ticker=_industry(HPG="bank"),
        entity_by_ticker={"HPG": "bank"},
    )
    assert out["cards"]["HPG"]["sector"]["label"] is None
    assert "ENTITY_CLASS" in out["cards"]["HPG"]["sector"]["reason"]
    assert out["cards"]["HPG"]["entity_type"]["value"] == "bank"


def test_research_liquidity_survives_exact_execution_block_without_fake_gtgd():
    snapshot = [_row("HPG"), _row("SSI", listing="HNX_LISTED")]
    workspace = _workspace("HPG", "SSI")
    out = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=workspace)
    for ticker in ("HPG", "SSI"):
        card = out["cards"][ticker]
        assert card["liquidity"]["method"] == LIQUIDITY_PROXY
        assert card["liquidity"]["research_value"] is None
        assert card["liquidity"]["research_value_reason"]
        assert card["execution"]["capacity_exact_status"] == EXECUTION_BLOCKED
        assert "gtgd" not in json.dumps(card).lower() or "no_fake_gtgd" in json.dumps(card)


def test_numeric_liquidity_value_is_rejected_as_fake_adv20():
    with pytest.raises(ScreenerMasterProjectionError, match="UNSUPPORTED_NUMERIC_RESEARCH_LIQUIDITY"):
        build_projection(
            snapshot_rows=[_row("HPG")],
            requested_at="t",
            liquidity_by_ticker={"HPG": {"research_value": 22.2 * 1000, "method": LIQUIDITY_PROXY}},
        )


def test_financial_v2_absent_does_not_drop_ticker():
    snapshot = [_row("HPG"), _row("AAA")]
    out = build_projection(
        snapshot_rows=snapshot, requested_at="t",
        financial_v2=_financial("HPG", absent=("AAA",)),
        workspace=_workspace("HPG", "AAA"),
    )
    assert set(out["cards"]) == {"HPG", "AAA"}
    assert out["cards"]["HPG"]["financial_v2"]["status"] == "AVAILABLE"
    assert out["cards"]["HPG"]["financial_v2"]["short_term_liquidity_state"] == "POSITIVE_NET_WORKING_CAPITAL"
    assert out["cards"]["AAA"]["financial_v2"]["status"] == "ABSENT"
    assert out["cards"]["AAA"]["financial_v2"]["reason"] == "FA_V2_CONTEXT_ABSENT"


def test_stance_and_tactical_states_are_independent():
    snapshot = [_row("HPG"), _row("SSI", listing="HNX_LISTED")]
    workspace = _workspace(
        "HPG", "SSI",
        stances={"HPG": "AVOID_NEW_ENTRY", "SSI": "INITIATE_RESEARCH_CANDIDATE"},
        entries={"HPG": "BREAKOUT_READY", "SSI": "DOWNTREND"},
    )
    out = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=workspace)
    assert out["cards"]["HPG"]["research"]["stance"] == "AVOID_NEW_ENTRY"
    assert out["cards"]["HPG"]["tactical"]["entry_state"] == "BREAKOUT_READY"
    assert out["cards"]["SSI"]["research"]["stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert out["cards"]["SSI"]["tactical"]["entry_state"] == "DOWNTREND"
    assert out["cards"]["HPG"]["research"]["stance"] != out["cards"]["HPG"]["tactical"]["entry_state"]


def test_naked_required_null_count_is_zero():
    snapshot = [_row("HPG"), _row("SSI", listing="HNX_LISTED", close=None, change=None), _row("AAA")]
    out = build_projection(
        snapshot_rows=snapshot, requested_at="t",
        workspace=_workspace("HPG", "SSI"),
        industry_by_ticker=_industry(HPG="Thép và Sản phẩm thép"),
        financial_v2=_financial("HPG", absent=("SSI", "AAA")),
    )
    assert out["coverage"]["naked_required_null_count"] == 0
    for card in out["cards"].values():
        assert card["price"]["status"]
        assert card["sector"]["status"]
        assert card["entity_type"]["status"]
        assert card["liquidity"]["research_value_status"]
        assert card["tactical"]["status"]
        assert card["research"]["status"]
        assert card["exchange_status"]


def test_deterministic_identity_excludes_requested_at_and_self():
    snapshot = [_row("HPG"), _row("SSI", listing="HNX_LISTED")]
    first = build_projection(snapshot_rows=snapshot, requested_at="2026-09-01T00:00:00+07:00")
    second = build_projection(snapshot_rows=snapshot, requested_at="2099-01-01T00:00:00Z")
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["artifact_identity"].startswith(CONTRACT_VERSION + ":")
    recomputed = content_identity(first)
    assert recomputed["artifact_sha256"] == first["artifact_sha256"]
    mutated = dict(first)
    mutated["as_of_session"] = "2099-01-01"
    assert content_identity(mutated)["artifact_sha256"] != first["artifact_sha256"]


def test_same_input_same_projection_and_js_is_serialization():
    snapshot = [_row("HPG"), _row("FPT")]
    workspace = _workspace("HPG", "FPT")
    first = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=workspace)
    second = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=workspace)
    assert first == second
    js = js_fallback(first)
    assert js.startswith("window.SCREENER_MASTER_PROJECTION = ")
    parsed = json.loads(js.split(" = ", 1)[1].rstrip(";\n"))
    assert parsed == first


def test_load_vci_industry_labels_uses_governed_provider_not_entity_class(tmp_path):
    path = tmp_path / "vci.jsonl"
    path.write_text(
        json.dumps({
            "provider": "vnstock:Listing(source=VCI).symbols_by_industries",
            "field": "industry", "ticker": "HPG", "value": "Thép và Sản phẩm thép",
            "timestamps": {"observed_at": "2026-07-12 20:34"},
        }, ensure_ascii=False) + "\n"
        + json.dumps({
            "provider": "VCI", "field": "industry", "ticker": "SSI", "value": "ignored-wrong-provider",
            "timestamps": {"observed_at": "2026-07-12 20:34"},
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    labels = load_vci_industry_labels(path)
    assert labels["HPG"]["label"] == "Thép và Sản phẩm thép"
    assert "SSI" not in labels


def test_freshness_does_not_collapse_stale_usable_and_unavailable():
    snapshot = [_row("HPG"), _row("AAA", close=None, change=None)]
    out = build_projection(snapshot_rows=snapshot, requested_at="t", workspace=_workspace("HPG"))
    assert out["cards"]["HPG"]["freshness"]["price"] == "CURRENT"
    assert out["cards"]["AAA"]["freshness"]["price"] == "UNAVAILABLE"
    assert out["cards"]["AAA"]["freshness"]["price"] != out["cards"]["HPG"]["freshness"]["tactical"]
    assert "row" in out["cards"]["HPG"]["freshness"]
