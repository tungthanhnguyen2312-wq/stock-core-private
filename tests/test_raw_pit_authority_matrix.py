import raw_pit_authority_matrix as m

EVIDENCE = {"prospective_sessions": 24, "prospective_dnse_bars": 100, "prospective_raw_qualified_bars": 40,
            "same_session_cross_source_agreement_09_28": 10, "hose_tickers": 403, "hose_event_tests_unadjusted": 3,
            "explicit_ex_date_events": 4438, "ratio_or_cash_terms_events": 0, "publication_time_events": 0,
            "qualified_factor_chain_events": 0, "official_verified_rebasing_pairs": 282, "t0_bar_not_final_pairs": 603}


def test_ten_dimensions_never_collapsed():
    out = m.evaluate(EVIDENCE)
    assert len(out["dimensions"]) == 10 and set(out["after"]) == set(m.BEFORE) == set(out["dimensions"])


def test_promotions_are_scoped_and_hard_blocks_remain():
    out = m.evaluate(EVIDENCE)["after"]
    assert out["PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE"]["state"] == "OPERATIONAL"
    assert out["PROSPECTIVE_RAW_AS_TRADED_PRICE"]["state"] == "QUALIFIED_SCOPED_CROSS_SOURCE"
    assert out["HISTORICAL_RAW_AS_TRADED_PRICE"]["state"] == "PARTIAL_HOSE_EMPIRICAL_SCOPED"
    for dim in ("CORPORATE_ACTION_FACTOR_CHAIN", "POINT_IN_TIME_ADJUSTED_HISTORY", "PIT_BACKTEST_ELIGIBILITY", "EXECUTION_REPLAY_ELIGIBILITY"):
        assert out[dim]["state"] == "BLOCKED" and out[dim]["blockers"]


def test_no_evidence_promotes_nothing_beyond_before_state():
    out = m.evaluate({})
    assert out["after"]["PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE"]["state"] == "BLOCKED"
    assert out["after"]["PROSPECTIVE_RAW_AS_TRADED_PRICE"]["state"] == "BLOCKED"
    assert out["after"]["CORPORATE_ACTION_EVENT_AUTHORITY"]["state"] == m.BEFORE["CORPORATE_ACTION_EVENT_AUTHORITY"]


def test_every_blocker_is_typed():
    keys = {"missing_evidence", "engineering_can_create", "only_future_calendar_time_can_create", "external_permission_or_data_required"}
    for cell in m.evaluate(EVIDENCE)["after"].values():
        for blocker in cell["blockers"]:
            assert keys <= set(blocker)


def test_factor_chain_promotes_pit_adjusted_only_with_a_qualified_event():
    out = m.evaluate({**EVIDENCE, "qualified_factor_chain_events": 1})["after"]
    assert out["POINT_IN_TIME_ADJUSTED_HISTORY"]["state"] == "QUALIFIED_BOUNDED"
    assert out["PIT_BACKTEST_ELIGIBILITY"]["state"] == "BLOCKED"  # universe/history still block backtests
