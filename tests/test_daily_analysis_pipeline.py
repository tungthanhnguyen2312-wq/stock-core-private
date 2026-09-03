from __future__ import annotations
import contextlib, io, json, os, sqlite3, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import canonical_daily_operation as cdo
import daily_analysis_pipeline as pipeline
import export_ai_bundle as exporter

class PipelineTests(unittest.TestCase):
    def make_upstream(self, root):
        for name in pipeline.REQUIRED[:-2]:
            (root/name).write_text("{}" if name.endswith(".json") else "x", encoding="utf-8")
        stamp=1700000000
        for name in pipeline.REQUIRED[:-2]: os.utime(root/name,(stamp,stamp))
    def test_order_root_and_watchlist_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="daily runtime ") as raw:
            calls=[]
            def fake(cmd, **kw): calls.append((cmd,kw)); return SimpleNamespace(returncode=0)
            with mock.patch.object(pipeline,"upstream_ok",return_value=(True,{})),mock.patch.object(pipeline,"inspect",return_value={}),mock.patch.object(pipeline,"enrich"):
                self.assertEqual(pipeline.main(["--runtime-root",raw,"--tickers","AAA","BBB"],fake),0)
            self.assertEqual(
                [Path(x[0][1]).name for x in calls[:-1]],
                ["vn_stock_pipeline.py","macro_sync.py","news_sync.py","vn_indicators.py","candle_scan.py","stock_analyzer.py","stock_analyzer.py","stock_analyzer.py","export_ai_bundle.py"],
            )
            self.assertTrue(all(str(pipeline.SCRIPT_DIR) in x[0][1] for x in calls[:-1]))
            self.assertEqual(calls[7][0][-2:],["AAA","BBB"]); self.assertEqual(calls[8][0][-1],"AAA,BBB")
            self.assertTrue(all(x[1]["env"][pipeline.RUNTIME_ROOT_ENV]==str(Path(raw).resolve()) for x in calls))
    def test_fail_fast(self):
        with tempfile.TemporaryDirectory() as raw:
            calls=[]
            def fake(cmd,**kw): calls.append(cmd); return SimpleNamespace(returncode=9 if len(calls)==2 else 0)
            self.assertEqual(pipeline.main(["--runtime-root",raw],fake),1); self.assertEqual(len(calls),2)
    def test_stale_blocks_export(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); self.make_upstream(root); os.utime(root/"ta_signals.csv",(1700000001,1700000001)); calls=[]
            def fake(cmd,**kw): calls.append(cmd); return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.main(["--runtime-root",raw,"--skip-price-update","--skip-macro","--skip-news"],fake),1)
            self.assertNotIn("export_ai_bundle.py",[Path(x[1]).name for x in calls])
    def test_verify_only(self):
        with tempfile.TemporaryDirectory() as raw:
            calls=[]
            def fake(cmd,**kw): calls.append(cmd); return SimpleNamespace(returncode=0)
            with mock.patch.object(pipeline,"upstream_ok",return_value=(True,{})),mock.patch.object(pipeline,"inspect",return_value={}),mock.patch.object(pipeline,"enrich"):
                self.assertEqual(pipeline.main(["--runtime-root",raw,"--verify-only"],fake),0)
            self.assertEqual(len(calls),1); self.assertIn("--verify",calls[0])
    def test_exporter_default_output_uses_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="runtime output ") as raw:
            with mock.patch.dict(os.environ, {exporter.RUNTIME_ROOT_ENV: raw}, clear=False):
                self.assertEqual(exporter.output_path(".").resolve(), Path(raw).resolve())
    def test_integration_writes_canonical_manifest_only_in_temp_runtime(self):
        with tempfile.TemporaryDirectory(prefix="daily runtime integration ") as raw:
            root = Path(raw); self.make_upstream(root); calls = []
            def fake(command, **kwargs):
                calls.append((command, kwargs))
                if Path(command[1]).name == "export_ai_bundle.py" and "--verify" not in command:
                    (root / "analysis_bundle.json").write_text(json.dumps({"reference_session_date": "2026-07-22"}), encoding="utf-8")
                    (root / "bundle_manifest.json").write_text(json.dumps({"files": []}), encoding="utf-8")
                return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.main(["--runtime-root", str(root), "--tickers", "AAA", "BBB"], fake), 0)
            manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.2.0")
            self.assertEqual(manifest["runtime_root"], str(root.resolve()))
            self.assertEqual(manifest["session_date"], "2026-07-22")
            self.assertEqual(manifest["daily_analysis"]["watchlist"], ["AAA", "BBB"])
            self.assertEqual([x["name"] for x in manifest["daily_analysis"]["command_step_order"]], ["price_update", "macro_sync", "news_sync", "indicators", "candle_scan", "strategy_all", "market_scan", "focus_analysis", "export_bundle", "verify_bundle"])
            for step in manifest["daily_analysis"]["command_step_order"]:
                self.assertEqual(step["exit_code"], 0); self.assertIn("started_at", step); self.assertIn("ended_at", step); self.assertIn("duration_seconds", step)
            item = manifest["artifact_verification"]["screen_snapshot.csv"]
            self.assertEqual(item["path"], str(root / "screen_snapshot.csv")); self.assertIn("size", item); self.assertIn("modified_time", item); self.assertIn("sha256", item)
            self.assertEqual(manifest["overall_verification_result"], "passed")
            self.assertFalse((pipeline.SCRIPT_DIR / "analysis_bundle.json").exists())
            self.assertTrue(all(call[1]["env"][pipeline.RUNTIME_ROOT_ENV] == str(root.resolve()) for call in calls))

    def test_stale_market_scan_focus_ta_and_snapshot_block_export(self):
        for stale, dependency in (("Market_Scan.csv", "screen_snapshot_live.csv"), ("Focus_Analysis.md", "macro_snapshot.csv"), ("ta_signals.csv", "screen_snapshot.csv")):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); self.make_upstream(root); os.utime(root / dependency, (1700000001, 1700000001)); calls=[]
                def fake(command, **kwargs): calls.append(command); return SimpleNamespace(returncode=0)
                self.assertEqual(pipeline.main(["--runtime-root", raw, "--skip-price-update", "--skip-macro", "--skip-news"], fake), 1)
                self.assertNotIn("export_ai_bundle.py", [Path(x[1]).name for x in calls])

    def make_metadata_db(self, root, updated_value):
        conn = sqlite3.connect(root / "vn_stock.db")
        conn.execute("CREATE TABLE metadata(ticker TEXT PRIMARY KEY, updated TEXT)")
        conn.execute("INSERT INTO metadata(ticker, updated) VALUES ('AAA', ?)", (updated_value,))
        conn.commit(); conn.close()

    def test_stale_vnstock_metadata_snapshot_blocks_export(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); self.make_upstream(root); self.make_metadata_db(root, "2000-01-01 00:00"); calls=[]
            def fake(cmd,**kw): calls.append(cmd); return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.main(["--runtime-root",raw,"--skip-price-update","--skip-macro","--skip-news"],fake),1)
            self.assertNotIn("export_ai_bundle.py",[Path(x[1]).name for x in calls])

    def test_fresh_vnstock_metadata_snapshot_does_not_block_export(self):
        with tempfile.TemporaryDirectory(prefix="daily runtime fresh meta ") as raw:
            root=Path(raw); self.make_upstream(root)
            fresh = pipeline.datetime.now(pipeline.timezone.utc).strftime("%Y-%m-%d %H:%M")
            self.make_metadata_db(root, fresh)
            def fake(command,**kwargs):
                if Path(command[1]).name=="export_ai_bundle.py" and "--verify" not in command:
                    (root/"analysis_bundle.json").write_text(json.dumps({"reference_session_date":"2026-07-27"}),encoding="utf-8")
                    (root/"bundle_manifest.json").write_text(json.dumps({"files":[]}),encoding="utf-8")
                return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.main(["--runtime-root",str(root),"--tickers","AAA"],fake),0)
            manifest=json.loads((root/"bundle_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["subsource_freshness"]["blocked"])
            self.assertEqual(manifest["subsource_freshness"]["sources"]["vnstock_metadata_snapshot"]["freshness_status"],"current")

    def test_failure_prevents_export_verify_and_partial_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); self.make_upstream(root); calls=[]
            def fake(command, **kwargs):
                calls.append(command); return SimpleNamespace(returncode=17 if Path(command[1]).name == "candle_scan.py" else 0)
            self.assertEqual(pipeline.main(["--runtime-root", raw], fake), 1)
            self.assertNotIn("export_ai_bundle.py", [Path(x[1]).name for x in calls]); self.assertFalse((root / "bundle_manifest.json").exists())

    def test_verify_only_does_not_rewrite_manifest(self):
        with tempfile.TemporaryDirectory(prefix="verify only ") as raw:
            root=Path(raw); self.make_upstream(root)
            (root / "analysis_bundle.json").write_text("{}", encoding="utf-8"); manifest=root / "bundle_manifest.json"; manifest.write_text("{\"files\": []}", encoding="utf-8"); before=manifest.read_bytes(); calls=[]
            def fake(command, **kwargs): calls.append(command); return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.main(["--runtime-root", raw, "--verify-only"], fake), 0)
            self.assertEqual(manifest.read_bytes(), before); self.assertEqual(len(calls), 1); self.assertIn("--verify", calls[0])

    def test_skip_flags_remove_only_requested_steps(self):
        args=pipeline.parse(["--runtime-root", "x", "--skip-price-update", "--skip-news"])
        names=[name for name, _ in pipeline.steps(args, ["POW"])]
        self.assertNotIn("price_update", names); self.assertNotIn("news_sync", names); self.assertIn("macro_sync", names); self.assertEqual(names[-1], "export_bundle")

    def test_exporter_verify_manifest_match_and_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="exporter verify ") as raw:
            root=Path(raw); source=root / "source.csv"; source.write_text("one", encoding="utf-8")
            manifest=root / "manifest.json"; manifest.write_text(json.dumps({"files": [{"file": "source.csv", "sha256": exporter.sha256_file(source)}]}), encoding="utf-8")
            self.assertEqual(exporter.verify_manifest(manifest, root), [])
            source.write_text("two", encoding="utf-8")
            self.assertEqual(exporter.verify_manifest(manifest, root)[0]["issue"], "sha256_changed")
    def test_manifest_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); self.make_upstream(root); (root/"analysis_bundle.json").write_text(json.dumps({"reference_session_date":"2026-07-22"}),encoding="utf-8"); (root/"bundle_manifest.json").write_text("{}",encoding="utf-8")
            pipeline.enrich(root,["POW"],[{"name":"x"}],pipeline.inspect(root)); data=json.loads((root/"bundle_manifest.json").read_text(encoding="utf-8")); item=data["artifact_verification"]["screen_snapshot.csv"]
            self.assertEqual(data["overall_verification_result"],"passed"); self.assertIn("sha256",item); self.assertIn("modified_time",item); self.assertIn("dependency_status",item)

    def test_publish_dashboard_step_flag(self):
        args = pipeline.parse(["--runtime-root", "x", "--publish-dashboard", "--live-publish"])
        names = [name for name, cmd in pipeline.steps(args, ["POW"])]
        self.assertIn("publish_dashboard", names)
        cmd = dict(pipeline.steps(args, ["POW"]))["publish_dashboard"]
        self.assertIn("--live", cmd)

    def test_observability_events_emitted_on_pipeline_run(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            logs_dir = root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            record = pipeline.run("test_step", [pipeline.sys.executable, "-c", "import sys; sys.exit(0)"], {}, runner=pipeline.subprocess.run, root=root)
            self.assertEqual(record["exit_code"], 0)
            events_file = logs_dir / "observability_events.jsonl"
            self.assertTrue(events_file.is_file())
            content = events_file.read_text(encoding="utf-8")
            self.assertIn("test_step", content)

class CanonicalPostCloseOwnerStatusTests(unittest.TestCase):
    """DAILY_OWNER_FLOW_POST_CLOSE_STABILIZATION_GATE_V1: --canonical-post-close must never label a
    routine pre-floor or data-lagging run FAILED_PRODUCER-style; it prints a distinct clean status."""

    def _run_with_stage(self, stage, message, local_state):
        def fake_run(*a, **k):
            raise cdo.CanonicalDailyOperationError(stage, message, local_state=local_state)
        with tempfile.TemporaryDirectory() as raw:
            buf = io.StringIO()
            with mock.patch.object(cdo, "run_canonical_daily_operation", fake_run), contextlib.redirect_stdout(buf):
                rc = pipeline.main(["--runtime-root", raw, "--canonical-post-close", "--offline"])
            return rc, buf.getvalue()

    def test_too_early_prints_current_session_stabilizing_not_failed_producer(self):
        rc, out = self._run_with_stage(
            cdo.STAGE_TOO_EARLY, "BEFORE_SAFETY_FLOOR,NO_DEFENSIBLE_INTENDED_SESSION",
            {"phase_a": {"resolved_session": None, "requested_session": None, "safety_floor": "15:30"}},
        )
        self.assertEqual(rc, 2)
        self.assertIn("STOCK LOOKUP DAILY", out)
        self.assertIn("Status: CURRENT_SESSION_STABILIZING", out)
        self.assertIn("Earliest normal daily start: 15:30 Asia/Ho_Chi_Minh", out)
        self.assertIn("Publication: NOT ATTEMPTED", out)
        self.assertNotIn("FAILED_PRODUCER", out)

    def test_post_close_data_not_ready_is_distinct_from_too_early(self):
        rc, out = self._run_with_stage(
            cdo.STAGE_BLOCKED_POST_ACQUISITION, "P3F9B_EXACT_SESSION_COVERAGE_INSUFFICIENT",
            {"phase_a": {"resolved_session": "2026-09-03"},
             "phase_b": {"reason_codes": ["P3F9B_EXACT_SESSION_COVERAGE_INSUFFICIENT"]}},
        )
        self.assertEqual(rc, 2)
        self.assertIn("Status: POST_CLOSE_DATA_NOT_READY", out)
        self.assertIn("Session: 2026-09-03", out)
        self.assertIn("Publication: BLOCKED", out)
        self.assertNotIn("CURRENT_SESSION_STABILIZING", out)
        self.assertNotIn("FAILED_PRODUCER", out)

    def test_acquisition_not_ready_also_exits_2_not_1(self):
        # STAGE_BLOCKED_ACQUISITION is the other post-floor "not ready" stage (e.g. same-day
        # partial/intraday evidence, the 17/1683 shape) -- must not be conflated with a hard
        # pipeline failure.
        rc, out = self._run_with_stage(cdo.STAGE_BLOCKED_ACQUISITION, "PARTIAL_OR_INTRADAY_SESSION_EVIDENCE:exact=17:total=1683:ratio=0.0101:floor=0.2", {})
        self.assertEqual(rc, 2)
        self.assertIn("Status: POST_CLOSE_DATA_NOT_READY", out)
        self.assertIn("Publication: BLOCKED", out)
        self.assertNotIn("FAILED_PRODUCER", out)
        self.assertNotIn("FAILED_ACQUISITION_PIPELINE", out)

    def test_genuine_pipeline_defect_still_exits_1_with_stage_named(self):
        rc, out = self._run_with_stage(cdo.STAGE_BLOCKED_DAILY_PRODUCER, "DAILY_PRODUCER_STATUS:FAILED", {})
        self.assertEqual(rc, 1)
        self.assertIn(f"Status: {cdo.STAGE_BLOCKED_DAILY_PRODUCER}", out)

    def test_unexpected_acquisition_exception_reports_genuine_failure_not_data_not_ready(self):
        # DAILY_LIVE_ACQUISITION_FAIL_FAST_AND_ZERO_RECOVERY_CORRECTIVE_V1 defect 3: today's real
        # 2026-09-03 incident -- a FileNotFoundError inside acquire_and_materialize -- must print
        # as a genuine pipeline failure and exit 1, never as routine POST_CLOSE_DATA_NOT_READY.
        rc, out = self._run_with_stage(
            cdo.STAGE_FAILED_ACQUISITION_PIPELINE,
            "FileNotFoundError:[Errno 2] No such file or directory: "
            "'market_wide_current_technical_coverage_recovery_artifact.json'",
            {"phase_a": {"resolved_session": "2026-09-03"}},
        )
        self.assertEqual(rc, 1)
        self.assertIn(f"Status: {cdo.STAGE_FAILED_ACQUISITION_PIPELINE}", out)
        self.assertIn("FileNotFoundError", out)
        self.assertIn("RECOVERY_ACTION", out)
        self.assertNotIn("POST_CLOSE_DATA_NOT_READY", out)
        self.assertNotIn("CURRENT_SESSION_STABILIZING", out)


if __name__ == "__main__": unittest.main()
