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

import bulk_ingest_dnse_raw as bulk  # noqa: E402
import market_raw_lake as lake  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _ohlc_body(symbol):
    return {"symbol": symbol, "t": [1, 2, 3], "o": [1, 2, 3], "h": [1, 2, 3], "l": [1, 2, 3],
           "c": [1, 2, 3], "v": [100, 200, 300]}


class PureHelperTests(unittest.TestCase):
    def test_date_window_epoch_spans_full_days(self):
        start, end = bulk.date_window_epoch("2026-08-01", "2026-08-03")
        self.assertLess(start, end)
        self.assertEqual(int((end - start + 1) / 86400), 3)

    def test_run_scope_id_is_stable_regardless_of_symbol_order(self):
        a = bulk.compute_run_scope_id(dataset="ohlc", symbols=["HPG", "VNM"], date_from="2026-08-01",
                                      date_to="2026-08-10", resolution="1D", instrument_type="STOCK")
        b = bulk.compute_run_scope_id(dataset="ohlc", symbols=["VNM", "HPG"], date_from="2026-08-01",
                                      date_to="2026-08-10", resolution="1D", instrument_type="STOCK")
        self.assertEqual(a, b)

    def test_run_scope_id_changes_with_date_range(self):
        a = bulk.compute_run_scope_id(dataset="ohlc", symbols=["HPG"], date_from="2026-08-01",
                                      date_to="2026-08-10", resolution="1D", instrument_type="STOCK")
        b = bulk.compute_run_scope_id(dataset="ohlc", symbols=["HPG"], date_from="2026-08-02",
                                      date_to="2026-08-10", resolution="1D", instrument_type="STOCK")
        self.assertNotEqual(a, b)

    def test_stock_snapshot_selection_excludes_unknown_security_groups_without_dropping_master_context(self):
        import pandas as pd

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.parquet"
            pd.DataFrame([
                {"symbol": "AAA", "instrument_class": "EQUITY", "exchange_raw": "STO"},
                {"symbol": "ZZZ", "instrument_class": "UNKNOWN_SECURITY_GROUP", "exchange_raw": "DVX"},
            ]).to_parquet(path, engine="pyarrow", index=False)
            selected = bulk.load_symbols_from_universe_snapshot(path, instrument_type="STOCK")
            context = bulk.load_universe_context(path, selected_symbols=selected)
        self.assertEqual(["AAA"], selected)
        self.assertEqual(["AAA"], context["universe_symbols"])
        self.assertEqual(2, context["security_master_discovered_count"])
        self.assertEqual({"EQUITY": 1, "UNKNOWN_SECURITY_GROUP": 1}, context["universe_by_instrument_class"])


class RunAllSuccessTests(unittest.TestCase):
    def test_all_symbols_succeed(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append(params["symbol"])
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s",
                             symbols=["HPG", "VNM", "QNS"], date_from="2026-08-01", date_to="2026-08-10",
                             run_id="run-1", request_get=fake_get, sleep=lambda _s: None)
        self.assertEqual("COMPLETE", result["status"])
        manifest = result["manifest"]
        self.assertEqual(["HPG", "QNS", "VNM"], manifest["successful_units"])
        self.assertEqual(0, manifest["failed_unit_count"])
        self.assertEqual(3, len(calls))


class CheckpointRestartTests(unittest.TestCase):
    def test_active_scope_lock_prevents_concurrent_refetch(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append(params["symbol"])
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope_id = bulk.compute_run_scope_id(
                dataset="ohlc", symbols=["HPG"], date_from="2026-08-01", date_to="2026-08-10",
                resolution="1D", instrument_type="STOCK",
            )
            lock_path = bulk._run_scope_lock_path(root, scope_id)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("active\n", encoding="utf-8")
            with self.assertRaises(bulk.RunScopeLockedError):
                bulk.run(runtime_root=root, api_key="k", api_secret="s", symbols=["HPG"],
                         date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                         request_get=fake_get, sleep=lambda _s: None)
        self.assertEqual([], calls)

    def test_second_run_skips_already_successful_symbols(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            symbol = params["symbol"]
            calls.append(symbol)
            if symbol == "QNS":
                return _FakeResponse(500, {"message": "server error"})
            return _FakeResponse(200, _ohlc_body(symbol))

        with TemporaryDirectory() as tmp:
            first = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s",
                            symbols=["HPG", "VNM", "QNS"], date_from="2026-08-01", date_to="2026-08-10",
                            run_id="run-1", request_get=fake_get, sleep=lambda _s: None, max_retries=0)
            self.assertEqual(["HPG", "VNM"], first["manifest"]["successful_units"])
            self.assertEqual(["QNS"], [f["unit_id"] for f in first["manifest"]["failed_units"]])
            calls_after_first = len(calls)
            self.assertEqual(3, calls_after_first)

            # QNS now succeeds on the retry-run.
            def fake_get_second(url, *, params, headers, timeout):
                symbol = params["symbol"]
                calls.append(symbol)
                return _FakeResponse(200, _ohlc_body(symbol))

            second = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s",
                             symbols=["HPG", "VNM", "QNS"], date_from="2026-08-01", date_to="2026-08-10",
                             run_id="run-2", request_get=fake_get_second, sleep=lambda _s: None)
        # Only QNS should have been re-attempted; HPG/VNM were already checkpointed success.
        self.assertEqual(["QNS"], calls[calls_after_first:])
        # successful_units is the *cumulative* state of the run scope (includes
        # HPG/VNM from run-1, untouched this time); skipped_units is *this
        # invocation's* skip list -- HPG/VNM were skipped again here because the
        # checkpoint already had them, which is the correct, desired behavior.
        self.assertEqual(["HPG", "QNS", "VNM"], second["manifest"]["successful_units"])
        self.assertEqual(["HPG", "VNM"], second["manifest"]["skipped_units"])
        self.assertEqual(1, second["manifest"]["attempted_unit_count"])

    def test_a_third_identical_run_makes_zero_network_calls(self):
        def fake_get(url, *, params, headers, timeout):
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG", "VNM"],
                   date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                   request_get=fake_get, sleep=lambda _s: None)
            calls = []

            def counting_get(url, *, params, headers, timeout):
                calls.append(params["symbol"])
                return _FakeResponse(200, _ohlc_body(params["symbol"]))

            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG", "VNM"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-2",
                             request_get=counting_get, sleep=lambda _s: None)
        self.assertEqual([], calls)
        self.assertEqual(["HPG", "VNM"], result["manifest"]["skipped_units"])
        self.assertEqual(0, result["manifest"]["attempted_unit_count"])

    def test_raw_files_from_prior_run_are_preserved_not_rewritten(self):
        def fake_get(url, *, params, headers, timeout):
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            first = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG"],
                            date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                            request_get=fake_get, sleep=lambda _s: None)
            raw_path = Path(first["manifest"]["successful_units"] and
                           lake.load_checkpoint(Path(tmp), "DNSE", "ohlc",
                                               first["run_scope_id"])["units"]["HPG"]["raw_file"])
            before = raw_path.read_bytes()
            bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG"],
                   date_from="2026-08-01", date_to="2026-08-10", run_id="run-2",
                   request_get=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not be called")),
                   sleep=lambda _s: None)
            self.assertEqual(before, raw_path.read_bytes())


class RetryBackoffTests(unittest.TestCase):
    def test_transient_failure_retries_then_succeeds(self):
        attempts = {"n": 0}

        def fake_get(url, *, params, headers, timeout):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise TimeoutError("simulated timeout")
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        sleeps = []
        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                             request_get=fake_get, sleep=sleeps.append, max_retries=5,
                             backoff_seconds=1.0, request_delay_seconds=0)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(3, attempts["n"])
        self.assertEqual([1.0, 2.0], sleeps)  # exponential backoff before attempts 2 and 3

    def test_retries_exhausted_records_failure(self):
        def fake_get(url, *, params, headers, timeout):
            raise TimeoutError("always fails")

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                             request_get=fake_get, sleep=lambda _s: None, max_retries=2)
        self.assertEqual("COMPLETE_WITH_FAILURES", result["status"])
        self.assertEqual(1, len(result["manifest"]["failed_units"]))
        self.assertEqual("request_failed_TimeoutError", result["manifest"]["failed_units"][0]["error_code"])

    def test_deterministic_client_error_is_not_retried(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append(1)
            return _FakeResponse(404, {"message": "unknown symbol"})

        with TemporaryDirectory() as tmp:
            bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["ZZZZ"],
                   date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                   request_get=fake_get, sleep=lambda _s: None, max_retries=5)
        self.assertEqual(1, len(calls))


class PartialFailureTests(unittest.TestCase):
    def test_one_bad_symbol_does_not_stop_the_rest(self):
        def fake_get(url, *, params, headers, timeout):
            if params["symbol"] == "BAD":
                return _FakeResponse(404, {"message": "unknown symbol"})
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s",
                             symbols=["HPG", "BAD", "VNM"], date_from="2026-08-01", date_to="2026-08-10",
                             run_id="run-1", request_get=fake_get, sleep=lambda _s: None)
        self.assertEqual("COMPLETE_WITH_FAILURES", result["status"])
        self.assertEqual(["HPG", "VNM"], result["manifest"]["successful_units"])
        self.assertEqual(1, result["manifest"]["failed_unit_count"])


class AuthAbortTests(unittest.TestCase):
    def test_authentication_failure_aborts_remaining_symbols(self):
        # bulk.run() sorts symbols deterministically (AAA, BBB, CCC, DDD); BBB
        # is the one made to fail auth, so CCC/DDD are the ones left un-called.
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append(params["symbol"])
            if params["symbol"] == "BBB":
                return _FakeResponse(401, {"message": "unauthorized"})
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s",
                             symbols=["DDD", "BBB", "CCC", "AAA"], date_from="2026-08-01",
                             date_to="2026-08-10", run_id="run-1", request_get=fake_get,
                             sleep=lambda _s: None)
        self.assertEqual("AUTHENTICATION_FAILED_MID_RUN", result["status"])
        manifest = result["manifest"]
        self.assertEqual(["CCC", "DDD"], manifest["skipped_units"])
        self.assertEqual(["AAA"], manifest["successful_units"])
        self.assertEqual(["AAA", "BBB"], calls)  # CCC/DDD never even called

    def test_auth_aborted_symbols_are_retried_on_a_later_run_once_auth_recovers(self):
        with TemporaryDirectory() as tmp:
            def failing_get(url, *, params, headers, timeout):
                return _FakeResponse(401, {"message": "unauthorized"})

            bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG", "VNM"],
                   date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                   request_get=failing_get, sleep=lambda _s: None)

            calls = []

            def recovered_get(url, *, params, headers, timeout):
                calls.append(params["symbol"])
                return _FakeResponse(200, _ohlc_body(params["symbol"]))

            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG", "VNM"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-2",
                             request_get=recovered_get, sleep=lambda _s: None)
        self.assertEqual(["HPG", "VNM"], sorted(calls))
        self.assertEqual("COMPLETE", result["status"])


class CredentialRedactionTests(unittest.TestCase):
    def test_secret_never_appears_in_manifest_or_output(self):
        def fake_get(url, *, params, headers, timeout):
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="my-secret-api-key",
                             api_secret="my-secret-api-secret", symbols=["HPG"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                             request_get=fake_get, sleep=lambda _s: None)
        dumped = json.dumps(result, default=str)
        self.assertNotIn("my-secret-api-key", dumped)
        self.assertNotIn("my-secret-api-secret", dumped)


class CoverageReportIntegrationTests(unittest.TestCase):
    def test_coverage_report_reflects_never_requested_universe_symbols(self):
        def fake_get(url, *, params, headers, timeout):
            return _FakeResponse(200, _ohlc_body(params["symbol"]))

        with TemporaryDirectory() as tmp:
            result = bulk.run(runtime_root=Path(tmp), api_key="k", api_secret="s", symbols=["HPG"],
                             date_from="2026-08-01", date_to="2026-08-10", run_id="run-1",
                             request_get=fake_get, sleep=lambda _s: None,
                             universe_context={"universe_symbols": ["HPG", "VNM", "QNS"],
                                              "universe_by_exchange": {"STO": 3},
                                              "universe_by_instrument_class": {"EQUITY": 3}})
        coverage = result["coverage_report"]
        entry = coverage["dataset_coverage"][0]
        self.assertEqual(["QNS", "VNM"], entry["never_requested_symbols"])
        self.assertFalse(coverage["is_ticker_qualification_table"])


class DryRunTests(unittest.TestCase):
    def test_dry_run_with_symbols_prints_plan_without_network(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get"
        ) as request:
            exit_code = bulk.main(["--symbols", "HPG,VNM"])
        self.assertEqual(0, exit_code)
        request.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(2, payload["requested_unit_count"])
        self.assertEqual("1D", payload["resolution"])

    def test_missing_symbol_source_is_a_clean_error_not_a_default_ticker_list(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = bulk.main([])
        self.assertEqual(2, exit_code)
        self.assertEqual("SYMBOL_SOURCE_REQUIRED", json.loads(output.getvalue())["status"])


class LiveModeCliTests(unittest.TestCase):
    def test_live_without_credentials_exits_2(self):
        output = io.StringIO()
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get"
        ) as request:
            exit_code = bulk.main(["--live", "--symbols", "HPG",
                                  "--secrets-file", str(Path(tmp) / "nope.env")])
            self.assertEqual(2, exit_code)
            request.assert_not_called()
            self.assertIn(bulk.CREDENTIAL_INJECTION_REQUIRED, output.getvalue())

    def test_live_with_credentials_end_to_end(self):
        output = io.StringIO()
        with TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True
        ), redirect_stdout(output), patch(
            "dnse_bulk_market_data._default_request_get",
            side_effect=lambda url, *, params, headers, timeout: _FakeResponse(200, _ohlc_body(params["symbol"])),
        ):
            exit_code = bulk.main(["--live", "--symbols", "HPG,VNM", "--runtime-root", tmp,
                                  "--run-id", "cli-run-1", "--from", "2026-08-01", "--to", "2026-08-10",
                                  "--secrets-file", str(Path(tmp) / "nope.env")])
            self.assertEqual(0, exit_code)
            result = json.loads(output.getvalue())
            self.assertEqual("COMPLETE", result["status"])
            raw_dir = lake.raw_run_dir(Path(tmp), "DNSE", "ohlc", "cli-run-1")
            self.assertEqual(2, len(list(raw_dir.glob("*.parquet"))))


if __name__ == "__main__":
    unittest.main()
