"""run.py — entry point điều phối pipeline VNSTOCK (LOCAL, không lên GitHub).

Chỉ GỌI các script hiện có qua subprocess với cwd = thư mục gốc project — không sao chép
logic crawler. Các script cũ vẫn chạy trực tiếp như trước (docs/CLI_REFERENCE.md là tài
liệu chuẩn); run.py chỉ là lối tắt thống nhất + không phụ thuộc thư mục đang đứng.

Cách dùng:
    python run.py --list                    # xem danh sách task
    python run.py --task prices             # = python vn_stock_pipeline.py update
    python run.py --task daily              # chuỗi hằng ngày: prices → macro → news → indicators → candles
    python run.py --task publish -- --live  # phần sau `--` được nối thêm vào lệnh gốc
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent

# Task → danh sách lệnh (mỗi lệnh là argv, không qua shell). Nguồn: docs/CLI_REFERENCE.md.
# Task nhiều bước dừng ngay khi một bước lỗi.
TASKS: dict[str, dict] = {
    "prices":       {"cmds": [["vn_stock_pipeline.py", "update"]],
                     "help": "Cập nhật OHLCV hằng ngày (chạy sau 15h giờ VN)"},
    "macro":        {"cmds": [["macro_sync.py"]],
                     "help": "Đồng bộ dữ liệu vĩ mô thế giới + VN"},
    "news":         {"cmds": [["news_sync.py"]],
                     "help": "Cào RSS tin tức (nên chạy 2-3 lần/ngày)"},
    "indicators":   {"cmds": [["vn_indicators.py"]],
                     "help": "Mixer chỉ báo → screen_snapshot.csv + market_breadth.csv (chạy CUỐI chuỗi dữ liệu)"},
    "candles":      {"cmds": [["candle_scan.py"]],
                     "help": "Quét mẫu nến 1D/1W/1M + SMC → data/*.json(.js) — cục bộ, 0 request"},
    "daily":        {"cmds": [["vn_stock_pipeline.py", "update"], ["macro_sync.py"], ["news_sync.py"],
                              ["vn_indicators.py"], ["candle_scan.py"]],
                     "help": "Chuỗi hằng ngày đúng thứ tự: prices → macro → news → indicators → candles"},
    "blacklist":    {"cmds": [["blacklist_sync.py"], ["meta_sync.py", "--blacklist-only"]],
                     "help": "Cập nhật blacklist (1 lần/tuần): blacklist_sync → meta_sync --blacklist-only"},
    "metadata":     {"cmds": [["meta_sync.py"]],
                     "help": "Đồng bộ metadata cơ bản (~2-2.5h, tự resume; thêm --refresh sau mùa BCTC)"},
    "shareholders": {"cmds": [["shareholders_sync.py"]],
                     "help": "Cào cổ đông lớn (~45-50 phút, 1 lần/tháng, tự resume)"},
    "bctc-sync":    {"cmds": [["bctc_sync.py", "scrape", "--file", "tickers_bctc.txt", "--refresh"]],
                     "help": "Cào BCTC quý mới → data_bctc/ (1 lần/quý)"},
    "bctc-process": {"cmds": [["bctc_processor.py"]],
                     "help": "Chuẩn hóa BCTC → financial_snapshot.csv/.parquet (sau bctc-sync)"},
    "analyze":      {"cmds": [["stock_analyzer.py", "--strategy", "all"]],
                     "help": "Quant engine offline 10 chiến lược → analysis_latest.json/.md (0 request)"},
    "ai-preview":   {"cmds": [["ai_analyzer.py", "--dry-run"]],
                     "help": "Xem trước dữ liệu sẽ gửi AI — MIỄN PHÍ"},
    "ai":           {"cmds": [["ai_analyzer.py"]],
                     "help": "Gọi Claude sinh báo cáo — TỐN PHÍ (~$0.10-0.15/lần), cần ANTHROPIC_API_KEY"},
    "publish":      {"cmds": [["publish_dashboard.py"]],
                     "help": "Publisher (dry-run mặc định; đẩy thật: run.py --task publish -- --live)"},
}


def list_tasks() -> None:
    print("Task khả dụng (python run.py --task <tên> [-- <tham số nối thêm>]):\n")
    width = max(len(name) for name in TASKS)
    for name, spec in TASKS.items():
        steps = " && ".join(" ".join(cmd) for cmd in spec["cmds"])
        print(f"  {name:<{width}}  {spec['help']}")
        print(f"  {'':<{width}}    → {steps}")
    print("\nTài liệu chuẩn về lệnh + lịch chạy: docs/CLI_REFERENCE.md")


def run_task(name: str, extra: list[str]) -> int:
    spec = TASKS[name]
    cmds = spec["cmds"]
    if extra and len(cmds) > 1:
        print(f"[LỖI] Task '{name}' gồm {len(cmds)} bước — không nhận tham số nối thêm "
              "(chạy từng task đơn nếu cần truyền cờ riêng).")
        return 2
    for i, cmd in enumerate(cmds, 1):
        argv = [sys.executable, str(ROOT / cmd[0]), *cmd[1:], *extra]
        print(f"[run.py] Bước {i}/{len(cmds)}: python {cmd[0]} {' '.join([*cmd[1:], *extra])}".rstrip())
        # cwd=ROOT vì nhiều script mở "vn_stock.db" theo đường dẫn tương đối với CWD
        rc = subprocess.run(argv, cwd=ROOT).returncode
        if rc != 0:
            print(f"[LỖI] Bước {i} ({cmd[0]}) thoát mã {rc} — dừng task '{name}'.")
            return rc
    print(f"[OK] Task '{name}' hoàn tất.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Entry point điều phối pipeline VNSTOCK — chỉ gọi script hiện có, không chứa logic.",
        epilog="Tham số sau `--` được nối vào lệnh gốc (chỉ với task 1 bước). "
               "Ví dụ: python run.py --task publish -- --live",
    )
    ap.add_argument("--task", choices=sorted(TASKS), help="tên task cần chạy")
    ap.add_argument("--list", action="store_true", help="liệt kê task + lệnh tương ứng")
    args, extra = ap.parse_known_args()
    if extra and extra[0] == "--":
        extra = extra[1:]

    if args.list:
        list_tasks()
        return 0
    if not args.task:
        ap.print_help()
        return 0
    return run_task(args.task, extra)


if __name__ == "__main__":
    raise SystemExit(main())
