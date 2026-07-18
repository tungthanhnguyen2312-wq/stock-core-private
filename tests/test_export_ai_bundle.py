# ==========================================================================
# TEST cho P0-1 (vn_indicators.py: is_live/days_stale/rs_rating live-only) và
# P0-2/P0-3 (export_ai_bundle.py: focus_extract + manifest + freshness gate).
# Chạy: `python -m unittest discover tests` hoặc `python -m unittest tests.test_export_ai_bundle`.
#
# Test tích hợp chạy trên DỮ LIỆU THẬT của repo (screen_snapshot_live.csv, vn_stock.db, ta_signals.csv
# ...) — cùng phong cách test_snapshot_rebuild.py, KHÔNG dùng fixture bịa, vì mục tiêu là xác nhận
# pipeline thật hoạt động đúng trên dữ liệu thật. export_ai_bundle.main() được gọi TRỰC TIẾP trong
# tiến trình với OUT_DIR trỏ vào thư mục tạm (mock) — không bao giờ ghi đè focus_extract.json/
# bundle_manifest.json thật của repo, và không copy vn_stock.db (177MB) đi đâu cả.
# ==========================================================================

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export_ai_bundle as bundle  # noqa: E402

# Mã ĐÃ BIẾT là chết (nến gần nhất 2026-06-11, xa phiên hiện hành hàng chục ngày) — dùng làm
# regression cố định cho bug RS ảo (P0-1): trước khi sửa, mã này từng lọt RS 94-99 lên đầu bảng.
KNOWN_STALE_TICKER = "CH5"

SOURCE_FILES_MUST_NOT_CHANGE = [
    "vn_stock.db", "ta_signals.csv", "analysis_latest.json",
    "financial_snapshot.parquet", "screen_snapshot.csv",
    "screen_snapshot_live.csv", "Focus_Analysis.md",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_bundle_main(argv: list[str], out_dir: Path) -> int:
    """Gọi bundle.main() trong tiến trình; CHỈ đổi hướng nơi GHI output (OUT_DIR) sang thư mục
    tạm. Mọi nguồn ĐỌC (DB, CSV, JSON, parquet, Focus_Analysis.md, context package) vẫn là dữ liệu
    thật của repo."""
    with mock.patch.object(bundle, "OUT_DIR", str(out_dir)), \
         mock.patch.object(sys, "argv", ["export_ai_bundle.py", *argv]):
        return bundle.main()


class ScreenSnapshotLiveTests(unittest.TestCase):
    """P0-1: is_live/days_stale + rs_rating chỉ xếp hạng trong mã live."""

    @classmethod
    def setUpClass(cls):
        cls.full = pd.read_csv(ROOT / "screen_snapshot.csv", encoding="utf-8-sig")
        cls.live = pd.read_csv(ROOT / "screen_snapshot_live.csv", encoding="utf-8-sig")

    def test_live_file_has_only_live_rows_with_zero_days_stale(self):
        self.assertGreater(len(self.live), 0)
        self.assertTrue((self.live["is_live"] == True).all())  # noqa: E712
        self.assertTrue((self.live["days_stale"] == 0).all())

    def test_known_stale_ticker_excluded_from_live_file_but_kept_in_full(self):
        self.assertNotIn(KNOWN_STALE_TICKER, set(self.live["ticker"]),
                         f"{KNOWN_STALE_TICKER} là mã chết — không được lọt vào bản live")
        full_row = self.full[self.full["ticker"] == KNOWN_STALE_TICKER]
        self.assertEqual(len(full_row), 1, "Mã chết vẫn phải còn trong bản đầy đủ (tương thích cũ)")
        self.assertFalse(bool(full_row.iloc[0]["is_live"]))
        self.assertGreater(int(full_row.iloc[0]["days_stale"]), 1)
        self.assertTrue(pd.isna(full_row.iloc[0]["rs_rating"]),
                        "Mã chết không được có rs_rating (bug cũ: RS ảo 94-99 chiếm đầu bảng)")

    def test_full_snapshot_keeps_all_rows_and_gains_new_columns(self):
        self.assertGreaterEqual(len(self.full), len(self.live))
        self.assertTrue({"is_live", "days_stale", "rs_rating"} <= set(self.full.columns))

    def test_focus_tickers_are_all_live_with_a_real_rs_rating(self):
        for tk in bundle.DEFAULT_TICKERS:
            row = self.live[self.live["ticker"] == tk]
            self.assertEqual(len(row), 1, f"{tk} phải có đúng 1 dòng trong screen_snapshot_live.csv")
            self.assertTrue(bool(row.iloc[0]["is_live"]))
            self.assertFalse(pd.isna(row.iloc[0]["rs_rating"]))

    def test_live_count_matches_market_breadth_all_row(self):
        breadth = pd.read_csv(ROOT / "market_breadth.csv", encoding="utf-8-sig")
        all_row = breadth[breadth["group"] == "ALL"].iloc[0]
        self.assertEqual(len(self.live), int(all_row["n_symbols"]))


class FreshnessGateLogicTests(unittest.TestCase):
    """P0-3: hàm thuần check_freshness() — độc lập với trạng thái stale/fresh THẬT của repo hôm nay,
    để test không tự nhiên đổi kết quả khi ai đó refresh lại Focus_Analysis.md sau này."""

    def test_blocks_when_one_category_older_than_prior_session(self):
        categories = {
            "screen_snapshot_live": "2026-07-17", "ta_signals": "2026-07-17",
            "analysis_latest": "2026-07-17", "focus_analysis": "2026-07-10",
            "context_package": "2026-07-17",
        }
        result = bundle.check_freshness(categories, prior_session="2026-07-16")
        self.assertTrue(result["blocked"])
        self.assertEqual([s["category"] for s in result["stale"]], ["focus_analysis"])

    def test_passes_when_everything_within_one_session(self):
        categories = {
            "screen_snapshot_live": "2026-07-17", "ta_signals": "2026-07-17",
            "analysis_latest": "2026-07-16", "focus_analysis": "2026-07-17",
            "context_package": "2026-07-17",
        }
        result = bundle.check_freshness(categories, prior_session="2026-07-16")
        self.assertFalse(result["blocked"])
        self.assertEqual(result["stale"], [])

    def test_unknown_category_is_reported_but_does_not_block(self):
        categories = {"screen_snapshot_live": "2026-07-17", "context_package": None}
        result = bundle.check_freshness(categories, prior_session="2026-07-16")
        self.assertFalse(result["blocked"])
        self.assertIn("context_package", result["unknown"])


class ExportAiBundleIntegrationTests(unittest.TestCase):
    """Chạy export_ai_bundle.py thật (--allow-stale để không phụ thuộc trạng thái fresh/stale hôm
    nay) trên dữ liệu thật, ghi ra thư mục tạm, rồi đối chiếu với nguồn."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmpdir.name)
        cls.before_hashes = {name: _sha256(ROOT / name) for name in SOURCE_FILES_MUST_NOT_CHANGE
                             if (ROOT / name).exists()}
        cls.returncode = run_bundle_main(["--allow-stale"], cls.out_dir)
        with (cls.out_dir / "focus_extract.json").open(encoding="utf-8") as f:
            cls.extract = json.load(f)
        with (cls.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            cls.manifest = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_allow_stale_run_succeeds(self):
        self.assertEqual(self.returncode, 0)

    def test_source_files_are_not_modified(self):
        for name, before in self.before_hashes.items():
            after = _sha256(ROOT / name)
            self.assertEqual(before, after, f"{name} bị export_ai_bundle.py sửa — script phải chỉ đọc")

    def test_focus_extract_has_all_five_default_tickers_with_no_warnings(self):
        self.assertEqual(set(self.extract["tickers"].keys()), set(bundle.DEFAULT_TICKERS))
        for tk in bundle.DEFAULT_TICKERS:
            self.assertEqual(self.extract["tickers"][tk]["warnings"], [],
                             f"{tk} không nên có cảnh báo thiếu dữ liệu với 5 mã mặc định hôm nay")

    def test_price_and_date_of_each_ticker_match_db_source(self):
        conn = bundle._connect_db_readonly(ROOT / "vn_stock.db")
        try:
            for tk in bundle.DEFAULT_TICKERS:
                row = conn.execute(
                    "SELECT date, close, volume FROM ohlcv WHERE ticker=? ORDER BY date DESC LIMIT 1",
                    (tk,)).fetchone()
                last_candle = self.extract["tickers"][tk]["ohlcv_recent"][-1]
                self.assertEqual(last_candle["date"], row[0])
                self.assertEqual(last_candle["close"], row[1])
                self.assertEqual(last_candle["volume"], row[2])
                snap = self.extract["tickers"][tk]["snapshot"]
                self.assertEqual(snap["date"], row[0])
                self.assertEqual(snap["close"], row[1])
        finally:
            conn.close()

    def test_ohlcv_recent_has_30_candles_per_ticker(self):
        for tk in bundle.DEFAULT_TICKERS:
            self.assertEqual(self.extract["tickers"][tk]["ohlcv_recent_count"], 30)
            self.assertEqual(len(self.extract["tickers"][tk]["ohlcv_recent"]), 30)

    def test_manifest_record_counts_match_real_files(self):
        by_file = {f["file"]: f for f in self.manifest["files"]}
        live_df = pd.read_csv(ROOT / "screen_snapshot_live.csv", encoding="utf-8-sig")
        self.assertEqual(by_file["screen_snapshot_live.csv"]["row_or_record_count"], len(live_df))
        ta_df = pd.read_csv(ROOT / "ta_signals.csv", encoding="utf-8-sig")
        self.assertEqual(by_file["ta_signals.csv"]["row_or_record_count"], len(ta_df))
        with (ROOT / "analysis_latest.json").open(encoding="utf-8") as f:
            analysis = json.load(f)
        self.assertEqual(by_file["analysis_latest.json"]["row_or_record_count"], len(analysis["scores"]))
        self.assertEqual(by_file["focus_extract.json"]["row_or_record_count"], 5)

    def test_manifest_sha256_matches_actual_source_files(self):
        by_file = {f["file"]: f for f in self.manifest["files"]}
        for name in ("screen_snapshot_live.csv", "ta_signals.csv", "analysis_latest.json"):
            self.assertEqual(by_file[name]["sha256"], _sha256(ROOT / name))
        self.assertEqual(by_file["focus_extract.json"]["sha256"],
                         _sha256(self.out_dir / "focus_extract.json"))

    def test_manifest_status_and_stale_warning_are_consistent(self):
        # [SỬA 2026-07-17 chiều] Bản gốc giả định --allow-stale LUÔN tạo ra status="stale_override"
        # — đúng tại thời điểm viết test (dữ liệu repo khi đó thực sự lệch phiên/lệch thứ tự
        # artifact). Sau khi các lỗi staleness thực tế được sửa (regenerate ta_signals.csv +
        # analysis_latest.json cùng phiên), --allow-stale trên dữ liệu SẠCH hợp lệ trả về "fresh"
        # — đây là hành vi ĐÚNG (cờ --allow-stale chỉ có tác dụng khi thực sự có gì đó stale để ghi
        # đè). Test kiểm tra BẤT BIẾN cấu trúc thay vì giả định trạng thái dữ liệu hôm nay, đúng với
        # chủ đích ban đầu của class này: "không phụ thuộc trạng thái fresh/stale hôm nay".
        status = self.manifest["freshness"]["status"]
        self.assertIn(status, ("fresh", "stale_override"))
        if status == "stale_override":
            self.assertIn("STALE_DATA_WARNING", self.manifest)
        else:
            self.assertNotIn("STALE_DATA_WARNING", self.manifest)


class DefaultRunIsAllOrNothingTests(unittest.TestCase):
    """Bất biến của freshness gate, không phụ thuộc trạng thái fresh/stale thật hôm nay: CHẶN ->
    không file nào được ghi + exit != 0; KHÔNG chặn -> cả 2 file được ghi + exit == 0. Không bao giờ
    ở trạng thái lửng lơ (ghi 1 phần, hoặc ghi file nhưng vẫn báo lỗi)."""

    def test_default_invocation_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            rc = run_bundle_main([], out_dir)
            extract_exists = (out_dir / "focus_extract.json").exists()
            manifest_exists = (out_dir / "bundle_manifest.json").exists()
            if rc == 0:
                self.assertTrue(extract_exists)
                self.assertTrue(manifest_exists)
            else:
                self.assertFalse(extract_exists, "Bị chặn nhưng vẫn ghi focus_extract.json"
                                 " — vi phạm 'mặc định không xuất bundle khi lệch phiên'")
                self.assertFalse(manifest_exists)


class NoSourceMutationTests(unittest.TestCase):
    """'Không sửa dữ liệu nguồn': export_ai_bundle.py mở DB read-only; cả hai script không chứa
    lệnh SQL ghi."""

    WRITE_SQL_RE = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|CREATE\s+TABLE)\b",
        re.IGNORECASE)

    def test_vn_indicators_source_has_no_write_sql(self):
        text = (ROOT / "vn_indicators.py").read_text(encoding="utf-8")
        self.assertIsNone(self.WRITE_SQL_RE.search(text))

    def test_export_ai_bundle_source_has_no_write_sql(self):
        text = (ROOT / "export_ai_bundle.py").read_text(encoding="utf-8")
        self.assertIsNone(self.WRITE_SQL_RE.search(text))

    def test_export_ai_bundle_opens_db_strictly_read_only(self):
        text = (ROOT / "export_ai_bundle.py").read_text(encoding="utf-8")
        self.assertIn("mode=ro", text)
        self.assertIn("PRAGMA query_only", text)

    def test_vn_stock_db_mtime_unchanged_by_bundle_run(self):
        before = (ROOT / "vn_stock.db").stat().st_mtime_ns
        with tempfile.TemporaryDirectory() as tmp:
            run_bundle_main(["--allow-stale"], Path(tmp))
        after = (ROOT / "vn_stock.db").stat().st_mtime_ns
        self.assertEqual(before, after)


# ==========================================================================
# TEST cho nâng cấp workflow 2026-07-17 chiều (bỏ Gemini): canonical_rs_rating (mục 3),
# freshness gate nâng cấp (mục 4), analysis_bundle.json (mục 1-2), fiscal period flag ở
# consumer export_ai_bundle.py (mục 6 — bản thân flag được test riêng ở test_fiscal_period_flag.py).
# ==========================================================================

class CanonicalRsRatingTests(unittest.TestCase):
    """Mục 3: canonical_rs_rating phải khớp screen_snapshot_live.csv cho MỌI mã mặc định, và
    reconcile_rs_rating() không bao giờ trả 2 số khác nhau mà không có 'explanation'."""

    @classmethod
    def setUpClass(cls):
        cls.live = pd.read_csv(ROOT / "screen_snapshot_live.csv", encoding="utf-8-sig")

    def test_canonical_matches_screen_snapshot_live_for_default_tickers(self):
        snapshot_rows, snapshot_info = bundle.load_live_snapshot_rows(bundle.DEFAULT_TICKERS)
        ta_rows, ta_info = bundle.load_ta_signal_rows(bundle.DEFAULT_TICKERS)
        for tk in bundle.DEFAULT_TICKERS:
            reconciliation = bundle.reconcile_rs_rating(tk, snapshot_rows, ta_rows, snapshot_info, ta_info)
            expected = self.live.loc[self.live["ticker"] == tk, "rs_rating"].iloc[0]
            self.assertEqual(reconciliation["canonical_rs_rating"], expected)
            self.assertEqual(reconciliation["canonical_source"], bundle.CANONICAL_RS_RATING_SOURCE)

    def test_reconciliation_mismatch_case_always_explains_itself(self):
        snapshot_rows = {"XYZ": {"rs_rating": 80}}
        ta_rows = {"XYZ": {"rs_rating": 60}}
        snapshot_info = {"mtime": 200, "mtime_iso": "2026-01-01T20:00:00+07:00"}
        ta_info = {"mtime": 100, "mtime_iso": "2026-01-01T19:00:00+07:00"}
        r = bundle.reconcile_rs_rating("XYZ", snapshot_rows, ta_rows, snapshot_info, ta_info)
        self.assertFalse(r["matches_canonical"])
        self.assertTrue(r["explanation"])
        self.assertIn("KHÔNG khớp", r["explanation"])

    def test_reconciliation_matching_case_also_explains_itself(self):
        snapshot_rows, ta_rows = {"XYZ": {"rs_rating": 80}}, {"XYZ": {"rs_rating": 80}}
        info = {"mtime_iso": "t1"}
        r = bundle.reconcile_rs_rating("XYZ", snapshot_rows, ta_rows, info, info)
        self.assertTrue(r["matches_canonical"])
        self.assertTrue(r["explanation"])

    def test_all_consumers_use_same_canonical_rs_rating(self):
        """'Mọi consumer dùng cùng nguồn canonical' (yêu cầu tường minh mục 3): đối chiếu chéo
        export_ai_bundle.py với context package AI ANALYZE (build_ticker_context.py) cho cùng mã."""
        checked = 0
        for tk in bundle.DEFAULT_TICKERS:
            path = bundle.CONTEXT_PACKAGES_DIR / f"{tk}_context.json"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                package = json.load(f)
            expected = self.live.loc[self.live["ticker"] == tk, "rs_rating"].iloc[0]
            self.assertEqual(package["technical_summary"]["rs_rating"], expected,
                             f"{tk}: context package rs_rating lệch canonical (screen_snapshot_live.csv)")
            checked += 1
        self.assertGreater(checked, 0, "Không tìm thấy context package nào để đối chiếu chéo")


class ArtifactOrderTests(unittest.TestCase):
    """Mục 4: chặn khi downstream được tạo TRƯỚC file nguồn mới nhất nó phụ thuộc."""

    def test_detects_downstream_older_than_upstream(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, downstream = root / "screen_snapshot.csv", root / "ta_signals.csv"
            upstream.write_text("x"); downstream.write_text("y")
            now = time.time()
            os.utime(downstream, (now - 100, now - 100))   # downstream CŨ HƠN upstream
            os.utime(upstream, (now, now))
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0]["downstream"], "ta_signals.csv")
            self.assertEqual(violations[0]["upstream"], "screen_snapshot.csv")

    def test_no_violation_when_downstream_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "screen_snapshot.csv").write_text("x")
            (root / "ta_signals.csv").write_text("y")
            violations = bundle.check_artifact_order(root, {"ta_signals.csv": ["screen_snapshot.csv"]})
            self.assertEqual(violations, [])

    def test_missing_files_are_skipped_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            violations = bundle.check_artifact_order(Path(tmp), {"a.csv": ["b.csv"]})
            self.assertEqual(violations, [])

    def test_default_graph_excludes_own_outputs(self):
        """focus_extract.json/analysis_bundle.json KHÔNG được nằm trong graph mặc định — so mtime
        BẢN CŨ của output với nguồn mới ngay trước khi lần chạy này ghi đè chúng sẽ luôn tự chặn
        vô nghĩa (xem comment tại định nghĩa ARTIFACT_DEPENDENCY_GRAPH)."""
        self.assertNotIn("focus_extract.json", bundle.ARTIFACT_DEPENDENCY_GRAPH)
        self.assertNotIn("analysis_bundle.json", bundle.ARTIFACT_DEPENDENCY_GRAPH)


class VerifyManifestChecksumDependencyTests(unittest.TestCase):
    """Mục 4 'checksum dependency': verify_manifest() phát hiện khi file nguồn đã đổi kể từ khi
    manifest được ghi."""

    def test_no_drift_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.csv"
            src.write_text("version-1")
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "source.csv", "sha256": bundle.sha256_file(src), "exists": True}]}))
            self.assertEqual(bundle.verify_manifest(manifest_path, root), [])

    def test_detects_sha256_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.csv"
            src.write_text("version-1")
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "source.csv", "sha256": bundle.sha256_file(src), "exists": True}]}))
            src.write_text("version-2-changed")
            mismatches = bundle.verify_manifest(manifest_path, root)
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0]["issue"], "sha256_changed")

    def test_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(
                {"files": [{"file": "gone.csv", "sha256": "deadbeef", "exists": True}]}))
            mismatches = bundle.verify_manifest(manifest_path, root)
            self.assertEqual(mismatches[0]["issue"], "file_no_longer_exists")


class AnalysisBundleIntegrationTests(unittest.TestCase):
    """Mục 1-2: analysis_bundle.json phải gộp market breadth + macro + context package +
    provenance + data_quality_flags cho các mã mặc định."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmpdir.name)
        cls.returncode = run_bundle_main(["--allow-stale"], cls.out_dir)
        with (cls.out_dir / "analysis_bundle.json").open(encoding="utf-8") as f:
            cls.bundle = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_run_succeeds(self):
        self.assertEqual(self.returncode, 0)

    def test_contains_market_breadth_and_macro_snapshot(self):
        self.assertIsInstance(self.bundle["market_breadth"], list)
        self.assertGreater(len(self.bundle["market_breadth"]), 0)
        self.assertIsInstance(self.bundle["macro_snapshot"], dict)
        self.assertGreater(len(self.bundle["macro_snapshot"]), 0)

    def test_each_ticker_has_canonical_rs_rating_and_context_package_slot(self):
        for tk in bundle.DEFAULT_TICKERS:
            entry = self.bundle["tickers"][tk]
            self.assertIn("canonical_rs_rating", entry)
            self.assertIn("rs_rating_reconciliation", entry)
            self.assertIn("context_package", entry)   # key luôn có mặt, giá trị có thể None
            self.assertIn("financial_latest_quality", entry)

    def test_has_provenance_and_data_quality_flags(self):
        self.assertIsInstance(self.bundle["provenance"], list)
        self.assertGreater(len(self.bundle["provenance"]), 0)
        self.assertIsInstance(self.bundle["data_quality_flags"], list)

    def test_manifest_registers_both_outputs(self):
        with (self.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            manifest = json.load(f)
        files = {f["file"] for f in manifest["files"]}
        self.assertIn("focus_extract.json", files)
        self.assertIn("analysis_bundle.json", files)

    def test_data_quality_flags_have_full_contract_shape(self):
        # item F: every flag must carry code/severity/scope/ticker/metric/message/evidence/
        # consumer_action — not just the legacy scope/ticker/code/severity/detail shape.
        self.assertGreater(len(self.bundle["data_quality_flags"]), 0)
        for flag in self.bundle["data_quality_flags"]:
            for key in ("code", "severity", "scope", "ticker", "metric", "message", "evidence", "consumer_action"):
                self.assertIn(key, flag)
            self.assertEqual(flag["message"], flag["detail"])
            self.assertIn(flag["severity"], ("error", "warning", "info"))

    def test_hpg_material_share_mismatch_is_promoted_to_root_flags(self):
        # item F/D: HPG's real share_reconciliation.material_warning (context package) must
        # reach root data_quality_flags — this was empty before the promotion fix.
        codes_for_hpg = [
            f["code"] for f in self.bundle["data_quality_flags"] if f["ticker"] == "HPG"
        ]
        self.assertIn("share_count_material_mismatch", codes_for_hpg)

    def test_manifest_financial_snapshot_entry_carries_new_date_fields(self):
        # item G: the fields load_financial_latest() computes must actually reach the
        # bundle_manifest.json output via build_manifest_files() — a prior version of this
        # fix computed the fields correctly but build_manifest_files() silently dropped them
        # (it constructs its own dict literal from an explicit key allowlist).
        with (self.out_dir / "bundle_manifest.json").open(encoding="utf-8") as f:
            manifest = json.load(f)
        entry = next(f for f in manifest["files"] if f["file"] == "financial_snapshot.parquet")
        for field in (
            "latest_verified_calendar_end", "latest_raw_fiscal_label",
            "verified_period_count", "unverified_period_count", "future_relative_to_calendar_count",
        ):
            self.assertIn(field, entry)
        self.assertEqual(entry["data_date"], entry["latest_verified_calendar_end"])
        if entry["data_date"] is not None:
            self.assertRegex(entry["data_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_macro_snapshot_carries_per_series_freshness(self):
        # item H: macro_snapshot.csv (what this bundle actually loads) must carry each
        # series' own freshness — not a single file-wide verdict.
        macro = self.bundle["macro_snapshot"]
        self.assertGreater(len(macro), 0)
        for series, entry in macro.items():
            for field in ("freshness_status", "age_days", "expected_frequency", "as_of"):
                self.assertIn(field, entry, f"{series} missing {field}")
            self.assertIn(entry["freshness_status"], ("current", "stale", "unknown"))

    def test_not_applicable_metrics_are_never_promoted_to_flags(self):
        # not_applicable is a confirmed, non-problematic status by contract — must never appear
        # as a data-quality flag (would be noise, and self-contradictory with its own meaning).
        for flag in self.bundle["data_quality_flags"]:
            evidence = flag.get("evidence")
            if isinstance(evidence, dict):
                self.assertNotEqual(evidence.get("status"), "not_applicable", flag)


class FiscalPeriodQualityIntegrationTests(unittest.TestCase):
    """Mục 6 (phía consumer): load_financial_latest() phải khai has_fiscal_period_flag và luôn có
    excluded_unverified_periods (danh sách rỗng nếu financial_snapshot.parquet hiện hành chưa có
    cột fiscal_period_status — tương thích ngược, xem docstring load_financial_latest)."""

    def test_load_financial_latest_reports_fiscal_flag_presence(self):
        by_ticker, info = bundle.load_financial_latest(bundle.DEFAULT_TICKERS)
        self.assertIn("has_fiscal_period_flag", info)
        for tk in bundle.DEFAULT_TICKERS:
            self.assertIn("excluded_unverified_periods", by_ticker[tk])

    def test_data_date_is_never_a_raw_fiscal_label(self):
        # item G, Data Contract Hardening v1.1: data_date must be a real calendar-verified
        # date (or None) — never the max raw "YYYY-Qn"/"YYYY" label across the whole snapshot
        # (the exact "2026-Q4 used as a financial date" trap).
        _, info = bundle.load_financial_latest(bundle.DEFAULT_TICKERS)
        for field in (
            "latest_verified_calendar_end", "latest_raw_fiscal_label",
            "verified_period_count", "unverified_period_count", "future_relative_to_calendar_count",
        ):
            self.assertIn(field, info)
        self.assertEqual(info["data_date"], info["latest_verified_calendar_end"])
        if info["data_date"] is not None:
            self.assertRegex(info["data_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertNotRegex(str(info["data_date"]), r"^\d{4}-Q[1-4]$")


if __name__ == "__main__":
    unittest.main()
