from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import pipeline_scheduler as scheduler

class PipelineSchedulerTests(unittest.TestCase):
    def test_single_instance_lock_acquires_and_releases(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lock_file = root / "locks" / "pipeline.lock"
            with scheduler.PipelineLock(lock_file):
                self.assertTrue(lock_file.is_file())
            self.assertFalse(lock_file.is_file())

    def test_concurrency_lock_blocks_second_instance(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lock_file = root / "locks" / "pipeline.lock"
            with scheduler.PipelineLock(lock_file):
                with self.assertRaises(scheduler.FileLockError):
                    with scheduler.PipelineLock(lock_file):
                        pass

    def test_log_rotation_when_file_exceeds_size(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            log_file = root / "daily_pipeline.log"
            log_file.write_text("x" * 100, encoding="utf-8")
            scheduler.rotate_log_file(log_file, max_bytes=50)
            self.assertTrue(root / "daily_pipeline.log.1")
            self.assertFalse(log_file.is_file())

    def test_scheduler_main_executes_runner(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            executed = []

            def fake_runner(args, runtime_root):
                executed.append((args, runtime_root))
                return 0

            res = scheduler.main(["--runtime-root", str(root), "--tickers", "POW", "SSI"], pipeline_runner=fake_runner)
            self.assertEqual(res, 0)
            self.assertEqual(len(executed), 1)
            self.assertEqual(executed[0][0].tickers, ["POW", "SSI"])

            events_file = root / "logs" / "observability_events.jsonl"
            self.assertTrue(events_file.is_file())
            content = events_file.read_text(encoding="utf-8")
            self.assertIn("pipeline_scheduler", content)

    def test_scheduler_locked_exit_code_3(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lock_file = root / "locks" / "pipeline.lock"
            with scheduler.PipelineLock(lock_file):
                res = scheduler.main(["--runtime-root", str(root)])
                self.assertEqual(res, 3)

if __name__ == "__main__":
    unittest.main()
