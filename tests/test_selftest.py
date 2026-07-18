# ==========================================================================
# TEST HỒI QUY cho stock_analyzer.py — chạy qua `python stock_analyzer.py --selftest`
# hoặc `python -m unittest discover tests`.
# ==========================================================================
# Fixture 17 mã BỊA (tests/fixtures/), mỗi mã thiết kế để trúng ĐÚNG chiến lược định
# trước — thay đổi nào làm lệch tập kết quả là test đỏ ngay. 3 mã "bẫy" phải không
# bao giờ lọt: BAD1 (án sàn, mọi chỉ số đẹp), ILL1 (kém thanh khoản), DEAD (dữ liệu
# phiên cũ 2022 — kiểm tra lọc live). FTS1 sàn HSX là regression test trực tiếp cho
# bug HSX vs HOSE (07/2026): FTSE mà không bắt được FTS1 nghĩa là bug tái phát.
# ==========================================================================

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stock_analyzer as sa  # noqa: E402 — phải sau khi chèn sys.path

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
FX_SNAP = os.path.join(FX, "screen_snapshot_fixture.csv")

# metadata giả cho fixture: ticker -> (dividend_yield %, market_cap đồng)
# -1 = "nguồn không có số" (đúng quy ước kho); mã vắng mặt -> NaN sau left join
META = {
    "VAL1": (8, 5e12), "FSC1": (6, 2e12), "FTS1": (-1, 6e13),
    "BAD1": (9, 5e13), "DEAD": (9, 9e13), "ILL1": (-1, 1e12),
}

# Tập mã kỳ vọng CHÍNH XÁC của từng chiến lược trên fixture (tính tay, xem comment đầu file)
EXPECTED = {
    "value": {"VAL1", "FSC1"},      # rẻ hơn trung vị ngành + ROE cao + có cổ tức
    "canslim": {"CAN1"},
    "momentum": {"MOM1"},
    "ftse": {"FTS1"},               # HSX — regression bug HSX vs HOSE
    "fscore": {"FSC1", "VAL1"},     # 9/9 và 7/9; BAD1 8/9 nhưng án sàn -> loại thẳng
    "smc": {"SMC1"},                # SMC2 bearish, SMC3 ngoài vùng discount
    "breakout": {"BRK1"},
    "turnaround": {"TUR1"},
    "rs": {"RS1"},
    "sector": {"SEC1"},             # Thep là ngành mạnh nhất trong breadth fixture
}


def make_hub(tmpdir):
    """DataHub trỏ toàn bộ vào fixture: snapshot/breadth/signals CSV + metadata sqlite tạm.
    macro/news/prices trỏ vào đường dẫn không tồn tại — kiểm luôn tính chịu thiếu nguồn."""
    db = os.path.join(tmpdir, "fixture.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE metadata(ticker TEXT PRIMARY KEY,"
                " dividend_yield REAL, market_cap REAL)")
    con.executemany("INSERT INTO metadata VALUES (?,?,?)",
                    [(t, dv, mc) for t, (dv, mc) in META.items()])
    con.commit()
    con.close()
    hub = sa.DataHub()
    hub.FILES = dict(sa.DataHub.FILES)
    hub.FILES.update({
        "snapshot": FX_SNAP,
        "breadth": os.path.join(FX, "market_breadth_fixture.csv"),
        "signals": os.path.join(FX, "ta_signals_fixture.csv"),
        "db": db,
        "macro": os.path.join(tmpdir, "khong_ton_tai.csv"),
        "news": os.path.join(tmpdir, "khong_ton_tai.csv"),
        "prices": os.path.join(tmpdir, "khong_ton_tai.parquet"),
    })
    return hub, db


def run_quiet(strategy_name, hub):
    """Chạy 1 chiến lược, nuốt output console (log vẫn ghi file, không sao)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return sa.STRATEGIES[strategy_name](hub).run()


class TestChienLuoc(unittest.TestCase):
    """Mỗi chiến lược phải trả ĐÚNG tập mã kỳ vọng trên fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vnstock_selftest_")
        cls.hub, cls.db = make_hub(cls.tmp)

    def test_moi_chien_luoc_dung_tap_ky_vong(self):
        for name, expected in EXPECTED.items():
            with self.subTest(strategy=name):
                res = run_quiet(name, self.hub)
                self.assertIsNotNone(res, f"'{name}' bị bỏ qua (thiếu nguồn?)")
                self.assertEqual(set(res["all_tickers"]), expected)

    def test_hoi_quy_hsx_ftse(self):
        # Regression TRỰC TIẾP cho bug 07/2026: kho ghi sàn TP.HCM là HSX, filter
        # so ="HOSE" từng trả 0 mã trong im lặng suốt 2 ngày.
        res = run_quiet("ftse", self.hub)
        self.assertIn("FTS1", res["all_tickers"],
                      "FTSE không bắt được mã sàn HSX — bug HSX vs HOSE tái phát!")

    def test_ma_cam_khong_duoc_lot(self):
        # BAD1 (án sàn), ILL1 (GTGD 0.5 tỷ), DEAD (phiên 2022) — chỉ số đều đẹp,
        # lọt vào bất kỳ chiến lược nào nghĩa là lọc nền / lọc live hỏng.
        for name in EXPECTED:
            res = run_quiet(name, self.hub)
            for cam in ("BAD1", "ILL1", "DEAD"):
                self.assertNotIn(cam, res["all_tickers"], f"{cam} lọt vào '{name}'")


class TestBaoCao(unittest.TestCase):
    """analysis_latest.json/.md sinh trên fixture phải đúng cấu trúc đã cam kết."""

    def test_json_va_md(self):
        tmp = tempfile.mkdtemp(prefix="vnstock_report_")
        hub, db = make_hub(tmp)
        out_j = os.path.join(tmp, "analysis_fixture.json")
        out_m = os.path.join(tmp, "analysis_fixture.md")
        with contextlib.redirect_stdout(io.StringIO()):
            results = [r for r in (sa.STRATEGIES[n](hub).run()
                                   for n in sorted(sa.STRATEGIES)) if r]
            sa.ReportEngine(hub, out_json=out_j, out_md=out_m, db_file=db).build(results)

        raw = open(out_j, encoding="utf-8").read()
        self.assertNotIn("NaN", raw, "JSON chứa NaN — parser phía web/AI sẽ vỡ")
        self.assertNotIn("Infinity", raw)
        p = json.loads(raw)
        self.assertEqual(list(p), ["summary", "market", "top_stocks", "scores",
                                   "strategies", "risks", "portfolio_suggestions",
                                   "score_method"], "sai bộ khóa / sai thứ tự")
        self.assertEqual(len(p["scores"]), 16)          # 16 mã live (DEAD bị loại)
        self.assertTrue(all(len(v) == 7 for v in p["scores"].values()))
        self.assertEqual(len(p["top_stocks"]), 16)      # min(TOP_PICKS, universe)
        for t in p["top_stocks"]:
            self.assertEqual(len(t["explain"]), 6, f"{t['ticker']} thiếu giải thích điểm")
        w = sum(x["weight_pct"] for x in p["portfolio_suggestions"]["positions"])
        self.assertGreaterEqual(w, 0)
        self.assertLessEqual(w, p["portfolio_suggestions"]["equity_pct"] + 0.5)

        md = open(out_m, encoding="utf-8").read()
        for sec in ("## Tóm tắt", "## Thị trường", "## Rủi ro",
                    "## Gợi ý danh mục", "## Cách chấm điểm"):
            self.assertIn(sec, md)
        self.assertIn("không phải khuyến nghị đầu tư", md)

        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM watchlist_history").fetchone()[0]
        con.close()
        self.assertGreater(n, 0, "watchlist_history không được ghi")


class TestGuard(unittest.TestCase):
    """3 guard chống 'sai âm thầm' phải kêu đúng lúc."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vnstock_guard_")
        _, cls.db = make_hub(cls.tmp)

    def test_guard1_schema_thieu_cot_phai_dung(self):
        p = os.path.join(self.tmp, "thieu_cot.csv")
        pd.read_csv(FX_SNAP).drop(columns=["rs_rating"]).to_csv(p, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            sa.load_snapshot(p, self.db)
        self.assertIn("rs_rating", buf.getvalue(), "lỗi schema không nêu tên cột thiếu")

    def test_guard2_exchange_la_chi_canh_bao(self):
        p = os.path.join(self.tmp, "exchange_la.csv")
        df = pd.read_csv(FX_SNAP)
        df.loc[df["ticker"] == "FTS1", "exchange"] = "HOSE"  # đúng kịch bản bug cũ, chiều ngược
        df.to_csv(p, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = sa.load_snapshot(p, self.db)  # không được crash
        self.assertIn("HOSE", buf.getvalue(), "giá trị exchange lạ không được cảnh báo")
        self.assertEqual(len(out), 17)

    def test_guard3_sentinel_0_ma(self):
        old_rs, old_min = sa.RS_ELITE_MIN, sa.EMPTY_WARN_MIN_UNIVERSE
        sa.RS_ELITE_MIN, sa.EMPTY_WARN_MIN_UNIVERSE = 1000, 5  # ép rs trả 0 mã + hạ ngưỡng
        try:
            hub, _ = make_hub(tempfile.mkdtemp(prefix="vnstock_sentinel_"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                res = sa.STRATEGIES["rs"](hub).run()
            self.assertEqual(res["count"], 0)
            self.assertIn("trả 0 mã", buf.getvalue(), "sentinel 0 mã không lên tiếng")
        finally:
            sa.RS_ELITE_MIN, sa.EMPTY_WARN_MIN_UNIVERSE = old_rs, old_min


if __name__ == "__main__":
    unittest.main()
