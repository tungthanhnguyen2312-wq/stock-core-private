from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from dnse_fhsc_volume_basis import parse_fhsc_trading_history
from historical_matched_traded_value_authority import (
    reconcile_fhsc_anchor,
    summarize_complete_trade_session,
)
from historical_matched_trading_value_authority import (
    adtv20_matched_value,
    build_historical_matched_trading_value_authority,
)
from tools.run_fhsc_historical_matched_value_coverage_scaleout import (
    fetch_fhsc_symbol,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fhsc_trading_history_parsing_preserves_composition_fields():
    raw_json = json.dumps({
        "error_code": 0,
        "message": "success",
        "data": {
            "symbol": "HPG",
            "resolution": "1D",
            "data": [
                {
                    "date": "2026-08-11",
                    "total": {"volume": 2000, "value": 40000000},
                    "matched": {"volume": 1500, "value": 30000000},
                    "put_through": {"volume": 500, "value": 10000000},
                }
            ]
        }
    }).encode("utf-8")
    parsed = parse_fhsc_trading_history(raw_json, instrument="HPG")
    assert parsed["parse_status"] == "PARSED"
    rows = parsed["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["session"] == "2026-08-11"
    assert row["matched_volume"] == 1500
    assert row["matched_value"] == 30000000
    assert row["put_through_volume"] == 500
    assert row["put_through_value"] == 10000000
    assert row["total_volume"] == 2000
    assert row["total_value"] == 40000000
    assert row["retained_arithmetic_identity"] is True
    assert row["retained_value_arithmetic_identity"] is True


def test_reconcile_fhsc_anchor_exact_and_conflict():
    candidate = {
        "ticker": "HPG",
        "session": "2026-08-11",
        "qualification_status": "CANDIDATE_PENDING_FHSC_ANCHOR",
        "g1_share_quantity": 1500,
        "matched_value_vnd": 30000000,
    }
    anchor_exact = {
        "fhsc_identity_retained_exact": True,
        "fhsc_matched_volume": 1500,
        "fhsc_matched_value": 30000000,
    }
    recon_exact = reconcile_fhsc_anchor(candidate, anchor_exact)
    assert recon_exact["status"] == "EXACT"
    assert recon_exact["g1_to_fhsc_matched_volume"] == "EXACT"
    assert recon_exact["g1_to_fhsc_matched_value"] == "EXACT"

    anchor_conflict = {
        "fhsc_identity_retained_exact": True,
        "fhsc_matched_volume": 1500,
        "fhsc_matched_value": 31000000,
    }
    recon_conflict = reconcile_fhsc_anchor(candidate, anchor_conflict)
    assert recon_conflict["status"] == "CONFLICT"
    assert recon_conflict["g1_to_fhsc_matched_value"] == "CONFLICT"


def test_adtv20_ready_at_twenty_sessions():
    rows = [
        {
            "ticker": "HPG",
            "session": f"2026-07-{day:02d}",
            "qualification_status": "MATCHED_VALUE_QUALIFIED",
            "matched_value_vnd": 100_000_000,
        }
        for day in range(1, 21)
    ]
    adtv = adtv20_matched_value(rows)
    assert adtv["HPG"]["status"] == "ADTV20_READY"
    assert adtv["HPG"]["observed_sessions"] == 20
    assert adtv["HPG"]["adtv20_matched_value_vnd"] == 100_000_000
    assert adtv["HPG"]["calendar_day_imputation"] is False


def test_fetch_fhsc_symbol_cache_hit():
    with tempfile.TemporaryDirectory() as tmp:
        raw_dir = Path(tmp) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"data": {"symbol": "TEST", "data": []}}).encode("utf-8")
        test_file = raw_dir / "TEST_stock_trading_history_1234567890abcdef.json"
        test_file.write_bytes(content)

        rec = fetch_fhsc_symbol("TEST", "dummy_key", raw_dir=raw_dir)
        assert rec["successful"] is True
        assert rec["source_cache_hit"] is True
        assert rec["http_status"] == 200
