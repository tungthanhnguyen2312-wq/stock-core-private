"""P3-F7 shadow daily-bundle contracts and regression checks."""
from __future__ import annotations
import inspect, json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from field_temporal_contract import stable_id  # noqa: E402
import mva_daily_research_bundle as m  # noqa: E402
import tools.run_p3f7_mva_daily_research_bundle as runner  # noqa: E402

def _sessions(): return [f"2026-01-{day:02d}" for day in range(1, 21)]
def _rows(): return [{"date": day, "close": 10 + index, "volume": 100 + index} for index, day in enumerate(_sessions())]

class CohortTests(unittest.TestCase):
    def test_complete_window_derives_shadow_only_cohort_without_canonical_authority(self):
        cohort = m.derive_empirical_active_cohort({"AAA": _rows(), "BBB": _rows()[:-1]}, sessions=_sessions(), candidate_tickers=["AAA", "BBB"])
        self.assertEqual(["AAA"], cohort["members"])
        self.assertEqual("DERIVED_SHADOW_DENOMINATOR_ONLY", cohort["authority"])
        self.assertIn("BBB", cohort["exclusions"])
        self.assertTrue(cohort["cohort_identity"].startswith("cohort_empirically_active:"))

    def test_missing_rows_are_not_imputed_and_dependent_features_fail_closed(self):
        self.assertEqual("MISSING", m.market_features(_rows()[:-1])["status"])
        self.assertEqual("SHADOW_ONLY", m.market_features(_rows())["status"])

    def test_invalid_mva_envelope_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "MVA_SHADOW_ENVELOPE_REQUIRED"):
            m.build_mva_daily_research_bundle(Path("runtime"), root=ROOT, envelope={})

class ArtifactTests(unittest.TestCase):
    def test_bundle_separates_proxy_authority_and_breadth_denominator(self):
        artifact = json.loads((runner.DEFAULT_OUTPUT_DIR / "p3f7_mva_daily_research_bundle_artifact.json").read_text(encoding="utf-8"))
        payload = dict(artifact); digest = payload.pop("artifact_sha256"); identity = payload.pop("artifact_identity")
        self.assertEqual(digest, stable_id(payload)); self.assertEqual(f"p3f7_mva_daily_research_bundle:{digest}", identity)
        summary, cohort = artifact["market_summary"], artifact["empirical_active_cohort"]
        self.assertEqual(summary["breadth"]["denominator"], cohort["member_count"])
        self.assertEqual(0, summary["authoritative_valuation_coverage"])
        self.assertGreater(summary["proxy_valuation_coverage"], 0)
        self.assertFalse(artifact["boundaries"]["active_universe_promoted"])
        self.assertFalse(artifact["is_actionable_for_execution"])

    def test_zero_ticker_specific_production_branches(self):
        source = inspect.getsource(m)
        for ticker in ("HPG", "VCB", "SSI", "GAS", "VNM"):
            self.assertNotIn(f'== "{ticker}"', source); self.assertNotIn(f"== '{ticker}'", source)
        artifact = json.loads((runner.DEFAULT_OUTPUT_DIR / "p3f7_mva_daily_research_bundle_artifact.json").read_text(encoding="utf-8"))
        self.assertEqual("PASS", artifact["ticker_specific_branch_audit"]["status"])

if __name__ == "__main__": unittest.main()
