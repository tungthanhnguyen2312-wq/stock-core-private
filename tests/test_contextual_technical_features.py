"""Canonical feature evidence, adversarial fitness and action non-regression."""
import copy
import json
from datetime import date, timedelta

import pytest

import canonical_market_bars as bars
import contextual_technical_features as features
import integrated_investment_decision_product as product
import market_wide_historical_research_context as history
import technical_structure_context as owned
from test_canonical_market_bars import daily
from test_market_only_pit_eligibility import observation, rehash

CUTOFF = "2026-10-02T16:00:00Z"
ASOF = "2026-10-02"


def seal(bar):
    bar.update(features.identity(bar, kind="canonical_market_bar"))
    return bar


def series(count=35, *, basis="RETROSPECTIVE_ADJUSTED", closes=None, tf="1D"):
    # Explicit synthetic session ledger; no production calendar is inferred.
    values = closes if closes is not None else [100 + i for i in range(count)]
    count = len(values)
    result = []
    for i, close in enumerate(values):
        day = (date(2026, 10, 2) - timedelta(days=count - i - 1)).isoformat()
        if basis in {"RAW_AS_TRADED", "PIT_CA_ADJUSTED"}:
            row = observation(day, close=close, known=day+"T09:00:00Z")
            row["normalized"]["ohlc"] = {"open": close-1, "high": close+2, "low": close-2, "close": close}
            if basis == "PIT_CA_ADJUSTED":
                row["price_mode"] = basis
                row["raw_lineage_identities"] = ["raw:original:"+day]
                row["factor_chain"] = [dict(status="QUALIFIED", factor_chain_identity="fixture:factor:1",
                    official_execution_status="EXECUTED", ex_date_status="EXPLICIT_OFFICIAL", ex_date="2026-01-01",
                    knowledge_cutoff="2026-01-01T08:00:00Z", adjustment_factor=1.1)]
            rehash(row)
        else:
            row = daily(day, open=close-1, high=close+2, low=close-2, close=close,
                        volume=100+i, retrieved_at=day+"T09:00:00Z")
        bar = bars.derive([row], ticker="VNM", timeframe="1D", period_session=day,
                          knowledge_cutoff=CUTOFF, source_identity="fixture:source")
        if tf != "1D":
            # Verified canonical aggregate fixture: exact explicit constituents and completion.
            bar.update(timeframe=tf, period_completeness="COMPLETE")
            seal(bar)
        result.append(bar)
    return result


def evaluate(source=None, tf="1D"):
    return features.evaluate_timeframe(source if source is not None else series(), ticker="VNM",
        timeframe=tf, as_of_session=ASOF, knowledge_cutoff=CUTOFF)


def values(result, name):
    return result["features"][name]["values"]


@pytest.mark.parametrize("o,c,direction", [(10,12,"BULLISH"),(12,10,"BEARISH"),(11,11,"FLAT")])
def test_geometry_exact(o,c,direction):
    g=features.morphology(dict(open=o,high=15,low=9,close=c))
    assert g["body_direction"] == direction
    assert g["range"] == 6 and g["body_size"] == abs(c-o)
    assert g["upper_wick"] == 15-max(o,c) and g["lower_wick"] == min(o,c)-9
    assert g["close_location"] == (c-9)/6 and g["midpoint"] == 12
    assert g["upper_wick"]+g["body_size"]+g["lower_wick"] == g["range"]


def test_zero_range_is_explicit_not_zero_ratio():
    g=features.morphology(dict.fromkeys(("open","high","low","close"),10))
    assert g["range"] == 0 and g["body_range_ratio"] is None
    assert g["close_location"] is None and g["ratio_status"] == "NOT_APPLICABLE_ZERO_RANGE"


@pytest.mark.parametrize("changes", [{"open":None},{"high":8},{"low":20},{"close":float('nan')},{"open":True},{"close":0}])
def test_invalid_ohlc_never_becomes_geometry(changes):
    assert features.morphology({"open":10,"high":15,"low":9,"close":12,**changes}) is None


def test_first_bar_has_geometry_but_no_prior_true_range():
    r=evaluate(series(1))
    assert r["features"]["candle"]["status"] == "DESCRIPTIVE_ONLY"
    assert r["features"]["gaps"]["status"] == "INSUFFICIENT_HISTORY"
    assert values(r,"gaps") is None


@pytest.mark.parametrize("change,expected", [(5,"GAP_UP_MORPHOLOGY"),(-5,"GAP_DOWN_MORPHOLOGY")])
def test_gaps_true_range_and_labels(change,expected):
    s=series(2); previous=s[-2]; close=previous["close"]+change
    s[-1].update(open=close,close=close,high=close+2,low=close-2);seal(s[-1])
    r=evaluate(s); g=values(r,"gaps")
    assert g["observed_open_minus_prior_close"] == change
    assert g["true_range"] == max(4,abs(close+2-previous["close"]),abs(close-2-previous["close"]))
    assert expected in {l["label"] for l in values(r,"patterns")["labels"]}


def test_raw_morphology_allowed_but_continuous_unknown_ca_blocked():
    r=evaluate(series(basis="RAW_AS_TRADED"))
    assert r["features"]["candle"]["status"] in features.USABLE
    assert r["features"]["continuous_indicators"]["status"] == "BLOCKED_CA_COMPARABILITY"
    assert values(r,"structure")["trend_reference"].startswith("RAW_CONFIRMED_SWING")


def test_qualified_pit_uses_existing_factor_gate_and_allows_atr():
    s=series(15,basis="PIT_CA_ADJUSTED");r=evaluate(s)
    assert all(b["price_basis"] == "PIT_CA_ADJUSTED" for b in s)
    components=values(r,"continuous_indicators")
    assert components["atr14"]["status"] == "AVAILABLE"
    assert components["atr14"]["values"] == 4
    assert components["sma20"]["status"] == "INSUFFICIENT_HISTORY"
    assert r["context"]["historical_pit_authority"] is False


def test_retrospective_rolling_context_stays_research_only():
    r=evaluate();v=values(r,"continuous_indicators")
    assert v["atr14"]["status"] == "DESCRIPTIVE_ONLY"
    assert v["sma20"]["values"] == pytest.approx(sum(range(115,135))/20)
    assert r["context"]["price_basis"] == "RETROSPECTIVE_ADJUSTED"
    assert r["non_voting"] and r["authority_effect"] == features.AUTHORITY_EFFECT


@pytest.mark.parametrize("family", ["structure","levels","base","volatility","continuous_indicators"])
def test_raw_ca_boundary_blocks_dependent_rolling_family(family):
    s=series(basis="RAW_AS_TRADED")
    s[-2]["corporate_action_crossing"].update(state="EVENTS_OBSERVED",event_identities=["event:1"]);seal(s[-2])
    r=evaluate(s)
    assert r["features"][family]["status"] == "BLOCKED_CA_COMPARABILITY"
    assert values(r,family) is None
    assert values(r,"candle") is not None


def test_ca_raw_gap_retained_without_true_range_or_economic_interpretation():
    s=series(2,basis="RAW_AS_TRADED")
    s[-1]["corporate_action_crossing"].update(state="EVENTS_OBSERVED");seal(s[-1])
    g=values(evaluate(s),"gaps")
    assert g["observed_open_minus_prior_close"] is not None
    assert g["true_range"] is None and g["economic_gap_interpretation"] == "UNQUALIFIED"


def test_mixed_price_basis_blocks_window_but_not_current_candle():
    s=series();s[-2]["price_basis"]="RAW_AS_TRADED";seal(s[-2]);r=evaluate(s)
    assert r["features"]["structure"]["status"] == "BLOCKED_BASIS"
    assert values(r,"candle") is not None


@pytest.mark.parametrize("tf", ["1D","1W","1M"])
def test_timeframes_independently_bound_and_deterministic(tf):
    s=series(tf=tf);a=evaluate(s,tf);b=evaluate(list(reversed(s)),tf)
    assert a == b and json.dumps(a,sort_keys=True,allow_nan=False) == json.dumps(b,sort_keys=True,allow_nan=False)
    assert a["context"]["timeframe"] == tf


@pytest.mark.parametrize("tf", ["1W","1M"])
def test_incomplete_current_aggregate_does_not_enter_completed_features(tf):
    s=series(tf=tf);expected=s[-2]["artifact_identity"]
    s[-1]["period_completeness"]="PARTIAL_CURRENT_PERIOD";seal(s[-1]);r=evaluate(s,tf)
    assert r["context"]["canonical_source_bar_identity"] == expected
    assert r["context"]["latest_period"]["period_completeness"] == "PARTIAL_CURRENT_PERIOD"
    for b in s: b["period_completeness"]="CALENDAR_SCOPE_UNKNOWN";seal(b)
    assert evaluate(s,tf)["features"]["candle"]["status"] == "INSUFFICIENT_HISTORY"


def test_invalid_constituent_is_not_skipped_inside_window():
    s=series();s[-6].update(close=None,status="UNAVAILABLE");seal(s[-6]);r=evaluate(s)
    assert r["features"]["structure"]["status"] == "SOURCE_FIELD_UNAVAILABLE"
    assert r["features"]["continuous_indicators"]["status"] == "SOURCE_FIELD_UNAVAILABLE"
    assert values(r,"candle") is not None


def test_current_invalid_bar_does_not_crash_or_reuse_old_current():
    s=series();s[-1].update(close=None,status="UNAVAILABLE");seal(s[-1]);r=evaluate(s)
    assert values(r,"candle") is None and values(r,"structure") is None


@pytest.mark.parametrize("count", [0,1,14,19])
def test_insufficient_structure_is_explicit(count):
    r=evaluate(series(count));assert r["features"]["structure"]["status"] == "INSUFFICIENT_HISTORY"


def test_existing_owner_methods_are_used_exactly():
    s=series();r=evaluate(s);closes=[b["close"] for b in s];v=values(r,"structure")
    assert v["close_only_structure"] == owned._structure(closes[-20:])
    assert v["breakout_event"] == owned._breakout_event(closes)
    assert v["range_state"] == owned._range_state(closes[-20:])
    assert values(r,"base")["base_duration_bars"] == owned._base_duration(closes[-20:],closes,v["close_only_structure"]["support"]["value"],v["close_only_structure"]["resistance"]["value"])["base_duration_sessions"]


@pytest.mark.parametrize("closes,state", [([100+i for i in range(35)],"BREAKOUT"),([100,102,104,102,100,101,103,101,99]*4+[105,99],"FAILED_BREAKOUT")])
def test_breakout_failure_uses_owned_pivot_method(closes,state):
    r=evaluate(series(closes=closes))
    assert values(r,"structure")["breakout"]["breakout_state"] == state


def test_support_resistance_age_observations_and_rejection():
    s=series(closes=[100+(i%2) for i in range(35)]);s[-1].update(open=101,close=100.5,high=102,low=99);seal(s[-1])
    v=values(evaluate(s),"levels")
    assert v["nearest_support"]["price"] == 100 and v["nearest_resistance"]["price"] == 101
    assert v["nearest_support"]["tests"] and v["nearest_support"]["rejects"]
    assert v["nearest_resistance"]["rejects"] and v["nearest_support"]["age_bars"] > 0
    assert v["nearest_support"]["observation_count"] == len(v["nearest_support"]["source_bar_identities"])


def test_base_established_and_compression_use_existing_rules():
    closes=[100+(i%2)*10 for i in range(15)]+[104+(i%2) for i in range(20)]
    r=evaluate(series(closes=closes));assert values(r,"base")["state"] == "ESTABLISHED"
    assert values(r,"base")["position"] is not None


def test_volume_unknown_native_units_dimensionless_only():
    r=evaluate();v=values(r,"volume")
    assert v["native_unit"] == "UNKNOWN" and v["relative_to_median"] > 0
    assert v["participant_inference"] == "NONE" and v["economic_value_or_shares_conversion"] == "NONE"
    assert r["features"]["volume"]["status"] == "DESCRIPTIVE_ONLY"


@pytest.mark.parametrize("field,value", [("volume_unit","LOTS"),("volume_basis","OTHER")])
def test_incompatible_volume_does_not_block_geometry(field,value):
    s=series();s[-5][field]=value;seal(s[-5]);r=evaluate(s)
    assert r["features"]["volume"]["status"] == "BLOCKED_BASIS" and values(r,"candle") is not None


def test_zero_volume_reference_has_null_ratios():
    s=series()
    for b in s: b["volume"]=0;seal(b)
    assert values(evaluate(s),"volume")["relative_to_median"] is None


def test_engulfing_is_morphology_with_no_action():
    s=series(2);s[0].update(open=100,close=105,low=99,high=106);seal(s[0])
    s[1].update(open=106,close=99,low=98,high=107);seal(s[1])
    labels=values(evaluate(s),"patterns")["labels"]
    engulf=next(l for l in labels if l["label"] == "BEARISH_ENGULFING_MORPHOLOGY")
    assert engulf["action_authority"] == "NONE" and engulf["primitive_conditions"]["current_body_contains_prior_body"]
    assert len(engulf["source_bar_identities"]) == 2


@pytest.mark.parametrize("available,opposed,expected", [(3,False,"ALIGNED"),(3,True,"MIXED_DIVERGENT"),(1,False,"PARTIALLY_ALIGNED"),(0,False,"UNKNOWN_UNAVAILABLE")])
def test_multi_timeframe_no_weighting(available,opposed,expected):
    s={tf:series(tf=tf,closes=[150-i for i in range(35)] if opposed and tf == "1M" else None) for tf in features.TIMEFRAMES[:available]}
    r=features.build_context(s,ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    assert r["multi_timeframe"]["state"] == expected and r["multi_timeframe"]["weights"] is None


@pytest.mark.parametrize("fault", ["identity","future","instrument","conflict"])
def test_bad_canonical_input_refused(fault):
    s=series()
    if fault == "identity":s[-1]["close"]+=1
    if fault == "future":s[-1]["knowledge_available_at"]="2026-10-03T08:00:00Z";seal(s[-1])
    if fault == "instrument":s[-1]["instrument"]["ticker"]="HPG";seal(s[-1])
    if fault == "conflict":b=copy.deepcopy(s[-1]);b["close"]-=1;seal(b);s.append(b)
    with pytest.raises(ValueError):evaluate(s)


def research_artifact():
    s={tf:series(tf=tf) for tf in features.TIMEFRAMES}
    projection=bars.project_research_series(s,target_session=ASOF,knowledge_cutoff=CUTOFF)
    context=features.build_context(s,ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)
    value={"contract_version":history.CONTRACT_VERSION,"session":ASOF,"records":{"VNM":{"multi_timeframe":projection,"contextual_technical":context}}}
    value.update(history.content_identity(value));return value


def test_real_product_adapter_is_additive_and_decision_identity_unchanged():
    kwargs=dict(session=ASOF,requested_at=CUTOFF,technical_structure_artifact={"records":{"VNM":{"eligible":False}}})
    before=product.build_artifact(**kwargs,historical_context_artifact=research_artifact())
    after=copy.deepcopy(before)
    record=after["records"]["VNM"]
    assert record.pop("contextual_technical_context")["status"] == "AVAILABLE"
    reference=record["evidence_axes"]["TACTICAL_STRUCTURE"].pop("contextual_feature_reference")
    assert reference["non_voting"] and reference["artifact_identity"]
    original=research_artifact();original["records"]["VNM"].pop("contextual_technical");original.update(history.content_identity(original))
    baseline=product.build_artifact(**kwargs,historical_context_artifact=original)
    # The richer historical artifact legitimately has a new content address.
    # Its old bar projection remains exact; only this parent lineage changes.
    record["market_sector_context"]["multi_timeframe"].pop("source_artifact_identity")
    baseline["records"]["VNM"]["market_sector_context"]["multi_timeframe"].pop("source_artifact_identity")
    assert record == baseline["records"]["VNM"]
    assert product.decision_identity(before["records"]["VNM"]) == before["records"]["VNM"]["decision_identity"]
    assert before["artifact_identity"] != baseline["artifact_identity"]


@pytest.mark.parametrize("fault", ["nested_hash","source_bar","cutoff","ticker","non_voting","input_reference"])
def test_product_rejects_incoherent_features_without_decision_change(fault):
    h=research_artifact();f=h["records"]["VNM"]["contextual_technical"]
    frame=f["timeframes"]["1D"];ctx=frame["context"]
    if fault == "nested_hash":frame["features"]["candle"]["values"]["close"]+=1
    if fault == "source_bar":ctx["canonical_source_bar_identity"]="forged";ctx.update(features.identity(ctx,kind="contextual_technical_inputs/v1"));frame.update(features.identity(frame))
    if fault == "cutoff":f["knowledge_cutoff"]="2026-10-03T16:00:00Z"
    if fault == "ticker":f["ticker"]="HPG"
    if fault == "non_voting":f["non_voting"]=False
    if fault == "input_reference":frame["features"]["candle"]["input_context_identity"]="wrong";frame.update(features.identity(frame))
    f.update(features.identity(f));h.update(history.content_identity(h))
    r=product.build_artifact(session=ASOF,requested_at=CUTOFF,technical_structure_artifact={"records":{"VNM":{"eligible":False}}},historical_context_artifact=h)["records"]["VNM"]
    assert r["contextual_technical_context"]["status"] == "UNAVAILABLE"
    assert r["research_action_posture"] == "INSUFFICIENT_CURRENT_RESEARCH"


def test_index_instrument_not_equity_only():
    s=series()
    for b in s:b["instrument"]["board"]="INDEX";seal(b)
    assert evaluate(s)["context"]["instrument"]["board"] == "INDEX"


@pytest.mark.parametrize("old_span,new_span,expected",[(10,2,"COMPRESSION"),(2,10,"EXPANSION"),(4,4,"STABLE")])
def test_range_distribution_compression_and_expansion(old_span,new_span,expected):
    s=series(closes=[100]*20)
    for i,b in enumerate(s):
        span=old_span if i<10 else new_span
        b.update(open=100,close=100,high=100+span/2,low=100-span/2);seal(b)
    v=values(evaluate(s),"volatility")
    assert v["range_context"] == expected
    assert v["rolling_range_distribution"]["percentile"] <= 1


@pytest.mark.parametrize("name,fields",[("DOJI_LIKE",dict(open=100,close=100,high=104,low=96)),
    ("LONG_BODY",dict(open=96,close=104,high=104,low=96)),
    ("UPPER_REJECTION_MORPHOLOGY",dict(open=100,close=101,high=110,low=99)),
    ("LOWER_REJECTION_MORPHOLOGY",dict(open=100,close=101,high=102,low=90)),
    ("INSIDE_BAR",dict(open=100,close=100,high=100.5,low=99.5)),
    ("OUTSIDE_BAR",dict(open=100,close=100,high=110,low=90))])
def test_bounded_secondary_label_vocabulary(name,fields):
    s=series(closes=[100,100]);s[-1].update(fields);seal(s[-1])
    labels=values(evaluate(s),"patterns")["labels"]
    assert name in {v["label"] for v in labels}
    assert all(v["action_authority"] == "NONE" for v in labels)


def test_missing_volume_is_explicit_and_independent_from_price_geometry():
    s=series();s[-4]["volume"]=None;seal(s[-4]);r=evaluate(s)
    assert r["features"]["volume"]["status"] == "SOURCE_FIELD_UNAVAILABLE"
    assert values(r,"volume") is None and values(r,"candle") is not None


@pytest.mark.parametrize("tf",["1W","1M"])
def test_completed_aggregate_does_not_outvote_unusable_constituent_permissions(tf):
    s=series(tf=tf);s[-1]["fitness"]["allowed_uses"]=[];seal(s[-1]);r=evaluate(s,tf)
    assert r["features"]["candle"]["status"] == "SOURCE_FIELD_UNAVAILABLE"
    assert r["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("tf",["1D","1W","1M"])
def test_adapted_owner_lookbacks_are_bar_units(tf):
    r=evaluate(series(tf=tf),tf)
    assert "base_duration_bars" in values(r,"base")
    assert "confirmation_lag_bars" in values(r,"structure")["swing_structure"]
    slope=values(r,"continuous_indicators")["sma20_slope"]["values"]
    assert slope["lookback_bars"] == 5 and "lookback_sessions" not in slope


@pytest.mark.parametrize("fault",["price_basis","volume_unit","instrument","future_known"])
def test_nested_rehashed_source_semantics_cannot_promote_feature(fault):
    h=research_artifact();f=h["records"]["VNM"]["contextual_technical"];frame=f["timeframes"]["1D"];ctx=frame["context"]
    if fault == "price_basis":ctx["price_basis"]="PIT_CA_ADJUSTED"
    if fault == "volume_unit":ctx["volume_unit"]="SHARES"
    if fault == "instrument":ctx["instrument"]["exchange"]="OTHER"
    if fault == "future_known":ctx["knowledge_available_at"]="2026-10-03T16:00:00Z"
    ctx.update(features.identity(ctx,kind="contextual_technical_inputs/v1"))
    for v in frame["features"].values():v["input_context_identity"]=ctx["artifact_identity"]
    frame.update(features.identity(frame));f.update(features.identity(f));h.update(history.content_identity(h))
    b=product.market_bar_context_records(h,session=ASOF,requested_at=CUTOFF)
    assert features.verified_context_records(h,session=ASOF,knowledge_cutoff=CUTOFF,verified_bar_contexts=b)["VNM"]["status"] == "UNAVAILABLE"


def test_all_blocked_source_diagnostic_can_be_verified_without_inventing_a_bar():
    s={tf:[] for tf in features.TIMEFRAMES};s["1D"]=series(1)
    s["1D"][0].update(close=None,status="UNAVAILABLE");seal(s["1D"][0])
    h={"contract_version":history.CONTRACT_VERSION,"session":ASOF,"records":{"VNM":{
        "multi_timeframe":bars.project_research_series(s,target_session=ASOF,knowledge_cutoff=CUTOFF),
        "contextual_technical":features.build_context(s,ticker="VNM",as_of_session=ASOF,knowledge_cutoff=CUTOFF)}}}
    h.update(history.content_identity(h));b=product.market_bar_context_records(h,session=ASOF,requested_at=CUTOFF)
    c=features.verified_context_records(h,session=ASOF,knowledge_cutoff=CUTOFF,verified_bar_contexts=b)
    assert c["VNM"]["status"] == "AVAILABLE"
    assert c["VNM"]["projection"]["timeframes"]["1D"]["features"]["candle"]["values"] is None


def test_new_t0_snapshot_retains_complete_context_without_mutating_product(tmp_path):
    import prospective_decision_retention as retention
    value=product.build_artifact(session=ASOF,requested_at=CUTOFF,
        technical_structure_artifact={"records":{"VNM":{"eligible":False}}},historical_context_artifact=research_artifact())
    before=copy.deepcopy(value)
    snapshot=retention.build_snapshot(session=ASOF,operation_identity="fixture:operation",producer_run_identity="fixture:run",integrated_artifact=value)
    assert retention.validate_snapshot(snapshot)
    assert snapshot["records"]["VNM"]["integrated_decision_at_t0"]["contextual_technical_context"] == value["records"]["VNM"]["contextual_technical_context"]
    path=retention.write_immutable_snapshot(tmp_path,snapshot)
    assert retention.write_immutable_snapshot(tmp_path,snapshot) == path and value == before
