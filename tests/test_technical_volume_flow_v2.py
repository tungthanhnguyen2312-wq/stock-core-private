"""Semantic version boundaries, exact rule order, freshness and stage separation."""
import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
import pytest
import canonical_market_bars as bars
import contextual_technical_features as v1
import contextual_technical_features_v2 as v2
import contextual_technical_dispatch as dispatch
import technical_relationship_view as view
import volume_and_flow_context as f1
import volume_and_flow_context_v2 as f2
import prospective_decision_retention as retention
import integrated_investment_decision_product as product
import market_wide_historical_research_context as history
from test_contextual_technical_features import series, seal, ASOF, CUTOFF
from test_volume_and_flow_context import foreign, snapshot


def context(version=v2, rows=None, sources=None, session=ASOF):
    return version.build_context(sources or {"1D": rows or series(45)}, ticker="VNM", as_of_session=session, knowledge_cutoff=CUTOFF)


def reseal(c, version=v2):
    for frame in c["timeframes"].values():
        frame["context"].update(version.identity(frame["context"], kind="contextual_technical_inputs/"+version.CONTRACT_VERSION.rsplit("/", 1)[1]))
        for f in frame["features"].values(): f["input_context_identity"] = frame["context"]["artifact_identity"]
        frame.update(version.identity(frame))
    if version == v2: c["multi_timeframe"] = v2.multi_timeframe(c["timeframes"])
    c.update(version.identity(c))
    return c


def period_rows(tf, count=45, last="2026-09-25", direction="UP"):
    """Explicit synthetic completed canonical periods; never a real capture clock."""
    rows = series(count, closes=[100+i if direction == "UP" else 200-i for i in range(count)])
    end = bars.period_bounds(last, tf)
    bounds = []
    for _ in rows:
        bounds.append(end)
        end = bars.period_bounds((date.fromisoformat(end[0])-timedelta(days=1)).isoformat(), tf)
    for row, (start, end) in zip(rows, reversed(bounds)):
        row.update(timeframe=tf, period_start=start, period_end=end, last_trading_session=end,
            period_completeness="COMPLETE", knowledge_available_at=end+"T09:00:00Z")
        # For a current period whose civil end is later, retain an explicitly observed date.
        if end > ASOF: row.update(last_trading_session=ASOF, knowledge_available_at=ASOF+"T09:00:00Z")
        seal(row)
    return rows


def retained(h=110, l=110):
    return {"previous_confirmed_swing_high": {"price":100}, "last_confirmed_swing_high":{"price":h},
        "previous_confirmed_swing_low":{"price":100}, "last_confirmed_swing_low":{"price":l}}


@pytest.mark.parametrize("h,l,expected", [(110,110,"HIGHER_HIGHS_HIGHER_LOWS"),(90,90,"LOWER_HIGHS_LOWER_LOWS"),
    (110,90,"RANGE_EXPANSION_HH_LL"),(90,110,"RANGE_CONTRACTION_LH_HL"),(100,110,"EQUAL_SWING_PRICE_UNRESOLVED"),
    (110,100,"EQUAL_SWING_PRICE_UNRESOLVED"),(100,100,"EQUAL_SWING_PRICE_UNRESOLVED"),
    (100+1e-12,110,"HIGHER_HIGHS_HIGHER_LOWS")])
def test_exact_swing_prices(h,l,expected):
    assert view.swing_reading(retained(h,l))["swing_relation"] == expected


def test_insufficient_and_malformed_swings():
    assert view.swing_reading({})["swing_relation"] == "INSUFFICIENT_CONFIRMED_SWINGS"
    r=retained();r["last_confirmed_swing_low"]["price"]=float("nan")
    assert view.swing_reading(r)["swing_relation"] == "UNKNOWN"


@pytest.mark.parametrize("distance,prior,relation,pivot,failed", [
    (.06,True,"ABOVE_PIVOT_BEYOND_EXTENDED_THRESHOLD","NOT_TESTING","FALSE"),
    (.05,False,"ABOVE_PIVOT_WITHIN_EXTENDED_THRESHOLD","NOT_TESTING","FALSE"),
    (0,True,"AT_OR_BELOW_PIVOT_WITHIN_NEAR_BAND","TESTING_AFTER_PRIOR_CLOSE_ABOVE_PIVOT","FALSE"),
    (-.01,False,"AT_OR_BELOW_PIVOT_WITHIN_NEAR_BAND","TESTING_WITHOUT_PRIOR_CLOSE_ABOVE_PIVOT","FALSE"),
    (-.1,True,"BELOW_PIVOT_BEYOND_NEAR_BAND","NOT_TESTING","TRUE"),
    (-.1,False,"BELOW_PIVOT_BEYOND_NEAR_BAND","NOT_TESTING","FALSE")])
@pytest.mark.parametrize("owner_state", tuple(view.owner.BREAKOUT_STATES_V3))
def test_pivot_geometry_uses_actual_distance_not_owner_labels(distance,prior,relation,pivot,failed,owner_state):
    r=view.pivot_reading(dict(status="AVAILABLE", breakout_state=owner_state, distance_to_pivot_pct=distance, prior_close_above_pivot=prior))
    assert r == dict(breakout_relation=relation, pivot_test=pivot, failed_breakout=failed)


def setup(rule, **changes):
    args=dict(structure_status="AVAILABLE", trend="UNKNOWN", swing="INSUFFICIENT_CONFIRMED_SWINGS", range_state="UNKNOWN")
    s=dict(breakout=dict(status="AVAILABLE", distance_to_pivot_pct=0.01, prior_close_above_pivot=False, breakout_state="BREAKOUT"))
    if rule == "R0": args["structure_status"]="INSUFFICIENT_HISTORY"
    if rule == "R1": s["breakout"].update(distance_to_pivot_pct=-.1, prior_close_above_pivot=True, breakout_state="FAILED_BREAKOUT")
    if rule == "R2": s["bos"]=dict(status="AVAILABLE",bos_state="BEARISH_BOS_DETECTED_BY_RULE")
    if rule == "R3": s["choch"]=dict(status="AVAILABLE",choch_state="BULLISH_CHOCH_DETECTED_BY_RULE")
    if rule == "R4": s["bos"]=dict(status="AVAILABLE",bos_state="BULLISH_BOS_DETECTED_BY_RULE")
    if rule == "R5": s["breakout_event"]=dict(status="AVAILABLE",event="RE_ENTRY_ABOVE_SUPPORT")
    if rule == "R6": args["trend"]="DOWN"
    if rule == "R7": s["breakout"].update(distance_to_pivot_pct=.1,breakout_state="EXTENDED_AFTER_BREAKOUT")
    if rule == "R8": args.update(trend="UP",swing="HIGHER_HIGHS_HIGHER_LOWS")
    if rule == "R9": args["range_state"]="ESTABLISHED"
    if rule == "R10": args.update(trend="NO_CLEAN_AGREEMENT",swing="RANGE_EXPANSION_HH_LL")
    args.update(changes)
    return view.setup_reading(s, **args)


@pytest.mark.parametrize("rule,expected", [("R0","UNKNOWN"),("R1","FAILED_BREAKOUT_DETERIORATION"),
    ("R2","BEARISH_STRUCTURE_BREAK"),("R3","REVERSAL_ATTEMPT"),("R4","CONFIRMED_IMPROVEMENT"),
    ("R5","EARLY_REPAIR"),("R6","CONTINUING_DETERIORATION"),("R7","EXTENDED"),("R8","ESTABLISHED_TREND"),
    ("R9","RANGE_CONSOLIDATION"),("R10","SIDEWAYS"),("R11","UNKNOWN")])
def test_each_setup_rule(rule,expected):
    result=setup(rule)
    assert (result["rule"],result["state"]) == (rule,expected)
    assert set(result["primitive_availability"]) == {"swing","BOS","CHoCH","event","breakout","slope","trend_reading"}


@pytest.mark.parametrize("field,state", [("bos","BEARISH_BOS_DETECTED_BY_RULE"),("choch","BEARISH_CHOCH_DETECTED_BY_RULE"),("breakout_event","BREAKDOWN_CONFIRMED")])
def test_bearish_events_precede_range_and_up_reading(field,state):
    key={"bos":"bos_state","choch":"choch_state","breakout_event":"event"}[field]
    s={field:{"status":"AVAILABLE",key:state}}
    r=view.setup_reading(s,structure_status="AVAILABLE",trend="UP",swing="HIGHER_HIGHS_HIGHER_LOWS",range_state="ESTABLISHED")
    assert r["rule"] == "R2" and "BEARISH_EVENT_WITH_UP_READING" in r["setup_conflicts"]


def test_bullish_choch_precedes_deterioration_and_unknown_is_not_sideways():
    assert setup("R3",trend="DOWN",swing="LOWER_HIGHS_LOWER_LOWS")["rule"] == "R3"
    assert setup("R11",swing="RANGE_EXPANSION_HH_LL")["state"] == "UNKNOWN"
    assert setup("R11",swing="RANGE_CONTRACTION_LH_HL")["state"] != "EARLY_REPAIR"


def test_dispatch_and_cross_version_rejection():
    a,b=context(v1),context()
    assert dispatch.verify_batch({"VNM":a},session=ASOF) == dispatch.V1
    assert dispatch.verify_batch({"VNM":b},session=ASOF) == dispatch.V2
    with pytest.raises(ValueError): v2.verify_context(a)
    with pytest.raises(ValueError): f1.verify_technical(b,"VNM",ASOF)
    with pytest.raises(ValueError,match="^TECHNICAL_VERSION_MIXED$"): dispatch.batch_version([a,b])
    with pytest.raises(ValueError,match="TECHNICAL_VERSION_UNKNOWN"): dispatch.module_for_version("future/v3")
    assert dispatch.production_version(ASOF)==dispatch.V1
    assert dispatch.production_version("2026-10-05")==dispatch.V2


def test_v1_bridge_does_not_consume_repair_or_volume_interpretation():
    a=context(v1); baseline=view.build_views(a)
    a["timeframes"]["1D"]["features"]["interpretation"]["values"]["repair_context"]="FUTURE_LEGACY_LABEL"
    for key in ("trend","participation_context","breakout_retest_context"):
        a["timeframes"]["1D"]["features"]["volume"]["values"][key]="MUST_NOT_BE_READ"
    reseal(a,v1)
    after=view.build_views(a)
    assert baseline["1D"]["concepts"]==after["1D"]["concepts"]
    assert after["1W"]["fitness"]["temporal"]["later_period_completeness"]["state"] == "UNKNOWN_FROM_V1"


@pytest.mark.parametrize("old,neutral", list(view.V1_RANGE_MAP.items()))
def test_every_v1_range_state(old,neutral):
    a=context(v1); a["timeframes"]["1D"]["features"]["base"]["values"]["state"]=old;reseal(a,v1)
    assert view.build_views(a)["1D"]["concepts"]["range_consolidation"]==neutral


@pytest.mark.parametrize("old,neutral", list(view.V1_TREND_MAP.items()))
def test_every_v1_trend(old,neutral):
    a=context(v1);a["timeframes"]["1D"]["features"]["structure"]["values"]["direction"]=old;reseal(a,v1)
    assert view.build_views(a)["1D"]["concepts"]["trend_reading"]==neutral


@pytest.mark.parametrize("tf,last,expected,behind", [("1D",ASOF,"CURRENT_SESSION",0),("1D","2026-10-01","STALE_LAST_OBSERVATION",None),
    ("1W",ASOF,"CURRENT_PERIOD_COMPLETED",0),("1W","2026-09-25","IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD",1),
    ("1W","2026-09-04","STALE_OLDER_COMPLETED_PERIOD",4),("1M",ASOF,"CURRENT_PERIOD_COMPLETED",0),
    ("1M","2026-09-30","IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD",1),("1M","2026-08-31","STALE_OLDER_COMPLETED_PERIOD",2)])
def test_temporal_arithmetic(tf,last,expected,behind):
    r=view.temporal_reading(timeframe=tf,as_of_session=ASOF,last_observed_session=last)
    assert (r["state"],r["periods_behind"])==(expected,behind)


@pytest.mark.parametrize("readings,expected", [({},"NO_ELIGIBLE_TIMEFRAME"),({"1D":"UP"},"SINGLE_TIMEFRAME_AVAILABLE"),
    ({"1D":"UP","1W":"UP"},"SAME_READING"),({"1D":"UP","1W":"DOWN"},"OPPOSING_READINGS"),
    ({"1D":"UP","1W":"NO_CLEAN_AGREEMENT"},"DIFFERENT_NON_OPPOSING_READINGS"),
    ({"1D":"UP","1W":"DOWN","1M":"UNKNOWN"},"OPPOSING_READINGS_PRESENT")])
def test_alignment_counts_and_non_opposition(readings,expected):
    c=context(sources={"1D":series(),"1W":period_rows("1W"),"1M":period_rows("1M",last="2026-09-30")})
    for tf,f in c["timeframes"].items():
        if tf not in readings: f["features"]["structure"]["status"]="INSUFFICIENT_HISTORY"
        else: f["features"]["structure"]["values"]["trend_reading"]=readings[tf]
    r=v2.multi_timeframe(c["timeframes"])
    assert r["state"]==expected and r["eligible_count"]==len(readings)
    assert not {"weights","score","confidence"}.intersection(r)


def test_stale_periods_and_basis_mismatch_excluded_honestly():
    c=context(sources={"1D":series(),"1W":period_rows("1W",last="2026-09-04"),"1M":period_rows("1M",last="2026-08-31")})
    assert c["multi_timeframe"]["state"]=="SINGLE_TIMEFRAME_AVAILABLE"
    assert set(c["multi_timeframe"]["exclusions"])=={"1W","1M"}
    c=context(sources={"1D":series(),"1W":period_rows("1W")})
    c["timeframes"]["1W"]["context"]["price_basis"]="RAW_AS_TRADED"
    assert v2.multi_timeframe(c["timeframes"])["state"]=="BASIS_MISMATCH_NOT_EVALUATED"


def test_owner_prices_states_and_local_volume_primitives_preserved():
    rows=series(closes=[100,105,110,105,100,95,90,95]*6)
    a,b=context(v1,rows),context(v2,rows)
    x=a["timeframes"]["1D"]["features"]["structure"]["values"];y=b["timeframes"]["1D"]["features"]["structure"]["values"]
    assert y["tactical_owner_market_structure_state"]==x["swing_structure"]["market_structure_state"]
    assert y["retained_swing_prices"]=={k:v for k,v in x["swing_structure"].items() if "confirmed_swing" in k}
    assert y["bos"]==x["bos"] and y["choch"]==x["choch"] and y["breakout"]==x["breakout"]
    av=a["timeframes"]["1D"]["features"]["volume"]["values"];bv=b["timeframes"]["1D"]["features"]["volume"]["values"]
    for key in ("current_native_volume","relative_to_median","relative_to_mean","distribution","ratio_status"): assert av[key]==bv[key]
    forbidden=("supporting_observations","contradicting_observations","confirmation_evidence","invalidation_evidence","repair_context","participation_context","breakout_retest_context")
    assert all('"'+key+'"' not in json.dumps(b) for key in forbidden)
    assert b["timeframes"]["1D"]["features"]["range_consolidation"]["values"]["algorithm"] == "BOUNDED_CLOSE_RANGE_DURATION"


def test_typed_native_and_prior_twenty_references_and_dedup_keys():
    rows=series(45)
    for i,r in enumerate(rows): r["volume"]=200 if i>=40 else 100;seal(r)
    c=context(rows=rows); views=view.build_views(c)
    items=f2.volume_items(views,series={"1D":rows},exhaustive_dates={r["last_trading_session"] for r in rows})
    native=next(i for i in items if i["horizon"]=="1D")
    trajectory=next(i for i in items if i["horizon"]=="1D/5")
    assert native["participation_measure"]=="NATIVE_RELATIVE_STATE" and native["participation_state"]=="EXPANSION"
    assert trajectory["participation_measure"]=="PRIOR_20_TRAJECTORY_TREND" and trajectory["participation_state"]=="FLAT"
    assert trajectory["values"]["prior_20_relative_ratios"]==[2]*5
    assert native["evidence_keys"]==views["1D"]["evidence_keys"]["native_volume_reference"]
    assert native["evidence_keys"]["common_cause_key"]==trajectory["evidence_keys"]["common_cause_key"]
    assert native["evidence_keys"]["canonical_evidence_key"]!=trajectory["evidence_keys"]["canonical_evidence_key"]


def test_exact_v2_seal_only_and_derived_evidence_remains_post():
    session="2026-10-03"
    rows=series(45);c=context(rows=rows,session=session);vs=view.build_views(c);s,dates=foreign()
    def seal_for(c):
        row={"ticker":"VNM","decision_session":session,"integrated_decision_at_t0":{"contextual_technical_context":{"projection":c}}}
        row=retention._identity(row,retention.RECORD_PREFIX,"prospective_snapshot_record_identity")
        return retention._identity({"contract_version":retention.CONTRACT_VERSION,"session":session,"records":{"VNM":row}},retention.SNAPSHOT_PREFIX,"snapshot_identity")
    a=f2.build_artifact(session=session,tickers=["VNM"],relationship_views={"VNM":vs},flow_series={"VNM":s},
        canonical_series={"VNM":{"1D":rows}},exhaustive_dates={"VNM":{r["last_trading_session"] for r in rows}},sealed_snapshot=seal_for(c))
    assert f2.t0_projection(a)["VNM"]
    assert all(i["knowledge_stage"]==f2.POST for i in a["records"]["VNM"]["items"] if i["sub_domain"]!="NATIVE_VOLUME_REFERENCE")
    old=context(v1,rows,session=session);mismatched=copy.deepcopy(c);mismatched["knowledge_cutoff"]="2026-10-02T15:59:00Z"
    for f in mismatched["timeframes"].values():f["context"]["knowledge_cutoff"]=mismatched["knowledge_cutoff"]
    reseal(mismatched)
    for seal_value in (None,seal_for(old),seal_for(mismatched)):
        items=f2.volume_items(vs,sealed_snapshot=seal_value)
        assert all(i["knowledge_stage"]==f2.POST for i in items)
        assert "TECHNICAL_IDENTITY_NOT_SEALED_IN_T0" in items[0]["reason_codes"]


def test_explicit_v1_bridge_all_post_and_normal_cross_pair_rejected():
    c=context(v1);vs=view.build_views(c)
    with pytest.raises(ValueError,match="EXPLICIT_DIAGNOSTIC"):
        f2.build_artifact(session=ASOF,tickers=["VNM"],relationship_views={"VNM":vs},flow_series={})
    a=f2.build_artifact(session=ASOF,tickers=["VNM"],relationship_views={"VNM":vs},flow_series={},allow_legacy_bridge=True,sealed_snapshot=snapshot(c))
    assert all(i["knowledge_stage"]==f2.POST for i in a["records"]["VNM"]["items"])
    assert a["evaluation_scope"]=="REPLAY_DIAGNOSTIC_NON_AUTHORITATIVE"


def test_stale_periods_cannot_enter_breadth():
    c=context(sources={"1D":series(45),"1W":period_rows("1W",last="2026-09-04"),"1M":period_rows("1M",last="2026-08-31")})
    a=f2.build_artifact(session=ASOF,tickers=["VNM","AAA"],relationship_views={"VNM":view.build_views(c)},flow_series={},sectors={"VNM":"sector"})
    for aggregate in a["aggregates"]:
        if aggregate.get("timeframe") in {"1W","1M"}: assert aggregate["eligible_denominator"]==0


def test_qualified_foreign_values_identical_new_evidence_identity():
    s,dates=foreign(20)
    a=f1.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates)
    b=f2.foreign_items("VNM",ASOF,s,in_cohort=True,exhaustive_dates=dates)
    for old,new in zip(a,b):
        for key in ("values","status","reason_codes","coverage_scope","session_continuity","unit_semantics","source_artifact_identities"):
            assert old[key]==new[key]
        assert old["artifact_identity"]!=new["artifact_identity"]
        assert old["technical_relationship"]==new["price_flow_relationship"]
    a=f2.build_artifact(session=ASOF,tickers=["VNM","AAA"],relationship_views={},flow_series={"VNM":s},exhaustive_dates={"VNM":dates})
    cohort=next(r for r in a["aggregates"] if r["kind"]=="FOREIGN_FLOW_COHORT_CONTEXT")
    assert (cohort["cohort_denominator"],cohort["outside_cohort_count"],cohort["current_qualified_numerator"])==(1,1,1)
    assert cohort["is_market_representative"] is False
    assert all(i["status"]=="UNAVAILABLE" and i["reason_codes"]==["SOURCE_NOT_QUALIFIED"] for i in a["records"]["AAA"]["items"] if i["participant"] in f2.PARTICIPANTS[1:])


@pytest.mark.parametrize("name,values", list(view.VOCABULARY_MANIFEST.items()))
def test_exhaustive_consumer_vocabulary_and_unknown_rejection(name,values):
    assert set(f2.CONSUMER_VOCABULARY[name])==set(values)
    for value in values: assert view.checked(value,f2.CONSUMER_VOCABULARY[name],name)==value
    with pytest.raises(ValueError,match="VOCABULARY_UNKNOWN"):view.checked("FUTURE_UNKNOWN",f2.CONSUMER_VOCABULARY[name],name)


@pytest.mark.parametrize("fault", ["hash","vocabulary","scope","keys"])
def test_relationship_view_fail_closed(fault):
    v=view.build_views(context())["1D"]
    if fault=="hash": v["concepts"]["setup_state"]="EXTENDED"
    if fault=="vocabulary": v["concepts"]["trend_reading"]="FUTURE_UP";view._seal(v)
    if fault=="scope": v["instrument"]["ticker"]="WRONG";view._seal(v)
    if fault=="keys": v["evidence_keys"]["setup_state"]["common_cause_key"]="wrong";view._seal(v)
    with pytest.raises(ValueError):view.verify_view(v)


def test_future_normal_product_then_full_retention_preserves_exact_v2():
    session="2026-10-03"
    c=context(session=session)
    projection=bars.project_research_series({"1D":series(45),"1W":[],"1M":[]},target_session=session,knowledge_cutoff=CUTOFF)
    parent=dict(contract_version=history.CONTRACT_VERSION,session=session,records={"VNM":{"multi_timeframe":projection,"contextual_technical":c}})
    parent.update(history.content_identity(parent))
    artifact=product.build_artifact(session=session,requested_at=CUTOFF,technical_structure_artifact={"records":{"VNM":{"eligible":False}}},historical_context_artifact=parent)
    row=artifact["records"]["VNM"]
    assert row["contextual_technical_context"]["projection"]["artifact_identity"]==c["artifact_identity"]
    assert row["decision_identity"]==product.decision_identity(row)
    sealed=retention.build_snapshot(session=session,operation_identity="synthetic:test",producer_run_identity="synthetic:test",integrated_artifact=artifact)
    assert retention.validate_snapshot(sealed)
    assert sealed["records"]["VNM"]["integrated_decision_at_t0"]==row
    bindings=f2.SealedTechnicalBindings(sealed)
    assert bindings.bindings["VNM"]==(session,dispatch.V2,c["artifact_identity"])


@pytest.mark.parametrize("name,digest", [("contextual_technical_features.py","a2088bd24ea336a0adac5aee95d0811ba34a308531ddcf65854247677c46be65"),
    ("volume_and_flow_context.py","b56cef329d04ba8bd4c49edaf93a89fd9c823a43ac5c717240c649dde5278070"),
    ("technical_structure_context.py","09cd61d1f7a1fdaba641da0573b7c66fd0c6a42995f6a98802ede91ad8c20238")])
def test_frozen_producer_and_tactical_owner_bytes(name,digest):
    assert hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_text(encoding="utf-8").encode()).hexdigest()==digest


def test_historical_diagnostic_never_qualifies_t0_even_with_synthetic_exact_seal():
    c=context()
    assert c["evaluation_scope"] == "REPLAY_DIAGNOSTIC"
    assert all(i["knowledge_stage"]==f2.POST for i in f2.volume_items(view.build_views(c),sealed_snapshot=snapshot(c)))


def test_unavailable_canonical_observation_has_no_invented_continuity():
    rows=series(45)
    rows[-1].update(status="UNAVAILABLE",last_trading_session=None,open=None,high=None,low=None,close=None,volume=None)
    seal(rows[-1])
    c=context(rows=rows)
    items=f2.volume_items(view.build_views(c),series={"1D":rows},exhaustive_dates={r["period_start"] for r in rows})
    r=next(i for i in items if i["horizon"]=="1D/5")
    assert r["status"]=="SOURCE_FIELD_UNAVAILABLE" and r["values"] is None
    assert r["session_continuity"]["proof_state"]=="UNVERIFIABLE"
    legacy=context(v1,rows=rows)
    legacy_items=f2.volume_items(view.build_views(legacy),series={"1D":rows},exhaustive_dates={r["period_start"] for r in rows})
    assert all(i["status"] not in f2.USABLE for i in legacy_items)


@pytest.mark.parametrize("sub_domain",["RELATIVE_VOLUME_PERSISTENCE","FOREIGN_VALUE"])
def test_rehashed_derived_post_evidence_cannot_enter_t0_projection(sub_domain):
    c=context(session="2026-10-03")
    a=f2.build_artifact(session="2026-10-03",tickers=["VNM"],relationship_views={"VNM":view.build_views(c)},flow_series={})
    item=next(i for i in a["records"]["VNM"]["items"] if i["sub_domain"]==sub_domain)
    item["knowledge_stage"]=f2.T0;f2.seal(item,f2.ITEM_VERSION);f2.seal(a)
    with pytest.raises(ValueError,match="POST_T0_EVIDENCE"): f2.t0_projection(a)


@pytest.mark.parametrize("field,key",[("bos","bos_state"),("choch","choch_state"),("breakout_event","event")])
def test_unknown_owner_event_vocabulary_rejected_even_after_rehash(field,key):
    c=context();c["timeframes"]["1D"]["features"]["structure"]["values"][field][key]="FUTURE_EVENT"
    reseal(c)
    with pytest.raises(ValueError,match="VOCABULARY_UNKNOWN"): dispatch.verify_context(c)


def test_mixed_views_rejected_before_joining():
    a=view.build_views(context(v1));b=view.build_views(context())
    with pytest.raises(ValueError,match="^TECHNICAL_VERSION_MIXED$"): f2.volume_items({"1D":a["1D"],"1W":b["1W"],"1M":b["1M"]})
