"""Focused coverage for release_session_contract.py.

publish_dashboard.py used to derive the dashboard release session by reading
screen_snapshot.csv's own `date` column with no external cross-check — a frozen leftover
copy always looks internally self-consistent, so that heuristic could never detect
staleness. These tests pin down the replacement: bundle_manifest.json's
freshness.reference_session as the one external authority, cross-validated against every
session-sensitive artifact, fail-closed on any disagreement, missing value, or malformed
manifest — never a silent min/max/first/fallback pick. See
docs/dashboard_release_session_contract.md.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import release_session_contract as rsc  # noqa: E402

REQUIRED = ("screen_snapshot.csv", "market_breadth.csv", "screen_snapshot_live.csv", "analysis_bundle.json")


def _manifest(session: str, *, blocked: bool = False, status: str = "fresh",
              trusted_session: str | None = None) -> dict:
    manifest = {
        "schema_version": "1.1.0",
        "freshness": {"reference_session": session, "blocked": blocked, "status": status},
    }
    if trusted_session is not None:
        manifest["trusted_subset"] = {"session_identity": trusted_session}
    return manifest


def _write(root: Path, name: str, content: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(content, encoding="utf-8")


def _snapshot_csv(session: str, *, extra_delisted_row: bool = False) -> str:
    text = f"ticker,exchange,date\nHPG,HSX,{session}\nABC,HNX,{session}\n"
    if extra_delisted_row:
        text += "OLD,DELISTED,2020-01-01\n"
    return text


class FullAgreementTests(unittest.TestCase):
    """Scenario 1: every required artifact on the same session -> pass."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_all_artifacts_agree_with_manifest_is_ready(self):
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session, trusted_session=session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(session))
        _write(self.root, "market_breadth.csv", f"group,date,n_up\nALL,{session},1\n")
        _write(self.root, "screen_snapshot_live.csv", _snapshot_csv(session))
        _write(self.root, "analysis_bundle.json", json.dumps({"reference_session_date": session}))

        report = rsc.resolve_release_session(self.root, REQUIRED)

        self.assertTrue(report.ready)
        self.assertEqual(report.session, session)
        self.assertEqual(report.authority, "bundle_manifest.json")
        self.assertEqual(report.mismatch_lines(), [])
        self.assertTrue(all(r.status == "ok" for r in report.results))

    def test_delisted_rows_in_screen_snapshot_do_not_affect_its_session(self):
        """screen_snapshot.csv is the full universe; a delisted ticker frozen years ago
        must not corrupt the max()-of-active-rows session read."""
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(session, extra_delisted_row=True))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertTrue(report.ready)


class StaleArtifactTests(unittest.TestCase):
    """Scenarios 2-5: each session-sensitive artifact, stale alone, fails closed and names
    itself precisely — this is the exact defect that let a dry-run report phiên 2026-07-24
    while bundle_manifest.json already said 2026-08-04."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(self.session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(self.session))
        _write(self.root, "market_breadth.csv", f"group,date,n_up\nALL,{self.session},1\n")
        _write(self.root, "screen_snapshot_live.csv", _snapshot_csv(self.session))
        _write(self.root, "analysis_bundle.json", json.dumps({"reference_session_date": self.session}))

    def _stale(self, name: str, content: str):
        _write(self.root, name, content)
        report = rsc.resolve_release_session(self.root, REQUIRED)
        self.assertFalse(report.ready, f"{name} being stale must fail the gate")
        self.assertEqual(report.session, self.session, "authority must stay the manifest's session, not drift")
        mismatch = next(r for r in report.results if r.name == name)
        self.assertEqual(mismatch.status, "mismatch")
        lines = report.mismatch_lines()
        self.assertTrue(any(name in line and "2026-07-24" in line and self.session in line for line in lines),
                        f"expected a precise observed/expected line for {name}, got {lines}")

    def test_stale_screen_snapshot_csv_fails(self):
        self._stale("screen_snapshot.csv", _snapshot_csv("2026-07-24"))

    def test_stale_screen_snapshot_live_csv_fails(self):
        self._stale("screen_snapshot_live.csv", _snapshot_csv("2026-07-24"))

    def test_stale_market_breadth_csv_fails(self):
        self._stale("market_breadth.csv", "group,date,n_up\nALL,2026-07-24,1\n")

    def test_stale_analysis_bundle_json_fails(self):
        self._stale("analysis_bundle.json", json.dumps({"reference_session_date": "2026-07-24"}))

    def test_only_the_stale_file_is_reported_not_its_healthy_siblings(self):
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-07-24"))
        report = rsc.resolve_release_session(self.root, REQUIRED)
        statuses = {r.name: r.status for r in report.results}
        self.assertEqual(statuses["screen_snapshot.csv"], "mismatch")
        self.assertEqual(statuses["market_breadth.csv"], "ok")
        self.assertEqual(statuses["screen_snapshot_live.csv"], "ok")
        self.assertEqual(statuses["analysis_bundle.json"], "ok")


class MissingManifestLegacyModeTests(unittest.TestCase):
    """Scenario 6: no bundle_manifest.json -> an explicit, separately-labeled legacy path,
    never an accidental reuse of the manifest-backed logic."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_no_manifest_but_unanimous_agreement_passes_as_legacy(self):
        session = "2026-08-04"
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(session))
        _write(self.root, "market_breadth.csv", f"group,date,n_up\nALL,{session},1\n")
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv", "market_breadth.csv"])
        self.assertTrue(report.ready)
        self.assertEqual(report.authority, "legacy_cross_check")
        self.assertEqual(report.session, session)

    def test_no_manifest_and_disagreement_fails_with_no_silent_pick(self):
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-08-04"))
        _write(self.root, "market_breadth.csv", "group,date,n_up\nALL,2026-08-01,1\n")
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv", "market_breadth.csv"])
        self.assertFalse(report.ready)
        self.assertEqual(report.authority, "legacy_cross_check")
        self.assertIsNone(report.session, "must not silently choose min/max/first among disagreeing files")
        self.assertTrue(any("disagree" in p for p in report.problems))

    def test_legacy_mode_is_never_confused_with_manifest_backed_authority(self):
        """A missing manifest must never be reported as if bundle_manifest.json governed it."""
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-08-04"))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertNotEqual(report.authority, "bundle_manifest.json")
        self.assertEqual(report.authority, "legacy_cross_check")


class MalformedOrMissingSessionFieldTests(unittest.TestCase):
    """Scenario 7: malformed/missing session data fails with a precise message — a present
    but broken manifest is a hard failure, never a silent demotion to legacy mode."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_manifest_present_but_not_json_fails_and_does_not_fall_back_to_legacy(self):
        _write(self.root, "bundle_manifest.json", "{not valid json")
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-08-04"))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        self.assertEqual(report.authority, "bundle_manifest.json")
        self.assertTrue(any("not readable JSON" in p for p in report.problems))

    def test_manifest_missing_freshness_block_fails_clearly(self):
        _write(self.root, "bundle_manifest.json", json.dumps({"schema_version": "1.1.0"}))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-08-04"))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        self.assertTrue(any("no freshness block" in p for p in report.problems))

    def test_manifest_missing_reference_session_fails_clearly(self):
        _write(self.root, "bundle_manifest.json", json.dumps({"freshness": {"blocked": False}}))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        self.assertTrue(any("reference_session is missing" in p for p in report.problems))

    def test_manifest_blocked_true_fails_even_with_a_session_value(self):
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session, blocked=True, status="stale_override")))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(session))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        self.assertTrue(any("blocked=true" in p for p in report.problems))

    def test_csv_with_no_date_values_is_reported_missing_not_silently_skipped(self):
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session)))
        _write(self.root, "screen_snapshot.csv", "ticker,exchange,date\nHPG,HSX,\n")
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        result = next(r for r in report.results if r.name == "screen_snapshot.csv")
        self.assertEqual(result.status, "missing")

    def test_trusted_subset_disagreement_is_a_hard_failure(self):
        _write(self.root, "bundle_manifest.json",
              json.dumps(_manifest("2026-08-04", trusted_session="2026-08-03")))
        report = rsc.resolve_release_session(self.root, [])
        self.assertFalse(report.ready)
        self.assertTrue(any("disagrees with" in p for p in report.problems))

    def test_future_session_is_rejected(self):
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest("2099-01-01")))
        report = rsc.resolve_release_session(self.root, [], today="2026-08-05")
        self.assertFalse(report.ready)
        self.assertTrue(any("in the future" in p for p in report.problems))

    def test_required_artifact_missing_from_disk_is_reported(self):
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest("2026-08-04")))
        report = rsc.resolve_release_session(self.root, ["screen_snapshot.csv"])
        self.assertFalse(report.ready)
        result = report.results[0]
        self.assertEqual(result.status, "missing")
        self.assertIn("missing from", result.detail)


class SessionNeutralArtifactTests(unittest.TestCase):
    """Scenario 8: a session-neutral artifact (financial statement snapshot, keyed by
    reporting period) must be allowed through untouched, never compared to the market
    session — an older reporting period is normal, not staleness."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_older_financial_snapshot_does_not_block_readiness(self):
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv(session))
        # A real reporting-period artifact; content is irrelevant since it's session-neutral.
        _write(self.root, "financial_snapshot.csv", "ticker,period,total_assets\nHPG,2026Q1,1000\n")

        report = rsc.resolve_release_session(
            self.root, ["screen_snapshot.csv", "financial_snapshot.csv"],
            session_neutral={"financial_snapshot.csv"},
        )
        self.assertTrue(report.ready)
        neutral = next(r for r in report.results if r.name == "financial_snapshot.csv")
        self.assertEqual(neutral.status, "neutral")
        self.assertIsNone(neutral.observed)

    def test_neutral_artifact_never_appears_in_mismatch_lines(self):
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2020-01-01"))  # deliberately stale
        report = rsc.resolve_release_session(
            self.root, ["screen_snapshot.csv", "financial_snapshot.parquet"],
            session_neutral={"financial_snapshot.parquet"},
        )
        self.assertFalse(report.ready)
        self.assertFalse(any("financial_snapshot" in line for line in report.mismatch_lines()))


class DeterministicOrderTests(unittest.TestCase):
    """Scenario 10: repeated runs over unchanged input produce identical results and the
    reporting order follows the caller-supplied list, not dict/set iteration."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        session = "2026-08-04"
        _write(self.root, "bundle_manifest.json", json.dumps(_manifest(session)))
        _write(self.root, "screen_snapshot.csv", _snapshot_csv("2026-07-01"))
        _write(self.root, "market_breadth.csv", "group,date,n_up\nALL,2026-07-02,1\n")
        _write(self.root, "screen_snapshot_live.csv", _snapshot_csv("2026-07-03"))

    def test_repeated_calls_are_byte_identical(self):
        order = ["screen_snapshot.csv", "market_breadth.csv", "screen_snapshot_live.csv"]
        first = rsc.resolve_release_session(self.root, order).render()
        second = rsc.resolve_release_session(self.root, order).render()
        self.assertEqual(first, second)

    def test_reporting_order_follows_caller_supplied_order_not_alphabetical(self):
        order = ["screen_snapshot_live.csv", "screen_snapshot.csv", "market_breadth.csv"]
        report = rsc.resolve_release_session(self.root, order)
        self.assertEqual([r.name for r in report.results], order)
        lines = report.mismatch_lines()
        # screen_snapshot_live.csv (07-03) must be reported before screen_snapshot.csv
        # (07-01), matching `order`, not sorted() which would reverse them.
        self.assertLess(
            next(i for i, l in enumerate(lines) if "screen_snapshot_live.csv" in l),
            next(i for i, l in enumerate(lines) if l.startswith("  screen_snapshot.csv")),
        )


if __name__ == "__main__":
    unittest.main()
