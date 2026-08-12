from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from discover_market_universe import CREDENTIAL_INJECTION_REQUIRED, main, run  # noqa: E402

import market_raw_lake as lake  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _instrument(symbol, market_id="STO"):
    return {"symbol": symbol, "securityGroupId": "ST", "marketId": market_id,
            "name": f"Company {symbol}", "shortName": symbol, "listedDate": "2020-01-01",
            "symbolType": "", "indexName": None}


class RunTests(unittest.TestCase):
    def test_single_page_run_writes_snapshot_manifest_and_raw_page(self):
        payload = {"data": [_instrument("HPG"), _instrument("VNM"), _instrument("QNS", "UPX")],
                   "page": 1, "pageSize": 100, "total": 3}
        with TemporaryDirectory() as tmp:
            result = run(runtime_root=Path(tmp), api_key="k", api_secret="s", page_size=100,
                        max_pages=5, run_id="test-run-1",
                        request_get=lambda *_a, **_k: _FakeResponse(200, payload))
            self.assertEqual("COMPLETE", result["status"])
            self.assertEqual(3, len(result["records"]))
            self.assertTrue(Path(result["snapshot_path"]).exists())
            self.assertTrue(Path(result["manifest_path"]).exists())
            self.assertEqual(1, result["raw_pages_written"])

            raw_dir = lake.raw_run_dir(tmp, "DNSE", "instruments", "test-run-1")
            raw_files = list(raw_dir.glob("*.parquet"))
            self.assertEqual(1, len(raw_files))

    def test_manifest_file_matches_returned_manifest(self):
        payload = {"data": [_instrument("HPG")], "page": 1, "pageSize": 100, "total": 1}
        with TemporaryDirectory() as tmp:
            result = run(runtime_root=Path(tmp), api_key="k", api_secret="s", page_size=100,
                        max_pages=5, run_id="test-run-1",
                        request_get=lambda *_a, **_k: _FakeResponse(200, payload))
            on_disk = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(result["manifest"], on_disk)

    def test_rerunning_same_run_id_is_idempotent_for_raw_pages(self):
        payload = {"data": [_instrument("HPG")], "page": 1, "pageSize": 100, "total": 1}
        with TemporaryDirectory() as tmp:
            getter = lambda *_a, **_k: _FakeResponse(200, payload)
            first = run(runtime_root=Path(tmp), api_key="k", api_secret="s", page_size=100,
                       max_pages=5, run_id="same-run", request_get=getter)
            second = run(runtime_root=Path(tmp), api_key="k", api_secret="s", page_size=100,
                        max_pages=5, run_id="same-run", request_get=getter)
            self.assertEqual(1, first["raw_pages_written"])
            self.assertEqual(0, second["raw_pages_written"])
            self.assertEqual(1, second["raw_pages_already_present"])

    def test_no_hardcoded_ticker_list_multi_page_sweep(self):
        symbols = [f"SYM{i:04d}" for i in range(150)]

        def fake_get(url, *, params, headers, timeout):
            page = int(params["page"])
            start = (page - 1) * 100
            chunk = symbols[start:start + 100]
            return _FakeResponse(200, {"data": [_instrument(s) for s in chunk], "page": page,
                                       "pageSize": 100, "total": 150})

        with TemporaryDirectory() as tmp:
            result = run(runtime_root=Path(tmp), api_key="k", api_secret="s", page_size=100,
                        max_pages=10, run_id="sweep-run", request_get=fake_get)
            self.assertEqual(150, len(result["records"]))
            self.assertEqual(2, result["raw_pages_written"])


class DryRunTests(unittest.TestCase):
    def test_dry_run_makes_no_request_and_needs_no_credentials(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get"
        ) as request:
            self.assertEqual(0, main([]))
        request.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual({"page": 1, "limit": 100}, payload["first_page_query"])


class LiveModeCredentialTests(unittest.TestCase):
    def test_live_without_credentials_prints_sentinel_and_exits_2(self):
        output = io.StringIO()
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get"
        ) as request:
            exit_code = main(["--live", "--secrets-file", str(Path(tmp) / "does-not-exist.env")])
        self.assertEqual(2, exit_code)
        request.assert_not_called()
        self.assertIn(CREDENTIAL_INJECTION_REQUIRED, output.getvalue())

    def test_live_with_env_credentials_runs_end_to_end(self):
        payload = {"data": [_instrument("HPG")], "page": 1, "pageSize": 100, "total": 1}
        output = io.StringIO()
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get",
            side_effect=lambda *_a, **_k: _FakeResponse(200, payload),
        ):
            exit_code = main(["--live", "--runtime-root", tmp, "--run-id", "cli-run-1",
                             "--secrets-file", str(Path(tmp) / "does-not-exist.env")])
            self.assertEqual(0, exit_code)
            self.assertIn("discovered_count=1", output.getvalue())
            snapshot_dir = Path(tmp) / "data" / "market_raw_lake" / "universe"
            self.assertTrue(any(snapshot_dir.glob("*.parquet")))


if __name__ == "__main__":
    unittest.main()
