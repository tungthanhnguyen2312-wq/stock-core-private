import copy
from dataclasses import replace

import pytest

import market_only_pit_eligibility as eligibility
import prospective_market_snapshot_contract as market

DAYS = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]
REQUIREMENTS = eligibility.SignalRequirements("TEST_MARKET_INPUTS", 2, volume_required=True)


def observation(day, *, ticker="VNM", close=11., known=None, **changes):
    known = known or day+"T09:00:00Z"
    row = market.build_snapshot(provider="DNSE", source_id="DNSE_OHLC_1D", route="/price/ohlc", ticker=ticker, exchange="HOSE",
        session=day, receipt_at=known, payload_sha256="a"*64, payload_bytes=10,
        payload_hash_kind="canonical_json_of_retained_observation", next_session=None,
        ohlc={"open":10., "high":15., "low":9., "close":close}, volume_value={"volume":100},
        board_basis={"unit":"VND"}, cross_source_agreement=True)
    row["volume_qualification"] = {"unit":"SHARES","basis":"AS_REPORTED","allowed_uses":["PROSPECTIVE_AS_KNOWN_VOLUME_EVIDENCE"]}
    row.update(changes)
    rehash(row)
    return row


def rehash(row):
    row["snapshot_identity"] = market.CONTRACT_VERSION+":"+market.sha256_hex(market.canonical({k:v for k,v in row.items() if k != "snapshot_identity"}))


def binding(**changes):
    value = {"ticker":"VNM","exchange":"HOSE","source_identity":"official:receipt", "knowledge_available_at":DAYS[0]+"T08:00:00Z",
             "window_start":DAYS[0],"window_end":DAYS[-1],"active_universe_at_time":"ACTIVE","temporal_membership_qualified":True,
             "state":"NO_APPLICABLE_CA_PROVEN"}
    value.update(changes)
    return value


def inputs():
    return dict(requirements=REQUIREMENTS,ticker="VNM",session=DAYS[1],knowledge_cutoff=DAYS[1]+"T10:00:00Z",
                market_versions=[observation(day) for day in DAYS[:2]],calendar_sessions=DAYS,
                universe_versions=[binding()],ca_versions=[binding()])


def test_market_gate_independent_of_unrelated_research_and_execution():
    row = eligibility.evaluate(**inputs())
    assert row["state"] == "ELIGIBLE" and not row["reason_codes"]
    assert row["net_execution_state"].startswith("UNAVAILABLE")
    assert row["authority_effect"] == "NONE"


@pytest.mark.parametrize("field", ["open","high","low","close"])
def test_later_price_never_used_at_t0(field):
    i = inputs()
    row = i["market_versions"][-1]
    row["normalized"]["ohlc"][field] += 1
    row["acquisition"]["knowledge_available_at_utc"] = DAYS[2]+"T09:00:00Z"
    row["acquisition"]["receipt_at_utc"] = DAYS[2]+"T09:00:00Z"
    rehash(row)
    assert "KNOWLEDGE_CUTOFF_VIOLATION" in eligibility.evaluate(**i)["reason_codes"]


def test_future_source_correction_cannot_mutate_original_selected_window():
    i = inputs()
    before = eligibility.evaluate(**i)
    i["market_versions"].append(observation(DAYS[1], close=12., known=DAYS[2]+"T09:00:00Z"))
    assert eligibility.evaluate(**i) == before


def test_later_volume_and_unknown_units_withheld_separately():
    i = inputs()
    i["market_versions"][-1]["volume_qualification"]["unit"] = "LOTS"
    rehash(i["market_versions"][-1])
    assert eligibility.evaluate(**i)["reason_codes"] == ["VOLUME_NOT_PIT_ELIGIBLE"]
    i["requirements"] = replace(REQUIREMENTS,volume_required=False)
    assert eligibility.evaluate(**i)["state"] == "ELIGIBLE"


@pytest.mark.parametrize("change", [{"knowledge_available_at":"2026-10-05T08:00:00Z"}, {"temporal_membership_qualified":False},
    {"active_universe_at_time":"UNKNOWN"}, {"window_start":DAYS[2]}, {"window_end":DAYS[0]}, {"source_identity":None}, {"exchange":"HNX"}])
def test_future_listing_delisting_and_current_survivor_presence_are_not_membership(change):
    i = inputs(); i["universe_versions"] = [binding(**change)]
    assert "ACTIVE_UNIVERSE_UNKNOWN" in eligibility.evaluate(**i)["reason_codes"]


@pytest.mark.parametrize("change", [{"knowledge_available_at":"2026-10-05T08:00:00Z"}, {"state":"CALENDAR_DATE_ONLY"},
    {"state":"MISSING_TERMS"}, {"window_start":DAYS[2]}, {"source_identity":None}])
def test_later_ca_terms_and_unqualified_calendar_do_not_establish_comparability(change):
    i = inputs(); i["ca_versions"] = [binding(**change)]
    assert "CA_FACTOR_REQUIRED_UNAVAILABLE" in eligibility.evaluate(**i)["reason_codes"]


def test_retrospective_adjusted_and_mixed_price_basis_are_excluded():
    i = inputs(); i["market_versions"][-1]["price_mode"] = eligibility.RETROSPECTIVE_ADJUSTED
    rehash(i["market_versions"][-1])
    assert {"PRICE_NOT_PIT_ELIGIBLE","BASIS_INCOMPATIBLE"} <= set(eligibility.evaluate(**i)["reason_codes"])


def test_future_benchmark_is_not_eligible_for_relative_strength_like_use():
    i = inputs(); i["requirements"] = replace(REQUIREMENTS,benchmark_required=True,benchmark_ticker="VNINDEX")
    i["benchmark_versions"] = [observation(d,ticker="VNINDEX") for d in DAYS[:2]]
    i["ca_versions"].append(binding(ticker="VNINDEX"))
    assert eligibility.evaluate(**i)["state"] == "ELIGIBLE"
    i["benchmark_versions"][-1] = observation(DAYS[1],ticker="VNINDEX",known=DAYS[2]+"T09:00:00Z")
    assert "BENCHMARK_NOT_ELIGIBLE" in eligibility.evaluate(**i)["reason_codes"]


def test_missing_lookback_is_not_padded_and_no_weekday_inference():
    i = inputs(); i["market_versions"].pop(0)
    assert "LOOKBACK_WINDOW_INSUFFICIENT" in eligibility.evaluate(**i)["reason_codes"]
    i = inputs(); i["calendar_sessions"] = [DAYS[0]]
    assert "SESSION_NOT_IN_GOVERNED_CALENDAR" in eligibility.evaluate(**i)["reason_codes"]


def test_identity_mutation_and_backdated_knowledge_cannot_qualify():
    i = inputs(); i["market_versions"][-1]["normalized"]["ohlc"]["close"] = 12.
    assert "PRICE_NOT_PIT_ELIGIBLE" in eligibility.evaluate(**i)["reason_codes"]
    rehash(i["market_versions"][-1]); i["market_versions"][-1]["acquisition"]["receipt_at_utc"] = DAYS[2]+"T09:00:00Z"
    rehash(i["market_versions"][-1])
    assert "PRICE_NOT_PIT_ELIGIBLE" in eligibility.evaluate(**i)["reason_codes"]


def test_contiguous_window_reports_first_region_and_empty_region_truthfully():
    rows = []
    for day in DAYS:
        i = inputs(); i.update(session=day,knowledge_cutoff=day+"T10:00:00Z",market_versions=[observation(d) for d in DAYS],requirements=replace(REQUIREMENTS,lookback_sessions=1))
        rows.append(eligibility.evaluate(**i))
    rows[2].update(state="EXCLUDED",reason_codes=["PRICE_NOT_PIT_ELIGIBLE"])
    report = eligibility.contiguous_coverage(rows,calendar_sessions=DAYS)[REQUIREMENTS.signal_id]
    assert report["eligible_ticker_sessions"] == 3 and report["first_contiguous_region"]["sessions"] == 2
    assert len(report["contiguous_regions"]) == 2
    empty = eligibility.contiguous_coverage([rows[2]],calendar_sessions=DAYS)[REQUIREMENTS.signal_id]
    assert empty["earliest"] is None and empty["first_contiguous_region"] is None


@pytest.mark.parametrize("timeframe", ["W","M"])
def test_future_period_constituent_and_excluded_constituent_never_strengthen_aggregate(timeframe):
    row = eligibility.evaluate(**inputs())
    result = eligibility.aggregate_period_eligibility(timeframe=timeframe,period_end=DAYS[1],knowledge_cutoff=DAYS[1]+"T10:00:00Z",constituent_rows=[row],expected_sessions=[DAYS[1]])
    assert result["state"] == "ELIGIBLE"
    row["knowledge_cutoff"] = DAYS[2]+"T10:00:00Z"
    assert "KNOWLEDGE_CUTOFF_VIOLATION" in eligibility.aggregate_period_eligibility(timeframe=timeframe,period_end=DAYS[1],knowledge_cutoff=DAYS[1]+"T10:00:00Z",constituent_rows=[row],expected_sessions=[DAYS[1]])["reason_codes"]
    row.update(knowledge_cutoff=DAYS[1]+"T10:00:00Z",state="EXCLUDED",reason_codes=["ACTIVE_UNIVERSE_UNKNOWN"])
    assert "ACTIVE_UNIVERSE_UNKNOWN" in eligibility.aggregate_period_eligibility(timeframe=timeframe,period_end=DAYS[1],knowledge_cutoff=DAYS[1]+"T10:00:00Z",constituent_rows=[row],expected_sessions=[DAYS[1]])["reason_codes"]


def test_existing_vnm_requirement_uses_actual_sma50_and_replay_volume_dependency():
    assert eligibility.existing_vnm_requirements().lookback_sessions == 50
    assert eligibility.existing_vnm_requirements().volume_required is False
    assert eligibility.existing_vnm_requirements(replay_inputs=True).volume_required is True
    assert eligibility.existing_vnm_requirements().ticker_scope == ("VNM",)


@pytest.mark.parametrize("mutation", ["later_terms","later_ex_date","not_executed","missing_raw_lineage"])
def test_pit_adjusted_requires_existing_qualified_factor_and_no_future_event(mutation):
    from qualified_corporate_action_factor_chain import build_factor_chain_entry
    entry = {"event_id":"fixture:event","ticker":"VNM","event_type":"STOCK_DIVIDEND","execution_status":"executed",
             "ex_date":DAYS[0],"adjustment_factor_status":"ready","adjustment_factor":0.9,"source_content_hashes":["b"*64]}
    factor = build_factor_chain_entry(entry,knowledge_cutoff=DAYS[0]+"T08:00:00Z")
    i = inputs(); i["requirements"] = replace(REQUIREMENTS,price_mode=eligibility.PIT_CA_ADJUSTED)
    for row in i["market_versions"]:
        row.update(price_mode=eligibility.PIT_CA_ADJUSTED,raw_lineage_identities=[row["snapshot_identity"]],factor_chain=[copy.deepcopy(factor)])
        rehash(row)
    i["ca_versions"] = [binding(state="QUALIFIED_FACTOR_CHAIN",factor_chain=[copy.deepcopy(factor)])]
    assert eligibility.evaluate(**i)["state"] == "ELIGIBLE"
    if mutation == "later_terms": i["market_versions"][-1]["factor_chain"][0]["knowledge_cutoff"] = DAYS[2]+"T09:00:00Z"
    if mutation == "later_ex_date": i["market_versions"][-1]["factor_chain"][0]["ex_date"] = DAYS[2]
    if mutation == "not_executed": i["market_versions"][-1]["factor_chain"][0]["official_execution_status"] = "ANNOUNCED"
    if mutation == "missing_raw_lineage": i["market_versions"][-1].pop("raw_lineage_identities")
    rehash(i["market_versions"][-1])
    assert "PRICE_NOT_PIT_ELIGIBLE" in eligibility.evaluate(**i)["reason_codes"]
