from __future__ import annotations

from pathlib import Path

import current_foreign_flow_positioning_bridge as bridge
import current_foreign_flow_retention as retention
from dnse_foreign_flow_capability import normalize_record

SESSION = "2026-09-18"


def test_bridge_supplies_only_current_qualified_flow_dimension(tmp_path):
    fresh = normalize_record({"symbol": "HPG", "time": f"{SESSION} 14:45:00",
                              "totalBuyTradedAmount": 100, "totalSellTradedAmount": 40},
                             source_endpoint="/price/HPG/foreign-trading")
    retention.write_exact_value_observation(tmp_path, "HPG", fresh)

    result = bridge.build_from_store(runtime_root=tmp_path, session=SESSION, tickers=["HPG", "VNM"])
    assert result["bridge_source_ticker_count"] == 1
    artifact = result["flow_positioning_artifact"]
    hpg = artifact["records"]["HPG"]
    assert hpg["foreign_flow"]["status"] == "AVAILABLE"
    assert hpg["foreign_flow"]["source"] == "DNSE"
    assert hpg["foreign_flow"]["state"] == "NET_FOREIGN_BUY"
    assert hpg["foreign_room"]["status"] != "AVAILABLE"  # never fabricated
    vnm = artifact["records"]["VNM"]
    assert vnm["foreign_flow"]["status"] != "AVAILABLE"  # no retained flow for VNM: absent, not zero


def test_bridge_ignores_stale_session(tmp_path):
    stale = normalize_record({"symbol": "HPG", "time": "2026-09-10 14:45:00",
                              "totalBuyTradedAmount": 100, "totalSellTradedAmount": 40},
                             source_endpoint="/price/HPG/foreign-trading")
    retention.write_exact_value_observation(tmp_path, "HPG", stale)
    result = bridge.build_from_store(runtime_root=tmp_path, session=SESSION, tickers=["HPG"])
    assert result["bridge_source_ticker_count"] == 0
