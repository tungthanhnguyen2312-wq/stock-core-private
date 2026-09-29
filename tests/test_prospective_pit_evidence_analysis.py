import prospective_pit_evidence_analysis as a


def test_bar_pair_classification():
    assert a.classify_bar_pair((10, 11, 9, 10), (10, 11, 9, 10)) == a.IDENTICAL
    factor = 1 / 1.1
    rebased = tuple(x * factor for x in (10, 11, 9, 10))
    assert a.classify_bar_pair((10, 11, 9, 10), rebased) == a.CONSISTENT_RATIO
    assert a.classify_bar_pair((10, 11, 9, 10), (10, 11, 8.5, 9.6)) == a.INCONSISTENT


def test_three_way_basis_identifies_unadjusted_official_series():
    t0, t1 = (72.5, 72.7, 71.4, 71.4), (65.91, 66.09, 64.91, 64.91)
    assert a.three_way_basis(t0, t0, t1) == a.HOSE_EQ_T0_ONLY
    assert a.three_way_basis(t1, t0, t1) == a.HOSE_EQ_T1_ONLY
    assert a.three_way_basis((1, 1, 1, 1), t0, t1) == a.OFFICIAL_EQ_NEITHER
    assert a.three_way_basis(t0, t0, t0) == a.OFFICIAL_EQ_BOTH


def test_event_window_ratio():
    assert round(a.event_window_ratio(26.35, 23.95), 4) == 0.9089


def test_event_authority_never_infers_ex_date_or_terms():
    events = [
        {"event_type": "CASH_DIVIDEND", "ex_date": "2026-08-01", "record_date": "2026-08-02", "execution_date": "2026-08-20",
         "materiality_status": "PRICE_SHARE_AFFECTING", "source": "idx"},
        {"event_type": "STOCK_DIVIDEND", "ex_date": None, "record_date": "2026-08-02", "execution_date": None,
         "materiality_status": "PRICE_SHARE_AFFECTING", "source": "idx"},
    ]
    table = a.event_authority_table(events)
    assert table["explicit_ex_date"] == 1  # a record date never becomes an ex-date
    assert table["ratio_or_cash_terms"] == 0 and table["publication_time_retained"] == 0
    assert table["ex_date_inferred_from_record_date"] == 0
    assert table["by_event_type"]["STOCK_DIVIDEND"]["record_date"] == 1


TICKS = [{"boardId": "G1", "time": "2026-06-17 09:00:01.000", "matchPrice": 30.0},
         {"boardId": "G1", "time": "2026-06-17 14:58:14.034", "matchPrice": 30.5},
         {"boardId": "G4", "time": "2026-06-17 10:00:00.000", "matchPrice": 99.0}]


def test_trades_reconstruction_fails_closed_without_completeness_proof():
    assert a.reconstruct_daily_ohlc_from_trades(TICKS, session="2026-06-17", completeness_proof=None)["state"] == "FAIL_CLOSED"
    partial = {"pages_complete": False}
    assert a.reconstruct_daily_ohlc_from_trades(TICKS, session="2026-06-17", completeness_proof=partial)["ohlc"] is None
    failed = {"pages_complete": True, "http_failures": 2}
    assert a.reconstruct_daily_ohlc_from_trades(TICKS, session="2026-06-17", completeness_proof=failed)["state"] == "FAIL_CLOSED"


def test_trades_reconstruction_fails_closed_at_page_cap_and_when_proven_is_derived_not_official():
    capped = {"pages_complete": True, "http_failures": 0, "page_sizes": [a.DNSE_TRADES_PAGE_CAP]}
    assert a.reconstruct_daily_ohlc_from_trades(TICKS, session="2026-06-17", completeness_proof=capped)["reason_codes"] == ["PAGE_AT_CAP_TRUNCATION_NOT_EXCLUDED"]
    proven = {"pages_complete": True, "http_failures": 0, "page_sizes": [3]}
    result = a.reconstruct_daily_ohlc_from_trades(TICKS, session="2026-06-17", completeness_proof=proven)
    assert result["state"] == "DERIVED_RAW_AS_TRADED_CANDIDATE" and result["authority"] == "DERIVED_NOT_OFFICIAL"
    assert result["ohlc"] == {"open": 30.0, "high": 30.5, "low": 30.0, "close": 30.5}  # G4 odd lot excluded
