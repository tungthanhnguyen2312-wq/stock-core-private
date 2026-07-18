# Release Checklist — GitHub Public Release

> Checklist cho lần polish repo 12/07/2026. Đánh dấu lại mỗi lần chuẩn bị release mới.

- [x] **README.md** — rút gọn thành landing page (tóm tắt EN + chi tiết VI), trỏ sang `docs/`
- [x] **Bản quyền** — All rights reserved; không có giấy phép open-source ở cấp repository
- [x] **CHANGELOG.md** — đã có sẵn, giữ ở gốc, cần `git add` (hiện untracked)
- [x] **.gitignore** — rà soát lại: thêm `NOTES_FOR_TUNG*.md` + rule IDE/OS phòng ngừa
- [x] **Documentation** (`docs/`) — `USER_GUIDE.md`, `ARCHITECTURE.md`, `CLI_REFERENCE.md`,
      `DATA_PIPELINE.md`, `FINANCIAL_REPORT.md`, `STOCK_ANALYZER.md`, `REPO_AUDIT.md`,
      `RELEASE_CHECKLIST.md` (file này)
- [x] **CONTRIBUTING.md / SECURITY.md / CODE_OF_CONDUCT.md** — mới tạo, scope đúng thực tế
      (repo chỉ chứa dashboard tĩnh + tài liệu, không phải toàn bộ pipeline)
- [ ] **Tests** — `tests/test_selftest.py` đã có và pass (`python stock_analyzer.py --selftest`,
      7/7 test), nhưng test này cần `stock_analyzer.py` đứng cạnh nó → **chỉ chạy được ở máy
      local có đủ code pipeline**, không chạy được từ checkout GitHub thuần (đã ghi rõ trong
      `.gitignore` dòng comment). Không có CI (GitHub Actions) chạy test này — cân nhắc thêm
      nếu muốn badge "tests passing" có ý nghĩa thật.
- [x] **Dashboard** — `index.html`/`signals.html`/`screener.html` không bị đụng logic; đã kiểm
      tra không có lỗi hiển thị mới do phase polish này gây ra (phase này không sửa `.html`/`.js`/`.css`)
- [x] **CLI** — không đổi tham số dòng lệnh của script nào; tài liệu CLI đã đồng bộ với hành vi
      hiện tại (không suy đoán thêm lệnh chưa tồn tại)
- [ ] **Examples** — chưa có thư mục `examples/` mẫu (VD: 1 file `screen_snapshot.csv` mẫu nhỏ
      để người xem repo hiểu format mà không cần chạy pipeline). Đề xuất, không bắt buộc.
- [x] **GitHub Pages** — không đổi cấu hình publish; `publish_dashboard.py` vẫn là con đường
      duy nhất đẩy web, whitelist tự bóc không đổi

## Trước khi push lần release đầu tiên

1. `git add CHANGELOG.md CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md .gitignore README.md docs/` —
   thêm CÓ CHỦ ĐÍCH từng file/thư mục, **không** `git add .` (giữ đúng nguyên tắc đã có của
   `publish_dashboard.py`).
2. `git status` — xác nhận không có file nặng/cá nhân nào lọt vào staged (không thấy
   `vn_stock.db`, `*.parquet`, `data_bctc/`, `NOTES_FOR_TUNG*.md`, v.v.).
3. `git diff --cached --stat` — soát lại danh sách file sẽ commit lần cuối.
4. Review lại README hiển thị đúng trên GitHub (markdown preview) trước khi push.
5. Sau khi push, kiểm tra GitHub Pages build không lỗi (Settings → Pages) và các link nội bộ
   trong README/`docs/*.md` không gãy (đường dẫn tương đối, phân biệt hoa/thường trên Linux
   runner của GitHub — khác Windows).

## Frontend Phase 1-5 — Deployment readiness (cập nhật 13/07/2026)

Sau khi dashboard được dựng lại toàn bộ (sidebar/top bar, migrate Bootstrap→Tailwind, redesign
Dashboard/Screener/Analysis, thêm sidebar thu gọn/panel kéo giãn/company panel, rồi audit
performance+GitHub Pages ở phase này) — audit riêng cho việc PUBLISH:

**Cấu hình GitHub Pages khuyến nghị (đã xác nhận đúng với site đang chạy)**
- Settings → Pages → Source: **Deploy from a branch** → Branch **`main`** → folder **`/ (root)`**.
- **KHÔNG** chọn thư mục `/docs` làm nguồn Pages — `docs/` trong repo này là tài liệu vận hành
  (USER_GUIDE.md, CLI_REFERENCE.md...), không phải nơi chứa site. `dashboard.html`/`index.html`/
  `assets/` đều nằm ở gốc repo. Nhầm sang `/docs` sẽ làm site build ra tài liệu thay vì dashboard.
- Không có `CNAME` → không dùng custom domain, site chạy ở domain mặc định GitHub cấp.
- Site là **project page** (`tungthanhnguyen2312-wq.github.io/market-dashboard/`), KHÔNG phải
  domain gốc — đã audit toàn bộ `href`/`src`/`url()` trong `.html`/`.css`/`.js`: 100% đường dẫn
  tương đối (không có path tuyệt đối `/...`), tương thích đúng với subpath này.

**Giới hạn của static hosting (GitHub Pages) cần biết**
- Không có API liệt kê thư mục → trang Archive (`archive.html`) dùng danh sách ghi tay
  (`assets/js/archive.js`), không tự động dò file mới khi thêm báo cáo — xem ghi chú "tự động hoá"
  trong chính file đó.
- Không có server-side rendering/redirect thật → `index.html` dùng `<meta http-equiv="refresh">` +
  `location.replace()` để trỏ sang `dashboard.html`, không phải HTTP 301 thật.
- Không có backend nào khác ngoài các file tĩnh — mọi "API" thực chất là fetch file `.csv`/`.json`
  tĩnh do pipeline Python sinh ra offline rồi copy vào repo qua `sync_and_push.bat`.

**File dữ liệu bắt buộc phải có mặt để dashboard hiển thị đúng** (do `sync_and_push.bat`/
`publish_dashboard.py` copy vào, KHÔNG sinh bởi frontend): `ai_report_latest.md`,
`ai_report_latest.json`, `screen_snapshot.csv`, `market_breadth.csv`, `analysis_latest.json`,
`data/candle_signals.json`, `data/sector_heatmap.json` (+ fallback `.js` cùng tên cho chế độ mở
trực tiếp bằng file, không qua server), `data/macro_snapshot.json` + `.js` cho trang Macro.

**Dữ liệu CỐ TÌNH bị chặn khỏi repo/site** (xem `.gitignore`) — không phải lỗi thiếu sót:
`vn_stock.db`, `*.parquet`, `ohlcv_flat.csv`, `data_bctc/`, `financial_snapshot.csv/.parquet`,
`blacklist.csv`, `tickers*.txt`. Hai hệ quả trực tiếp cho frontend:
- **Financial Statements/Ratios/Growth/Profitability/Cash Flow/Valuation** — không có trang/tab
  thật nào hiển thị số liệu này; `company-panel.js`'s tab "Báo cáo tài chính" hiện trạng thái
  "đang chờ dữ liệu" một cách trung thực thay vì bịa số. Quyết định này đã xác nhận lại ở Phase 3
  và Phase 4, không đổi ở phase này.
- **`macro.html`** — đọc snapshot web đã chuẩn hóa; CSV vĩ mô thô và DB vẫn local. Nếu không có
  dữ liệu mua/bán khối ngoại thật, trang hiển thị empty state và link tham khảo thay vì dùng
  `foreign_room_pct` hoặc số 0.

**Nợ kỹ thuật đã biết, KHÔNG xử lý ở các phase frontend (theo đúng giới hạn "không dùng build
system/templating")**: sidebar + top bar lặp lại nguyên văn trong cả 7 trang `.html` (không có
layer template chung). Muốn khử lặp cần 1 trong 2 hướng, cả hai đều ngoài phạm vi hiện tại:
(a) một build step nhẹ (ví dụ 11ty/script Python ghép template) sinh HTML tĩnh trước khi publish,
hoặc (b) runtime include qua JS fetch (đánh đổi lấy FOUC/flash sidebar). Để dành cho phase kiến
trúc riêng nếu thực sự cần.
