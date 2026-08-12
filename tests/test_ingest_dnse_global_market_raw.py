from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ingest_dnse_global_market_raw as global_raw  # noqa: E402


class _Response:
    status_code = 200
    def json(self):
        return {"workingDates": ["2026-08-12"]}


class GlobalRawIngestTests(unittest.TestCase):
    def test_checkpoint_makes_global_dataset_idempotent(self):
        with TemporaryDirectory() as tmp:
            first = global_raw.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", run_id="r1",
                                   request_get=lambda *_args, **_kwargs: _Response())
            calls = []
            second = global_raw.run(runtime_root=Path(tmp), api_key="key", api_secret="secret", run_id="r2",
                                    request_get=lambda *_args, **_kwargs: calls.append(1))
        self.assertEqual("COMPLETE", first["status"])
        self.assertEqual("COMPLETE", second["status"])
        self.assertEqual([], calls)
        self.assertEqual(["market"], second["manifest"]["skipped_units"])


if __name__ == "__main__":
    unittest.main()
