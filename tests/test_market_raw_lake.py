from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import market_raw_lake as lake
from market_data_contracts import RawObservation


def _make_observation(*, instrument="HPG", retrieved_at="2026-08-11T10:00:00+07:00",
                      request_identity="req-1", payload=None) -> RawObservation:
    payload = payload if payload is not None else {"symbol": instrument, "close": 22000}
    payload_json = json.dumps(payload, sort_keys=True)
    import hashlib
    return RawObservation(
        provider="DNSE", dataset="ohlc", instrument=instrument, retrieved_at=retrieved_at,
        request_identity=request_identity, raw_payload_hash=hashlib.sha256(payload_json.encode()).hexdigest(),
        schema_version="1.0.0", raw_payload=payload, provenance={"endpoint": "/price/ohlc"},
    )


class WriteRawObservationTests(unittest.TestCase):
    def test_write_creates_a_parquet_file(self):
        with TemporaryDirectory() as tmp:
            observation = _make_observation()
            result = lake.write_raw_observation(tmp, observation, run_id="run-1")
            self.assertTrue(result["written"])
            self.assertTrue(Path(result["path"]).exists())
            self.assertTrue(result["path"].endswith(".parquet"))

    def test_round_trip_preserves_raw_payload_exactly(self):
        with TemporaryDirectory() as tmp:
            payload = {"symbol": "HPG", "o": [1, 2, 3], "nested": {"a": 1}}
            observation = _make_observation(payload=payload)
            result = lake.write_raw_observation(tmp, observation, run_id="run-1")
            frame = pd.read_parquet(result["path"])
            self.assertEqual(1, len(frame))
            row = frame.iloc[0]
            self.assertEqual(payload, json.loads(row["raw_payload_json"]))
            self.assertEqual(observation.observation_id, row["observation_id"])
            self.assertEqual("HPG", row["instrument"])
            self.assertEqual("DNSE", row["provider"])
            self.assertEqual("ohlc", row["dataset"])

    def test_rewriting_identical_observation_is_a_true_noop(self):
        with TemporaryDirectory() as tmp:
            observation = _make_observation()
            first = lake.write_raw_observation(tmp, observation, run_id="run-1")
            before_bytes = Path(first["path"]).read_bytes()
            second = lake.write_raw_observation(tmp, observation, run_id="run-1")
            self.assertFalse(second["written"])
            self.assertEqual("already_present_identical", second["reason"])
            self.assertEqual(before_bytes, Path(first["path"]).read_bytes())

    def test_different_run_ids_produce_two_distinct_immutable_files(self):
        with TemporaryDirectory() as tmp:
            observation = _make_observation()
            first = lake.write_raw_observation(tmp, observation, run_id="run-1")
            second = lake.write_raw_observation(tmp, observation, run_id="run-2")
            self.assertNotEqual(first["path"], second["path"])
            self.assertTrue(Path(first["path"]).exists())
            self.assertTrue(Path(second["path"]).exists())

    def test_two_different_observations_never_collide(self):
        with TemporaryDirectory() as tmp:
            first_obs = _make_observation(retrieved_at="2026-08-11T10:00:00+07:00")
            second_obs = _make_observation(retrieved_at="2026-08-11T11:00:00+07:00")
            first = lake.write_raw_observation(tmp, first_obs, run_id="run-1")
            second = lake.write_raw_observation(tmp, second_obs, run_id="run-1")
            self.assertNotEqual(first_obs.observation_id, second_obs.observation_id)
            self.assertNotEqual(first["path"], second["path"])
            self.assertTrue(Path(first["path"]).exists())
            self.assertTrue(Path(second["path"]).exists())

    def test_existing_file_with_different_content_raises_immutability_error(self):
        with TemporaryDirectory() as tmp:
            observation = _make_observation()
            path = lake.raw_file_path(tmp, observation.provider, observation.dataset, "run-1",
                                      observation.instrument, observation.observation_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not-actually-a-matching-parquet-file")
            with self.assertRaises(lake.RawLakeImmutabilityError):
                lake.write_raw_observation(tmp, observation, run_id="run-1")

    def test_unit_id_with_unsafe_characters_produces_a_valid_path(self):
        with TemporaryDirectory() as tmp:
            observation = _make_observation(instrument="universe_page:0001/weird*name")
            result = lake.write_raw_observation(tmp, observation, run_id="run:with/slashes")
            self.assertTrue(Path(result["path"]).exists())


class SnapshotParquetTests(unittest.TestCase):
    def test_write_snapshot_parquet_round_trips(self):
        with TemporaryDirectory() as tmp:
            frame = pd.DataFrame([{"symbol": "HPG", "exchange_raw": "STO"},
                                  {"symbol": "VNM", "exchange_raw": "STO"}])
            path = Path(tmp) / "snapshot.parquet"
            result = lake.write_snapshot_parquet(path, frame)
            self.assertEqual(2, result["rows"])
            read_back = pd.read_parquet(path)
            self.assertEqual(["HPG", "VNM"], sorted(read_back["symbol"]))


class CheckpointTests(unittest.TestCase):
    def test_load_checkpoint_without_prior_state_returns_fresh_skeleton(self):
        with TemporaryDirectory() as tmp:
            checkpoint = lake.load_checkpoint(tmp, "DNSE", "ohlc", "scope-1")
            self.assertEqual({}, checkpoint["units"])
            self.assertEqual(lake.CHECKPOINT_SCHEMA_VERSION, checkpoint["schema_version"])

    def test_save_then_load_round_trips(self):
        with TemporaryDirectory() as tmp:
            checkpoint = lake.new_checkpoint("DNSE", "ohlc", "scope-1")
            checkpoint = lake.record_unit_result(checkpoint, "HPG", status="success",
                                                 raw_file="x.parquet", observation_id="abc123")
            lake.save_checkpoint(tmp, checkpoint)
            reloaded = lake.load_checkpoint(tmp, "DNSE", "ohlc", "scope-1")
            self.assertEqual("success", lake.unit_status(reloaded, "HPG"))
            self.assertEqual({"HPG"}, lake.completed_units(reloaded))

    def test_record_unit_result_increments_attempts_and_preserves_first_attempt(self):
        checkpoint = lake.new_checkpoint("DNSE", "ohlc", "scope-1")
        checkpoint = lake.record_unit_result(checkpoint, "HPG", status="failed", error_code="rate_limited")
        first_attempt_at = checkpoint["units"]["HPG"]["first_attempt_at"]
        self.assertEqual(1, checkpoint["units"]["HPG"]["attempts"])
        checkpoint = lake.record_unit_result(checkpoint, "HPG", status="success", observation_id="abc")
        self.assertEqual(2, checkpoint["units"]["HPG"]["attempts"])
        self.assertEqual(first_attempt_at, checkpoint["units"]["HPG"]["first_attempt_at"])
        self.assertEqual("success", checkpoint["units"]["HPG"]["status"])

    def test_record_unit_result_is_pure_does_not_mutate_input(self):
        checkpoint = lake.new_checkpoint("DNSE", "ohlc", "scope-1")
        updated = lake.record_unit_result(checkpoint, "HPG", status="success")
        self.assertEqual({}, checkpoint["units"])
        self.assertIn("HPG", updated["units"])

    def test_invalid_status_raises(self):
        checkpoint = lake.new_checkpoint("DNSE", "ohlc", "scope-1")
        with self.assertRaises(ValueError):
            lake.record_unit_result(checkpoint, "HPG", status="not_a_real_status")

    def test_unit_status_for_unknown_unit_is_none(self):
        checkpoint = lake.new_checkpoint("DNSE", "ohlc", "scope-1")
        self.assertIsNone(lake.unit_status(checkpoint, "NOPE"))

    def test_corrupt_checkpoint_file_falls_back_to_fresh_skeleton(self):
        with TemporaryDirectory() as tmp:
            path = lake.checkpoint_path(tmp, "DNSE", "ohlc", "scope-1")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not valid json", encoding="utf-8")
            checkpoint = lake.load_checkpoint(tmp, "DNSE", "ohlc", "scope-1")
            self.assertEqual({}, checkpoint["units"])

    def test_different_run_scope_ids_are_isolated(self):
        with TemporaryDirectory() as tmp:
            checkpoint_a = lake.record_unit_result(
                lake.new_checkpoint("DNSE", "ohlc", "scope-A"), "HPG", status="success")
            lake.save_checkpoint(tmp, checkpoint_a)
            checkpoint_b = lake.load_checkpoint(tmp, "DNSE", "ohlc", "scope-B")
            self.assertEqual({}, checkpoint_b["units"])


class ManifestTests(unittest.TestCase):
    def test_build_manifest_counts_match_lists(self):
        manifest = lake.build_manifest(
            provider="DNSE", dataset="ohlc", run_id="run-1", run_scope_id="scope-1",
            started_at="t0", ended_at="t1", requested_units=["HPG", "VNM", "QNS"],
            attempted_units=["HPG", "VNM", "QNS"], successful_units=["HPG", "VNM"],
            failed_units=[{"unit_id": "QNS", "error_code": "http_status_404"}],
            skipped_units=[], output_dir="raw/DNSE/ohlc/run-1", checkpoint_file="checkpoints/x.json",
        )
        self.assertEqual(3, manifest["requested_unit_count"])
        self.assertEqual(2, manifest["successful_unit_count"])
        self.assertEqual(1, manifest["failed_unit_count"])
        self.assertEqual(["HPG", "QNS", "VNM"], manifest["requested_units"])

    def test_save_then_load_manifest_round_trips(self):
        with TemporaryDirectory() as tmp:
            manifest = lake.build_manifest(
                provider="DNSE", dataset="ohlc", run_id="run-1", run_scope_id="scope-1",
                started_at="t0", ended_at="t1", requested_units=["HPG"], attempted_units=["HPG"],
                successful_units=["HPG"], failed_units=[], skipped_units=[],
                output_dir="x", checkpoint_file="y",
            )
            lake.save_manifest(tmp, manifest)
            reloaded = lake.load_manifest(tmp, "DNSE", "ohlc", "run-1")
            self.assertEqual(manifest, reloaded)

    def test_load_missing_manifest_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(lake.load_manifest(tmp, "DNSE", "ohlc", "does-not-exist"))


if __name__ == "__main__":
    unittest.main()
