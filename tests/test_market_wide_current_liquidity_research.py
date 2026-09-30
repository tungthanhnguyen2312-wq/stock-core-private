from market_wide_current_liquidity_research import artifact_authority_boundary, build_artifact

def _trade(): return {"ok":True,"body":{"trades":[{"boardId":"G1","time":"2026-08-21 14:59:00","matchPrice":1,"matchQtty":1,"avgPrice":1,"totalVolumeTraded":10,"grossTradeAmount":1},{"boardId":"T1","time":"2026-08-21 14:59:00","matchPrice":1,"matchQtty":1,"avgPrice":1,"totalVolumeTraded":2,"grossTradeAmount":1}]}}
def _ohlc(): return {"ok":True,"body":{"t":[1787328000],"v":[100]}}
def test_current_dataset_is_deterministic_and_fail_closed():
    a=build_artifact(candidates=["AAA","BBB"],trades={"AAA":_trade()},ohlc={"AAA":_ohlc()},requested_at="x")
    assert a["coverage"]["reconciled_count"]==2 and a["records"]["BBB"]["disposition"]=="MISSING"
    assert a["records"]["AAA"]["g1_v_reconciliation"]["exact_match"]
    assert a["authority_boundary"]["POSITION_SIZING"]=="BLOCKED"
    assert a["authority_boundary"]["EXECUTION_CAPACITY"]=="BLOCKED"
    assert a["authority_boundary"]["PIT_BACKTEST"]=="BLOCKED"
    assert a["authority_boundary"]["RAW_AS_TRADED"]=="NOT_PROMOTED"
    current=a["authority_boundary"]["CURRENT_SESSION_LIQUIDITY_RESEARCH"]
    assert current["state"]=="DESCRIPTIVE_ONLY" and current["eligible_count"]==1 and current["denominator"]==2
    assert a["authority_boundary"]["ADTV_RESEARCH"]["state"]=="PER_RECORD"
    assert a["authority_boundary"]["ADTV_RESEARCH"]["in_this_artifact"] is False
    assert a["authority_boundary"]["ADV_VOLUME_RESEARCH"]["basis"]=="AS_TRADED_NOT_CA_NORMALIZED"
    assert a["authority_boundary"]["QUALIFIED_LIQUIDITY_INPUTS"]["state"]=="PER_RECORD"
    assert a["authority_boundary"]["QUALIFIED_LIQUIDITY_INPUTS"] is not False
    assert a["authority_boundary"]["per_record_fitness_is_authoritative"] is True


def test_descriptive_artifact_summary_does_not_claim_global_adtv_block_or_qualify_rows():
    boundary=artifact_authority_boundary(eligible_count=952, universe_count=1683)
    assert boundary["CURRENT_SESSION_LIQUIDITY_RESEARCH"]["eligible_count"]==952
    assert boundary["ADTV_RESEARCH"]["state"]=="PER_RECORD"
    assert "BLOCKED" not in str(boundary["ADTV_RESEARCH"])
    assert boundary["QUALIFIED_LIQUIDITY_INPUTS"]["state"]=="PER_RECORD"
    assert boundary["LIVE_POSITION_SIZING"]=="BLOCKED"
    assert boundary["EXECUTION_REPLAY"]=="BLOCKED"
