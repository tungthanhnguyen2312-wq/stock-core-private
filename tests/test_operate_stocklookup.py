"""The one supported operating command: gating, rollback, dry-run purity and lock behaviour.

Every subprocess is replaced by a recording fake, so these tests assert the command's own
contract (what it refuses, what order it runs things in, what it restores) without running
the real pipeline.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import operate_stocklookup as operate  # noqa: E402

SESSION = "2026-07-30"
GENERATED_AT = "2026-07-30T10:00:00+00:00"


def _runtime(root: Path) -> Path:
    (root / "data_bctc").mkdir(parents=True, exist_ok=True)
    (root / "data_bctc" / "AAA_balance_sheet_quarter.parquet").write_bytes(b"payload")
    for name in operate.REQUIRED_UPSTREAM:
        if name != "vn_stock.db":
            (root / name).write_text("upstream", encoding="utf-8")
    connection = sqlite3.connect(root / "vn_stock.db")
    connection.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT)")
    connection.execute("INSERT INTO ohlcv VALUES ('HPG', ?)", (SESSION,))
    connection.commit()
    connection.close()
    return root


def _artifacts(root: Path, *, session=SESSION, generated_at=GENERATED_AT, bundle_text=None):
    bundle_text = bundle_text if bundle_text is not None else json.dumps({
        "generated_at": generated_at, "reference_session_date": session,
        "price_basis": "unknown", "price_basis_verified": False, "is_actionable": False,
        "tickers": {"HPG": {"snapshot": {"date": session}}},
    })
    (root / "analysis_bundle.json").write_text(bundle_text, encoding="utf-8")
    (root / "focus_extract.json").write_text(json.dumps({"reference_session_date": session}), encoding="utf-8")
    (root / operate.SIDECAR_FILENAME).write_text(json.dumps({"schema_version": "1.0.0", "records": []}), encoding="utf-8")
    required = [{"file": name, "sha256": operate._sha256(root / name)}
                for name in sorted(("analysis_bundle.json", "focus_extract.json", operate.SIDECAR_FILENAME))]
    (root / "bundle_manifest.json").write_text(json.dumps({
        "generated_at": generated_at,
        "trusted_subset": {"session_identity": session, "tickers": ["HPG"],
                            "unproven_tickers": [], "required_artifacts": required,
                            "bundle_reference_session_date": session},
    }), encoding="utf-8")


class RecordingRunner:
    """Stands in for subprocess.run; every invocation succeeds unless configured to fail."""

    def __init__(self, fail_on: str | None = None, side_effect=None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.side_effect = side_effect

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        joined = " ".join(str(part) for part in command)
        if self.side_effect:
            self.side_effect(joined)
        failed = self.fail_on and self.fail_on in joined
        return SimpleNamespace(returncode=1 if failed else 0,
                               stdout="" if failed else "ok", stderr="boom" if failed else "")

    def names(self) -> list[str]:
        return [Path(c[1]).name if len(c) > 1 else c[0] for c in self.calls]


class OperatorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = _runtime(Path(tmp.name))
        _artifacts(self.root)

    def _operator(self, runner, **kwargs):
        params = {"execute": True, "publish": False, "live": False}
        params.update(kwargs)
        return operate.Operator(self.root, ["HPG", "VNM"], runner=runner, **params)

    # ---------------------------------------------------------------- dry run
    def test_dry_run_writes_nothing_and_publishes_nothing(self):
        runner = RecordingRunner()
        before = {p.name: p.read_bytes() for p in self.root.glob("*.json")}
        self.assertEqual(self._operator(runner, execute=False, publish=True).run(), 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.glob("*.json")}, before)
        self.assertFalse((self.root / "reports").exists())
        self.assertNotIn("publish_dashboard.py", runner.names())
        self.assertNotIn("export_ai_bundle.py", runner.names())

    # ---------------------------------------------------------------- ordering
    def test_sidecar_is_built_before_the_export_that_binds_it(self):
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner).run(), 0)
        names = runner.names()
        self.assertLess(names.index("build_statement_taxonomy_sidecar.py"), names.index("export_ai_bundle.py"))

    def test_publishing_only_happens_after_verification_and_consumer_validation(self):
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner, publish=True).run(), 0)
        joined = [" ".join(c) for c in runner.calls]
        publish = next(i for i, c in enumerate(joined) if "publish_dashboard.py" in c)
        verify = next(i for i, c in enumerate(joined) if "--verify" in c)
        consumer = next(i for i, c in enumerate(joined) if "load_optional_analysis_bundle" in c)
        self.assertLess(verify, publish)
        self.assertLess(consumer, publish)

    def test_live_publish_passes_live_and_dry_run_does_not(self):
        (self.root / "data").mkdir(exist_ok=True)
        (self.root / "data" / "build_info.json").write_text("{}", encoding="utf-8")
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner, publish=True, live=True).run(), 0)
        publish_call = next(c for c in runner.calls if "publish_dashboard.py" in " ".join(c))
        self.assertIn("--live", publish_call)
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner, publish=True).run(), 0)
        publish_call = next(c for c in runner.calls if "publish_dashboard.py" in " ".join(c))
        self.assertNotIn("--live", publish_call)

    def test_input_preparation_is_opt_in_and_never_fetches_market_data(self):
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner).run(), 0)
        self.assertNotIn("candle_scan.py", runner.names())
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner, prepare=True).run(), 0)
        names = runner.names()
        self.assertIn("candle_scan.py", names)
        for forbidden in ("vn_stock_pipeline.py", "macro_sync.py", "news_sync.py", "meta_sync.py"):
            self.assertNotIn(forbidden, names)
        self.assertTrue((self.root / "reports" / "operate_rollback").exists())

    # ---------------------------------------------------------------- gates
    def test_missing_upstream_artifact_blocks_before_anything_runs(self):
        (self.root / "market_breadth.csv").unlink()
        runner = RecordingRunner()
        self.assertEqual(self._operator(runner).run(), 1)
        self.assertEqual(runner.calls, [])

    def test_a_manifest_without_a_proof_fails_the_session_artifact_gate(self):
        def strip_proof(joined):
            if "export_ai_bundle.py" in joined and "--verify" not in joined:
                (self.root / "bundle_manifest.json").write_text(json.dumps({"generated_at": GENERATED_AT}), encoding="utf-8")
        self.assertEqual(self._operator(RecordingRunner(side_effect=strip_proof)).run(), 1)

    def test_an_artifact_changed_after_the_manifest_fails_the_hash_gate(self):
        def tamper(joined):
            if "export_ai_bundle.py" in joined and "--verify" not in joined:
                (self.root / "focus_extract.json").write_text('{"tampered":true}', encoding="utf-8")
        self.assertEqual(self._operator(RecordingRunner(side_effect=tamper)).run(), 1)

    def test_a_bundle_claiming_actionable_output_on_an_unverified_basis_fails_the_smoke_check(self):
        def rewrite(joined):
            if "export_ai_bundle.py" in joined and "--verify" not in joined:
                _artifacts(self.root, bundle_text=json.dumps({
                    "generated_at": GENERATED_AT, "reference_session_date": SESSION,
                    "price_basis": "unknown", "price_basis_verified": False, "is_actionable": True,
                    "tickers": {"HPG": {"snapshot": {"date": SESSION}}}}))
        operator = self._operator(RecordingRunner(side_effect=rewrite))
        self.assertEqual(operator.run(), 1)
        report = json.loads((self.root / "reports" / "operate_stocklookup_latest.json").read_text(encoding="utf-8"))
        self.assertEqual(report["failed_gate"], "post_publish_smoke")

    def test_consumer_rejection_stops_the_run_before_publishing(self):
        runner = RecordingRunner(fail_on="load_optional_analysis_bundle")
        self.assertEqual(self._operator(runner, publish=True).run(), 1)
        self.assertNotIn("publish_dashboard.py", runner.names())

    # ---------------------------------------------------------------- rollback
    def test_a_failed_run_restores_the_previous_artifact_set(self):
        before = {name: (self.root / name).read_bytes() for name in operate.PRODUCTION_ARTIFACTS}

        def replace_then_fail(joined):
            if "export_ai_bundle.py" in joined and "--verify" not in joined:
                (self.root / "analysis_bundle.json").write_text('{"new":"session"}', encoding="utf-8")

        runner = RecordingRunner(fail_on="--verify", side_effect=replace_then_fail)
        self.assertEqual(self._operator(runner).run(), 1)
        after = {name: (self.root / name).read_bytes() for name in operate.PRODUCTION_ARTIFACTS}
        self.assertEqual(after, before)
        report = json.loads((self.root / "reports" / "operate_stocklookup_latest.json").read_text(encoding="utf-8"))
        self.assertTrue(report["rollback"]["performed"])
        self.assertIn("analysis_bundle.json", report["rollback"]["restored"])

    def test_an_artifact_that_did_not_exist_before_is_removed_not_left_behind(self):
        (self.root / operate.SIDECAR_FILENAME).unlink()
        _artifacts(self.root)
        (self.root / operate.SIDECAR_FILENAME).unlink()

        def create_sidecar(joined):
            if "build_statement_taxonomy_sidecar.py" in joined:
                (self.root / operate.SIDECAR_FILENAME).write_text("{}", encoding="utf-8")

        runner = RecordingRunner(fail_on="export_ai_bundle.py", side_effect=create_sidecar)
        self.assertEqual(self._operator(runner).run(), 1)
        self.assertFalse((self.root / operate.SIDECAR_FILENAME).exists())

    # ---------------------------------------------------------------- report
    def test_the_operating_report_records_every_artifact_hash_and_no_absolute_path(self):
        self.assertEqual(self._operator(RecordingRunner()).run(), 0)
        report = json.loads((self.root / "reports" / "operate_stocklookup_latest.json").read_text(encoding="utf-8"))
        self.assertEqual(report["outcome"], "success")
        self.assertEqual(sorted(report["artifact_sha256"]), sorted(operate.PRODUCTION_ARTIFACTS))
        self.assertNotIn(str(self.root), json.dumps(report))


class InvocationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = _runtime(Path(tmp.name))
        _artifacts(self.root)

    def test_unusable_runtime_root_and_bad_flag_combinations_exit_two(self):
        runner = RecordingRunner()
        self.assertEqual(operate.main(["--runtime-root", str(self.root / "nope")], runner=runner), 2)
        self.assertEqual(operate.main(["--runtime-root", str(self.root), "--live"], runner=runner), 2)
        self.assertEqual(operate.main(["--runtime-root", str(self.root), "--publish", "--live"], runner=runner), 2)
        self.assertEqual(operate.main(["--runtime-root", str(self.root), "--prepare-inputs"], runner=runner), 2)
        self.assertEqual(operate.main(["--runtime-root", str(self.root), "--tickers", " , "], runner=runner), 2)
        self.assertEqual(runner.calls, [])

    def test_a_second_instance_is_refused_while_the_lock_is_held(self):
        from pipeline_scheduler import PipelineLock
        with PipelineLock(self.root / "locks" / "pipeline.lock"):
            self.assertEqual(operate.main(["--runtime-root", str(self.root), "--execute"],
                                          runner=RecordingRunner()), 3)


if __name__ == "__main__":
    unittest.main()
