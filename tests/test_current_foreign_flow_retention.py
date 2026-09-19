from __future__ import annotations
import json
from pathlib import Path
import pytest
import current_foreign_flow_retention as retention

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-18"

def _page(**extra):
    row = {"symbol":"HPG","time":SESSION+" 14:45:00","totalBuyTradedAmount":100,"totalSellTradedAmount":40,"totalBuyVolume":999,"totalSellVolume":500,"foreignerBuyPossibleQuantity":9}
    value = {"instrument":"HPG","source_event_time":SESSION,"endpoint":"/price/HPG/foreign-trading","body":{"foreigners":[row]}}
    value.update(extra); return value

def test_real_manifest_is_deterministic_and_has_eleven_eligible_tickers():
    first = retention.build_manifest_from_root(ROOT, SESSION); second = retention.build_manifest_from_root(ROOT, SESSION)
    assert first == second and first["cohort_count"] == 11
    assert first["eligible_tickers"] == sorted(first["eligible_tickers"])
    assert set(first["eligible_tickers"]) == {"EVF","FPT","HPG","NVL","PAN","PNJ","POW","PVD","QNS","SSI","VNM"}
    assert first["authority_boundary"]["no_velocity_price_or_ranking_input"] is True

def test_exact_raw_page_reuses_value_normalization_without_volume_or_room():
    result = retention.normalize_exact_raw_page(ticker="HPG", reference_session=SESSION, page=_page())
    assert result["foreign_buy_value"] == 100 and result["foreign_net_value"] == 60
    store_shape = {"foreign_buy_value_vnd": result["foreign_buy_value"], "foreign_sell_value_vnd": result["foreign_sell_value"]}
    assert "volume" not in json.dumps(store_shape).lower() and "room" not in json.dumps(store_shape).lower()


def _sequence_page(index, *, token=None, cursor=None, session=SESSION, ticker="HPG", buy=100):
    page = _page(raw_payload={
        "foreigners": [{"symbol": ticker, "time": session + f" 14:{45-index:02d}:00",
                        "totalBuyTradedAmount": buy, "totalSellTradedAmount": 40}],
        **({"nextPageToken": token} if token else {}),
    })
    page["provenance"] = {"endpoint": f"/price/{ticker}/foreign-trading", "page_index": index,
                          "page_cursor": cursor, "request_parameters": {"from": 1, "to": 2,
                          "limit": 100, "order": "DESC", **({"nextPageToken": cursor} if cursor else {})}}
    page["instrument"] = ticker
    page["source_event_time"] = session
    return page


def test_complete_paginated_sequence_selects_newest_exact_session_value():
    result = retention.normalize_exact_raw_sequence(
        ticker="HPG", reference_session=SESSION,
        pages=[_sequence_page(0, token="next", buy=100), _sequence_page(1, cursor="next", buy=50)],
    )
    assert result["foreign_buy_value"] == 100 and result["foreign_net_value"] == 60


@pytest.mark.parametrize("pages,error", [
    ([_sequence_page(0, token="next")], "PAGINATION_NOT_COMPLETE"),
    ([_sequence_page(0, token="next"), _sequence_page(2, cursor="next")], "PAGE_INDEX_GAP"),
    ([_sequence_page(0, token="next"), _sequence_page(1, cursor="wrong")], "CURSOR_LINEAGE_BROKEN"),
    ([_sequence_page(0, ticker="VNM")], "TICKER_OR_REQUESTED_SESSION_MISMATCH"),
    ([_sequence_page(0, session="2026-09-17")], "TICKER_OR_REQUESTED_SESSION_MISMATCH"),
])
def test_paginated_sequence_fails_closed_on_invalid_lineage_or_scope(pages, error):
    with pytest.raises(ValueError, match=error):
        retention.normalize_exact_raw_sequence(ticker="HPG", reference_session=SESSION, pages=pages)


def test_paginated_sequence_rejects_conflicting_latest_exact_session_records():
    second = _sequence_page(1, cursor="next", buy=101)
    second["raw_payload"]["foreigners"][0]["time"] = SESSION + " 14:45:00"
    with pytest.raises(ValueError, match="CONFLICTING_EXACT_SESSION_RECORDS"):
        retention.normalize_exact_raw_sequence(ticker="HPG", reference_session=SESSION,
                                               pages=[_sequence_page(0, token="next", buy=100), second])

@pytest.mark.parametrize("change", [{"instrument":"VNM"}, {"source_event_time":"2026-09-17"}, {"endpoint":"/price/VNM/foreign-trading"}, {"body":{"foreigners":[]}}, {"body":{"foreigners":[{"symbol":"HPG","time":SESSION+" 14:45:00","totalBuyTradedAmount":1,"totalSellTradedAmount":1}],"nextPageToken":"more"}}])
def test_raw_adapter_fails_closed_on_wrong_scope_or_malformed_page(change):
    with pytest.raises((ValueError, Exception)):
        retention.normalize_exact_raw_page(ticker="HPG", reference_session=SESSION, page=_page(**change))

def test_conflicting_exact_store_write_fails_closed_and_same_write_is_idempotent(tmp_path):
    observation = retention.normalize_exact_raw_page(ticker="HPG", reference_session=SESSION, page=_page())
    retention.write_exact_value_observation(tmp_path, "HPG", observation)
    retention.write_exact_value_observation(tmp_path, "HPG", observation)
    stored = json.loads((tmp_path / "data/dnse-foreign-flow/observations/HPG.json").read_text())
    retained = stored["observations"][0]
    assert not any("volume" in key or "room" in key for key in retained)
    assert "event_scoped" not in retained["provenance"]
    changed = dict(observation); changed["foreign_buy_value"] = 101
    with pytest.raises(ValueError, match="CONFLICTING"):
        retention.write_exact_value_observation(tmp_path, "HPG", changed)
