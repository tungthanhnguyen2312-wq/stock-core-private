import sys
import os
import sqlite3
import argparse
from datetime import datetime
import pandas as pd
from vn_time import vn_now

# Console Windows mặc định cp1252 -> vỡ khi in tiếng Việt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# TỰ ĐỘNG HÓA BLACKLIST — phần TỰ ĐỘNG HÓA ĐƯỢC
# ==========================================
# Nguồn: trường `trading_status` trong Trading(VCI).price_board() — trạng thái giao dịch
# do Sở công bố (kiểm soát / đình chỉ / vi phạm CBTT / hạn chế GD), lấy BULK ~50 mã/request.
#
# [!] GIỚI HẠN QUAN TRỌNG — những gì file này KHÔNG làm được:
# - KHÔNG phát hiện được mã "bị cắt margin thuần túy" (vẫn giao dịch bình thường nhưng
#   không đủ điều kiện ký quỹ: lỗ lũy kế, niêm yết <6 tháng, BCTC ngoại trừ...).
#   Danh sách đó CHỈ có trong công bố quý của HOSE/HNX (PDF) -> VẪN NHẬP TAY vào
#   blacklist.csv với status=margin_cut như trước.
# - Endpoint TCBS https://apipubaws.tcbs.com.vn/tcanalysis/v1/margin/list KHÔNG tồn tại
#   (404, kiểm chứng 2026-07-09). Endpoint KBS .../stock/trading-margin cũng chết.
#   ĐỪNG "suy ra blacklist = toàn thị trường TRỪ danh mục margin của 1 công ty CK":
#   UPCOM không bao giờ được cấp margin theo luật -> phép trừ đó gắn cờ oan ~900 mã.
#
# CƠ CHẾ MERGE AN TOÀN với blacklist.csv (file vẫn là nguồn nhập tay):
# - Dòng NHẬP TAY  = note KHÔNG bắt đầu bằng "Auto:" -> GIỮ NGUYÊN, thắng khi trùng mã.
# - Dòng TỰ ĐỘNG   = note bắt đầu bằng "Auto:"       -> XÓA và TÁI SINH mỗi lần chạy,
#   nên mã được Sở gỡ án sẽ tự rụng khỏi danh sách (đúng yêu cầu "reset khi hết án").
# Sau khi chạy file này, chạy `python meta_sync.py --blacklist-only` để đẩy cờ vào DB.

# Tái dùng nguyên bộ delay/retry + hằng số của lớp metadata (không nhân bản logic)
from meta_sync import call_api, get_universe, DB_PATH, BLACKLIST_FILE, PRICE_BOARD_BATCH

# Map trạng thái VCI -> status blacklist (4 mức chuẩn của meta_sync)
# TRADING_ACTIVATED = giao dịch bình thường -> không gắn cờ
# [!] Hậu tố ACTIVATED/UNACTIVATED của VCI KHÔNG có tài liệu chính thức (quan sát 2026-07:
# nhóm RESTRICTION_* trùng khớp danh sách "hạn chế giao dịch" của HNX/UPCOM ~117 mã).
# Map dưới đây là phán đoán thận trọng — cột note luôn giữ status GỐC để tự phán xét lại.
STATUS_MAP = {
    "TRADING_SUSPENSION": "suspend",                        # đình chỉ giao dịch
    "None": "suspend",                                      # không còn trạng thái bảng giá -> nghi hủy NY/ngừng GD
    "TRADING_CONTROL_ACTIVATED": "control",                 # diện kiểm soát
    "TRADING_CONTROL_AND_RESTRICTION_UNACTIVATED": "control",  # kiểm soát + hạn chế GD
    "TRADING_RESTRICTION_ACTIVATED": "control",             # hạn chế giao dịch
    "TRADING_RESTRICTION_UNACTIVATED": "control",           # hạn chế giao dịch (biến thể)
    "TRADING_FINANCIAL_REPORT_ACTIVATED": "warning",        # vi phạm CBTT báo cáo tài chính
    "TRADING_OTHER_VIOLATIONS_ACTIVATED": "warning",        # vi phạm khác
    "TRADING_INFORMATION_DISCLOSURE_ACTIVATED": "warning",  # vi phạm công bố thông tin
    "TRADING_NONE_EXECUTION_ACTIVATED": "warning",          # không phát sinh khớp lệnh (ý nghĩa VCI chưa rõ)
}
NORMAL_STATUS = "TRADING_ACTIVATED"

CSV_HEADER = """\
# ============================================================================
# blacklist.csv — MÃ BỊ CẮT MARGIN / CẢNH BÁO / KIỂM SOÁT / ĐÌNH CHỈ
# File này gồm 2 lớp, meta_sync.py đọc cả 2 và merge vào cột margin_status:
#   1) Dòng TỰ ĐỘNG (note bắt đầu "Auto:") — blacklist_sync.py sinh ra từ
#      trading_status của Sở (qua VCI). ĐỪNG SỬA TAY: sẽ bị ghi đè mỗi lần chạy.
#   2) Dòng NHẬP TAY (note khác) — blacklist_sync.py GIỮ NGUYÊN, thắng khi trùng mã.
#      Dùng cho danh sách CẮT MARGIN quý của HOSE/HNX (không có API, phải nhập tay):
#      hsx.vn / hnx.vn -> "DS chứng khoán không đủ điều kiện giao dịch ký quỹ".
# status hợp lệ: margin_cut | warning | control | suspend
# ============================================================================
"""

def scan_trading_status(tickers):
    """Quét trading_status toàn thị trường qua price_board bulk (batch 50/request).
    Trả về dict ticker -> raw_status; mã lỗi mạng bị bỏ qua lần này (chạy lại sẽ có)."""
    from vnstock.api.trading import Trading
    status = {}
    for i in range(0, len(tickers), PRICE_BOARD_BATCH):
        chunk = tickers[i:i + PRICE_BOARD_BATCH]
        pb = call_api(lambda c=chunk: Trading(source="VCI", random_agent=True).price_board(c),
                      f"price_board[{i}:{i+len(chunk)}]")
        if not isinstance(pb, pd.DataFrame):
            continue
        sym = pb[("listing", "symbol")].astype(str).str.upper()
        raw = pb[("listing", "trading_status")].astype(str)
        status.update(dict(zip(sym, raw)))
        print(f"   [scan] {min(i + len(chunk), len(tickers))}/{len(tickers)} mã")
    return status

def build_auto_rows(status_by_ticker):
    """Sinh dòng blacklist tự động từ trạng thái Sở. Status VCI lạ -> warning + cảnh báo."""
    today = vn_now().strftime("%Y-%m-%d")
    rows = []
    for tk, raw in sorted(status_by_ticker.items()):
        if raw == NORMAL_STATUS:
            continue
        st = STATUS_MAP.get(raw)
        if st is None:
            print(f" [cảnh báo] {tk}: trading_status lạ '{raw}' -> tạm gắn warning, nên kiểm tra map")
            st = "warning"
        rows.append({"ticker": tk, "status": st, "note": f"Auto: {raw}", "updated": today})
    return pd.DataFrame(rows, columns=["ticker", "status", "note", "updated"])

def load_manual_rows():
    """Đọc dòng nhập tay từ blacklist.csv hiện có. Loại: dòng Auto cũ (tái sinh)
    và dòng ví dụ template (note chứa 'VI DU')."""
    if not os.path.exists(BLACKLIST_FILE):
        return pd.DataFrame(columns=["ticker", "status", "note", "updated"])
    bl = pd.read_csv(BLACKLIST_FILE, comment="#", dtype=str).fillna("")
    bl["ticker"] = bl["ticker"].str.strip().str.upper()
    is_auto = bl["note"].str.startswith("Auto:")
    is_example = bl["note"].str.contains("VI DU", case=False)
    if is_example.any():
        print(f" [merge] Loại {is_example.sum()} dòng VÍ DỤ template: {', '.join(bl.loc[is_example, 'ticker'])}")
    return bl[~is_auto & ~is_example]

def main():
    ap = argparse.ArgumentParser(description="Tự động cập nhật lớp Auto của blacklist.csv từ trading_status của Sở (VCI)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kết quả, KHÔNG ghi blacklist.csv")
    ap.add_argument("--limit", type=int, default=0, help="chỉ quét N mã đầu (để test)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    universe = get_universe(conn)
    conn.close()
    if args.limit:
        universe = universe[:args.limit]
    print(f"[blacklist_sync] Quét trading_status {len(universe)} mã "
          f"(~{-(-len(universe) // PRICE_BOARD_BATCH)} request)")

    status = scan_trading_status(universe)
    dist = pd.Series(list(status.values())).value_counts()
    print("\n== Phân bố trading_status toàn thị trường ==")
    for k, v in dist.items():
        print(f"  {k:<40} {v:>5} mã")

    auto = build_auto_rows(status)
    manual = load_manual_rows()
    # trùng mã: dòng nhập tay thắng (ghi chú của người luôn giàu thông tin hơn máy)
    dup = set(auto["ticker"]) & set(manual["ticker"])
    if dup:
        print(f" [merge] {len(dup)} mã có cả dòng tay lẫn Auto -> giữ dòng tay: {', '.join(sorted(dup))}")
        auto = auto[~auto["ticker"].isin(dup)]
    out = pd.concat([manual, auto], ignore_index=True).sort_values("ticker")

    print(f"\n== Kết quả: {len(auto)} mã Auto + {len(manual)} mã nhập tay = {len(out)} dòng ==")
    print(out.head(10).to_string(index=False))
    if len(out) > 10:
        print(f"  ... và {len(out) - 10} dòng nữa")

    if args.dry_run:
        print("\n[dry-run] KHÔNG ghi file. Bỏ --dry-run để ghi blacklist.csv")
        return
    with open(BLACKLIST_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(CSV_HEADER)
        out.to_csv(f, index=False)
    print(f"\n[blacklist_sync] Đã ghi {len(out)} dòng -> {BLACKLIST_FILE}")
    print("  Bước tiếp: python meta_sync.py --blacklist-only  (đẩy cờ vào bảng metadata)")

if __name__ == "__main__":
    main()
