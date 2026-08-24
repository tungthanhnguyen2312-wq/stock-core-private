from historical_matched_traded_value_authority import (
    MATCHED_VALUE_FORMULA,
    adv20_status,
    qualify_anchor_rows,
    summarize_complete_trade_session,
)


def _trade(board, price, quantity, time="2026-08-11 14:45:00.000"):
    return {"boardId": board, "matchPrice": price, "matchQtty": quantity, "time": time}


def _candidate(*, terminal=True):
    return summarize_complete_trade_session(
        ticker="AAA", session="2026-08-11",
        pages=[
            {"page_index": 1, "page_cursor": None, "next_page_token": "next", "trades": [_trade("G1", "20", "100"), _trade("G4", "20", "1")]},
            {"page_index": 2, "page_cursor": "next", "next_page_token": None if terminal else "later", "trades": [_trade("T1", "20", "50")]},
        ], raw_payload_hashes=["b", "a"],
    )


def test_g1_only_value_preserves_actual_other_board_composition():
    candidate = _candidate()
    assert candidate["matched_value_vnd"] == 20_000_000
    assert candidate["g1_share_quantity"] == 1000
    assert [row["board_id"] for row in candidate["board_composition"]] == ["G1", "G4", "T1"]
    assert [row["included_in_matched_value"] for row in candidate["board_composition"]] == [True, False, False]


def test_exact_fhsc_volume_and_value_anchor_qualifies_without_averaging():
    second = dict(_candidate(), ticker="BBB", session="2026-08-10")
    anchor = {"fhsc_identity_retained_exact": True, "fhsc_matched_volume": 1000, "fhsc_matched_value": 20_000_000}
    result = qualify_anchor_rows([(_candidate(), anchor), (second, anchor)])
    assert result["formula_status"] == "QUALIFIED_EMPIRICAL_SCOPE"
    assert result["qualified_rows"][0]["fhsc_reconciliation"]["status"] == "EXACT"
    assert result["formula"] == MATCHED_VALUE_FORMULA


def test_value_or_volume_conflict_blocks_that_row_and_formula():
    result = qualify_anchor_rows([(_candidate(), {
        "fhsc_identity_retained_exact": True, "fhsc_matched_volume": 1000, "fhsc_matched_value": 2_000_001,
    })])
    assert result["formula_status"] == "NOT_QUALIFIED"
    assert result["rows"][0]["qualification_status"] == "CONFLICTING"


def test_one_exact_anchor_is_not_a_formula_contract():
    result = qualify_anchor_rows([(_candidate(), {
        "fhsc_identity_retained_exact": True, "fhsc_matched_volume": 1000, "fhsc_matched_value": 20_000_000,
    })])
    assert result["formula_status"] == "NOT_QUALIFIED"
    assert result["rows"][0]["qualification_status"] == "EXACT_BUT_INSUFFICIENT_ANCHOR_BREADTH"


def test_unfinished_page_chain_is_not_a_complete_session():
    candidate = _candidate(terminal=False)
    assert candidate["qualification_status"] == "INCOMPLETE_SESSION"
    assert candidate["matched_value_vnd"] is None


def test_page_chain_missing_first_page_is_not_complete():
    candidate = summarize_complete_trade_session(
        ticker="AAA", session="2026-08-11",
        pages=[{"page_index": 2, "page_cursor": "next", "next_page_token": None, "trades": [_trade("G1", "20", "100")]}],
        raw_payload_hashes=["a"],
    )
    assert candidate["qualification_status"] == "INCOMPLETE_SESSION"
    assert candidate["session_completeness"]["reason"] == "PAGE_CHAIN_DOES_NOT_START_AT_FIRST_PAGE"


def test_adv20_does_not_average_three_qualified_sessions():
    rows = []
    for session in ("2026-08-07", "2026-08-10", "2026-08-11"):
        row = {"ticker": "AAA", "session": session, "qualification_status": "MATCHED_VALUE_QUALIFIED"}
        rows.append(row)
    result = adv20_status(rows)
    assert result["AAA"]["status"] == "ADV20_INSUFFICIENT_HISTORY"
    assert result["AAA"]["qualified_complete_sessions"] == 3
    assert result["AAA"]["adv20_vnd"] is None
