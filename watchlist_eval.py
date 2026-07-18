#!/usr/bin/env python3
# ==========================================================================
# watchlist_eval.py — Backtest TỐI THIỂU cho watchlist_history (nền đã có sẵn từ 2026-07 trong
# stock_analyzer.py:ScoreEngine/ReportEngine.save_watchlist(), class Backtester ở đó vẫn là STUB
# NotImplementedError trỏ sang đúng script này).
#
# Đo forward return T+5/T+20/T+60 PHIÊN (không phải ngày lịch) của mọi mã từng lọt watchlist_history
# + excess return so VN-Index CÙNG kỳ, gộp thống kê theo score bucket và theo strategy tag (proxy
# "TA signal" — xem giới hạn ở KHÔNG LOOK-AHEAD bên dưới).
#
# KHÔNG LOOK-AHEAD (bắt buộc theo thiết kế, không phải tùy chọn):
#   - Forward return CHỈ tính khi phiên T+N đã THỰC SỰ tồn tại trong ohlcv (không suy đoán/ngoại
#     suy/nội suy). Chưa đủ N phiên trôi qua kể từ session_date -> None ("chưa đủ dữ liệu"), KHÔNG
#     phải 0 và KHÔNG bị bỏ qua khỏi báo cáo (vẫn đếm vào "chưa đánh giá được").
#   - Lịch giao dịch CHUẨN dùng để đếm "N phiên sau" là lịch của CHÍNH VN-Index (ticker VNINDEX) —
#     coi là "thị trường có mở cửa phiên đó". T+N của một mã = giá đóng cửa CHÍNH XÁC tại ngày đó
#     nếu mã có giao dịch; mã không có nến đúng ngày đó (đình chỉ/ngừng GD) -> None, KHÔNG dùng giá
#     gần nhất thay thế (tránh forward-fill nhìn trước thực chất).
#   - close tại session_date lấy TỪ CHÍNH watchlist_history (giá đã ký tại thời điểm chấm điểm),
#     không truy vấn lại ohlcv rồi có thể vô tình lấy nhầm phiên khác.
#
# GIỚI HẠN ĐÃ BIẾT (bản tối thiểu, ghi rõ thay vì giả vờ đầy đủ):
#   - "TA signal" trong thống kê là cột `strategies` của watchlist_history (chiến lược
#     stock_analyzer.py --strategy đã chọn mã hôm đó: canslim/fscore/momentum/rs/sector/smc/...),
#     KHÔNG PHẢI tín hiệu nến/SMC của candle_scan.py (patterns/fvg/ob/confluence) — ta_signals.csv
#     bị GHI ĐÈ mỗi phiên, không có bảng lịch sử theo ngày nên không thể tra cứu lại tín hiệu nến
#     của một session_date trong quá khứ. Muốn có thống kê theo tín hiệu nến thật, cần thêm bảng
#     lịch sử ta_signals (ngoài phạm vi "bản tối thiểu" — để P1 sau).
#   - watchlist_history mới có từ 2026-07-10 (P0 mới) — vài phiên đầu, hầu hết cửa sổ T+20/T+60
#     CHƯA ĐỦ dữ liệu tương lai để đánh giá; đây là trạng thái ĐÚNG, không phải lỗi.
#
# Dùng:
#   python watchlist_eval.py                    # in báo cáo + ghi watchlist_eval_latest.json/.md
#   python watchlist_eval.py --horizons 5,20     # tùy chỉnh N phiên (mặc định 5,20,60)
#
# CHỈ ĐỌC vn_stock.db (mode=ro) — không ghi DB, không gọi mạng/API, không phải khuyến nghị đầu tư.
# ==========================================================================

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "vn_stock.db"
INDEX_SYMBOL = "VNINDEX"
DEFAULT_HORIZONS = (5, 20, 60)
OUT_JSON = "watchlist_eval_latest.json"
OUT_MD = "watchlist_eval_latest.md"
SCORE_BUCKET_EDGES = [0, 40, 50, 60, 70, 80, 100]
SCORE_BUCKET_LABELS = ["<40", "40-50", "50-60", "60-70", "70-80", "80-100"]


def _connect_readonly(path: str) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy database: {path}")
    conn = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def load_watchlist_history(conn: sqlite3.Connection) -> pd.DataFrame:
    try:
        df = pd.read_sql(
            "SELECT session_date, ticker, run_ts, score, fundamental, technical, momentum, "
            "liquidity, macro, risk, close, strategies FROM watchlist_history "
            "ORDER BY session_date, ticker", conn)
    except pd.errors.DatabaseError as exc:
        raise RuntimeError(
            "Không có bảng watchlist_history — chạy `python stock_analyzer.py --strategy all`"
            " ít nhất 1 lần trước (bảng này do ReportEngine.save_watchlist() tạo)."
        ) from exc
    return df


def load_trading_calendar(conn: sqlite3.Connection, symbol: str = INDEX_SYMBOL) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT date FROM ohlcv WHERE ticker=? ORDER BY date", (symbol,)).fetchall()
    if not rows:
        raise RuntimeError(f"Không có dữ liệu ohlcv cho {symbol} — không thể dùng làm lịch giao dịch chuẩn.")
    return [r[0] for r in rows]


def load_close_series(conn: sqlite3.Connection, tickers: list[str]) -> dict[str, dict[str, float]]:
    """{ticker: {date: close}} cho MỌI mã cần tra T+N — 1 query duy nhất, không N+1."""
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    rows = conn.execute(
        f"SELECT ticker, date, close FROM ohlcv WHERE ticker IN ({placeholders})", tickers).fetchall()
    out: dict[str, dict[str, float]] = {}
    for tk, d, c in rows:
        out.setdefault(tk, {})[d] = c
    return out


def n_sessions_after(calendar: list[str], start_date: str, n: int) -> str | None:
    """Ngày giao dịch thứ n SAU start_date theo lịch chuẩn (VNINDEX). None nếu chưa đủ n phiên đã
    trôi qua tính đến phiên cuối cùng có trong lịch — ĐÂY LÀ CHỐT CHẶN LOOK-AHEAD, không suy đoán."""
    idx = bisect.bisect_right(calendar, start_date)
    target_idx = idx + n - 1
    if target_idx >= len(calendar):
        return None
    return calendar[target_idx]


def evaluate(df: pd.DataFrame, conn: sqlite3.Connection, horizons: tuple[int, ...]) -> pd.DataFrame:
    if df.empty:
        return df
    calendar = load_trading_calendar(conn)
    tickers = sorted(set(df["ticker"]) | {INDEX_SYMBOL})
    close_by_ticker = load_close_series(conn, tickers)
    index_close = close_by_ticker.get(INDEX_SYMBOL, {})

    out = df.copy()
    for n in horizons:
        target_dates, tk_fwd, idx_fwd, excess = [], [], [], []
        for _, row in out.iterrows():
            tgt = n_sessions_after(calendar, row["session_date"], n)
            target_dates.append(tgt)
            if tgt is None:
                tk_fwd.append(None); idx_fwd.append(None); excess.append(None)
                continue
            c0 = row["close"]
            c1 = close_by_ticker.get(row["ticker"], {}).get(tgt)
            i0 = index_close.get(row["session_date"])
            i1 = index_close.get(tgt)
            r_tk = round((c1 / c0 - 1) * 100, 4) if (c1 is not None and c0) else None
            r_idx = round((i1 / i0 - 1) * 100, 4) if (i1 is not None and i0) else None
            tk_fwd.append(r_tk)
            idx_fwd.append(r_idx)
            excess.append(round(r_tk - r_idx, 4) if (r_tk is not None and r_idx is not None) else None)
        out[f"target_date_t{n}"] = target_dates
        out[f"fwd_return_t{n}_pct"] = tk_fwd
        out[f"vnindex_return_t{n}_pct"] = idx_fwd
        out[f"excess_return_t{n}_pct"] = excess
        out[f"evaluable_t{n}"] = out[f"excess_return_t{n}_pct"].notna()
    return out


def score_bucket(score: float | None) -> str | None:
    if score is None or pd.isna(score):
        return None
    for lo, hi, label in zip(SCORE_BUCKET_EDGES[:-1], SCORE_BUCKET_EDGES[1:], SCORE_BUCKET_LABELS):
        if lo <= score < hi or (hi == 100 and score == 100):
            return label
    return None


def summarize_group(g: pd.DataFrame, horizons: tuple[int, ...]) -> dict:
    stat = {"n_picks": int(len(g))}
    for n in horizons:
        col = f"excess_return_t{n}_pct"
        evaluable = g[g[f"evaluable_t{n}"]]
        stat[f"t{n}"] = {
            "n_evaluable": int(len(evaluable)),
            "n_pending": int(len(g) - len(evaluable)),
            "mean_excess_return_pct": round(float(evaluable[col].mean()), 3) if len(evaluable) else None,
            "median_excess_return_pct": round(float(evaluable[col].median()), 3) if len(evaluable) else None,
            "hit_rate_pct": round(float((evaluable[col] > 0).mean() * 100), 1) if len(evaluable) else None,
            "mean_ticker_return_pct": round(float(evaluable[f"fwd_return_t{n}_pct"].mean()), 3) if len(evaluable) else None,
            "mean_vnindex_return_pct": round(float(evaluable[f"vnindex_return_t{n}_pct"].mean()), 3) if len(evaluable) else None,
        }
    return stat


def build_report(evaluated: pd.DataFrame, horizons: tuple[int, ...]) -> dict:
    overall = summarize_group(evaluated, horizons)

    by_bucket = {}
    if len(evaluated):
        buckets = evaluated["score"].apply(score_bucket)
        for label in SCORE_BUCKET_LABELS:
            g = evaluated[buckets == label]
            if len(g):
                by_bucket[label] = summarize_group(g, horizons)

    # "TA signal" proxy = cột strategies (xem giới hạn đã ghi ở đầu file) — 1 mã có thể thuộc
    # nhiều strategy cùng lúc nên tổng n_picks theo nhóm có thể > tổng số dòng gốc, đây là CHỦ Ý.
    by_strategy = {}
    if len(evaluated) and "strategies" in evaluated.columns:
        exploded = evaluated.assign(
            strategy=evaluated["strategies"].fillna("").str.split(",")
        ).explode("strategy")
        exploded["strategy"] = exploded["strategy"].str.strip()
        exploded = exploded[exploded["strategy"] != ""]
        for strat, g in exploded.groupby("strategy"):
            by_strategy[strat] = summarize_group(g, horizons)

    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "horizons_sessions": list(horizons),
        "index_symbol": INDEX_SYMBOL,
        "no_lookahead_policy": (
            "Forward return chỉ tính khi phiên T+N đã thực sự tồn tại trong ohlcv tính đến hôm nay;"
            " chưa đủ dữ liệu -> None (đếm là 'pending', không phải 0 và không bị loại khỏi mẫu)."
        ),
        "known_limitations": [
            "'TA signal' trong by_strategy là cột strategies của stock_analyzer.py (chiến lược đã"
            " chọn mã), KHÔNG PHẢI tín hiệu nến/SMC candle_scan.py — không có bảng lịch sử ta_signals"
            " theo ngày để tra cứu lại quá khứ (xem docstring đầu file).",
            "watchlist_history mới bắt đầu tích lũy — số phiên 'evaluable' còn thấp cho T+20/T+60"
            " cho tới khi đủ thời gian trôi qua; đây là trạng thái dự kiến, không phải lỗi.",
            "Đây là thống kê mô tả (descriptive), KHÔNG phải kiểm định thống kê (p-value/ý nghĩa"
            " thống kê) và KHÔNG phải khuyến nghị mua/bán.",
        ],
        "overall": overall,
        "by_score_bucket": by_bucket,
        "by_strategy": by_strategy,
        "n_rows_total": int(len(evaluated)),
        "n_sessions_covered": int(evaluated["session_date"].nunique()) if len(evaluated) else 0,
        "session_date_range": (
            [str(evaluated["session_date"].min()), str(evaluated["session_date"].max())]
            if len(evaluated) else [None, None]
        ),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Watchlist Forward-Return Evaluation (bản tối thiểu)",
        "",
        f"Generated: `{report['generated_at']}`  ·  "
        f"{report['n_rows_total']} lượt pick trên {report['n_sessions_covered']} phiên"
        f" ({report['session_date_range'][0]} → {report['session_date_range'][1]})",
        "",
        "Đây là thống kê mô tả forward return sau khi lọt watchlist_history — KHÔNG phải khuyến "
        "nghị mua/bán, KHÔNG phải kiểm định thống kê ý nghĩa (mẫu còn nhỏ).",
        "",
        "## Tổng thể",
        "",
        "| Horizon (phiên) | Đã đánh giá | Chưa đủ dữ liệu | Excess return TB (%) | Hit rate (%) |",
        "|---|---|---|---|---|",
    ]
    for n in report["horizons_sessions"]:
        s = report["overall"].get(f"t{n}", {})
        lines.append(f"| T+{n} | {s.get('n_evaluable')} | {s.get('n_pending')} |"
                     f" {s.get('mean_excess_return_pct')} | {s.get('hit_rate_pct')} |")
    lines += ["", "## Theo score bucket", "",
             "| Bucket | N picks | " + " | ".join(f"T+{n} excess TB (%)" for n in report["horizons_sessions"]) + " |",
             "|---|---|" + "---|" * len(report["horizons_sessions"])]
    for label, s in report["by_score_bucket"].items():
        vals = " | ".join(str(s.get(f"t{n}", {}).get("mean_excess_return_pct")) for n in report["horizons_sessions"])
        lines.append(f"| {label} | {s['n_picks']} | {vals} |")
    lines += ["", "## Theo strategy (proxy 'TA signal' — xem giới hạn)", "",
             "| Strategy | N picks | " + " | ".join(f"T+{n} excess TB (%)" for n in report["horizons_sessions"]) + " |",
             "|---|---|" + "---|" * len(report["horizons_sessions"])]
    for strat, s in sorted(report["by_strategy"].items()):
        vals = " | ".join(str(s.get(f"t{n}", {}).get("mean_excess_return_pct")) for n in report["horizons_sessions"])
        lines.append(f"| {strat} | {s['n_picks']} | {vals} |")
    lines += ["", "## Giới hạn đã biết", ""]
    lines += [f"- {w}" for w in report["known_limitations"]]
    lines += ["", "## How AI Should Use This", "",
             "Dùng để MÔ TẢ hiệu suất lịch sử của hệ thống chấm điểm, không dùng để đảm bảo hiệu suất"
             " tương lai; luôn nêu n_evaluable/n_pending kèm mọi con số trung bình; không suy ra ý"
             " nghĩa thống kê khi mẫu còn nhỏ; không đưa khuyến nghị mua/bán.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest tối thiểu cho watchlist_history — forward "
                                 "return T+N phiên + excess return so VN-Index, không look-ahead.")
    ap.add_argument("--horizons", default=",".join(str(n) for n in DEFAULT_HORIZONS),
                    help="Danh sách N phiên cách nhau bởi dấu phẩy (mặc định 5,20,60)")
    ap.add_argument("--db", default=DB_PATH, help="Đường dẫn vn_stock.db (mặc định vn_stock.db)")
    args = ap.parse_args()
    try:
        horizons = tuple(sorted({int(x) for x in args.horizons.split(",") if x.strip()}))
    except ValueError:
        print(f"[watchlist_eval] LỖI: --horizons không hợp lệ: '{args.horizons}'", file=sys.stderr)
        return 2
    if not horizons:
        print("[watchlist_eval] LỖI: --horizons rỗng", file=sys.stderr)
        return 2

    try:
        conn = _connect_readonly(args.db)
    except FileNotFoundError as exc:
        print(f"[watchlist_eval] LỖI: {exc}", file=sys.stderr)
        return 2

    try:
        history = load_watchlist_history(conn)
        if history.empty:
            print("[watchlist_eval] watchlist_history rỗng — chưa có phiên chấm điểm nào được lưu.")
            return 0
        evaluated = evaluate(history, conn, horizons)
    except RuntimeError as exc:
        print(f"[watchlist_eval] LỖI: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    report = build_report(evaluated, horizons)
    Path(OUT_JSON).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                              encoding="utf-8")
    Path(OUT_MD).write_text(render_markdown(report), encoding="utf-8")

    print(f"[watchlist_eval] {report['n_rows_total']} lượt pick / {report['n_sessions_covered']} phiên"
         f" ({report['session_date_range'][0]} -> {report['session_date_range'][1]})"
         f" -> {OUT_JSON}, {OUT_MD}")
    for n in horizons:
        s = report["overall"].get(f"t{n}", {})
        print(f"   T+{n}: {s.get('n_evaluable')} đã đánh giá, {s.get('n_pending')} chưa đủ dữ liệu"
             f" | excess TB {s.get('mean_excess_return_pct')}% | hit rate {s.get('hit_rate_pct')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
