# CHANGELOG — VNSTOCK

Lịch sử phát triển chính thức của dự án. Chi tiết riêng về giao diện web: xem [CHANGELOG_UI.md](CHANGELOG_UI.md). Tài liệu kỹ thuật hiện hành: xem [docs/](docs/).

---

## [1.4.0] — 2026-07-14 · Candlestick patterns 1D/1W/1M

- Thêm engine pandas/NumPy có registry 31 mẫu, context xu hướng, tolerance ATR/% giá, scan lịch sử không look-ahead và resample tuần/tháng từ OHLCV ngày.
- Giữ nguyên `candle_signals`/SMC legacy; sinh riêng snapshot schema v1 `data/candlestick_patterns.json/.js` bằng writer atomic, JSON strict và giới hạn output cấu hình được.
- Confidence 0–100 dựa trên sáu nhóm bằng chứng; có stars, `forming/completed`, confirmations, warnings thanh khoản/margin/xung đột.
- Signals có tab mẫu nến, summary, filter/sort, table responsive/accessibility, JSON-first + `file://` fallback và click dòng mở company panel.
- Thêm unit test cho 17 mẫu quan trọng, resample, tolerance, dữ liệu thiếu, status và serialization; publish whitelist chỉ nhận đúng artifact web mới.

---

## [1.3.0] — 2026-07-14 · Macro pipeline dashboard

- Hoàn thiện `macro.html` bằng dữ liệu thật từ bảng `macro`: KPI, biểu đồ có lịch sử, bảng metadata nguồn/kỳ/tần suất, freshness theo từng nhịp cập nhật và empty state khối ngoại trung thực.
- `macro_sync.py` tự sinh `data/macro_snapshot.json` + `.js` từ cùng một object, JSON strict không NaN/Infinity, ghi nguyên tử; có `--export-web-only` để tái sinh artifact mà không gọi mạng.
- Loader ưu tiên JSON trên HTTP/GitHub Pages và fallback `window.MACRO_SNAPSHOT` khi mở `file://`. Không gọi snapshot là live/real-time.
- Whitelist publish nhận đúng hai artifact Macro; DB, CSV thô, Python, config và log vẫn không publish. Local chỉ có `foreign_room_pct`, chưa có dữ liệu giao dịch khối ngoại.

---

## Release Notes — GitHub Public Release

> **Lưu ý về đánh số phiên bản**: các mục `[0.7.0]` → `[1.1.0]` bên dưới đánh số theo
> **cột mốc phát triển pipeline nội bộ** (tính năng backend/data, có từ trước khi repo này
> public) — KHÔNG phải số phiên bản của GitHub Release. Repo `market-dashboard` chưa từng có
> Git tag/Release nào. Đề xuất: gắn **`v1.0.0`** làm tag/Release đầu tiên tại thời điểm public
> hoá (đánh dấu "bản snapshot công khai đầu tiên", độc lập với số hiệu 1.1.0 ở trên). Việc tạo
> tag là thao tác git — không thực hiện trong phase tài liệu này, chỉ khuyến nghị.
>
> **Trạng thái tại thời điểm chuẩn bị release**: dashboard 7 trang (`dashboard`/`screener`/`analysis`/
> `signals`/`macro`/`about`/`archive`, `index.html` chỉ redirect) ổn định sau Frontend Phase 1-5
> (xem mục [1.2.0] dưới đây), đã qua audit bảo mật (không rò rỉ secret/thông tin cá nhân trong file
> sẽ public sau khi vá `sync_and_push.bat`), có `requirements.txt`, tuyên bố bản quyền
> "All rights reserved" trong README (không cấp giấy phép open-source),
> `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`. Chưa có ảnh chụp màn hình chính thức —
> xem README § Dashboard Preview.

---

## [1.2.0] — 2026-07-13 · Frontend Phase 1-5 (redesign + khung sườn Tailwind)

### Thay đổi kiến trúc
- **Khung sườn dùng chung mới** (`assets/css/shell.css` + `assets/js/shell.js`): sidebar + top bar đồng nhất cho toàn bộ 7 trang, thay thế navbar `nav.css` cũ (nay chỉ còn dùng ở báo cáo tĩnh lưu trữ `playbook-*.html`/`report-*.html`). Tailwind CDN được thêm CHỈ cho khung sườn (Preflight tắt để không xung đột với Bootstrap 5 đang phục vụ nội dung dữ liệu bên trong — cả hai cùng tồn tại có chủ đích, không phải một cuộc "migrate" toàn bộ).
- **`dashboard.html` thay `index.html` làm trang chính** — `index.html` giờ CHỈ còn redirect (`meta refresh` + `location.replace`) để giữ nguyên URL gốc GitHub Pages.
- **3 trang mới**: `about.html` (giới thiệu dự án, tech stack, liên kết), `archive.html` (kho lưu trữ báo cáo tĩnh — danh sách ghi tay trong `assets/js/archive.js`, tách ra khỏi khối "KHU VỰC 3" từng nằm trong `index.html`), `macro.html` (bản khung ở mốc này; đã hoàn thiện bằng pipeline snapshot trong bản 1.3.0).
- **Sidebar thu gọn được** (icon-only, nhớ trạng thái qua `localStorage`), **panel 2 cột kéo giãn được** (`assets/js/resizable-panels.js`, dùng ở `dashboard.html`/`analysis.html`), **panel chi tiết mã** khi bấm dòng bảng (`assets/js/company-panel.js`, chỉ ở `screener.html`) — 3 tab Tổng quan/Biểu đồ/Báo cáo tài chính (tab BCTC hiện trạng thái "đang chờ dữ liệu" trung thực, không bịa số vì `financial_snapshot.*` chưa public).
- Bảng DataTables đổi từ style theo id riêng (`#market-table`) sang class dùng chung `.vs-datatable` — áp style thống nhất được cho mọi bảng trong site (`market-table`, `tblScreen`, `tblBreadth`).
- Audit performance + GitHub Pages riêng cho phase này: xác nhận cấu hình Pages (branch `main`, root, không CNAME), toàn bộ `href`/`src`/`url()` là đường dẫn tương đối (tương thích subpath project page). Chi tiết đầy đủ: [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).
- Chi tiết UI cụ thể (component, style, đổi gì trong từng file): [CHANGELOG_UI.md](CHANGELOG_UI.md).

### Ghi chú tương thích
- KHÔNG đổi ID mà `app.js` phụ thuộc (`ai-report`, `report-date`, `last-updated`, `filter-exchange`, `filter-industry`, `market-table`, `table-status`) hay logic fetch/parse/lọc của `app.js`/`analysis.js`.
- KHÔNG đổi schema `data/*.json`/`.js`, `screen_snapshot.csv`, `analysis_latest.json` — phase này chỉ sửa trình bày, không sửa nguồn dữ liệu.
- `signals.html` không dùng Bootstrap/DataTables (giữ nguyên CSS riêng), chỉ thêm khung sườn Tailwind như các trang khác.

---

## [1.1.0] — 2026-07-12 · Gộp FINANCIAL_REPORT vào VNSTOCK

### Thay đổi kiến trúc
- **Gộp dự án `FINANCIAL_REPORT` (độc lập cũ) vào VNSTOCK** thành nhánh BCTC — xem tài liệu kỹ thuật hiện hành trong [docs/](docs/). Đã tạo backup đầy đủ trước khi gộp; bản backup không thuộc repository này.
- **Đổi tên theo convention VNSTOCK** (`*_sync.py` = cào mạng · `*_processor.py` = biến đổi offline): `scrape_report.py` → `bctc_sync.py`, `financial_processor.py` → `bctc_processor.py`. KHÔNG đụng tên file `.py` nào của 8 module pipeline cũ (Task Scheduler đang trỏ tên cũ).
- **Di chuyển vào VNSTOCK gốc**: `bctc_sync.py`, `bctc_processor.py`, `config.json`, `data_bctc/` (3.583 file), `financial_snapshot.csv/.parquet`. `AUDIT_REPORT.md` + `VALIDATION_REPORT.md` → `docs/`. Log gộp vào `logs/` (không đè file nào có sẵn). Xóa `__pycache__` cũ, không chuyển.
- **Va chạm `tickers.txt` xử lý bằng đổi tên**: `FINANCIAL_REPORT/tickers.txt` → `VNSTOCK/tickers_bctc.txt` (`bctc_sync.py` đã trỏ sang file mới); `VNSTOCK/tickers.txt` (universe giá, 1.745 mã) giữ nguyên không đụng. Ghi nhận: 2 file khảo sát ra **byte-identical** tại thời điểm gộp — tách tên để phòng lệch nhau về sau, không phải vì đang lệch.
- **`.gitignore`**: thêm `data_bctc/`, `financial_snapshot.csv`, `financial_snapshot.parquet`, `tickers_bctc.txt`, `config.json`, `docs/AUDIT_REPORT.md`, `docs/VALIDATION_REPORT.md` — xác nhận bằng `publish_dashboard.py` dry-run: whitelist 25 file, không có file BCTC nào lọt vào.
- **Sửa đường dẫn**: `TICKERS_FILE`/`REPORT_OUT`/tên logger+log file trong `bctc_sync.py`/`bctc_processor.py` (đều dùng `pathlib` + `Path(__file__).resolve().parent`, tự resolve đúng khi file đứng ở vị trí mới); cập nhật self-reference trong `docs/*.md` + `NOTES_FOR_TUNG_SHAREHOLDERS.md`.
- README.md: thêm mục 1.5 (cheatsheet + tần suất **quý**), 1 dòng bảng tầng dữ liệu (2.1), 5 bẫy dữ liệu BCTC vào mục 4.2 (đặc biệt: ngân hàng/CK/bảo hiểm NaN thật ở inventory/gross_margin/current_ratio — đã kiểm chứng bằng số, không phải lỗi), sơ đồ luồng dữ liệu Tổng quan, mục lục.

### Ghi chú tương thích
- KHÔNG đụng `stock_analyzer.py`, 8 module pipeline cũ (`vn_stock_pipeline.py`, `meta_sync.py`, `blacklist_sync.py`, `macro_sync.py`, `news_sync.py`, `vn_indicators.py`, `candle_scan.py`, `ai_analyzer.py`), `shareholders_sync.py`.
- KHÔNG nhồi `financial_snapshot.*` vào `vn_stock.db` — quyết định schema riêng, để sau.
- FINANCIAL_REPORT cũ để lại `README.md` (nội dung đã chắt lọc vào README VNSTOCK, không copy nguyên si) + thư mục rỗng `logs/`, `data_bctc/` không còn tồn tại (đã chuyển hết) — chưa xóa, để Tùng review.

---

## [1.0.0-rc1] — 2026-07-12 · Release Candidate

### Tính năng lớn
- **`shareholders_sync.py` — chân kiềng mới, cào cổ đông lớn (nguồn VCI, failover KBS)**: ghi bảng `shareholders` + tiến độ `shareholders_progress` vào `vn_stock.db` (resume done/empty/failed, KHÔNG đụng `ohlcv`/`meta`/`metadata`/`macro`/`news`); tỷ lệ sở hữu quy đồng nhất về %% (VCI trả phân số 0..1, KBS trả %% thẳng — đã chuẩn hóa); `shareholder_type` để NULL vì nguồn không phân biệt được. Test thật 20 mã: 100% qua VCI, 0 lỗi.
- **`stock_analyzer.py` — Quant Engine offline hoàn chỉnh** (3 phase, 11–12/07):
  - 10 chiến lược lọc dạng class + registry: `value` · `canslim` · `momentum` · `ftse` · `fscore` (proxy) · `smc` · `breakout` · `turnaround` · `rs` · `sector`.
  - **ScoreEngine**: chấm 0-100 mỗi mã = 6 cấu phần có trọng số (cơ bản 25% · kỹ thuật 20% · đà 20% · thanh khoản 15% · vĩ mô 10% · rủi ro 10%), kèm giải thích từng cấu phần cho top mã.
  - **ReportEngine**: đúng 2 file `analysis_latest.json` (~60 KB, máy/AI đọc) + `analysis_latest.md` (~25 KB, người đọc) — không sinh file rác.
  - 3 chế độ CLI: `--strategy all|<tên>` · `--tickers <MÃ...>` (Focus_Analysis.md) · `--scan-market` (Market_Scan.md/.csv), cùng `--list-strategies`.
  - Bảng **`watchlist_history`** trong `vn_stock.db` (bảng DUY NHẤT analyzer được ghi; khóa `session_date+ticker`) — top 20 điểm mỗi phiên, nền dữ liệu cho backtest tương lai.

### Thay đổi kiến trúc
- Thêm **lớp phân tích** (Analysis Layer) độc lập trên pipeline: `DataHub` (một cửa 7 nguồn dữ liệu, nạp lười + cache, thiếu file không crash) · `BaseStrategy` · `ScoreEngine` · `ReportEngine` · khung `Backtester` (chưa cài — chủ đích).
- Không đụng module pipeline nào; toàn bộ vẫn 1 file phẳng/việc, ngưỡng lọc là hằng số đầu file.
- Logging: console giữ nguyên, thêm bản sao timestamp vào `logs/stock_analyzer.log` (cùng quy ước `publish_log.txt`).

### Sửa lỗi
- **Bug FTSE `HSX` vs `HOSE`**: kho ghi sàn TP.HCM là `HSX` (quy ước VCI) — bộ lọc so `="HOSE"` trả 0 kết quả trong im lặng ở cả `--scan-market` lẫn `--strategy ftse`. Đã sửa bằng `.isin(("HSX","HOSE"))` tại 1 hàm dùng chung `ftse_candidates()`; bẫy ghi vào README mục 4.2.
- `None` từ JSON render thành chữ "None" trong bảng Markdown; tiêu đề MD ghi cứng "10 chiến lược"; VIX = NaN làm vỡ format — đều đã vá.
- Chống OneDrive lock khi ghi báo cáo; đóng kết nối SQLite trong `finally`.

### Bổ sung ổn định hóa — đêm 12/07/2026
- **3 guard chống "sai âm thầm"** (lớp bug HSX): schema-guard (thiếu cột snapshot → dừng, nêu đích danh cột + ai cần), domain-check cột `exchange` (giá trị lạ → cảnh báo, không dừng), sentinel "0 mã" (universe ≥ 200 mà chiến lược trả 0 → cảnh báo nghi filter hỏng).
- **`--selftest`**: unittest (stdlib) trên fixture 17 mã bịa trong `tests/` — 7 test khẳng định tập mã kỳ vọng của cả 10 chiến lược, regression trực tiếp bug HSX, cấu trúc JSON/MD, và cả 3 guard. **Mutation check đã thực hiện**: cố tình sửa filter thành `="HOSE"` → selftest FAIL đúng 2 test → revert; chứng minh test không pass giả.
- **Sửa `fscore`**: án sàn/kém thanh khoản giờ bị LOẠI THẲNG thay vì chỉ trừ 1/9 điểm (trước fix, mã đình chỉ đạt 8/9 vẫn lọt danh sách "khỏe mạnh" — vi phạm khế ước `base_ok`). Kết quả trên dữ liệu thật: 76 → 49 mã.

### Ghi chú tương thích
- 2 chế độ cũ `--tickers` / `--scan-market` giữ nguyên 100% tên file output.
- `.gitignore` bổ sung output cá nhân của analyzer (`analysis_latest.*`, `Focus_Analysis.md`, `Market_Scan.*`) — repo public chỉ chứa website.
- README (mục 2.5) đã đồng bộ với implementation.

---

## [0.9.0] — 2026-07-11 · Hợp nhất repo + tài liệu

- Thư mục VNSTOCK trở thành git repo của website `market-dashboard` (GitHub Pages); code `.py` và dữ liệu cá nhân gitignore toàn bộ.
- **`publish_dashboard.py`** thay `sync_and_push.bat`: whitelist tự bóc từ html/js, không bao giờ `git add .`, dry-run mặc định, tự retry `index.lock` (OneDrive).
- Ghép `signals.html` (tín hiệu nến/SMC) + `screener.html` (bảng lọc) vào site cùng `data/*.json` + fallback `*.js` cho `file://`.
- Tài liệu hợp nhất về **một `README.md`** (backend + frontend + cảnh báo); xóa `README_PIPELINE.md`, `GIAITHICH.md` (nội dung gộp vào phụ lục).

## [0.8.0] — 2026-07-10 · SMC + cổ tức + Việt hóa

- `candle_scan.py`: thêm Smart Money Concept (FVG/OB/BOS + confluence), góc cổ tức, xuất `data/*` cho dashboard.
- `metadata` thêm cột `dividend_yield` (%, từ KBS; `-1` = nguồn không có số); backfill bằng `meta_sync.py --ratio-only`.
- Việt hóa 31 tên cột screener (`COLUMN_LABELS` trong `app.js`), định dạng tiền/ngày kiểu Việt Nam.
- Fallback nguồn giá đổi TCBS → KBS (Quote vnstock v4 bỏ TCBS).

## [0.7.0] — 2026-07-09 · Refactor UI TradingView

- Viết lại toàn bộ giao diện: dark mode CSS variables, navbar chung `nav.css` cho 8 trang, 5 KPI cards, watchlist, 2 biểu đồ Chart.js, chips lọc nhanh, bảng screener phong cách TradingView. Chi tiết: [CHANGELOG_UI.md](CHANGELOG_UI.md).

## Giai đoạn nền — đến đầu 07/2026

- 6 chân kiềng quanh `vn_stock.db`: giá (`vn_stock_pipeline.py`, 1.686 mã / ~1,9 triệu dòng, backfill tự resume, 2 nguồn VCI+KBS) · metadata+luật (`meta_sync.py`, `blacklist_sync.py`) · mixer (`vn_indicators.py` → `screen_snapshot.csv` + `market_breadth.csv`) · vĩ mô (`macro_sync.py`) · tin tức (`news_sync.py`) · báo cáo AI (`ai_analyzer.py`, Claude API — chân duy nhất tốn phí).
- Các nguyên tắc sống còn hình thành từ giai đoạn này (rate-limit 60 req/phút, point-in-time, `meta` vs `metadata`, blacklist 2 lớp...) — nay ở README mục 4.

---

## Hạn chế đã biết (1.0.0-rc1)

- **F-Score là bản proxy** — kho chưa có BCTC nhiều kỳ (dòng tiền, biên lãi, đòn bẩy); 9 tiêu chí thay thế trộn chất lượng + xác nhận thị trường.
- **Điểm 0-100 là heuristic chưa được backtest** — trọng số là quy ước, chưa kiểm chứng bằng hiệu suất thật.
- **Kho chưa có ROA và nợ (D/E)** — Red Flags dùng proxy lỗ/ROE âm/án sàn.
- **Chưa có test tự động** — bug HSX sống 2 ngày là hệ quả trực tiếp.
- **Repo nằm trong OneDrive** — thỉnh thoảng lock file (đã bọc retry/try-except, chưa trị tận gốc).
- Chạy `--strategy <một tên>` ghi đè `analysis_latest.*` chỉ với chiến lược đó (hành vi chủ đích — file luôn phản ánh lần chạy gần nhất).

## Future Roadmap (ghi nhận — KHÔNG triển khai trong RC này)

> **Đã hoàn thành từ danh sách gốc** (giữ lại để tra cứu lịch sử, không còn là roadmap): `--selftest`
> (xem "Bổ sung ổn định hóa" ở mục [1.0.0-rc1] trên) và tích hợp `analysis.html` (xem mục [1.2.0] trên).

1. **`Backtester.run()`** (khi `watchlist_history` đủ ~4-6 tuần): join với `ohlcv` đo T+20/T+60 theo chiến lược → hiệu chỉnh `SCORE_WEIGHTS` bằng số liệu thật.
2. **Đưa analyzer vào `.bat` hằng ngày** (sau `vn_indicators.py`) để watchlist tích lũy đều.
3. **ROA / D-E**: mở rộng `meta_sync.py` khi nguồn KBS có — nâng F-Score gần bản chuẩn.
4. Cột tùy chọn screener, lưu bộ lọc vào localStorage, PWA nhẹ cho dashboard (từ CHANGELOG_UI §7). *(Panel chi tiết mã đã có một phần từ Phase 1-5 — xem `assets/js/company-panel.js` ở mục [1.2.0], hiện chỉ trên `screener.html`; mở rộng sang các bảng khác vẫn còn mở.)*

---

## Phụ lục — Roadmap cũ của FINANCIAL_REPORT (trước khi gộp 12/07/2026)

> Dự án `FINANCIAL_REPORT` không có `CHANGELOG.md` riêng — nội dung dưới là roadmap ghi trong
> `README.md` cũ của nó, giữ lại làm tham khảo (tên file đã cập nhật theo convention mới:
> `scrape_report.py` → `bctc_sync.py`, `financial_processor.py` → `bctc_processor.py`).
> Đây là backlog CHƯA triển khai, không phải cam kết lộ trình của VNSTOCK.

### Giai đoạn 1: Ổn định & chuẩn hóa
- [x] Tách hàm `normalize_period_str()` dùng chung cho cả `bctc_sync.py` và `bctc_processor.py`.
- [ ] Thêm unit test cho period parsing (các biến thể 2025Q1, 2025-Q1_1, 2024-year, v.v.).
- [x] Đảm bảo `scrape_meta.csv` ghi nhận đúng `period_type` (quarter/year).

### Giai đoạn 2: Mở rộng tính năng
- [ ] Hỗ trợ `--failed-only` theo từng loại báo cáo.
- [ ] Tích hợp SQLite `bctc.db` để lưu trữ dữ liệu thô đã crawl, phục vụ truy vấn SQL.
- [ ] Tự động lên lịch (cron/Windows Task Scheduler) chạy scrape sau mùa BCTC (T1/T4/T7/T10).

### Giai đoạn 3: Phân tích nâng cao
- [ ] Xuất flat table `bctc_flat.parquet` từ processor, sẵn sàng cho panel analysis.
- [ ] Xây dựng dashboard nhanh bằng Streamlit hoặc Power BI từ snapshot.
- [ ] Thêm chỉ số định giá (P/E, P/B) bằng cách merge dữ liệu giá từ VNSTOCK (nay cùng 1 repo, dễ làm hơn trước).

### Giai đoạn 4: CI/CD & Monitoring
- [ ] Thiết lập GitHub Actions chạy scrape + processor định kỳ.
- [ ] Gửi cảnh báo qua email/telegram khi có job thất bại liên tiếp.
- [ ] Tạo health-check script kiểm tra xem snapshot đã cập nhật đến quý gần nhất chưa.

---

*Quy ước phiên bản từ 1.0.0: MAJOR = đổi schema dữ liệu/kiến trúc · MINOR = tính năng mới · PATCH = sửa lỗi.*
