"""Unit, window, stage, cohort and consumer boundary regressions."""
import copy
from datetime import date, timedelta

import pytest

import contextual_technical_features as technical
import dnse_foreign_flow_store as store
import prospective_decision_retention as retention
import volume_and_flow_context as vf
from test_contextual_technical_features import series, seal, CUTOFF, ASOF


def inputs(volumes=None, count=45):
    rows = series(count)
    if volumes is not None:
        for row,value in zip(rows,volumes): row["volume"]=value;seal(row)
    context=technical.build_context({"1D":rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    return rows,context


def volume(rows,context):
    return vf.volume_items(context,series={"1D":rows},exhaustive_dates={r["last_trading_session"] for r in rows})


def item(items,domain="VOLUME",horizon="1D/5"):
    return next(i for i in items if i["domain"]==domain and i["horizon"]==horizon)


def foreign(count=5,nets=None,unit="vnd"):
    observations=[]
    for index in range(count):
        day=(date(2026,10,2)-timedelta(days=count-index-1)).isoformat()
        net=nets[index] if nets else index+1
        raw={"ticker":"VNM","session_date":day,"source":"DNSE", "value_unit":unit,
            "source_contract_version":store.SOURCE_CONTRACT_VERSION,"foreign_buy_value":max(net,0)+100,
            "foreign_sell_value":max(-net,0)+100,"foreign_buy_volume":999999}
        observations.append(store._value_observation(raw))
    dates={o["session_date"] for o in observations}
    counts=store._streaks_and_counts(observations,exhaustive_dates=dates,registry_dates=frozenset())
    return {"status":"available","observations":observations,"latest_session":observations[-1] if observations else {},
        "freshness":{"status":"current","latest_qualified_session_date":ASOF}, **counts,
        "window_summaries":{f"{n}_session":store._window_summary(observations,window_size=n,exhaustive_dates=dates,registry_dates=frozenset()) for n in (5,10)}},dates


@pytest.mark.parametrize("unit",["UNKNOWN","SHARES"])
def test_native_reference_preserves_unit_and_own_history_owner(unit):
    rows,context=inputs()
    for row in rows: row["volume_unit"]=unit;seal(row)
    context=technical.build_context({"1D":rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    native=item(volume(rows,context),horizon="1D")
    assert native["unit_semantics"]["native"]==unit
    assert native["values"]["feature_identity"]==context["timeframes"]["1D"]["artifact_identity"]
    assert "current_native_volume" not in native["values"]
    assert native["coverage_scope"]["kind"]=="OWN_HISTORY"


def test_prior_20_median_sequence_rank_counts_persistence_acceleration():
    rows,context=inputs([100]*40+[200,200,200,200,200])
    r=item(volume(rows,context))
    assert r["status"] in vf.USABLE
    v=r["values"]
    assert v["prior_20_relative_ratios"]==[2]*5
    assert v["state_counts"]=={"EXPANSION":5}
    assert v["current_state_streak"]==5 and v["own_history_percentile"]==1
    assert v["acceleration_difference"]==0 and v["trend"]=="FLAT"
    assert r["required_observations"]==25 and r["actual_observations"]==25


@pytest.mark.parametrize("values,expected",[([200,210,220,230,240],"RISING"),([50,40,30,20,10],"FALLING")])
def test_volume_trend_and_acceleration(values,expected):
    rows,c=inputs([100]*40+values)
    v=item(volume(rows,c))["values"]
    assert v["trend"]==expected
    assert v["acceleration_difference"]>0 if expected=="RISING" else v["acceleration_difference"]<0


@pytest.mark.parametrize("ratio,expected",[(1.3,"EXPANSION"),(0.7,"CONTRACTION"),(1,"STABLE"),(None,"UNDEFINED_ZERO_REFERENCE")])
def test_exact_standing_thresholds(ratio,expected):
    assert vf.relative_state(ratio)==expected
    assert vf.conventions.EXPANSION_RATIO==1.3 and vf.conventions.COMPRESSION_RATIO==0.7


def test_zero_baseline_does_not_become_zero_participation():
    rows,c=inputs([0]*45)
    r=item(volume(rows,c))
    assert r["status"]=="NOT_APPLICABLE_ZERO_REFERENCE" and r["values"] is None


@pytest.mark.parametrize("count",[1,19,24,25,39,40])
def test_exact_window_observations_and_insufficient_history(count):
    rows,c=inputs(count=count)
    for size in vf.VOLUME_WINDOWS:
        r=item(volume(rows,c),horizon=f"1D/{size}")
        assert r["actual_observations"]==min(count,20+size)
        if count<20+size: assert r["status"]=="INSUFFICIENT_HISTORY"
        else: assert r["status"] in vf.USABLE


def test_gap_not_skipped_and_continuity_unknown_not_inferred_from_weekdays():
    rows,c=inputs()
    ledger={r["last_trading_session"] for r in rows}
    del rows[-4]
    c=technical.build_context({"1D":rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    r=item(vf.volume_items(c,series={"1D":rows},exhaustive_dates=ledger))
    assert r["status"]=="BLOCKED_SESSION_CONTINUITY" and r["values"] is None
    r=item(vf.volume_items(c,series={"1D":rows}))
    assert r["status"]=="BLOCKED_SESSION_CONTINUITY"


@pytest.mark.parametrize("change",[{"volume_unit":"SHARES"},{"source":{"provider":"OTHER"}},{"volume_basis":"LOTS"}])
def test_cross_source_unit_basis_volumes_rejected(change):
    rows,c=inputs()
    rows[-3].update(change);seal(rows[-3])
    c=technical.build_context({"1D":rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    r=item(volume(rows,c))
    assert r["status"]=="BLOCKED_BASIS" and r["values"] is None


def test_ca_ceiling_is_not_weakened():
    rows,c=inputs()
    rows[-4]["corporate_action_crossing"]={"state":"EVENTS_OBSERVED","comparability":"NOT_ESTABLISHED"};seal(rows[-4])
    c=technical.build_context({"1D":rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    assert item(volume(rows,c))["status"]=="BLOCKED_CA_COMPARABILITY"


def test_w_m_do_not_gain_rolling_features_from_a_daily_candle():
    rows,c=inputs()
    for r in volume(rows,c):
        if r["horizon"].startswith(("1W","1M")): assert r["status"] not in vf.USABLE


@pytest.mark.parametrize("count",[1,4,5,9,10,19,20])
def test_foreign_window_maturity_counts_and_unit(count):
    s,dates=foreign(count)
    results=vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates)
    for size in vf.FLOW_WINDOWS:
        r=item(results,"PARTICIPANT_FLOW",f"1D/{size}")
        assert r["actual_observations"]==min(count,size) and r["required_observations"]==size
        assert r["unit_semantics"]["native"]=="VND"
        assert r["status"] in vf.USABLE if count>=size else r["status"]=="INSUFFICIENT_HISTORY"


@pytest.mark.parametrize("nets",[[1,2,3,4,5],[-1,-2,-3,-4,-5],[0,0,0,0,0],[1,-2,3,-4,5]])
def test_foreign_primitives_without_motive_or_economic_denominator(nets):
    s,dates=foreign(5,nets)
    v=item(vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates),"PARTICIPANT_FLOW","1D/5")["values"]
    assert v["net_value_vnd"]==sum(nets)==v["buy_value_vnd"]-v["sell_value_vnd"]
    assert v["gross_value_vnd"]==v["buy_value_vnd"]+v["sell_value_vnd"]
    assert v["net_over_gross"]==sum(nets)/v["gross_value_vnd"]
    assert v["positive_sessions"]==sum(n>0 for n in nets)
    assert v["negative_sessions"]==sum(n<0 for n in nets)
    assert v["foreign_over_total_traded_value"]["status"]=="BLOCKED"
    assert v["own_history_percentile"] is None
    assert v["net_buy_streak"]==5 if all(n>0 for n in nets) else v["net_buy_streak"]<5


@pytest.mark.parametrize("change",[{"source":"FHSC"},{"qualification_status":"UNQUALIFIED"},{"foreign_net_value_vnd":0},{"foreign_buy_value_vnd":True},{"foreign_sell_value_vnd":float('inf')}])
def test_foreign_incompatible_or_invalid_values_fail_closed(change):
    s,dates=foreign()
    s["observations"][-1].update(change)
    with pytest.raises(ValueError):vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates)


def test_foreign_gap_invalidates_window_and_streak():
    s,dates=foreign(6)
    del s["observations"][-3]
    r=item(vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates),"PARTICIPANT_FLOW","1D/5")
    assert r["status"]=="INSUFFICIENT_HISTORY" and r["values"] is None
    assert "INSUFFICIENT_CONTIGUOUS_HISTORY" in r["reason_codes"]


def test_foreign_zero_gross_is_undefined_ratio_not_missing_or_zero_flow():
    s,dates=foreign(1,[0])
    s["observations"][0].update(foreign_buy_value_vnd=0,foreign_sell_value_vnd=0)
    r=item(vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates),"PARTICIPANT_FLOW","1D/1")
    assert r["values"]["net_value_vnd"]==0 and r["values"]["gross_value_vnd"]==0
    assert r["values"]["net_over_gross"] is None
    assert r["values"]["ratio_status"]=="NOT_APPLICABLE_ZERO_GROSS"


def test_new_t0_projection_cannot_use_an_unbound_technical_identity():
    rows,c=inputs()
    sealed=snapshot(c)
    other=copy.deepcopy(c)
    other["multi_timeframe"]["state"]="UNKNOWN_UNAVAILABLE"
    vf.seal(other,technical.CONTRACT_VERSION)
    with pytest.raises(ValueError,match="NOT_BOUND_IN_SEALED_T0"):
        vf.volume_items(other,sealed_snapshot=sealed)


def test_foreign_duplicate_future_rejected_and_reversed_order_stable():
    s,dates=foreign()
    original=vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates)
    other=copy.deepcopy(s);other["observations"].reverse()
    assert vf.foreign_items("VNM",ASOF,other,in_cohort=True,exhaustive_dates=dates)==original
    other["observations"].append(other["observations"][-1])
    with pytest.raises(ValueError,match="DUPLICATE"):vf.foreign_items("VNM",ASOF,other,in_cohort=True)
    s["observations"][-1]["session_date"]="2026-10-03"
    with pytest.raises(ValueError,match="FUTURE"):vf.foreign_items("VNM",ASOF,s,in_cohort=True)


@pytest.mark.parametrize("price,net,expected",[("PERSISTENT_IMPROVEMENT",-1,"PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE"),("DETERIORATING",1,"FOREIGN_BUYING_PRICE_WEAKNESS"),("EARLY_IMPROVEMENT",1,"FOREIGN_BUYING_PRICE_CONFIRMATION")])
def test_flow_price_uses_existing_method(price,net,expected):
    s,dates=foreign(5,[net]*5)
    velocity={"ticker":"VNM","session":ASOF,"overall_transition_state":price,"axes":{"participation_confirmation":{"state":"IMPROVING"}},"source_snapshot_identity":"test:t0"}
    r=item(vf.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates,velocity_record=velocity),"PARTICIPANT_FLOW","1D/5")
    assert r["technical_relationship"]["state"]==expected
    assert r["technical_relationship"]["method_contract"]==vf.divergence.CONTRACT_VERSION


@pytest.mark.parametrize("breakout,base,repair",[("BREAKOUT","ESTABLISHED","EARLY_REPAIR"),("RETEST","ESTABLISHED","REVERSAL_ATTEMPT"),("TESTING_PIVOT","UNAVAILABLE","CONTINUING_DETERIORATION")])
def test_technical_join_retains_exact_observations(breakout,base,repair):
    rows,c=inputs()
    frame=copy.deepcopy(c["timeframes"]["1D"])
    frame["features"]["structure"]["values"]["breakout"]["breakout_state"]=breakout
    frame["features"]["base"]["values"]["state"]=base
    frame["features"]["interpretation"]["values"]["repair_context"]=repair
    r=vf.technical_relationship(frame,"EXPANSION")
    assert (r["breakout"],r["base"],r["repair"])==(breakout,base,repair)
    frame["features"]["structure"]["status"]="UNAVAILABLE"
    assert vf.technical_relationship(frame,"EXPANSION")["state"]=="TECHNICAL_CONTEXT_UNAVAILABLE"


def snapshot(c):
    row={"ticker":"VNM","decision_session":ASOF,"integrated_decision_at_t0":{"contextual_technical_context":{"projection":c}}}
    row=retention._identity(row,retention.RECORD_PREFIX,"prospective_snapshot_record_identity")
    return retention._identity({"contract_version":retention.CONTRACT_VERSION,"session":ASOF,"records":{"VNM":row}},retention.SNAPSHOT_PREFIX,"snapshot_identity")


def test_mixed_stage_and_post_t0_exclusion():
    rows,c=inputs()
    s,dates=foreign()
    a=vf.build_artifact(session=ASOF,tickers=["VNM"],technical_contexts={"VNM":c},flow_series={"VNM":s},
        canonical_series={"VNM":{"1D":rows}},exhaustive_dates={"VNM":{r["last_trading_session"] for r in rows}},sealed_snapshot=snapshot(c))
    assert a["build_stage"]==vf.POST
    eligible=vf.t0_projection(a)["VNM"]
    assert eligible and all(i["sub_domain"]=="NATIVE_VOLUME_REFERENCE" and i["knowledge_stage"]==vf.T0 for i in eligible)
    assert all(i["knowledge_stage"]==vf.POST for i in a["records"]["VNM"]["items"] if i["sub_domain"]!="NATIVE_VOLUME_REFERENCE")


def test_no_retroactive_t0_stage_and_wrong_seal_fails_closed():
    rows,c=inputs()
    assert all(i["knowledge_stage"]==vf.POST for i in volume(rows,c))
    bad=snapshot(c);bad["records"]["VNM"]["integrated_decision_at_t0"]={}
    with pytest.raises(ValueError,match="SNAPSHOT_INVALID"):vf.volume_items(c,sealed_snapshot=bad)
    other=copy.deepcopy(c);other["ticker"]="OTHER"
    with pytest.raises(ValueError):vf.volume_items(other)


def test_small_cohort_scope_denominators_other_participants_and_no_action_mutation():
    rows,c=inputs()
    s,dates=foreign()
    source=copy.deepcopy(c)
    a=vf.build_artifact(session=ASOF,tickers=["VNM","AAA"],technical_contexts={"VNM":c},flow_series={"VNM":s},exhaustive_dates={"VNM":dates},sectors={"VNM":"food"})
    agg=next(r for r in a["aggregates"] if r["kind"]=="FOREIGN_FLOW_COHORT_CONTEXT")
    assert agg["cohort_denominator"]==1 and agg["current_qualified_numerator"]==1
    assert agg["coverage_percentage"]==100 and agg["outside_cohort_count"]==1
    assert not agg["is_market_representative"] and all(r["kind"]!="FOREIGN_MARKET_BREADTH" for r in a["aggregates"])
    assert c==source
    for ticker,row in a["records"].items():
        for r in row["items"]:
            if r["participant"] in vf.PARTICIPANTS[1:]:assert r["status"]=="UNAVAILABLE" and r["reason_codes"]==["SOURCE_NOT_QUALIFIED"]
    assert item(a["records"]["AAA"]["items"],"PARTICIPANT_FLOW","1D/1")["reason_codes"]==["OUTSIDE_RETAINED_FOREIGN_COHORT"]


def test_repeated_build_reversed_series_universe_are_deterministic():
    rows,c=inputs()
    args=dict(session=ASOF,tickers=["VNM","AAA"],technical_contexts={"VNM":c},flow_series={},canonical_series={"VNM":{"1D":rows}},exhaustive_dates={"VNM":{r["last_trading_session"] for r in rows}})
    a=vf.build_artifact(**args)
    args["tickers"].reverse();args["canonical_series"]["VNM"]["1D"].reverse()
    assert vf.build_artifact(**args)==a
    assert vf.research_reference(a,"VNM")["artifact_identity"]==a["artifact_identity"]
    a["records"]["VNM"]["items"][0]["knowledge_stage"]=vf.T0
    with pytest.raises(ValueError):vf.t0_projection(a)


def test_prepared_items_cannot_claim_unbound_t0():
    rows,c=inputs()
    prepared=volume(rows,c)
    prepared[0]["knowledge_stage"]=vf.T0;vf.seal(prepared[0],vf.ITEM_VERSION)
    with pytest.raises(ValueError,match="NOT_SEALED_T0"):
        vf.build_artifact(session=ASOF,tickers=["VNM"],technical_contexts={"VNM":c},flow_series={},prepared_volume_items={"VNM":prepared})


def test_foreign_cannot_enter_t0_even_with_resealed_invalid_stage():
    s,dates=foreign()
    a=vf.build_artifact(session=ASOF,tickers=["VNM"],technical_contexts={},flow_series={"VNM":s})
    a["records"]["VNM"]["items"][0]["knowledge_stage"]=vf.T0
    vf.seal(a)
    with pytest.raises(ValueError,match="CANNOT_ENTER_T0"):vf.t0_projection(a)


@pytest.mark.parametrize("tf",["1W","1M"])
def test_exact_completed_periods_can_qualify_and_missing_period_is_blocked(tf):
    import calendar
    rows=[]
    for index in range(45):
        if tf=="1W":
            start=date(2026,9,21)-timedelta(weeks=44-index)
            end=start+timedelta(days=6)
        else:
            month_index=2026*12+8-(44-index)
            year,month=divmod(month_index,12);month+=1
            start=date(year,month,1);end=date(year,month,calendar.monthrange(year,month)[1])
        from test_canonical_market_bars import daily
        from canonical_market_bars import derive
        constituents=[daily(start.isoformat(),retrieved_at=start.isoformat()+"T09:00:00Z",volume=100+index),
                      daily(end.isoformat(),retrieved_at=end.isoformat()+"T09:00:00Z",volume=100+index)]
        ledger={"sessions":[start.isoformat(),end.isoformat()],"window_start":start.isoformat(),"window_end":end.isoformat(),
                "artifact_identity":"test_explicit_calendar","source":{"kind":"EXPLICIT_TEST_LEDGER"}}
        rows.append(derive(constituents,ticker="VNM",timeframe=tf,period_session=start.isoformat(),knowledge_cutoff=CUTOFF,
                           source_identity="test:periods",calendar_evidence=ledger))
    c=technical.build_context({tf:rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    r=item(vf.volume_items(c,series={tf:rows}),horizon=tf+"/5")
    assert r["status"] in vf.USABLE
    del rows[-3]
    c=technical.build_context({tf:rows},ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    r=item(vf.volume_items(c,series={tf:rows}),horizon=tf+"/5")
    assert r["status"]=="BLOCKED_SESSION_CONTINUITY" and r["values"] is None
