from market_wide_current_liquidity_research import build_artifact

def _trade(): return {"ok":True,"body":{"trades":[{"boardId":"G1","time":"2026-08-21 14:59:00","matchPrice":1,"matchQtty":1,"avgPrice":1,"totalVolumeTraded":10,"grossTradeAmount":1},{"boardId":"T1","time":"2026-08-21 14:59:00","matchPrice":1,"matchQtty":1,"avgPrice":1,"totalVolumeTraded":2,"grossTradeAmount":1}]}}
def _ohlc(): return {"ok":True,"body":{"t":[1787328000],"v":[100]}}
def test_current_dataset_is_deterministic_and_fail_closed():
    a=build_artifact(candidates=["AAA","BBB"],trades={"AAA":_trade()},ohlc={"AAA":_ohlc()},requested_at="x")
    assert a["coverage"]["reconciled_count"]==2 and a["records"]["BBB"]["disposition"]=="MISSING"
    assert a["records"]["AAA"]["g1_v_reconciliation"]["exact_match"]
    assert a["authority_boundary"]["POSITION_SIZING"]=="BLOCKED"
