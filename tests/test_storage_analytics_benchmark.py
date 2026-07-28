from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import storage_analytics_benchmark as benchmark


class BenchmarkContractTests(unittest.TestCase):
    def test_pair_requires_semantic_parity_and_exact_measurement_bound(self):
        calls = {"sqlite": 0, "duck": 0}
        def sqlite_query():
            calls["sqlite"] += 1
            return [{"ticker": "HPG", "value": 1, "none": None}]
        def duck_query():
            calls["duck"] += 1
            return [{"ticker": "HPG", "value": 1, "none": None}]
        result = benchmark._measure_pair("synthetic", sqlite_query, duck_query)
        self.assertEqual(calls, {"sqlite": 3, "duck": 3})
        self.assertEqual(result["parity"], "pass")
        self.assertEqual(result["sqlite_pandas"]["runs"], 2)
        self.assertEqual(result["duckdb_parquet"]["runs"], 2)

    def test_pair_fails_closed_for_value_difference(self):
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark._measure_pair("synthetic", lambda: [{"value": 1}], lambda: [{"value": 2}])

    def test_output_rows_preserve_nulls_and_float_precision(self):
        import pandas as pd
        frame = pd.DataFrame([{"ticker": "HPG", "price": 8060.000000000001, "value": None}])
        rows = benchmark._rows(frame)
        self.assertIsNone(rows[0]["value"])
        self.assertEqual(rows[0]["price"], 8060.000000000001)

    def test_missing_authority_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(benchmark.BenchmarkError):
                benchmark.run_benchmark(runtime_root=root, lake_root=root / "lake", output_path=root / "out.json")


if __name__ == "__main__":
    unittest.main()
