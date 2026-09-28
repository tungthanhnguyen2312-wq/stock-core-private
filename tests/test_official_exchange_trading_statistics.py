from __future__ import annotations

import json

import pytest

import official_exchange_trading_statistics as official

# 2026-09-28 00:00:00 UTC; HPG figures are the retained official HOSE row for that session.
SEPT_28 = 1790553600
HPG_ROW = {
    "symbol": "HPG     ", "reportDate": SEPT_28, "month": 9, "year": 2026,
    "totalShare": 33595805.0, "totalValue": 694368015300.0,
    "mainVolume": 24184800.0, "mainValue": 492561095000.0,
    "oddlotvolume": 61005.0, "oddlotvalue": 1249420300.0,
    "bigLotVolume": 9350000.0, "bigLotValue": 200557500000.0,
    "bigLotVolume_OL": 0.0, "bigLotValue_OL": 0.0, "closePrice": 20200.0,
}


def _hose_body(*rows: dict, success: bool = True) -> bytes:
    return json.dumps({"data": {"list": list(rows), "paging": {"pageIndex": 1, "pageSize": 20, "totalCount": 4424, "totalPages": 222}},
                       "success": success, "message": None}).encode("utf-8")


HNX_HEADER = (
    "<table><thead><tr><th>STT</th><th>Ngày</th><th>KLGD (Cổ phiếu)</th><th>GTGD (Nghìn đồng)</th>"
    "<th>Thị trường</th><th>Nhà đầu tư nước ngoài</th></tr>"
    "<tr><th>Khớp lệnh</th><th>Thỏa thuận</th><th>Tổng</th><th>Khớp lệnh</th><th>Thỏa thuận</th><th>Tổng</th>"
    "<th>% KLGD</th><th>% GTGD</th></tr></thead><tbody>"
)


def _hnx_row(index: int, date: str, matched: str, put_through: str, total: str, matched_value: str, put_value: str, total_value: str) -> str:
    cells = [str(index), date, matched, put_through, total, matched_value, put_value, total_value,
             "26,24", "22,09", "276.100", "3.632.520", "0", "0", "361.167.078"]
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def _hnx_body(*rows: str) -> bytes:
    return (HNX_HEADER + "".join(rows) + "</tbody></table>").encode("utf-8")


def test_hose_parse_maps_components_and_derives_exact_aggregates():
    parsed = official.parse_hose_trading_result(_hose_body(HPG_ROW), symbol="hpg")
    assert parsed["parse_status"] == official.PARSED
    row = parsed["rows"][0]
    assert row["session"] == "2026-09-28"
    assert row["row_integrity"] == "COMPONENTS_SUM_TO_TOTAL"
    assert row["components"][official.MATCHED_ROUND_LOT] == {"volume_shares": 24184800, "value_vnd": 492561095000}
    assert row["components"][official.MATCHED_ODD_LOT] == {"volume_shares": 61005, "value_vnd": 1249420300}
    assert row["components"][official.MATCHED_ALL] == {"volume_shares": 24245805, "value_vnd": 493810515300}
    assert row["components"][official.PUT_THROUGH_ALL] == {"volume_shares": 9350000, "value_vnd": 200557500000}
    assert row["symbol_binding"] == "RESPONSE_FIELD"
    assert parsed["paging"]["totalCount"] == 4424


def test_hose_components_that_do_not_close_are_flagged_not_repaired():
    broken = {**HPG_ROW, "totalShare": 33595806.0}
    row = official.parse_hose_trading_result(_hose_body(broken), symbol="HPG")["rows"][0]
    assert row["row_integrity"] == "COMPONENTS_DO_NOT_SUM_TO_TOTAL"
    assert row["components"][official.TOTAL]["volume_shares"] == 33595806


@pytest.mark.parametrize("mutation, reason", [
    ({"symbol": "HPX"}, "SYMBOL_MISMATCH"),
    ({"reportDate": SEPT_28 + 3600}, "REPORT_DATE_NOT_UTC_MIDNIGHT_EPOCH"),
    ({"month": 8}, "REPORT_DATE_MONTH_YEAR_DISAGREE"),
    ({"mainValue": 1.5}, "FIELD_NOT_NON_NEGATIVE_WHOLE:mainValue"),
    ({"oddlotvolume": -1.0}, "FIELD_NOT_NON_NEGATIVE_WHOLE:oddlotvolume"),
    ({"bigLotValue": None}, "FIELD_NOT_NUMERIC:bigLotValue"),
])
def test_hose_rows_failing_identity_or_numeric_checks_are_rejected(mutation, reason):
    parsed = official.parse_hose_trading_result(_hose_body({**HPG_ROW, **mutation}), symbol="HPG")
    assert parsed["rows"] == []
    assert parsed["rejected"][0]["reason"] == reason


def test_hose_duplicate_session_and_unsuccessful_or_malformed_responses_fail_closed():
    assert official.parse_hose_trading_result(_hose_body(HPG_ROW, HPG_ROW), symbol="HPG")["parse_status"] == "DUPLICATE_SESSION_ROWS"
    assert official.parse_hose_trading_result(_hose_body(HPG_ROW, success=False), symbol="HPG")["parse_status"] == "HOSE_RESPONSE_NOT_SUCCESS"
    assert official.parse_hose_trading_result(b"<html>", symbol="HPG")["parse_status"] == "MALFORMED_JSON"


def test_hnx_parse_reads_vietnamese_numbers_and_scales_thousand_vnd_exactly():
    body = _hnx_body(_hnx_row(1, "28/09/2026", "13.716.282", "0", "13.716.282", "182.193.500,3", "0", "182.193.500,3"))
    parsed = official.parse_hnx_thong_tin_tong_hop(body, symbol="shs", exchange=official.HNX)
    assert parsed["parse_status"] == official.PARSED
    row = parsed["rows"][0]
    assert row["session"] == "2026-09-28"
    assert row["components"][official.MATCHED_ALL] == {"volume_shares": 13716282, "value_vnd": 182193500300}
    assert row["row_integrity"] == "COMPONENTS_SUM_TO_TOTAL"
    assert row["symbol_binding"] == "REQUEST_PARAMETER_ONLY"
    assert official.MATCHED_ROUND_LOT not in row["components"]


def test_hnx_header_drift_fails_closed_before_any_number_is_read():
    body = _hnx_body(_hnx_row(1, "28/09/2026", "1", "0", "1", "1", "0", "1")).replace("Thỏa thuận".encode(), b"PT")
    assert official.parse_hnx_thong_tin_tong_hop(body, symbol="SHS", exchange=official.HNX)["parse_status"] == "HNX_HEADER_SCHEMA_DRIFT"


def test_hnx_rows_with_bad_numbers_dates_or_shapes_are_rejected_individually():
    body = _hnx_body(
        _hnx_row(1, "28/09/2026", "1,234.5", "0", "1", "1", "0", "1"),   # English formatting
        _hnx_row(2, "2026-09-25", "1", "0", "1", "1", "0", "1"),          # wrong date format
        _hnx_row(3, "24/09/2026", "10", "0", "10", "1,2345", "0", "1,2345"),  # not whole VND after x1000
        "<tr><td>4</td><td>23/09/2026</td></tr>",
        _hnx_row(5, "22/09/2026", "10", "5", "16", "1", "0", "1"),       # components do not close
    )
    parsed = official.parse_hnx_thong_tin_tong_hop(body, symbol="SHS", exchange=official.HNX)
    reasons = [item["reason"] for item in parsed["rejected"]]
    assert reasons[0].startswith("FIELD_NOT_VN_NUMBER")
    assert "SESSION_DATE_INVALID" in reasons
    assert any(reason.startswith("FIELD_NOT_WHOLE_AFTER_UNIT_SCALING") for reason in reasons)
    assert "ROW_CELL_COUNT_UNEXPECTED" in reasons
    assert [row["row_integrity"] for row in parsed["rows"]] == ["COMPONENTS_DO_NOT_SUM_TO_TOTAL"]


def test_request_builders_are_route_specific():
    hose = official.hose_request("hpg", page=2)
    assert hose["url"].endswith("/tradingresult/HPG?pageIndex=2&pageSize=20") and hose["method"] == "GET"
    upcom = official.hnx_request("acv", exchange=official.UPCOM, rows=60)
    assert upcom["method"] == "POST" and upcom["form"]["p_market"] == "UC" and upcom["form"]["p_record_on_page"] == "60"
    assert official.hnx_request("SHS", exchange=official.HNX)["form"]["p_market"] == "NY"
    with pytest.raises(official.OfficialTradingStatisticsError):
        official.hnx_request("HPG", exchange=official.HOSE)
    with pytest.raises(official.OfficialTradingStatisticsError):
        official.parse_response({"source": "VNSTOCK"}, b"{}")
    assert official.exchange_for_dnse_market_id("STX") == official.HNX
    assert official.exchange_for_dnse_market_id("XXX") is None
