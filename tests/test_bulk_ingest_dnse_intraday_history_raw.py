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

    def test_rate_limit_retry_honors_capped_retry_after_then_succeeds(self):
        class Response:
            def __init__(self, status, body=None, headers=None):
                self.status_code, self._body, self.headers = status, body or {}, headers or {}
            def json(self): return self._body
        responses = [Response(429, headers={"Retry-After": "9"}), Response(200, {"trades": []})]
        sleeps = []
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                session_date="2026-08-11", run_id="r", api_key="k", api_secret="s",
                pagination_contract_proven=True, max_retries=2, backoff_seconds=1, max_backoff_seconds=3,
                request_delay_seconds=0, sleep=sleeps.append,
                request_get=lambda *_a, **_k: responses.pop(0))
        self.assertEqual([3], sleeps)
        self.assertEqual(1, result["manifest"]["retry_attempts"])
        self.assertEqual(1, result["manifest"]["retry_after_honored"])
        self.assertEqual(1, result["manifest"]["successful_unit_count"])

    def test_transient_failures_retry_then_exhaust_without_leaking_transport_detail(self):
        for exc in (ConnectionError("host=example"), TimeoutError("secret=not-retained")):
            with self.subTest(type=type(exc).__name__), tempfile.TemporaryDirectory() as tmp:
                calls, sleeps = [], []
                def get(*_a, **_k):
                    calls.append(1)
                    raise exc
                result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                    session_date="2026-08-11", run_id="r", api_key="k", api_secret="s",
                    pagination_contract_proven=True, max_retries=1, backoff_seconds=1,
                    request_delay_seconds=0, sleep=sleeps.append, request_get=get)
                self.assertEqual(2, len(calls))
                self.assertEqual([1], sleeps)
                self.assertEqual(1, result["manifest"]["retry_exhaustion"])
                self.assertEqual(2, result["manifest"]["transport_failures"])
                self.assertTrue(result["manifest"]["failed_units"][0]["error_code"].startswith("request_failed_"))

    def test_all_429s_are_bounded_and_auth_and_nonretry_failures_are_not_retried(self):
        class Response:
            def __init__(self, status): self.status_code, self.headers = status, {}
            def json(self): return {"message": "failure"}
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            exhausted = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["HPG"],
                session_date="2026-08-11", run_id="rate", api_key="k", api_secret="s",
                pagination_contract_proven=True, max_retries=2, request_delay_seconds=0, sleep=lambda _s: None,
                request_get=lambda *_a, **_k: (calls.append(1) or Response(429)))
            self.assertEqual(3, len(calls))
            self.assertEqual(1, exhausted["manifest"]["retry_exhaustion"])
        for status, expected_calls in ((401, 1), (400, 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                calls = []
                result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["AAA", "BBB"],
                    session_date="2026-08-11", run_id=f"{status}", api_key="k", api_secret="s",
                    pagination_contract_proven=True, max_retries=3, request_delay_seconds=0,
                    request_get=lambda *_a, **_k: (calls.append(1) or Response(status)))
                self.assertEqual(expected_calls, len(calls))
                self.assertEqual(0, result["manifest"]["retry_attempts"])

    def test_successes_are_reused_but_prior_retryable_failures_reopen(self):
        class Response:
            def __init__(self, status, body=None): self.status_code, self._body, self.headers = status, body or {}, {}
            def json(self): return self._body
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="one", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: Response(200, {"trades": []}))
            second = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="two", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: self.fail("success must be reused"))
            self.assertEqual(1, second["manifest"]["reused_successes"])
            self.assertEqual(first["manifest"]["successful_units"], second["manifest"]["successful_units"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="one", api_key="k", api_secret="s", pagination_contract_proven=True, max_retries=0,
                request_delay_seconds=0, request_get=lambda *_a, **_k: Response(429))
            retried = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="two", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: Response(200, {"trades": []}))
            self.assertEqual(1, failed["manifest"]["failed_unit_count"])
            self.assertEqual(1, retried["manifest"]["retryable_failed_retried"])
            self.assertEqual(1, retried["manifest"]["successful_unit_count"])

    def test_nonretryable_failure_stays_skipped_and_pacing_is_global(self):
        class Response:
            def __init__(self, status, body=None): self.status_code, self._body, self.headers = status, body or {}, {}
            def json(self): return self._body
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="one", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: Response(400))
            result = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="two", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: self.fail("nonretryable failure must not reopen"))
            self.assertEqual(1, result["manifest"]["skipped_unit_count"])
        with tempfile.TemporaryDirectory() as tmp:
            sleeps = []
            result = ingest.run(runtime_root=Path(tmp), dataset="trades_history", symbols=["AAA", "BBB"],
                session_date="2026-08-11", run_id="pace", api_key="k", api_secret="s", pagination_contract_proven=True,
                request_delay_seconds=0.25, sleep=sleeps.append,
                request_get=lambda *_a, **_k: Response(200, {"trades": []}))
            self.assertEqual([0.25], sleeps)
            self.assertEqual(2, result["manifest"]["http_request_attempts"])

    def test_pagination_resume_uses_only_the_saved_next_cursor_and_original_raw_run(self):
        class Response:
            status_code = 200
            headers = {}
            def __init__(self, body): self.body = body
            def json(self): return self.body
        requests = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def first(_url, *, params, **_kwargs):
                requests.append(params.get("nextPageToken"))
                if params.get("nextPageToken") is None:
                    return Response({"trades": [{"id": 1}], "nextPageToken": "cursor-2"})
                raise ConnectionError("temporary")
            ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="initial", api_key="k", api_secret="s", pagination_contract_proven=True, max_retries=0,
                request_delay_seconds=0, request_get=first)
            resumed = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="new-invocation", api_key="k", api_secret="s", pagination_contract_proven=True,
                request_delay_seconds=0,
                request_get=lambda _url, *, params, **_kwargs: (requests.append(params.get("nextPageToken")) or Response({"trades": [{"id": 2}]})))
            state = next(iter(resumed["checkpoint"]["intraday_pagination"].values()))
            self.assertEqual([None, "cursor-2", "cursor-2"], requests)
            self.assertEqual("initial", state["raw_run_id"])
            self.assertEqual(2, state["page_count"])

    def test_active_scope_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = ingest.compute_run_scope_id(dataset="trades_history", symbols=["HPG"], session_date="2026-08-11", limit=100)
            path = ingest.lake.run_scope_lock_path(root, "DNSE", "trades_history", scope)
            path.parent.mkdir(parents=True)
            path.write_text(f"run_scope_id={scope}\npid={__import__('os').getpid()}\n", encoding="utf-8")
            with self.assertRaises(ingest.RunScopeLockedError):
                ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                    run_id="r", api_key="k", api_secret="s", pagination_contract_proven=True,
                    request_get=lambda *_a, **_k: self.fail("locked run must not request"))

    def test_checkpoint_interruption_adopts_exact_pending_raw_page_without_refetch(self):
        class Response:
            status_code = 200
            headers = {}
            def json(self): return {"trades": [{"id": 1}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual_save = ingest.lake.save_checkpoint
            saves = []
            def fail_after_raw(runtime_root, checkpoint):
                saves.append(checkpoint)
                if len(saves) == 2:
                    raise RuntimeError("simulated final checkpoint interruption")
                return actual_save(runtime_root, checkpoint)
            with mock.patch.object(ingest.lake, "save_checkpoint", side_effect=fail_after_raw):
                with self.assertRaisesRegex(RuntimeError, "interruption"):
                    ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                        run_id="initial", api_key="k", api_secret="s", pagination_contract_proven=True,
                        request_delay_seconds=0, request_get=lambda *_a, **_k: Response())
            resumed = ingest.run(runtime_root=root, dataset="trades_history", symbols=["HPG"], session_date="2026-08-11",
                run_id="later", api_key="k", api_secret="s", pagination_contract_proven=True, request_delay_seconds=0,
                request_get=lambda *_a, **_k: self.fail("valid pending raw page must be adopted, not refetched"))
            self.assertEqual(1, resumed["manifest"]["orphan_raw_pages_adopted"])
            self.assertEqual(0, resumed["manifest"]["orphan_raw_pages_unreferenced"])
            self.assertEqual({}, resumed["checkpoint"].get("pending_raw_pages"))


if __name__ == "__main__":
    unittest.main()
