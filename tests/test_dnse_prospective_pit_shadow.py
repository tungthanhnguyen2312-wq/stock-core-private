from __future__ import annotations

import json
import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dnse_prospective_pit_shadow as pit
from tools import collect_dnse_prospective_pit_shadow as collector


def payload(**changes):
    value = {
        "T": "bc", "symbol": "HPG", "resolution": "1", "time": 1780000000,
        "lastUpdated": 1780000060, "open": 22.0, "high": 22.1, "low": 21.9,
        "close": 22.05, "volume": 1000, "type": "STOCK",
    }
    value.update(changes)
    return value


def observation(**changes):
    return pit.build_observation(payload=payload(**changes), channel="ohlc_closed.1.json",
                                 message_type="bc",
                                 receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                 collector_execution_id="test-execution-1")


class CanonicalContractTests(unittest.TestCase):
    def test_hash_is_deterministic_for_key_order(self):
        self.assertEqual(pit.sha256_json({"b": 2, "a": 1}), pit.sha256_json({"a": 1, "b": 2}))

    def test_source_time_missing_is_explicit_and_not_replaced(self):
        # Build from an actually missing source field, rather than a null one.
        record = pit.build_observation(payload={k: v for k, v in payload().items() if k != "time"},
                                       channel="ohlc_closed.1.json", message_type="bc",
                                       receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                       collector_execution_id="test-execution-1")
        self.assertEqual("missing_from_payload", record["source_time"]["source_time_status"])
        self.assertIsNone(record["source_time"]["candle_start_time"])
        self.assertIsNone(record["logical_bar_identity"])

    def test_receipt_timestamp_must_be_timezone_aware(self):
        with self.assertRaisesRegex(pit.ProspectivePitContractError, "timezone_required"):
            pit.build_observation(payload=payload(), channel="ohlc_closed.1.json", message_type="bc",
                                  receipt_at=datetime(2026, 8, 11, 9, 0),
                                  collector_execution_id="test-execution-1")

    def test_collector_execution_id_is_required_and_retained(self):
        with self.assertRaisesRegex(pit.ProspectivePitContractError, "collector_execution_id_required"):
            pit.build_observation(payload=payload(), channel="ohlc_closed.1.json", message_type="bc",
                                  receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                  collector_execution_id="")
        self.assertEqual("test-execution-1", observation()["collector_execution_id"])

    def test_secret_shaped_field_is_rejected_before_retention(self):
        with self.assertRaisesRegex(pit.ProspectivePitContractError, "secret_shaped_field_rejected"):
            observation(accessToken="not-retainable")

    def test_rest_transport_is_not_a_receipt_time_observation(self):
        with self.assertRaisesRegex(pit.ProspectivePitContractError, "websocket_source_required"):
            pit.build_observation(payload=payload(), channel="ohlc_closed.1.json", message_type="bc",
                                  source_transport="rest",
                                  receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                  collector_execution_id="test-execution-1")

    def test_real_schema_shaped_hpg_and_vcb_payloads_are_accepted_without_optional_fields(self):
        hpg = payload(symbol="HPG", time=1787019660, lastUpdated=1787019716, open=21.25,
                      high=21.3, low=21.25, close=21.3, volume=27700)
        vcb = payload(symbol="VCB", time=1787019720, lastUpdated=1787019778, open=58.3,
                      high=58.4, low=58.3, close=58.3, volume=22800)
        for value in (hpg, vcb):
            self.assertNotIn("tradingDate", value)
            self.assertNotIn("tradingSessionId", value)
            record = pit.build_observation(payload=value, channel="ohlc_closed.1.json", message_type="bc",
                                           receipt_at=datetime(2026, 8, 18, 2, 22, tzinfo=timezone.utc),
                                           collector_execution_id="real-schema-shaped")
            self.assertEqual(value["symbol"], record["source"]["symbol"])
            self.assertIsNone(record["source_time"]["trading_date"])
            self.assertIsNone(record["source_time"]["trading_session_id"])

    def test_request_payload_correspondence_rejects_wrong_symbol_resolution_type_and_channel(self):
        expected = {"expected_symbol": "HPG", "expected_resolution": "1",
                    "expected_channel": "ohlc_closed.1.json"}
        for changed, code in (
            ({"symbol": "VCB"}, "requested_symbol_mismatch"),
            ({"resolution": "5"}, "requested_resolution_mismatch"),
            ({"T": "b"}, "closed_message_type_required"),
            ({"channel": "ohlc_closed.5.json"}, "requested_channel_mismatch"),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(pit.ProspectivePitContractError, code):
                pit.validate_payload_correspondence(payload=payload(**changed), **expected)

    def test_observation_builder_rejects_declared_context_mismatch(self):
        for changed, code in (
            ({"T": "b"}, "payload_message_type_mismatch"),
            ({"channel": "ohlc_closed.5.json"}, "payload_channel_mismatch"),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(pit.ProspectivePitContractError, code):
                pit.build_observation(payload=payload(**changed), channel="ohlc_closed.1.json",
                                      message_type="bc",
                                      receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                      collector_execution_id="test-execution-1")


class RetentionTests(unittest.TestCase):
    def test_duplicate_is_not_overwritten_and_revision_is_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = observation()
            self.assertEqual("first_receipt", pit.retain_observation(root, first)["classification"])
            original_line = (root / pit.OBSERVATIONS_FILENAME).read_text()
            duplicate = pit.retain_observation(root, observation())
            self.assertEqual("duplicate_identical", duplicate["classification"])
            revised = pit.retain_observation(root, observation(close=22.2))
            self.assertEqual("revision", revised["classification"])
            rows = [json.loads(line) for line in (root / pit.OBSERVATIONS_FILENAME).read_text().splitlines()]
            self.assertEqual(2, len(rows))
            self.assertEqual(original_line, (root / pit.OBSERVATIONS_FILENAME).read_text().splitlines()[0] + "\n")
            self.assertEqual("first_receipt", rows[0]["retention_classification"])
            self.assertEqual("revision", rows[1]["retention_classification"])
            self.assertEqual([rows[0]["observation_id"]], rows[1]["revises_observation_ids"])

    def test_distinct_receipt_time_is_retained_when_source_time_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = {k: v for k, v in payload().items() if k != "time"}
            a = pit.build_observation(payload=source, channel="ohlc_closed.1.json", message_type="bc",
                                      receipt_at=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc),
                                      collector_execution_id="test-execution-1")
            b = pit.build_observation(payload=source, channel="ohlc_closed.1.json", message_type="bc",
                                      receipt_at=datetime(2026, 8, 11, 9, 1, tzinfo=timezone.utc),
                                      collector_execution_id="test-execution-2")
            self.assertEqual("first_receipt_source_time_missing", pit.retain_observation(root, a)["classification"])
            self.assertEqual("first_receipt_source_time_missing", pit.retain_observation(root, b)["classification"])
            self.assertEqual(2, len((root / pit.OBSERVATIONS_FILENAME).read_text().splitlines()))

    def test_malformed_retained_jsonl_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / pit.OBSERVATIONS_FILENAME).write_text('{"truncated":\n', encoding="utf-8")
            with self.assertRaisesRegex(pit.ProspectivePitContractError, "malformed_retained_observation_line:1"):
                pit.retain_observation(root, observation())


class _FakeSocket:
    def __init__(self, messages, *, repeat_ping=False):
        self.messages = list(messages)
        self.sent = []
        self.repeat_ping = repeat_ping

    async def recv(self):
        if self.messages:
            value = self.messages.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value if isinstance(value, str) else json.dumps(value)
        if self.repeat_ping:
            return json.dumps({"action": "ping"})
        await asyncio.sleep(60)
        return "{}"  # pragma: no cover - sleep is cancelled by timeout

    async def send(self, value):
        self.sent.append(value)


class _FakeConnection:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class CollectorTests(unittest.TestCase):
    def _collect(self, messages, *, repeat_ping=False, **kwargs):
        socket = _FakeSocket(messages, repeat_ping=repeat_ping)
        fake_websockets = SimpleNamespace(connect=lambda *args, **ignored: _FakeConnection(socket))
        defaults = {
            "ticker": "HPG", "resolution": "1", "timeout_seconds": 1,
            "total_session_timeout_seconds": 2, "collector_execution_id": "collector-test",
        }
        defaults.update(kwargs)
        with patch.object(collector, "credentials_for_request", return_value=("key", "secret")), \
             patch.dict(sys.modules, {"websockets": fake_websockets}):
            return asyncio.run(collector.collect_once(**defaults))

    def test_bc_immediately_after_subscribed_is_retained(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"}, payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"subscribed": 1}, result["observability"]["control_message_counts"])
        self.assertEqual({}, result["observability"]["ignored_message_types"])

    def test_subscribed_ping_then_bc_does_not_exhaust_semantic_budget(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"},
            {"action": "ping"}, payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"subscribed": 1, "ping": 1}, result["observability"]["control_message_counts"])

    def test_subscribed_two_pings_then_bc_does_not_exhaust_semantic_budget(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"},
            {"action": "ping"}, {"action": "ping"}, payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"subscribed": 1, "ping": 2}, result["observability"]["control_message_counts"])

    def test_multiple_pings_are_observable_but_not_semantic_frames(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"},
            *({"action": "ping"} for _ in range(5)), payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual(5, result["observability"]["control_message_counts"]["ping"])

    def test_pings_only_are_bounded_by_absolute_session_deadline(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"},
        ], repeat_ping=True, timeout_seconds=5, total_session_timeout_seconds=0.01)
        self.assertEqual("BLOCKED_NO_COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertGreater(result["observability"]["control_message_counts"]["ping"], 1)
        self.assertEqual("post_subscribe_message", result["observability"]["timeout_stage"])

    def test_ignored_non_bc_metadata_is_retained_without_body(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"T": "b", "token": "not-retained"},
            payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"b": 1}, result["observability"]["ignored_message_types"])
        self.assertNotIn("token", json.dumps(result["observability"]))

    def test_unknown_control_flood_remains_bounded_and_fail_closed(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"},
            {"action": "unknown_control"}, {"action": "unknown_control"}, payload(),
        ])
        self.assertEqual("BLOCKED_NO_COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"subscribed": 1, "unknown_control": 1},
                         result["observability"]["control_message_counts"])

    def test_ignored_non_bc_content_flood_remains_bounded(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "subscribed"},
            {"T": "b"}, {"T": "b"}, payload(),
        ])
        self.assertEqual("BLOCKED_NO_COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual({"b": 2}, result["observability"]["ignored_message_types"])

    def test_wrong_symbol_after_pings_fails_closed(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "ping"},
            payload(symbol="VCB"),
        ])
        self.assertEqual("CONNECTION_OR_PROTOCOL_FAIL", result["status"])
        self.assertEqual("requested_symbol_mismatch", result["error_code"])

    def test_wrong_resolution_after_pings_fails_closed(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "ping"},
            payload(resolution="5"),
        ])
        self.assertEqual("CONNECTION_OR_PROTOCOL_FAIL", result["status"])
        self.assertEqual("requested_resolution_mismatch", result["error_code"])

    def test_malformed_frame_after_pings_fails_closed(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, {"action": "ping"}, "{bad-json",
        ])
        self.assertEqual("CONNECTION_OR_PROTOCOL_FAIL", result["status"])

    def test_secret_shaped_keepalive_fields_are_not_retained(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"},
            {"action": "ping", "token": "not-retained"}, payload(),
        ])
        self.assertEqual("COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertNotIn("token", json.dumps(result["observability"]))

    def test_timeout_stage_is_deterministic(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"}, asyncio.TimeoutError(),
        ])
        self.assertEqual("BLOCKED_NO_COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual("post_subscribe_message", result["observability"]["timeout_stage"])

    def test_total_session_timeout_is_bounded(self):
        result = self._collect([
            {"action": "welcome"}, {"action": "auth_success"},
        ], timeout_seconds=5, total_session_timeout_seconds=0.01)
        self.assertEqual("BLOCKED_NO_COMPLETED_EVENT_OBSERVED", result["status"])
        self.assertEqual("post_subscribe_message", result["observability"]["timeout_stage"])

    def test_output_directory_collision_refuses_existing_manifest_and_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / collector.EXECUTION_MANIFEST_FILENAME).write_text("old", encoding="utf-8")
            (root / pit.OBSERVATIONS_FILENAME).write_text("old\n", encoding="utf-8")
            with self.assertRaisesRegex(collector.OutputDirectoryCollisionError, "execution_manifest.json"):
                collector.run(ticker="HPG", resolution="1", timeout_seconds=1,
                              total_session_timeout_seconds=2, out_dir=root)
            self.assertEqual("old", (root / collector.EXECUTION_MANIFEST_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual("old\n", (root / pit.OBSERVATIONS_FILENAME).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
