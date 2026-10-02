"""Adversarial temporal, basis, lineage and non-voting product contract checks."""
import copy
import json
from pathlib import Path

import pytest
import canonical_market_bars as bars
import prospective_market_snapshot_contract as market
import market_only_pit_eligibility as pit
import integrated_investment_decision_product as product
import market_wide_historical_research_context as history
from test_market_only_pit_eligibility import observation, rehash

CUTOFF = "2026-08-01T10:00:00Z"


def daily(day="2026-07-06", **changes):
    row = dict(session=day, open=10, high=15, low=9, close=12, volume=100,
        provider="DNSE", dataset="DNSE_OHLC_1D", price_unit="SOURCE_PRICE_UNIT_UNDOCUMENTED",
        price_basis="CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
        qualification="CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY", retrieved_at="2026-08-01T09:00:00Z")
    row.update(changes)
    return row


def inputs():
    return [daily(), daily("2026-07-10", open=11, high=20, low=8, close=18, volume=200)]


def calendar():
    # Explicit synthetic ledger; neither the engine nor this fixture infers weekdays.
    return dict(sessions=["2026-07-06", "2026-07-10"], window_start="2026-07-01", window_end="2026-07-31",
        artifact_identity="test_explicit_ledger:1", source={"kind":"EXPLICIT_TEST_LEDGER"})


def derive(rows=None, tf="1W", **changes):
    args = dict(ticker="VNM", timeframe=tf, period_session="2026-07-06", knowledge_cutoff=CUTOFF,
                source_identity="retained:1", calendar_evidence=calendar())
    args.update(changes)
    return bars.derive(inputs() if rows is None else rows, **args)


@pytest.mark.parametrize("tf", ["1W", "1M"])
def test_first_open_last_close_and_extrema(tf):
    b = derive(tf=tf)
    assert [b[k] for k in ("open", "high", "low", "close")] == [10,20,8,18]
    assert b["period_completeness"] == "COMPLETE"
    assert b["first_trading_session"] == "2026-07-06" and b["last_trading_session"] == "2026-07-10"
    assert b["knowledge_available_at"] == "2026-08-01T09:00:00+00:00"


def test_daily_is_exact_projection_with_original_instrument_and_values():
    row=daily(exchange="HNX", board="LISTED", traded_value=12345, traded_value_unit="VND")
    b=derive([row],tf="1D")
    assert all(b[k] == row[k] for k in ("open","high","low","close","volume"))
    assert b["instrument"] == {"ticker":"VNM","exchange":"HNX","board":"LISTED"}
    assert b["turnover"] == 12345 and b["turnover_unit"] == "VND"
    with pytest.raises(ValueError,match="INSTRUMENT"):
        derive([daily(ticker="HPG")])


def test_ordering_duplicates_and_exact_lineage():
    baseline=derive()
    assert derive(list(reversed(inputs()))) == baseline
    assert derive(inputs()+[inputs()[0]]) == baseline
    assert baseline["constituent_count"] == 2
    assert baseline["constituent_sessions"] == [r["session"] for r in inputs()]
    assert baseline["constituent_observation_identities"] == [bars.project_daily(r,ticker="VNM",source_identity="retained:1")["constituent_observation_identities"][0] for r in inputs()]
    with pytest.raises(ValueError,match="CONFLICTING_DUPLICATE"):
        derive(inputs()+[daily(close=13)])


def test_missing_session_is_incomplete():
    assert derive(inputs()[:1])["period_completeness"] == "INCOMPLETE_SESSION_COVERAGE"


def test_future_version_and_session_never_repair_past():
    before=derive()
    assert derive(inputs()+[daily(close=13,retrieved_at="2026-08-02T09:00:00Z")]) == before
    b=derive([daily(retrieved_at="2026-07-06T08:00:00Z"),daily("2026-07-10",retrieved_at="2026-07-10T08:00:00Z")],
             knowledge_cutoff="2026-07-08T10:00:00Z")
    assert b["constituent_sessions"] == ["2026-07-06"]
    assert b["period_completeness"] == "PARTIAL_CURRENT_PERIOD"
    later=derive(inputs()+[daily(close=13,retrieved_at="2026-08-02T09:00:00Z")], knowledge_cutoff="2026-08-03T09:00:00Z")
    assert later["open"] == 10 and later["knowledge_available_at"] == "2026-08-02T09:00:00+00:00"


@pytest.mark.parametrize("tf", ["1W","1M"])
def test_current_period_and_future_calendar_not_complete(tf):
    b=derive([daily(retrieved_at="2026-07-06T08:00:00Z")],tf=tf,knowledge_cutoff="2026-07-06T10:00:00Z")
    assert b["period_completeness"] == "PARTIAL_CURRENT_PERIOD"
    cal={**calendar(),"knowledge_available_at":"2026-08-02T09:00:00Z"}
    assert derive(calendar_evidence=cal)["period_completeness"] == "CALENDAR_SCOPE_UNKNOWN"


def test_governed_calendar_does_not_repair_september():
    cal=bars.governed_calendar_projection(json.loads((Path(__file__).resolve().parents[1]/"config/governed_trading_session_calendar_v1.json").read_text()))
    b=derive([daily("2026-09-08",retrieved_at="2026-10-01T08:00:00Z")],period_session="2026-09-08",knowledge_cutoff="2026-10-01T10:00:00Z",calendar_evidence=cal)
    assert b["period_completeness"] == "CALENDAR_SCOPE_UNKNOWN" and b["expected_sessions"] == []


def test_native_volume_stays_unknown_and_mixed_units_withheld():
    b=derive()
    assert b["volume"] == 300 and b["constituent_volume_values"] == [100,200]
    assert b["volume_unit"] == "UNKNOWN" and b["fitness"]["volume"] == "UNIT_UNDOCUMENTED"
    rows=inputs(); rows[1]["volume_unit"]="SHARES"
    assert derive(rows)["volume"] is None
    rows=inputs(); rows[1]["provider"]="OTHER"
    assert derive(rows)["volume"] is None


def test_retrospective_and_unknown_basis_cannot_gain_authority():
    b=derive()
    assert b["price_basis"] == pit.RETROSPECTIVE_ADJUSTED and b["fitness"]["historical_pit_eligible"] is False
    rows=inputs();rows[1]["price_basis"]="UNKNOWN"
    b=derive(rows)
    assert b["status"] == "UNAVAILABLE" and b["close"] is None and not b["fitness"]["allowed_uses"]
    for mode in ["AS_KNOWN","EMPIRICAL","PROXY_RESEARCH_ONLY","UNKNOWN"]:
        assert bars.project_daily(daily(price_basis=mode),ticker="VNM",source_identity="x")["price_basis"] == mode


def test_weak_fitness_and_invalid_geometry_propagate():
    rows=inputs();rows[1]["qualification"]="UNQUALIFIED"
    assert derive(rows)["fitness"]["allowed_uses"] == []
    assert derive([daily(high=1)])["status"] == "UNAVAILABLE"
    assert derive([daily(retrieved_at=None)])["constituent_count"] == 0


def test_raw_and_ca_crossing_keep_values_without_factors():
    rows=[observation("2026-07-06"), observation("2026-07-10")]
    event={"ticker":"VNM","ex_date":"2026-07-10","event_id":"official:event","official_observed_at":"2026-07-15T08:00:00Z"}
    b=derive(rows,ca_events=[event])
    assert b["price_basis"] == pit.RAW_AS_TRADED and b["status"] == "AVAILABLE"
    assert b["corporate_action_crossing"]["state"] == "EVENTS_OBSERVED"
    assert b["corporate_action_crossing"]["factor_chain_state"] == "NOT_ESTABLISHED"
    assert b["fitness"]["continuous_indicator_use"] == "NOT_ESTABLISHED"
    assert b["knowledge_available_at"] == "2026-07-15T08:00:00+00:00"
    assert derive(rows,requested_price_mode=pit.PIT_CA_ADJUSTED)["status"] == "UNAVAILABLE"
    assert "FACTOR_CHAIN_NOT_QUALIFIED" in derive(rows,requested_price_mode=pit.PIT_CA_ADJUSTED)["warnings"]
    future={**event,"official_observed_at":"2026-08-02T08:00:00Z"}
    assert derive(rows,ca_events=[future]) == derive(rows)
    assert derive(rows,ca_events=[{**event,"event_type":"AGM"}]) == derive(rows)


def test_future_qualified_pit_uses_same_boundary_and_keeps_factor_lineage():
    rows=[observation("2026-07-06"),observation("2026-07-10")]
    for row in rows:
        row["price_mode"]=pit.PIT_CA_ADJUSTED
        row["raw_lineage_identities"]=["raw:original"]
        row["factor_chain"]=[dict(status="QUALIFIED",factor_chain_identity="factor:1",official_execution_status="EXECUTED",
            ex_date_status="EXPLICIT_OFFICIAL",ex_date="2026-07-01",knowledge_cutoff="2026-07-01T08:00:00Z",adjustment_factor=1.1)]
        rehash(row)
    b=derive(rows,requested_price_mode=pit.PIT_CA_ADJUSTED)
    assert b["status"] == "AVAILABLE" and b["price_basis"] == pit.PIT_CA_ADJUSTED
    assert b["constituent_factor_chains"][0]["raw_lineage_identities"] == ["raw:original"]
    rows[0]["factor_chain"][0]["knowledge_cutoff"]="2026-08-02T08:00:00Z";rehash(rows[0])
    assert derive(rows,requested_price_mode=pit.PIT_CA_ADJUSTED)["status"] == "UNAVAILABLE"


def research_artifact():
    projection=bars.research_projection(inputs(),ticker="VNM",target_session="2026-07-31",knowledge_cutoff=CUTOFF,
        source_identity="retained:1",calendar_evidence=calendar())
    artifact={"contract_version":history.CONTRACT_VERSION,"session":"2026-07-31","records":{"VNM":{"multi_timeframe":projection}}}
    artifact.update(history.content_identity(artifact))
    return artifact


def test_product_attaches_context_without_changing_posture_or_decision_identity():
    kwargs=dict(session="2026-07-31",requested_at=CUTOFF,technical_structure_artifact={"records":{"VNM":{"eligible":False}}})
    before=product.build_artifact(**kwargs)
    after=product.build_artifact(**kwargs,historical_context_artifact=research_artifact())
    b=before["records"]["VNM"];a=after["records"]["VNM"]
    context=a["market_sector_context"].pop("multi_timeframe")
    assert context["status"] == "AVAILABLE" and context["non_voting"] is True
    assert a == b
    assert context["projection"]["1W"]["latest_completed"]["period_completeness"] == "COMPLETE"
    assert context["projection"]["PIT_CA_ADJUSTED"]["status"] == "UNAVAILABLE"


def test_existing_historical_builder_supplies_the_single_product_projection():
    from test_market_wide_historical_research_context import universe_resolution, p3f9b_snapshot, _ur
    from field_temporal_contract import stable_id
    snapshot=p3f9b_snapshot({"VNM":{"observations":inputs()}})
    snapshot["requested_at"]="2026-08-25T10:00:00Z"
    snapshot["snapshot_sha256"]=stable_id({k:v for k,v in snapshot.items() if k not in ("snapshot_identity","snapshot_sha256")})
    snapshot["snapshot_identity"]="p3f9_exact_session_snapshot:"+snapshot["snapshot_sha256"]
    h=history.build_artifact(universe_resolution_artifact=universe_resolution({"VNM":_ur("VNM")},denominator=1,observed=1),
        p3f9b_snapshot=snapshot,market_calendar=calendar())
    contexts=product.market_bar_context_records(h,session="2026-08-24",requested_at=snapshot["requested_at"])
    assert contexts["VNM"]["status"] == "AVAILABLE"
    assert contexts["VNM"]["projection"]["1M"]["latest_completed"]["period_start"] == "2026-07-01"


@pytest.mark.parametrize("fault", ["hash","session","future","ticker","nested_hash"])
def test_product_rejects_incoherent_or_future_context(fault):
    artifact=copy.deepcopy(research_artifact())
    p=artifact["records"]["VNM"]["multi_timeframe"]
    if fault == "session":artifact["session"]="2026-08-01"
    if fault == "future":p["knowledge_cutoff"]="2026-08-02T10:00:00Z"
    if fault == "ticker":p["1D"]["latest_observed"]["instrument"]["ticker"]="HPG"
    if fault == "nested_hash":p["1D"]["latest_observed"]["close"]=777
    if fault in ("ticker","nested_hash"):
        p.update(market.content_identity(p,kind="market_bar_research_projection"))
    if fault != "hash":artifact.update(history.content_identity(artifact))
    else:artifact["artifact_sha256"]="tampered"
    result=product.market_bar_context_records(artifact,session="2026-07-31",requested_at=CUTOFF)
    assert result["VNM"]["status"] == "UNAVAILABLE"
