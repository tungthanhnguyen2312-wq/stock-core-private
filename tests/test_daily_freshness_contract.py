"""The daily pipeline's freshness dependency contract.

    metadata / current-share refresh
    -> focus analysis
    -> context packages
    -> AI bundle export
    -> Consumer exact-session validation
    -> optional live publish

Each stage consumes what the one before it produced. Running a stage on a predecessor's stale
output yields an artifact that is internally consistent and describes two different sessions,
which is the failure mode these tests exist to make impossible. Every subprocess is a
recording fake and every runtime is a temporary copy, so nothing here touches production.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import official_source_registry as registry  # noqa: E402
import operate_stocklookup as operate  # noqa: E402

SESSION = "2026-08-03"
PRIOR = "2026-07-30"
TICKERS = ["HPG", "VNM"]


class RecordingRunner:
    """Stands in for subprocess.run; every invocation succeeds unless configured to fail."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, command, **kwargs):
        self.calls.append([str(part) for part in command])
        joined = " ".join(str(part) for part in command)
        failed = bool(self.fail_on and self.fail_on in joined)
        return SimpleNamespace(returncode=1 if failed else 0,
                               stdout="" if failed else "ok", stderr="boom" if failed else "")

    def names(self) -> list[str]:
        return [Path(call[1]).name if len(call) > 1 else call[0] for call in self.calls]

    def index_of(self, needle: str) -> int:
        for position, call in enumerate(self.calls):
            if needle in " ".join(call):
                return position
        return -1


def _write_focus_analysis(root: Path, session: str) -> None:
    """The exporter parses the session out of one specific sentence; match it exactly."""
    (root / "Focus_Analysis.md").write_text(
        "# Phan tich sau\n\n"
        f"*Sinh boi `stock_analyzer.py` luc {session} 17:02 - phiên snapshot mới nhất: "
        f"**{session}** - nguon: kho local.*\n\n## HPG\n\n## VNM\n", encoding="utf-8")


def _build_runtime(root: Path, *, session: str, shares_observed: str,
                   focus_session: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "data_bctc").mkdir(parents=True, exist_ok=True)
    (root / "data_bctc" / "AAA_balance_sheet_quarter.parquet").write_bytes(b"payload")
    for name in operate.REQUIRED_UPSTREAM:
        if name != "vn_stock.db":
            (root / name).write_text("upstream", encoding="utf-8")
    _write_focus_analysis(root, focus_session)

    evidence = root / "data" / "official-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "share_basis_citations.jsonl").write_text("", encoding="utf-8")

    connection = sqlite3.connect(root / "vn_stock.db")
    connection.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT)")
    connection.executemany("INSERT INTO ohlcv VALUES (?, ?)",
                           [(ticker, session) for ticker in TICKERS])
    connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
    connection.executemany("INSERT INTO metadata VALUES (?, ?, ?)",
                           [(ticker, 1000.0, f"{shares_observed} 17:00") for ticker in TICKERS])
    connection.execute("CREATE TABLE corporate_event_records "
                       "(ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
    connection.commit()
    connection.close()
    return root


def _write_artifacts(root: Path, session: str) -> None:
    generated_at = f"{session}T10:00:00+00:00"
    (root / "analysis_bundle.json").write_text(json.dumps({
        "generated_at": generated_at, "reference_session_date": session,
        "price_basis": "unknown", "price_basis_verified": False, "is_actionable": False,
        "tickers": {"HPG": {"snapshot": {"date": session}}},
    }), encoding="utf-8")
    (root / "focus_extract.json").write_text(
        json.dumps({"reference_session_date": session}), encoding="utf-8")
    (root / operate.SIDECAR_FILENAME).write_text(
        json.dumps({"schema_version": "1.0.0", "records": []}), encoding="utf-8")
    required = [{"file": name, "sha256": operate._sha256(root / name)}
                for name in sorted(("analysis_bundle.json", "focus_extract.json",
                                    operate.SIDECAR_FILENAME))]
    (root / "bundle_manifest.json").write_text(json.dumps({
        "generated_at": generated_at,
        "trusted_subset": {"session_identity": session, "tickers": ["HPG"],
                           "unproven_tickers": [], "required_artifacts": required,
                           "bundle_reference_session_date": session},
    }), encoding="utf-8")


def _write_context_packages(directory: Path, session: str, tickers=TICKERS) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        (directory / f"{ticker}_context.json").write_text(json.dumps({
            "ticker": ticker,
            "generated_at": f"{session}T11:00:00+00:00",
            "latest_available_dates": {"price": session, "technical": session},
        }), encoding="utf-8")


class DailyChainTestCase(unittest.TestCase):
    """A frozen, fully aligned session, with each fixture individually de-alignable."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = _build_runtime(self.base / "runtime", session=SESSION,
                                   shares_observed=SESSION, focus_session=SESSION)
        _write_artifacts(self.root, SESSION)
        self.packages = self.base / "context_packages"
        _write_context_packages(self.packages, SESSION)
        self.served = self.base / "served"
        self.served.mkdir()

        previous = os.environ.get(operate.__dict__.get("_CTX_ENV", "STOCK_LOOKUP_CONTEXT_PACKAGES_DIR"))
        os.environ["STOCK_LOOKUP_CONTEXT_PACKAGES_DIR"] = str(self.packages)
        self.addCleanup(self._restore_env, previous)

    @staticmethod
    def _restore_env(previous):
        if previous is None:
            os.environ.pop("STOCK_LOOKUP_CONTEXT_PACKAGES_DIR", None)
        else:
            os.environ["STOCK_LOOKUP_CONTEXT_PACKAGES_DIR"] = previous

    def operator(self, runner, **kwargs):
        params = {"execute": True, "publish": False, "live": False}
        params.update(kwargs)
        if params.get("publish"):
            params.setdefault("web_root", self.served)
        return operate.Operator(self.root, list(TICKERS), runner=runner, **params)


class StageOrderTests(DailyChainTestCase):
    def test_the_aligned_session_runs_every_stage_in_dependency_order(self) -> None:
        runner = RecordingRunner()
        operator = self.operator(runner, refresh_metadata=True, prepare=True, publish=True)
        self.assertEqual(operator.run(), 0)

        order = [runner.index_of(marker) for marker in
                 ("meta_sync.py", "candle_scan.py", "build_ticker_context.py",
                  "export_ai_bundle.py", "publish_release.py")]
        self.assertNotIn(-1, order, f"a stage never ran: {runner.names()}")
        self.assertEqual(order, sorted(order), f"stages ran out of order: {runner.names()}")

    def test_metadata_is_refreshed_before_focus_analysis_and_context_packages(self) -> None:
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner, refresh_metadata=True, prepare=True).run(), 0)
        metadata = runner.index_of("meta_sync.py")
        focus = runner.index_of("stock_analyzer.py")
        context = runner.index_of("build_ticker_context.py")
        self.assertLess(metadata, focus)
        self.assertLess(focus, context)

    def test_focus_analysis_is_rebuilt_before_context_packages(self) -> None:
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner, prepare=True).run(), 0)
        self.assertLess(runner.index_of("stock_analyzer.py"),
                        runner.index_of("build_ticker_context.py"))

    def test_context_packages_are_rebuilt_before_the_export(self) -> None:
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner, prepare=True).run(), 0)
        self.assertLess(runner.index_of("build_ticker_context.py"),
                        runner.index_of("export_ai_bundle.py"))

    def test_metadata_is_never_refreshed_without_the_flag(self) -> None:
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner, prepare=True).run(), 0)
        self.assertNotIn("meta_sync.py", runner.names())

    def test_one_restorable_database_copy_covers_both_writing_stages(self) -> None:
        runner = RecordingRunner()
        operator = self.operator(runner, refresh_metadata=True, prepare=True)
        self.assertEqual(operator.run(), 0)
        taken = [step for step in operator.steps if step["step"] == "database_backup"]
        skipped = [step for step in operator.steps
                   if step["step"] == "backup_database" and step["status"] == "skipped"]
        self.assertEqual(len(taken), 1, "the pre-run database copy must be taken exactly once")
        self.assertEqual(len(skipped), 1, "the second writing stage must not overwrite it")


class ShareFreshnessGateTests(DailyChainTestCase):
    def _lagged_root(self) -> Path:
        root = _build_runtime(self.base / "lagged", session=SESSION,
                              shares_observed=PRIOR, focus_session=SESSION)
        _write_artifacts(root, SESSION)
        return root

    def test_lagged_shares_fail_before_the_export_when_they_reach_the_artifact(self) -> None:
        runner = RecordingRunner()
        operator = operate.Operator(self._lagged_root(), list(TICKERS), execute=True,
                                    publish=False, live=False,
                                    include_canonical_financial_facts=True, runner=runner)
        self.assertEqual(operator.run(), 1)
        failure = next(s for s in operator.steps if s["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_share_freshness")
        self.assertNotIn("export_ai_bundle.py", runner.names())

    def test_the_failure_names_the_remediation(self) -> None:
        runner = RecordingRunner()
        operator = operate.Operator(self._lagged_root(), list(TICKERS), execute=True,
                                    publish=False, live=False,
                                    include_canonical_financial_facts=True, runner=runner)
        operator.run()
        report = operator.report("failed", None, None)
        detail = next(s for s in report["steps"] if s["step"] == "preflight_share_freshness")
        self.assertEqual(detail["provider_reported_lagged_count"], len(TICKERS))
        self.assertEqual(detail["shares_observation_date"], PRIOR)
        self.assertEqual(detail["reference_session"], SESSION)

    def test_lag_is_allowed_only_where_it_cannot_reach_the_artifact(self) -> None:
        """The default bundle carries no share-derived value, so lag cannot enter it."""
        runner = RecordingRunner()
        operator = operate.Operator(self._lagged_root(), list(TICKERS), execute=True,
                                    publish=False, live=False, runner=runner)
        self.assertEqual(operator.run(), 0)
        step = next(s for s in operator.steps if s["step"] == "preflight_share_freshness")
        self.assertEqual(step["status"], "passed")
        self.assertTrue(step["lag_allowed_because"])
        self.assertEqual(step["provider_reported_lagged_count"], len(TICKERS))

    def test_a_lagged_value_is_never_relabelled_as_current(self) -> None:
        runner = RecordingRunner()
        operator = operate.Operator(self._lagged_root(), list(TICKERS), execute=True,
                                    publish=False, live=False, runner=runner)
        operator.run()
        step = next(s for s in operator.steps if s["step"] == "preflight_share_freshness")
        self.assertEqual(step["provider_reported_current_count"], 0)
        self.assertEqual(step["counts"].get("provider_reported_current", 0), 0)

    def test_the_reported_lanes_reconcile_with_the_universe(self) -> None:
        runner = RecordingRunner()
        operator = self.operator(runner)
        operator.run()
        step = next(s for s in operator.steps if s["step"] == "preflight_share_freshness")
        named = ("qualified_official_count", "provider_reported_current_count",
                 "provider_reported_lagged_count", "conflicted_or_unverifiable_count",
                 "unavailable_count", "withheld_other_count")
        self.assertTrue(step["counts_reconcile"])
        self.assertEqual(sum(step[key] for key in named), step["active_universe_count"])


class DerivedInputGateTests(DailyChainTestCase):
    def test_stale_focus_analysis_fails_before_the_export(self) -> None:
        _write_focus_analysis(self.root, PRIOR)
        runner = RecordingRunner()
        operator = self.operator(runner)
        self.assertEqual(operator.run(), 1)
        failure = next(s for s in operator.steps if s["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_derived_session_inputs")
        self.assertEqual(failure["focus_analysis_session"], PRIOR)
        self.assertNotIn("export_ai_bundle.py", runner.names())

    def test_stale_context_packages_fail_before_the_export(self) -> None:
        _write_context_packages(self.packages, PRIOR, tickers=["VNM"])
        runner = RecordingRunner()
        operator = self.operator(runner)
        self.assertEqual(operator.run(), 1)
        failure = next(s for s in operator.steps if s["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_derived_session_inputs")
        self.assertEqual(failure["context_package_sessions"]["VNM"], PRIOR)
        self.assertNotIn("export_ai_bundle.py", runner.names())

    def test_a_missing_context_package_is_stale_not_absent(self) -> None:
        (self.packages / "VNM_context.json").unlink()
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner).run(), 1)

    def test_the_aligned_session_passes_the_gate(self) -> None:
        runner = RecordingRunner()
        operator = self.operator(runner)
        self.assertEqual(operator.run(), 0)
        step = next(s for s in operator.steps
                    if s["step"] == "preflight_derived_session_inputs")
        self.assertEqual(step["status"], "passed")
        self.assertEqual(step["focus_analysis_session"], SESSION)


class IndexSymbolContextPackageTests(DailyChainTestCase):
    """The 2026-08-03 false success.

    `prepare_context_packages_1/2` exited 0 and the export still refused, because the rebuild
    excluded index symbols while `export_ai_bundle.load_context_package_info()` is passed the
    full ticker list. `VNINDEX_context.json` therefore stayed on the previous session, and
    every stage that could have noticed had been told to skip it.
    """

    INDEX = "VNINDEX"

    def _operator_with_index(self, runner, **kwargs):
        params = {"execute": True, "publish": False, "live": False}
        params.update(kwargs)
        return operate.Operator(self.root, [*TICKERS, self.INDEX], runner=runner, **params)

    def test_the_rebuild_covers_index_symbols(self) -> None:
        # The fake runner cannot write packages, so stand in for what the rebuild produces.
        _write_context_packages(self.packages, SESSION, tickers=[*TICKERS, self.INDEX])
        runner = RecordingRunner()
        self.assertEqual(self._operator_with_index(runner, prepare=True).run(), 0)
        context_calls = [call for call in runner.calls
                         if "build_ticker_context.py" in " ".join(call)]
        self.assertTrue(context_calls, "the context-package stage never ran")
        requested = ",".join(" ".join(call) for call in context_calls)
        self.assertIn(self.INDEX, requested,
                      "an index symbol the export's gate checks was never rebuilt")

    def test_a_stale_index_package_fails_the_preflight(self) -> None:
        """Previously this passed the preflight and then failed inside the export."""
        _write_context_packages(self.packages, PRIOR, tickers=[self.INDEX])
        runner = RecordingRunner()
        operator = self._operator_with_index(runner)
        self.assertEqual(operator.run(), 1)
        failure = next(step for step in operator.steps if step["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_derived_session_inputs")
        self.assertEqual(failure["context_package_sessions"][self.INDEX], PRIOR)
        self.assertNotIn("export_ai_bundle.py", runner.names())

    def test_a_missing_index_package_is_not_silently_excused(self) -> None:
        runner = RecordingRunner()
        operator = self._operator_with_index(runner)
        self.assertEqual(operator.run(), 1)
        failure = next(step for step in operator.steps if step["status"] == "failed")
        self.assertEqual(failure["step"], "preflight_derived_session_inputs")
        self.assertIsNone(failure["context_package_sessions"][self.INDEX])

    def test_the_preflight_checks_exactly_what_the_export_checks(self) -> None:
        """The two gates disagreeing is the defect; assert the ticker sets are identical."""
        runner = RecordingRunner()
        operator = self._operator_with_index(runner)
        _write_context_packages(self.packages, SESSION, tickers=[*TICKERS, self.INDEX])
        self.assertEqual(operator.run(), 0)
        step = next(s for s in operator.steps
                    if s["step"] == "preflight_derived_session_inputs")
        self.assertEqual(sorted(step["context_package_sessions"]),
                         sorted([*TICKERS, self.INDEX]))


class FailedStageContainmentTests(DailyChainTestCase):
    def test_nothing_publishes_after_a_failed_stage(self) -> None:
        _write_focus_analysis(self.root, PRIOR)
        runner = RecordingRunner()
        operator = self.operator(runner, publish=True, live=True)
        self.assertEqual(operator.run(), 1)
        self.assertNotIn("publish_release.py", runner.names())

    def test_a_failed_export_stops_the_chain_before_publication(self) -> None:
        runner = RecordingRunner(fail_on="export_ai_bundle.py")
        operator = self.operator(runner, publish=True, live=True)
        self.assertEqual(operator.run(), 1)
        self.assertNotIn("publish_release.py", runner.names())

    def test_a_failed_run_reports_failure_not_success(self) -> None:
        runner = RecordingRunner(fail_on="export_ai_bundle.py")
        operator = self.operator(runner, publish=True)
        self.assertEqual(operator.run(), 1)
        outcomes = {step["step"]: step["status"] for step in operator.steps}
        self.assertEqual(outcomes.get("export_analysis_bundle"), "failed")
        self.assertNotIn("post_publish_smoke", outcomes)

    def test_live_publication_needs_the_flag_and_every_prior_gate(self) -> None:
        runner = RecordingRunner()
        self.assertEqual(self.operator(runner, publish=True, live=False).run(), 0)
        publish = next(call for call in runner.calls if "publish_release.py" in " ".join(call))
        self.assertNotIn("--live", publish)

    def test_refresh_metadata_is_refused_without_execute(self) -> None:
        code = operate.main(["--runtime-root", str(self.root), "--refresh-metadata"],
                            runner=RecordingRunner())
        self.assertEqual(code, 2)


class DryRunPurityTests(DailyChainTestCase):
    def test_a_dry_run_measures_shares_but_refreshes_nothing(self) -> None:
        runner = RecordingRunner()
        operator = self.operator(runner, execute=False)
        self.assertEqual(operator.run(), 0)
        self.assertNotIn("meta_sync.py", runner.names())
        self.assertNotIn("export_ai_bundle.py", runner.names())
        self.assertTrue(any(s["step"] == "preflight_share_freshness" for s in operator.steps))


class B1ApprovalInstantTests(unittest.TestCase):
    """The recorded instant, and what may be concluded from it.

    `approved_at` is `2026-08-03T14:00:00Z`; the commit that wrote it was created at about
    `07:22Z`. No owner record in the repository states which clock 14:00 was read from, so
    the instant is unverified and stays unverified until the owner says otherwise.
    """

    @staticmethod
    def _state(**overrides) -> dict:
        state = {"state": "APPROVED", "approved_at": "2026-08-03T14:00:00Z"}
        state.update(overrides)
        return {"approval_state": state}

    def test_the_shipped_instant_is_unverified(self) -> None:
        verdict = registry.approval_instant_verdict()
        self.assertEqual(verdict["verdict"], registry.VERDICT_UNVERIFIED)

    def test_a_future_instant_is_unverified(self) -> None:
        verdict = registry.approval_instant_verdict(
            self._state(), now=datetime(2026, 8, 3, 7, 22, tzinfo=timezone.utc))
        self.assertEqual(verdict["verdict"], registry.VERDICT_UNVERIFIED)
        self.assertEqual(verdict["reason"], "approved_at_is_in_the_future")

    def test_waiting_does_not_verify_an_instant(self) -> None:
        """The defect is the missing provenance, and time does not supply it."""
        verdict = registry.approval_instant_verdict(
            self._state(), now=datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(verdict["verdict"], registry.VERDICT_UNVERIFIED)
        self.assertEqual(verdict["reason"], "approved_at_has_no_clock_provenance")

    def test_owner_supplied_provenance_verifies_the_instant(self) -> None:
        state = self._state(**{"approved_at": "2026-08-03T07:00:00+00:00",
                               registry.APPROVAL_PROVENANCE_FIELD:
                                   "owner recorded 14:00 Asia/Ho_Chi_Minh"})
        verdict = registry.approval_instant_verdict(
            state, now=datetime(2026, 8, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(verdict["verdict"], registry.VERDICT_VERIFIED)

    def test_an_unapproved_state_is_pending_not_unverified(self) -> None:
        verdict = registry.approval_instant_verdict(
            {"approval_state": {"state": "AWAITING_OWNER_APPROVAL"}})
        self.assertEqual(verdict["verdict"], registry.VERDICT_PENDING)

    def test_an_unverified_instant_admits_nothing(self) -> None:
        decision = registry.admit("hose", "https://www.hsx.vn/notice.pdf",
                                  "corporate_action_notice")
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_APPROVAL_TIMESTAMP)

    def test_the_registry_summary_carries_the_verdict(self) -> None:
        self.assertEqual(registry.registry_summary()["approval_instant"]["verdict"],
                         registry.VERDICT_UNVERIFIED)


if __name__ == "__main__":
    unittest.main()
