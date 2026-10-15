"""Tests for atomic file writing, validation, and promotion helper (atomic_io.py).

Validates atomic file writes, JSON/CSV pre-promotion validation, replacement of existing files,
preservation of target files on validation or writer failure, and temporary file cleanup.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from atomic_io import (
    AtomicWriteError,
    atomic_copy_file,
    atomic_write_file,
    atomic_write_json,
    validate_csv_file,
    validate_json_file,
)


def test_v5_historical_interfaces_share_the_canonical_objects():
    """Frozen import names survive without duplicated functions or exceptions."""
    import atomic_io as old
    import observability_events as events
    from stocklookup_core.acquisition import artifact_io as owner
    import pickle

    for name in ("AtomicWriteError", "atomic_write_file", "atomic_write_json",
                 "atomic_copy_file", "retain_immutable_bytes", "retain_immutable_file",
                 "validate_json_file", "validate_csv_file", "os", "tempfile"):
        assert getattr(old, name) is getattr(owner, name)
    for name in ("EventStage", "EventOutcome", "build_observability_event",
                 "emit_observability_event"):
        assert getattr(events, name) is getattr(owner, name)
    assert pickle.loads(pickle.dumps(old.AtomicWriteError("refused"))).__class__ is owner.AtomicWriteError
    assert pickle.loads(pickle.dumps(events.EventStage.ATOMIC_PROMOTION)) is owner.EventStage.ATOMIC_PROMOTION
    assert pickle.loads(pickle.dumps(old.atomic_write_file)) is owner.atomic_write_file


def test_v5_both_import_orders_preserve_frozen_bindings():
    import subprocess
    import sys

    for first in ("atomic_io", "stocklookup_core.acquisition.artifact_io", "observability_events"):
        subprocess.run([sys.executable, "-c", f"""
import {first}
import atomic_io as old
import observability_events as events
from stocklookup_core.acquisition import artifact_io as owner
assert old.atomic_write_file is owner.atomic_write_file
assert old.AtomicWriteError is owner.AtomicWriteError
assert events.EventStage is owner.EventStage
assert old.os is owner.os
assert old.tempfile is owner.tempfile
"""], check=True)


def test_v5_existing_fsync_patch_slot_fails_without_changing_old_bytes(tmp_path, monkeypatch):
    import atomic_io as old
    import pytest
    from stocklookup_core.acquisition import artifact_io as owner

    target = tmp_path / "artifact.json"
    target.write_bytes(b"original")
    def fail(*args):
        raise OSError("INJECTED_TEMP_FSYNC")
    monkeypatch.setattr(old.os, "fsync", fail)
    with pytest.raises(old.AtomicWriteError):
        owner.atomic_write_file(target, b"candidate")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob(".tmp-*"))


class AtomicIoTests(unittest.TestCase):
    def test_successful_first_write(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.json"
            data = {"status": "ok", "value": 123}
            atomic_write_json(target, data)

            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), data)

    def test_successful_replacement_of_existing_artifact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "artifact.json"
            target.write_text(json.dumps({"version": 1}), encoding="utf-8")

            new_data = {"version": 2, "updated": True}
            atomic_write_json(target, new_data)

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), new_data)

    def test_json_validation_failure_preserves_old_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "artifact.json"
            original_content = json.dumps({"version": 1, "valid": True})
            target.write_text(original_content, encoding="utf-8")

            invalid_json_bytes = b"{"  # Malformed JSON

            with self.assertRaises(ValueError):
                atomic_write_file(target, invalid_json_bytes, validator=validate_json_file)

            # Target remains untouched
            self.assertEqual(target.read_text(encoding="utf-8"), original_content)
            # No lingering temporary files in directory
            temp_files = list(Path(tmp_dir).glob(".tmp-*"))
            self.assertEqual(temp_files, [])

    def test_simulated_writer_failure_preserves_old_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "artifact.txt"
            target.write_text("original content", encoding="utf-8")

            def faulty_validator(p: Path):
                raise RuntimeError("Simulated validation error")

            with self.assertRaises(AtomicWriteError):
                atomic_write_file(target, "new content", validator=faulty_validator)

            self.assertEqual(target.read_text(encoding="utf-8"), "original content")
            self.assertEqual(list(Path(tmp_dir).glob(".tmp-*")), [])

    def test_simulated_replace_failure_preserves_old_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "artifact.txt"
            target.write_text("original content", encoding="utf-8")

            with mock.patch("os.replace", side_effect=OSError("Permission denied on replace")):
                with self.assertRaises(AtomicWriteError):
                    atomic_write_file(target, "new content")

            self.assertEqual(target.read_text(encoding="utf-8"), "original content")
            self.assertEqual(list(Path(tmp_dir).glob(".tmp-*")), [])

    def test_temp_file_cleanup_on_success_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "test.json"
            atomic_write_json(target, {"key": "val"})
            self.assertEqual(list(Path(tmp_dir).glob(".tmp-*")), [])

            with self.assertRaises(ValueError):
                atomic_write_file(target, b"invalid json", validator=validate_json_file)
            self.assertEqual(list(Path(tmp_dir).glob(".tmp-*")), [])

    def test_deterministic_repeated_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target1 = Path(tmp_dir) / "out1.json"
            target2 = Path(tmp_dir) / "out2.json"

            data = {"b": 2, "a": 1, "items": [1, 2, 3]}
            atomic_write_json(target1, data)
            atomic_write_json(target2, data)

            hash1 = hashlib.sha256(target1.read_bytes()).hexdigest()
            hash2 = hashlib.sha256(target2.read_bytes()).hexdigest()
            self.assertEqual(hash1, hash2)

    def test_csv_validation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            valid_csv = Path(tmp_dir) / "valid.csv"
            valid_csv.write_text("ticker,close,volume\nAAA,10.5,1000\n", encoding="utf-8")
            validate_csv_file(valid_csv, required_columns=["ticker", "close"])

            invalid_csv = Path(tmp_dir) / "invalid.csv"
            invalid_csv.write_text("ticker,close\nAAA,10.5\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_csv_file(invalid_csv, required_columns=["volume"])

    def test_atomic_copy_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "source.json"
            src.write_text(json.dumps({"data": "test"}), encoding="utf-8")

            dst = Path(tmp_dir) / "dest.json"
            atomic_copy_file(src, dst, validator=validate_json_file)

            self.assertTrue(dst.exists())
            self.assertEqual(dst.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
