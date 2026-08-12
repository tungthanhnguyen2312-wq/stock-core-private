from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bulk_ingest_dnse_intraday_history_raw as ingest  # noqa: E402


class IntradayCollectorTests(unittest.TestCase):
    def test_bulk_run_refuses_unproven_pagination(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ingest.PaginationContractNotReady, "not first-party proven"):
                ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                           session_date="2026-08-11", run_id="r", api_key="k", api_secret="s")

    def test_cli_dry_validation_and_live_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.parquet"
            import pandas as pd
            pd.DataFrame([{"symbol": "HPG", "instrument_class": "EQUITY"}]).to_parquet(path)
            self.assertEqual(0, ingest.main(["--dataset", "quotes_history", "--session-date", "2026-08-11", "--universe-snapshot", str(path)]))
            self.assertEqual(2, ingest.main(["--live", "--dataset", "quotes_history", "--session-date", "2026-08-11", "--universe-snapshot", str(path)]))

    def test_readiness_gate_allows_only_proven_trades_endpoint(self):
        self.assertEqual("MARKET_WIDE_ACQUISITION_READY", ingest.PAGINATION_READINESS["trades_history"])
        self.assertEqual("PARTIAL", ingest.PAGINATION_READINESS["quotes_history"])

    def test_two_page_checkpoint_and_manifest_keep_page_and_record_metrics_distinct(self):
        class Response:
            def __init__(self, body): self.body = body; self.status_code = 200
            def json(self): return self.body
        def get(_url, *, params, **_kwargs):
            if "nextPageToken" not in params:
                return Response({"trades": [{"time": "t", "x": 1}], "nextPageToken": "n"})
            return Response({"trades": [{"time": "t", "x": 2}]})
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                session_date="2026-08-11", run_id="r", api_key="k", api_secret="s",
                pagination_contract_proven=True, request_get=get)
            self.assertEqual(1, len(result["manifest"]["successful_units"]))
            self.assertEqual(2, result["manifest"]["raw_page_files"])
            self.assertEqual(2, result["manifest"]["raw_records"])

    def test_empty_quotes_is_success_and_nested_payload_not_mutated(self):
        class Response:
            status_code = 200
            def json(self): return {"quotes": []}
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), dataset="quotes_history", symbols=["HPG"],
                session_date="2026-08-11", run_id="r", api_key="k", api_secret="s",
                pagination_contract_proven=True, request_get=lambda *_a, **_k: Response())
            self.assertEqual(1, len(result["manifest"]["successful_units"]))
            self.assertEqual(0, result["manifest"]["raw_records"])

    def test_finite_page_guard_fails_closed(self):
        class Response:
            status_code = 200
            def json(self): return {"trades": [{"time": "t"}], "nextPageToken": "next"}
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                session_date="2026-08-11", run_id="r", api_key="k", api_secret="s",
                pagination_contract_proven=True, max_pages_per_work=1,
                request_get=lambda *_a, **_k: Response())
        self.assertEqual("max_pages_per_work_exceeded", result["manifest"]["failed_units"][0]["error_code"])


if __name__ == "__main__":
    unittest.main()
