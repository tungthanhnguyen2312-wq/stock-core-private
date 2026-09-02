from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from market_wide_relative_volume_research import build_artifact, content_identity
from tools.run_market_wide_relative_volume_research import replay


def _row(session: str, volume: float, *, provider: str = "DNSE", field: str = "DNSE_OHLC.volume") -> dict:
    return {
        "session": session, "volume": volume, "provider": provider,
        "field_identity": {"volume": field},
        "field_representation": {"volume": "DNSE_PROVIDER_NATIVE_RAW"},
    }


def _history(current: float, *, scale: float = 1.0) -> list[dict]:
    days = [f"2026-01-{day:02d}" for day in range(1, 22)]
    return [_row(day, (index + 1) * scale) for index, day in enumerate(days[:-1])] + [_row(days[-1], current * scale)]


class RelativeVolumeResearchTests(unittest.TestCase):
    def _artifact(self, records: dict[str, dict]) -> dict:
        return build_artifact(candidates=list(records), records=records, session="2026-01-21", requested_at="test")

    def test_percentile_is_deterministic_and_tie_aware(self):
        records = {"AAA": {"observations": _history(10)}, "BBB": {"observations": _history(10)}, "CCC": {"observations": _history(30)}}
        first, second = self._artifact(records), self._artifact(copy.deepcopy(records))
        self.assertEqual(first, second)
        self.assertEqual(1 / 3, first["records"]["AAA"]["relative_volume_percentile"])
        self.assertEqual(5 / 6, first["records"]["CCC"]["relative_volume_percentile"])
        self.assertEqual(3, first["records"]["AAA"]["cohort_denominator"])

    def test_percentiles_are_in_range_and_missing_is_not_zero(self):
        artifact = self._artifact({"AAA": {"observations": _history(1)}, "BBB": {"observations": _history(2)}, "CCC": {"observations": _history(float("nan"))}})
        for ticker in ("AAA", "BBB"):
            self.assertLessEqual(0, artifact["records"][ticker]["relative_volume_percentile"])
            self.assertLessEqual(artifact["records"][ticker]["relative_volume_percentile"], 1)
        self.assertIsNone(artifact["records"]["CCC"]["relative_volume_percentile"])
        self.assertEqual("VOLUME_MISSING_OR_INVALID", artifact["records"]["CCC"]["reason"])

    def test_session_provider_field_and_negative_mismatches_fail_closed(self):
        mixed_session = _history(5)[:-1] + [_row("2025-12-31", 5)]
        wrong_provider = _history(5); wrong_provider[-1]["provider"] = "OTHER"
        wrong_field = _history(5); wrong_field[-1]["field_identity"]["volume"] = "OTHER.volume"
        negative = _history(5); negative[-1]["volume"] = -1
        artifact = self._artifact({
            "SESSION": {"observations": mixed_session}, "PROVIDER": {"observations": wrong_provider},
            "FIELD": {"observations": wrong_field}, "NEGATIVE": {"observations": negative},
        })
        self.assertEqual("CURRENT_VOLUME_UNAVAILABLE", artifact["records"]["SESSION"]["reason"])
        self.assertEqual("PROVIDER_MISMATCH", artifact["records"]["PROVIDER"]["reason"])
        self.assertEqual("NATIVE_FIELD_MISMATCH", artifact["records"]["FIELD"]["reason"])
        self.assertEqual("VOLUME_MISSING_OR_INVALID", artifact["records"]["NEGATIVE"]["reason"])

    def test_acceleration_requires_exactly_twenty_prior_and_excludes_current(self):
        rows = _history(100)
        artifact = self._artifact({"AAA": {"observations": rows}})
        record = artifact["records"]["AAA"]
        self.assertEqual(20, record["valid_prior_completed_session_count"])
        self.assertEqual(100 / 10.5, record["volume_acceleration_ratio"])
        short = self._artifact({"AAA": {"observations": rows[1:]}})["records"]["AAA"]
        self.assertEqual("UNAVAILABLE_INSUFFICIENT_HISTORY", short["acceleration_status"])

    def test_zero_baseline_and_future_rows_are_blocked(self):
        zero = [_row(f"2026-01-{day:02d}", 0) for day in range(1, 21)] + [_row("2026-01-21", 1)]
        future = _history(4) + [_row("2026-01-22", 1)]
        artifact = self._artifact({"ZERO": {"observations": zero}, "FUTURE": {"observations": future}})
        self.assertEqual("UNAVAILABLE_ZERO_BASELINE", artifact["records"]["ZERO"]["acceleration_status"])
        self.assertEqual("FUTURE_SESSION_ROW_PROHIBITED", artifact["records"]["FUTURE"]["reason"])
        self.assertEqual(1, artifact["coverage"]["future_session_violations"])

    def test_unknown_constant_scale_cancels_and_no_absolute_or_value_semantics_emit(self):
        original = self._artifact({"AAA": {"observations": _history(100)}, "BBB": {"observations": _history(20)}})
        scaled = self._artifact({"AAA": {"observations": _history(100, scale=1000)}, "BBB": {"observations": _history(20, scale=1000)}})
        for ticker in ("AAA", "BBB"):
            self.assertEqual(original["records"][ticker]["relative_volume_percentile"], scaled["records"][ticker]["relative_volume_percentile"])
            self.assertEqual(original["records"][ticker]["volume_acceleration_ratio"], scaled["records"][ticker]["volume_acceleration_ratio"])
        self.assertEqual("UNKNOWN", original["authority_boundary"]["ABSOLUTE_VOLUME_UNIT"])
        self.assertEqual("NOT_IMPLEMENTED", original["authority_boundary"]["ABSOLUTE_TRADED_VALUE"])
        self.assertEqual("NOT_IMPLEMENTED", original["authority_boundary"]["ADV_ADTV"])
        self.assertEqual("STILL_BLOCKED", original["authority_boundary"]["EXECUTION_CAPACITY"])
        self.assertFalse(any("current_volume" in key for key in original["records"]["AAA"]))

    def test_ai_pass_through_is_compact_and_never_actionable(self):
        artifact = self._artifact({"AAA": {"observations": _history(5)}})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            entries = bundle.attach_market_wide_relative_volume_research({"AAA": {"ticker": "AAA"}}, True, str(path))
        result = entries["AAA"]["market_wide_relative_volume_research"]
        self.assertFalse(result["is_actionable"])
        self.assertNotIn("current_volume", result)
        self.assertNotIn("traded_value", result)

    def test_retained_runner_writes_self_verifying_artifact(self):
        source = {"resolved_completed_session": "2026-01-21", "canonical_identity": "snapshot:test", "records": {"AAA": {"observations": _history(5)}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); snapshot = root / "snapshot.json"; snapshot.write_text(json.dumps(source), encoding="utf-8")
            artifact = json.loads(replay(snapshot, root / "out").read_text(encoding="utf-8"))
        self.assertEqual(content_identity(artifact)["artifact_sha256"], artifact["artifact_sha256"])
        self.assertFalse(artifact["authority_boundary"]["is_actionable"])


if __name__ == "__main__":
    unittest.main()
