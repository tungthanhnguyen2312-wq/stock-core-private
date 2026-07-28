"""Focused contract tests for the isolated Phase 2E orchestration pilot."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bounded_orchestration_pilot as pilot
import export_ai_bundle as bundle


class IsolatedPathTests(unittest.TestCase):
    def test_rejects_production_or_ancestor_runtime_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            production = root / "dashboard-runtime"
            production.mkdir()
            with self.assertRaises(pilot.PilotError):
                pilot.require_isolated_root(production, production)
            with self.assertRaises(pilot.PilotError):
                pilot.require_isolated_root(root, production)

    def test_bundle_context_path_defaults_and_requires_explicit_override(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bundle.AI_RUNTIME_ROOT_ENV, None)
            os.environ.pop(bundle.CONTEXT_PACKAGES_DIR_ENV, None)
            self.assertEqual(bundle.context_packages_dir(), bundle.AI_RUNTIME_ROOT / "exports" / "context_packages")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {bundle.AI_RUNTIME_ROOT_ENV: tmp}):
            self.assertEqual(bundle.context_packages_dir(), Path(tmp) / "exports" / "context_packages")


class SnapshotGroupContractTests(unittest.TestCase):
    def test_accepts_multiple_reader_validated_records_per_ticker(self):
        groups = {"POW": {"exchange": {}, "industry": {}}, "SSI": {"pe": {}, "pb": {}}}
        pilot.validate_snapshot_ticker_groups(groups, ("POW", "SSI"))

    def test_rejects_missing_or_unexpected_ticker_identities(self):
        with self.assertRaises(pilot.PilotError):
            pilot.validate_snapshot_ticker_groups({"POW": {"exchange": {}}}, ("POW", "SSI"))
        with self.assertRaises(pilot.PilotError):
            pilot.validate_snapshot_ticker_groups({"POW": {"exchange": {}}, "XXX": {"exchange": {}}}, ("POW",))

    def test_rejects_empty_ticker_identity_group(self):
        with self.assertRaises(pilot.PilotError):
            pilot.validate_snapshot_ticker_groups({"POW": {}}, ("POW",))

class AssetOrderTests(unittest.TestCase):
    def _workspace(self, root: Path) -> None:
        for name in ("stock-core-private", "ai-core-private", "dashboard-runtime"):
            (root / name).mkdir()
        for name in pilot.RUNTIME_INPUTS:
            (root / "dashboard-runtime" / name).write_text("x", encoding="utf-8")
        (root / "dashboard-runtime" / "config").mkdir()

    def test_approved_database_and_registry_context_outputs_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence, isolated = root / "evidence", root / "isolated"
            commands, environments = [], []
            def fake_copy_runtime(_source, destination):
                destination.mkdir(parents=True)
                (destination / "vn_stock.db").write_text("db", encoding="utf-8")
            def fake_copy_consumer(_source, destination):
                (destination / "exports" / "context_packages").mkdir(parents=True)
            def fake_run(command, **kwargs):
                commands.append(tuple(command)); environments.append(kwargs["env"])
                if "metadata_registry_export.py" in command[1]:
                    output = Path(command[-1]); (output / "vnstock_metadata_snapshot_test.jsonl").write_text("{}", encoding="utf-8")
            groups = {ticker: {"exchange": {}} for ticker in pilot.DEFAULT_TICKERS}
            with mock.patch.object(pilot, "copy_runtime_inputs", fake_copy_runtime), \
                 mock.patch.object(pilot, "copy_consumer_for_isolation", fake_copy_consumer), \
                 mock.patch.object(pilot, "run_command", fake_run), \
                 mock.patch.object(pilot, "load_snapshot_groups", return_value=groups), \
                 mock.patch.object(pilot, "compare_contexts", return_value={"passed": True}), \
                 mock.patch.object(pilot, "verify_bundle_contract", return_value={"freshness_status": "fresh"}):
                pilot.run_pilot(workspace=root, runtime_root=isolated, evidence_dir=evidence, frozen_at="2026-07-28T10:43:00Z")
            context_root = isolated / "ai-runtime" / "exports" / "context_packages"
            self.assertEqual(Path(commands[1][commands[1].index("--output") + 1]), context_root / "database")
            self.assertEqual(Path(commands[2][commands[2].index("--output") + 1]), context_root / "registry")
            self.assertNotEqual(context_root / "database", context_root / "registry")
            self.assertEqual(Path(environments[-1][bundle.CONTEXT_PACKAGES_DIR_ENV]), context_root / "registry")
    def test_snapshot_failure_skips_both_downstream_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence = root / "evidence"
            isolated = root / "isolated"
            with mock.patch.object(pilot, "copy_runtime_inputs"), mock.patch.object(pilot, "copy_consumer_for_isolation"), \
                 mock.patch.object(pilot, "run_command", side_effect=pilot.PilotError("snapshot blocked")):
                report = pilot.run_pilot(workspace=root, runtime_root=isolated, evidence_dir=evidence,
                                         frozen_at="2026-07-28T10:43:00Z")
            self.assertFalse(report["checks"]["passed"])
            self.assertEqual([asset["status"] for asset in report["assets"]], ["failed", "skipped", "skipped"])

    def test_empty_evidence_directory_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence = root / "evidence"
            evidence.mkdir()
            isolated = root / "isolated"
            with mock.patch.object(pilot, "copy_runtime_inputs"), mock.patch.object(pilot, "copy_consumer_for_isolation"), \
                 mock.patch.object(pilot, "run_command", side_effect=pilot.PilotError("snapshot blocked")):
                report = pilot.run_pilot(workspace=root, runtime_root=isolated, evidence_dir=evidence,
                                         frozen_at="2026-07-28T10:43:00Z")
            self.assertFalse(report["checks"]["passed"])
    def test_preflight_only_evidence_directory_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "01_preflight.json").write_text("{}", encoding="utf-8")
            isolated = root / "isolated"
            with mock.patch.object(pilot, "copy_runtime_inputs"), mock.patch.object(pilot, "copy_consumer_for_isolation"), \
                 mock.patch.object(pilot, "run_command", side_effect=pilot.PilotError("snapshot blocked")):
                report = pilot.run_pilot(workspace=root, runtime_root=isolated, evidence_dir=evidence,
                                         frozen_at="2026-07-28T10:43:00Z")
            self.assertFalse(report["checks"]["passed"])
    def test_evidence_directory_rejects_unexpected_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "unsafe.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaises(pilot.PilotError):
                pilot.run_pilot(workspace=root, runtime_root=root / "isolated", evidence_dir=evidence,
                                frozen_at="2026-07-28T10:43:00Z")
    def test_frozen_clock_and_dependency_order_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._workspace(root)
            evidence = root / "evidence"
            isolated = root / "isolated"
            commands = []
            def fake_copy_runtime(_source, destination):
                destination.mkdir(parents=True)
                (destination / "vn_stock.db").write_text("db", encoding="utf-8")
            def fake_copy_consumer(_source, destination):
                (destination / "exports" / "context_packages").mkdir(parents=True)
                (destination / "exports" / "direct_cli_context_packages").mkdir(parents=True)
            def fake_run(command, **_kwargs):
                commands.append(tuple(command))
                if "metadata_registry_export.py" in command[1]:
                    registry_dir = Path(command[-1])
                    self.assertTrue(registry_dir.is_dir(), "runner must create explicit snapshot output parent")
                    (registry_dir / "vnstock_metadata_snapshot_test.jsonl").write_text(
                        "\n".join("{}" for _ in pilot.DEFAULT_TICKERS), encoding="utf-8")
            with mock.patch.object(pilot, "copy_runtime_inputs", fake_copy_runtime), \
                 mock.patch.object(pilot, "copy_consumer_for_isolation", fake_copy_consumer), \
                 mock.patch.object(pilot, "run_command", fake_run), \
                 mock.patch.object(pilot, "load_snapshot_groups", return_value={ticker: {"exchange": {"ticker": ticker, "field": "exchange"}, "industry": {"ticker": ticker, "field": "industry"}} for ticker in pilot.DEFAULT_TICKERS}), \
                 mock.patch.object(pilot, "compare_contexts", return_value={"passed": True}), \
                 mock.patch.object(pilot, "verify_bundle_contract", return_value={"freshness_status": "fresh"}):
                report = pilot.run_pilot(workspace=root, runtime_root=isolated, evidence_dir=evidence,
                                         frozen_at="2026-07-28T10:43:00Z")
            self.assertTrue(report["checks"]["passed"])
            self.assertEqual([asset["name"] for asset in report["assets"]], ["metadata_snapshot", "ticker_context_packages", "ai_artifact_set"])
            self.assertEqual([asset["dependencies"] for asset in report["assets"]], [(), ("metadata_snapshot",), ("ticker_context_packages",)])
            self.assertTrue(all("2026-07-28T10:43:00Z" in command for command in commands[1:]))


if __name__ == "__main__":
    unittest.main()
