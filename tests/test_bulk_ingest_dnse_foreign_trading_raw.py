from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import bulk_ingest_dnse_foreign_trading_raw as ingest  # noqa: E402
import dnse_foreign_trading_raw as contract  # noqa: E402
import market_data_source_authority as authority  # noqa: E402


class _Response:
    def __init__(self, body: dict, status_code: int = 200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def _record(symbol: str, board: str = "G1", time: str = "2026-08-11 14:45:00.000") -> dict:
    return {"symbol": symbol, "boardId": board, "marketId": "STO", "time": time,
            "buyVolume": 1, "sellVolume": 2, "buyTradedAmount": 100, "sellTradedAmount": 200}


def _context(symbols: list[str]) -> dict:
    return {"security_master_count": len(symbols), "symbol_exchange": {symbol: "STO" for symbol in symbols}}


class ContractTests(unittest.TestCase):
    def test_request_is_same_session_desc_with_optional_cursor(self):
        query = contract.request_query("HPG", "2026-08-11", limit=100, cursor="next")
        self.assertEqual("DESC", query["order"])
        self.assertEqual("next", query["nextPageToken"])
        self.assertLess(query["from"], query["to"])
        self.assertEqual("HPG__20260811", contract.work_unit_id("hpg", "2026-08-11"))

    def test_dynamic_universe_keeps_unknown_out_of_dataset_scope(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.parquet"
            pd.DataFrame([
                {"symbol": "AAA", "instrument_class": "EQUITY"},
                {"symbol": "ZZZ", "instrument_class": "UNKNOWN_SECURITY_GROUP"},
            ]).to_parquet(path, index=False)
            self.assertEqual(["AAA"], contract.load_applicable_symbols(path))


class IngestionTests(unittest.TestCase):
    def test_pagination_retains_each_page_and_preserves_boards(self):
        calls = []
        def get(_url, *, params, **_kwargs):
            calls.append(dict(params))
            if "nextPageToken" not in params:
                return _Response({"foreigners": [_record("HPG", "G1")], "nextPageToken": "cursor-1"})
            return _Response({"foreigners": [_record("HPG", "T1")]})
        with TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", symbols=["HPG"],
                                session_date="2026-08-11", run_id="r1", universe_context=_context(["HPG"]),
                                request_get=get, sleep=lambda _s: None)
            files = list((Path(tmp) / "data/market_raw_lake/raw/DNSE/foreign_trading/r1").glob("*.parquet"))
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(2, len(calls))
        self.assertEqual(2, len(files))
        self.assertEqual({"G1": 1, "T1": 1}, result["coverage_report"]["coverage_by_board_raw"])
        self.assertEqual(2, result["coverage_report"]["retained_raw_records"])

    def test_repeated_cursor_fails_closed_without_infinite_polling(self):
        def get(_url, *, params, **_kwargs):
            return _Response({"foreigners": [_record("HPG")], "nextPageToken": "__INITIAL__"})
        with TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", symbols=["HPG"],
                                session_date="2026-08-11", run_id="r1", universe_context=_context(["HPG"]),
                                request_get=get, sleep=lambda _s: None)
        self.assertEqual("COMPLETE_WITH_FAILURES", result["status"])
        self.assertEqual("repeated_cursor", result["manifest"]["failed_units"][0]["error_code"])

    def test_checkpoint_restart_skips_completed_symbol_and_no_duplicate_request(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = ingest.run(runtime_root=root, api_key="key", api_secret="secret", symbols=["HPG"],
                               session_date="2026-08-11", run_id="r1", universe_context=_context(["HPG"]),
                               request_get=lambda *_a, **_k: _Response({"foreigners": [_record("HPG")]}),
                               sleep=lambda _s: None)
            calls = []
            second = ingest.run(runtime_root=root, api_key="key", api_secret="secret", symbols=["HPG"],
                                session_date="2026-08-11", run_id="r2", universe_context=_context(["HPG"]),
                                request_get=lambda *_a, **_k: calls.append(1), sleep=lambda _s: None)
        self.assertEqual("COMPLETE", first["status"])
        self.assertEqual([], calls)
        self.assertEqual(["HPG__20260811"], second["manifest"]["skipped_units"])

    def test_empty_response_is_retained_and_not_rewritten_as_failure(self):
        with TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", symbols=["HPG"],
                                session_date="2026-08-11", run_id="r1", universe_context=_context(["HPG"]),
                                request_get=lambda *_a, **_k: _Response({"foreigners": []}), sleep=lambda _s: None)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(1, result["coverage_report"]["empty_successful_responses"])
        self.assertEqual(1, result["coverage_report"]["retained_raw_files"])
        self.assertEqual(0, result["coverage_report"]["retained_raw_records"])

    def test_http_failure_and_request_file_record_metrics_are_distinct(self):
        def get(url, *, params, **_kwargs):
            if "/BAD/" in url:
                return _Response({"message": "bad"}, 400)
            return _Response({"foreigners": [_record("GOOD"), _record("GOOD", "G4")]})
        with TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", symbols=["GOOD", "BAD"],
                                session_date="2026-08-11", run_id="r1", universe_context=_context(["GOOD", "BAD"]),
                                request_get=get, sleep=lambda _s: None)
        coverage = result["coverage_report"]
        self.assertEqual(1, coverage["successful_work_units"])
        self.assertEqual(1, coverage["failed_work_units"])
        self.assertEqual(1, coverage["retained_raw_files"])
        self.assertEqual(2, coverage["retained_raw_records"])

    def test_raw_identity_keeps_request_and_authority_is_not_changed(self):
        response = {"body": {"foreigners": [_record("HPG", "G4")]}, "endpoint": "/price/HPG/foreign-trading",
                    "query_sent": {"order": "DESC"}, "http_status": 200, "elapsed_ms": 1,
                    "provider_interface_version": "v"}
        raw = contract.observation(symbol="HPG", session_date="2026-08-11", response=response, cursor=None,
                                  page_index=0, run_id="r", run_scope_id="scope", page_unit="unit",
                                  records=response["body"]["foreigners"])
        self.assertIn('"page_index":0', raw.request_identity)
        self.assertEqual(["G4"], raw.provenance["returned_board_ids"])
        self.assertEqual("PRODUCTION_ENABLED_HPG_VNM_QNS", authority.DNSE_FOREIGN_FLOW_VALUE_AUTHORITY)
        self.assertEqual(100, raw.raw_payload["foreigners"][0]["buyTradedAmount"])

    def test_manifest_never_serializes_credentials(self):
        with TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), api_key="secret-key", api_secret="secret-value", symbols=["HPG"],
                                session_date="2026-08-11", run_id="r1", universe_context=_context(["HPG"]),
                                request_get=lambda *_a, **_k: _Response({"foreigners": [_record("HPG")]}),
                                sleep=lambda _s: None)
        dumped = json.dumps(result, default=str)
        self.assertNotIn("secret-key", dumped)
        self.assertNotIn("secret-value", dumped)


if __name__ == "__main__":
    unittest.main()
