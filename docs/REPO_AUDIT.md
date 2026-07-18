# Repository Audit — GitHub Release Prep (2026-07-12)

> Audit thuần đọc, thực hiện trước khi polish repo cho bản public. Không có file nào bị xóa
> trong bước này — mọi khuyến nghị xóa/gitignore đều để chủ repo tự quyết.
> Không nhầm với `docs/AUDIT_REPORT.md` (audit nội bộ về API/công thức BCTC, mục đích khác,
> vẫn gitignore như cũ).

## 1. Tổng quan repo tại thời điểm audit

- **30 file** đang tracked trong git (`git ls-files`) — dashboard tĩnh (`.html`/`.js`/`.css`) +
  vài CSV nhẹ + bộ test hồi quy (`tests/`). Đây đã là chủ đích của repo: `market-dashboard`
  trên GitHub chỉ là **website**, không phải toàn bộ mã nguồn pipeline.
- **Remote:** `https://github.com/tungthanhnguyen2312-wq/market-dashboard.git`.
- `.gitignore` đã được xây dựng rất kỹ (nhiều đợt bổ sung có ghi ngày + lý do) để tách bạch
  tài sản dữ liệu cá nhân/pipeline code khỏi web công khai. Đã xác minh bằng `git check-ignore -v`
  cho toàn bộ file nặng (`vn_stock.db`, `ohlcv_flat.*`, `financial_snapshot.*`, `data_bctc/`) —
  tất cả đều bị chặn đúng như khai báo.

## 2. File tạm / cache / build artefact

| Mục | Vị trí | Kết luận |
|---|---|---|
| `__pycache__/` | gốc + `tests/__pycache__` | Đã gitignore (`__pycache__/`). Vật lý vẫn tồn tại trên đĩa (bytecode cache) — an toàn xóa bất kỳ lúc nào, Python tự sinh lại. |
| IDE files (`.vscode/`, `.idea/`) | không tìm thấy | Không có, đã bổ sung rule phòng ngừa vào `.gitignore` cho người sau clone bằng editor khác. |
| OS junk (`Thumbs.db`, `desktop.ini`) | không tìm thấy | Không có, đã bổ sung rule phòng ngừa. |
| File backup (`*.bak`, `*~`) | không tìm thấy | Không có. |
| Thư mục rỗng | không tìm thấy | `find -type d -empty` sạch. |
| Log files | `logs/*.log` (6 file) | Đã gitignore (`logs/`). Có giá trị debug cục bộ — giữ nguyên, không cần dọn. |

## 3. File cá nhân / nội bộ (không phải tài liệu vận hành public)

| File | Trạng thái trước audit | Xử lý trong phase này |
|---|---|---|
| `NOTES_FOR_TUNG.md` | Untracked, không gitignore — chứa 1 quyết định đang chờ (KBS vs VCI cho BCTC) | Thêm vào `.gitignore`, **giữ nguyên nội dung** (theo quyết định của chủ repo) |
| `NOTES_FOR_TUNG_SHAREHOLDERS.md` | Untracked, không gitignore | Thêm vào `.gitignore`, giữ nguyên |
| `docs/AUDIT_REPORT.md`, `docs/VALIDATION_REPORT.md` | Đã gitignore từ trước (12/07) | Giữ nguyên, không đụng — mục đích khác với docs/ public mới tạo phase này |
| `Focus_Analysis.md`, `Market_Scan.md/.csv` | Đã gitignore từ trước | Giữ nguyên — output cá nhân của `stock_analyzer.py` |
| `analysis_latest.json/.md`, `ai_report_2*.{md,json}` | Đã gitignore từ trước | Giữ nguyên |

## 4. File mới/lạ phát hiện trong lúc audit (chưa có trong tài liệu cũ)

- **`analysis.html` + `analysis.js`** (untracked, tạo 12/07 ~10:44) — có vẻ là bản nháp trang
  dashboard mới cho `stock_analyzer.py` (khớp với mục Future Roadmap #3 trong CHANGELOG cũ:
  "Tích hợp dashboard: trang analysis.html"). **Không sửa/không xóa** — đây là logic
  HTML/JS đang phát triển dở, nằm ngoài phạm vi "chỉ dọn tài liệu" của phase này. Khuyến nghị:
  khi sẵn sàng public, nhớ thêm vào whitelist tham chiếu của `publish_dashboard.py` (script tự
  bóc từ thẻ `<script src>`/`fetch`, không cần sửa tay whitelist) và cập nhật bảng file trong
  [docs/ARCHITECTURE.md](ARCHITECTURE.md#file-trong-repo-web).
- **`CHANGELOG.md`** (untracked nhưng không bị gitignore) — nội dung hợp lệ, nên track vào git
  cùng đợt polish này (xem Release Checklist).

## 5. Quét bí mật (secrets)

Grep `api[_-]?key|password|secret|token` trên toàn bộ file loại `.html/.js/.css/.bat/.csv/.json`
(loại trừ file gitignore) — không phát hiện giá trị bí mật nào bị hard-code. `ai_analyzer.py`
đọc key qua biến môi trường (`ANTHROPIC_API_KEY`), đúng như README đã cảnh báo. 2 match dương
tính giả: `.claude/settings.local.json` (đã gitignore, chỉ chứa *tên biến* env, không phải giá
trị) và `news_latest.csv` (đã gitignore, chữ "token" xuất hiện tình cờ trong nội dung tin tức).

## 6. File nặng — xác nhận KHÔNG lọt vào git

`git check-ignore -v` xác nhận từng dòng `.gitignore` khớp đúng file dự kiến, không dựa vào suy
đoán: `vn_stock.db` (176 MB), `ohlcv_flat.csv` (108 MB) + `.parquet` (23 MB), `financial_snapshot.csv/.parquet`,
`data_bctc/` (52 MB), `data vnstock.xlsx` — tất cả bị chặn bởi dòng riêng hoặc rule chung, không có
file nào trong nhóm này từng lọt vào lịch sử git.

## 7. Kết luận

Repo đã ở trạng thái vệ sinh tốt từ trước (nhờ kỷ luật `.gitignore` + `publish_dashboard.py`
whitelist-only). Việc cần làm trong phase polish này chủ yếu là **tổ chức lại tài liệu**
(README khổng lồ → landing page + `docs/`), không phải dọn rác — repo về cơ bản không có rác.

## 8. Rà soát cấu trúc thư mục

Không di chuyển/đổi tên bất kỳ file `.py` nào trong phase này (đúng ràng buộc). Chỉ tài liệu
được tổ chức lại:

- `README.md` (gốc) → rút gọn thành landing page, trỏ sang `docs/`.
- `docs/` mới: `USER_GUIDE.md`, `ARCHITECTURE.md`, `CLI_REFERENCE.md`, `DATA_PIPELINE.md`,
  `FINANCIAL_REPORT.md`, `STOCK_ANALYZER.md`, `REPO_AUDIT.md` (file này), `RELEASE_CHECKLIST.md`
  — toàn bộ **public**, nội dung trích/xếp lại từ README cũ, không có thông tin mới.
  `AUDIT_REPORT.md`/`VALIDATION_REPORT.md` (đã có từ trước) **giữ nguyên vị trí + gitignore**.
- `CHANGELOG.md`, `CHANGELOG_UI.md` giữ ở gốc (đúng convention GitHub — công cụ/badge thường
  tìm `CHANGELOG.md` ở root, không phải trong `docs/`).
- Không phát hiện file `.py` nào đặt sai chỗ hay trùng tên; cấu trúc `data/` (web) tách biệt rõ
  với `data_bctc/` (nội bộ) — không cần đổi.

---

*Xem checklist đầy đủ trước khi release: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)*
