import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import requests

import vn_stock_pipeline as pipeline


def raw_bar(symbol="VNINDEX", date="2026-07-18", volume=100):
    del symbol
    return pd.DataFrame(
        {
            "time": [date],
            "open": [1200.0],
            "high": [1210.0],
            "low": [1190.0],
            "close": [1205.0],
            "volume": [volume],
        }
    )


def normalized_bar(symbol="VNINDEX", date="2026-07-18", volume=100):
    return pipeline.normalize(raw_bar(symbol, date, volume), symbol, "VCI")


def transient(kind="read_timeout", status=None, retry_after=None):
    return pipeline.TransientRequestError(
        kind,
        "https://provider.example/history",
        0.01,
        status_code=status,
        retry_after=retry_after,
    )


def permanent(status):
    return pipeline.PermanentRequestError(
        "http_status",
        "https://provider.example/history",
        0.01,
        status_code=status,
    )


class FakeResponse:
    def __init__(self, status_code=200, data=None, headers=None):
        self.status_code = status_code
        self._data = {} if data is None else data
        self.headers = {} if headers is None else headers

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FetchRetryTests(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch.object(pipeline.time, "sleep").start()
        self.jitter = mock.patch.object(pipeline.random, "uniform", return_value=0).start()
        self.addCleanup(mock.patch.stopall)

    def quote_with_effects(self, effects):
        provider = mock.Mock()
        provider.history.side_effect = effects
        return mock.patch.object(pipeline, "_quote", return_value=provider), provider

    def test_immediate_success_has_no_retry(self):
        quote_patch, provider = self.quote_with_effects([raw_bar()])
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("success", outcome.status)
        self.assertEqual(1, provider.history.call_count)
        self.sleep.assert_not_called()

    def test_connect_timeout_retries_then_succeeds(self):
        quote_patch, provider = self.quote_with_effects(
            [transient("connect_timeout"), raw_bar()]
        )
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("success", outcome.status)
        self.assertEqual(2, provider.history.call_count)
        self.sleep.assert_called_once_with(1.0)

    def test_read_timeout_retries_then_succeeds(self):
        quote_patch, provider = self.quote_with_effects(
            [transient("read_timeout"), raw_bar()]
        )
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("success", outcome.status)
        self.assertEqual(2, provider.history.call_count)

    def test_exhausted_transient_attempts_fail_clearly(self):
        effects = [transient(), transient(), transient(), transient()]
        quote_patch, provider = self.quote_with_effects(effects)
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("failed", outcome.status)
        self.assertTrue(outcome.transient_failure)
        self.assertEqual(4, provider.history.call_count)
        self.assertTrue(all("read_timeout" in item for item in outcome.errors))

    def test_transient_primary_plus_permanent_failover_counts_toward_budget(self):
        quote_patch, _ = self.quote_with_effects(
            [transient(), transient(), permanent(403)]
        )
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("failed", outcome.status)
        self.assertTrue(outcome.transient_failure)

    def test_429_honors_bounded_retry_after(self):
        quote_patch, _ = self.quote_with_effects(
            [transient("http_status", 429, retry_after=99), raw_bar()]
        )
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("success", outcome.status)
        self.sleep.assert_called_once_with(pipeline.RETRY_AFTER_MAX)

    def test_500_502_503_are_retried(self):
        for status in (500, 502, 503):
            with self.subTest(status=status):
                self.sleep.reset_mock()
                quote_patch, provider = self.quote_with_effects(
                    [transient("http_status", status), raw_bar()]
                )
                with quote_patch:
                    outcome = pipeline.fetch_one(
                        "VNINDEX", "2026-07-17", "2026-07-18"
                    )
                self.assertEqual("success", outcome.status)
                self.assertEqual(2, provider.history.call_count)
                self.sleep.assert_called_once()

    def test_400_401_403_do_not_retry_within_provider(self):
        for status in (400, 401, 403):
            with self.subTest(status=status):
                quote_patch, provider = self.quote_with_effects(
                    [permanent(status), permanent(status)]
                )
                with quote_patch:
                    outcome = pipeline.fetch_one(
                        "VNINDEX", "2026-07-17", "2026-07-18"
                    )
                self.assertEqual("failed", outcome.status)
                self.assertFalse(outcome.transient_failure)
                self.assertEqual(2, provider.history.call_count)

    def test_empty_from_both_sources_is_not_failure(self):
        quote_patch, provider = self.quote_with_effects(
            [pd.DataFrame(), pd.DataFrame()]
        )
        with quote_patch:
            outcome = pipeline.fetch_one("VNINDEX", "2026-07-17", "2026-07-18")
        self.assertEqual("empty", outcome.status)
        self.assertEqual(2, provider.history.call_count)


class TransportTests(unittest.TestCase):
    @mock.patch.object(pipeline.requests, "get")
    def test_connect_and_read_timeouts_are_classified(self, get):
        for error, expected in (
            (requests.exceptions.ConnectTimeout(), "connect_timeout"),
            (requests.exceptions.ReadTimeout(), "read_timeout"),
        ):
            with self.subTest(expected=expected):
                get.side_effect = error
                with self.assertRaises(pipeline.TransientRequestError) as raised:
                    pipeline._bounded_send_request_direct(
                        "https://example.test/path?token=secret", {}
                    )
                self.assertEqual(expected, raised.exception.kind)
                self.assertEqual("https://example.test/path", raised.exception.endpoint)

    @mock.patch.object(pipeline.requests, "get")
    def test_transport_uses_connect_and_read_timeout_pair(self, get):
        get.return_value = FakeResponse(data={"ok": True})
        result = pipeline._bounded_send_request_direct("https://example.test/path", {})
        self.assertEqual({"ok": True}, result)
        self.assertEqual(
            (pipeline.CONNECT_TIMEOUT, pipeline.READ_TIMEOUT),
            get.call_args.kwargs["timeout"],
        )

    @mock.patch.object(pipeline.requests, "get")
    def test_http_status_classification_and_retry_after(self, get):
        get.return_value = FakeResponse(429, headers={"Retry-After": "7"})
        with self.assertRaises(pipeline.TransientRequestError) as raised:
            pipeline._bounded_send_request_direct("https://example.test/path", {})
        self.assertEqual(429, raised.exception.status_code)
        self.assertEqual(7.0, raised.exception.retry_after)

        for status in (400, 401, 403):
            with self.subTest(status=status):
                get.return_value = FakeResponse(status)
                with self.assertRaises(pipeline.PermanentRequestError):
                    pipeline._bounded_send_request_direct(
                        "https://example.test/path", {}
                    )

    def test_log_does_not_expose_query_or_secret(self):
        error = pipeline.TransientRequestError(
            "read_timeout",
            pipeline._safe_endpoint(
                "https://user:password@example.test/history?token=TOPSECRET&account=private"
            ),
            0.1,
        )
        output = io.StringIO()
        with redirect_stdout(output):
            pipeline._request_log("AAA", "VCI", 1, "failed", 0.1, error)
        rendered = output.getvalue()
        self.assertNotIn("TOPSECRET", rendered)
        self.assertNotIn("password", rendered)
        self.assertNotIn("account", rendered)
        self.assertNotIn("?", rendered)


class DatabaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.stdout_patch = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.stdout_patch.start()
        self.addCleanup(self.stdout_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.db_patch = mock.patch.object(pipeline, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        with closing(sqlite3.connect(self.db_path)) as conn:
            pipeline.init_db(conn)

    def seed(self, ticker="VNINDEX", date="2026-07-17", volume=10):
        with closing(sqlite3.connect(self.db_path)) as conn:
            pipeline.upsert(conn, normalized_bar(ticker, date, volume))

    def rows(self, ticker="VNINDEX"):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT date, volume FROM ohlcv WHERE ticker=? ORDER BY date", (ticker,)
            ).fetchall()

    def test_empty_or_invalid_result_does_not_overwrite_existing_row(self):
        self.seed(volume=77)
        before = self.rows()
        with mock.patch.object(pipeline, "get_universe", return_value=["VNINDEX"]), mock.patch.object(
            pipeline, "fetch_one", return_value=pipeline.FetchOutcome("empty")
        ), mock.patch.object(pipeline.time, "sleep"):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_SUCCESS, code)
        self.assertEqual(before, self.rows())

        invalid = pipeline.FetchOutcome(
            "failed", errors=["VCI:invalid_schema"], transient_failure=False
        )
        with mock.patch.object(pipeline, "get_universe", return_value=["VNINDEX"]), mock.patch.object(
            pipeline, "fetch_one", return_value=invalid
        ), mock.patch.object(pipeline.time, "sleep"):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_FAILURE, code)
        self.assertEqual(before, self.rows())

    def test_network_wait_occurs_without_open_database_transaction(self):
        self.seed()

        def assert_database_is_writable(*_args):
            probe = sqlite3.connect(self.db_path, timeout=0.1)
            try:
                probe.execute("BEGIN IMMEDIATE")
                probe.execute(
                    "INSERT OR REPLACE INTO meta VALUES(?,?,?,?)",
                    ("PROBE", "done", 0, "now"),
                )
                probe.rollback()
            finally:
                probe.close()
            return pipeline.FetchOutcome(
                "failed", errors=["VCI:read_timeout"], transient_failure=True
            )

        with mock.patch.object(pipeline, "get_universe", return_value=["VNINDEX"]), mock.patch.object(
            pipeline, "fetch_one", side_effect=assert_database_is_writable
        ), mock.patch.object(pipeline.time, "sleep"):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_FAILURE, code)

    def test_rerun_is_idempotent_and_does_not_duplicate(self):
        frame = normalized_bar(volume=123)
        with closing(sqlite3.connect(self.db_path)) as conn:
            pipeline.upsert(conn, frame)
            pipeline.upsert(conn, frame)
            count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        self.assertEqual(1, count)

    def test_index_volume_is_replaced_not_accumulated(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            for ticker in ("VNINDEX", "HNXINDEX"):
                with self.subTest(ticker=ticker):
                    pipeline.upsert(conn, normalized_bar(ticker, volume=100))
                    pipeline.upsert(conn, normalized_bar(ticker, volume=125))
                    volume = conn.execute(
                        "SELECT volume FROM ohlcv WHERE ticker=?", (ticker,)
                    ).fetchone()[0]
                    self.assertEqual(125, volume)

    def test_committed_batch_survives_next_ticker_failure(self):
        self.seed("AAA", volume=10)
        self.seed("BBB", volume=20)
        outcomes = [
            pipeline.FetchOutcome(
                "success", data=normalized_bar("AAA", "2026-07-18", 30)
            ),
            pipeline.FetchOutcome(
                "failed", errors=["VCI:read_timeout"], transient_failure=True
            ),
        ]
        with mock.patch.object(pipeline, "get_universe", return_value=["AAA", "BBB"]), mock.patch.object(
            pipeline, "fetch_one", side_effect=outcomes
        ), mock.patch.object(pipeline.time, "sleep"):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_PARTIAL, code)
        self.assertIn(("2026-07-18", 30), self.rows("AAA"))
        self.assertEqual([("2026-07-17", 20)], self.rows("BBB"))

    def test_source_circuit_breaker_stops_after_budget(self):
        for ticker in ("AAA", "BBB", "CCC", "DDD"):
            self.seed(ticker)
        failure = pipeline.FetchOutcome(
            "failed", errors=["VCI:read_timeout"], transient_failure=True
        )
        fetch = mock.Mock(return_value=failure)
        with mock.patch.object(
            pipeline, "get_universe", return_value=["AAA", "BBB", "CCC", "DDD"]
        ), mock.patch.object(pipeline, "fetch_one", fetch), mock.patch.object(
            pipeline.time, "sleep"
        ):
            code = pipeline.cmd_update()
        self.assertEqual(pipeline.EXIT_SOURCE_UNAVAILABLE, code)
        self.assertEqual(pipeline.SOURCE_FAILURE_BUDGET, fetch.call_count)


class ExitCodeTests(unittest.TestCase):
    def test_success_partial_and_failure_exit_codes(self):
        self.assertEqual(pipeline.EXIT_SUCCESS, pipeline._result_exit_code(2, 0))
        self.assertEqual(pipeline.EXIT_PARTIAL, pipeline._result_exit_code(1, 1))
        self.assertEqual(pipeline.EXIT_FAILURE, pipeline._result_exit_code(0, 1))
        self.assertEqual(
            pipeline.EXIT_SOURCE_UNAVAILABLE,
            pipeline._result_exit_code(1, 3, source_unavailable=True),
        )

    def test_main_propagates_command_exit_code(self):
        with mock.patch.dict(pipeline.CMDS, {"update": mock.Mock(return_value=2)}):
            self.assertEqual(2, pipeline.main(["update"]))
        self.assertEqual(pipeline.EXIT_FAILURE, pipeline.main(["not-a-command"]))


if __name__ == "__main__":
    unittest.main()
