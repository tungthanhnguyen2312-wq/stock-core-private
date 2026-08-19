# CHANGELOG UI — Refactor giao diện toàn dự án

## Cập nhật 2026-07-14 — Bảng mẫu hình nến

- `signals.html` có tab “Mẫu hình nến” nhưng giữ nguyên Watchlist, hợp lưu, cổ tức và heatmap trong tab Tổng quan.
- Thêm summary, 11 nhóm filter, sort, sticky table, trạng thái forming/completed bằng chữ, sao SVG có accessible label và điều hướng bàn phím.
- `assets/js/candlestick-patterns.js` ưu tiên JSON, fallback global JS khi `file://`, validate schema và escape toàn bộ chuỗi động; không hiện path/file/exception trên UI.
- Layout kiểm soát tràn ngang ở 375/768/1024/1440px, focus visible và reduced-motion; company panel được mở rộng thành API dùng chung với Screener.

---

## Cập nhật 2026-07-14 — Dashboard Vĩ mô

- Thay nội dung khung `macro.html` bằng dashboard dữ liệu pipeline: overview, tối đa 8 KPI thật, biểu đồ Chart.js chỉ khi đủ lịch sử, empty state khối ngoại và bảng toàn bộ chỉ báo.
- Thêm `assets/css/macro.css` và `assets/js/macro.js`; DOM động dùng `textContent`/node API, link nguồn được kiểm tra protocol và mở tab mới an toàn.
- Responsive tại 375/768/1024/1440px, bảng cuộn ngang trên mobile, canvas có mô tả truy cập, tôn trọng `prefers-reduced-motion`.
- Delta chỉ biểu diễn hướng tăng/giảm; không tự gắn diễn giải “tốt/xấu” cho CPI, VIX, USD/VND hay US10Y.

---

## Cập nhật 2026-07-13 — Frontend Phase 1-5 (khung sườn Tailwind + redesign)

Tóm tắt kiến trúc đầy đủ: xem [CHANGELOG.md](CHANGELOG.md) mục `[1.2.0]`. Phần này ghi riêng các
thay đổi giao diện/UI cụ thể, theo đúng phạm vi của file này:

- **Sidebar + top bar dùng chung mới** (`assets/css/shell.css`, `assets/js/shell.js`) thay `nav.css`
  cho 7 trang chính; `nav.css` nay chỉ còn phục vụ báo cáo tĩnh lưu trữ (`playbook-*`/`report-*`).
  Sidebar thu gọn được (icon-only), nhớ trạng thái qua `localStorage`.
- **Tailwind CDN** thêm CHỈ cho khung sườn (Preflight tắt) — Bootstrap 5 + design system `style.css`
  cũ vẫn nguyên vẹn cho nội dung dữ liệu bên trong (card/bảng/badge), không phải một cuộc migrate.
- **Lucide Icons** (CDN) thay icon chữ/emoji ở khung sườn.
- **2 component mới**: panel 2 cột kéo giãn tỷ lệ (`assets/js/resizable-panels.js`, ở `dashboard.html`/
  `analysis.html`) và panel chi tiết mã trượt từ phải khi bấm dòng bảng (`assets/js/company-panel.js`,
  chỉ ở `screener.html`) — 3 tab Tổng quan/Biểu đồ/Báo cáo tài chính (tab BCTC báo trạng thái
  "đang chờ dữ liệu" trung thực, chưa có số vì `financial_snapshot.*` không public).
- Style bảng DataTables đổi từ id riêng (`#market-table`) sang class dùng chung `.vs-datatable`.
- Thêm `@media (prefers-reduced-motion: reduce)` áp dụng toàn site.
- 3 trang mới: `about.html`, `archive.html` (danh sách ghi tay trong `archive.js`), `macro.html`
  (đã được nối với web snapshot ở bản cập nhật 14/07/2026).
- `index.html` đổi vai trò: từ trang chính (Bootstrap, `nav.css`) thành redirect thuần sang
  `dashboard.html` (trang chính mới), giữ nguyên URL gốc GitHub Pages.

---

## Cập nhật 2026-07-10 — Việt hóa bảng screener

- Toàn bộ 31 tên cột chuyển sang tiếng Việt (`Mã`, `Ngày`, `Giá đóng cửa (₫)`, `% Phiên`, `GTGD 20p (tỷ)`, `RS`, `Cấu trúc`...) qua bảng ánh xạ `COLUMN_LABELS` trong `app.js` — field gốc trong CSV giữ nguyên nên lọc/sort không đổi.
- Giá đóng cửa định dạng tiền Việt: `15400` → `15.400` (chỉ đổi hiển thị, sort vẫn theo số).
- Cột ngày hiển thị `dd/mm/yyyy` theo chuẩn Việt Nam.

---

**Ngày:** 2026-07-09
**Phạm vi:** Toàn bộ 8 trang HTML + CSS + JS. Không thay đổi chức năng, logic xử lý, luồng dữ liệu hay liên kết giữa các trang.

---

## 1. Các file đã chỉnh sửa

| File | Mức độ | Nội dung |
|---|---|---|
| `index.html` | Viết lại layout | Dashboard mới: navbar + KPI + 2 cột nội dung |
| `style.css` | Viết lại | Design system dark mode bằng CSS variables |
| `nav.css` | **Mới** | Component navbar dùng chung cho cả 8 trang |
| `app.js` | Mở rộng | Giữ nguyên logic cũ, thêm lớp hiển thị UI |
| `playbook-2026-04-01.html` | Sửa nhỏ | Thay nav inline cũ bằng nav chung + link `nav.css` |
| `playbook-2026-04-02.html` | Sửa nhỏ | Như trên |
| `playbook-2026-04-03.html` | Sửa nhỏ | Như trên |
| `playbook-2026-04-09.html` | Sửa nhỏ | Như trên |
| `report-2026-04-21.html` | Sửa nhỏ | Như trên |
| `vnindex_playbook_2026-04-03.html` | Sửa nhỏ | Chèn nav chung (trước đây không có nav) |
| `vn_crosscheck_update_2026-04-08.html` | Sửa nhỏ | Như trên |
| `CHANGELOG_UI.md` | **Mới** | File này |

## 2. Theme & Design System

- Dark mode toàn trang theo palette: nền `#0F172A`, card `#1E293B`, border `#334155`, chữ `#F8FAFC`, phụ `#94A3B8`, primary `#3B82F6`, success `#22C55E`, warning `#F59E0B`, danger `#EF4444`.
- Toàn bộ màu khai báo bằng **CSS variables** trong `:root` — đổi theme chỉ cần sửa một chỗ.
- Font **Inter** (Google Fonts), heading 600–700, body 400–500, số dùng `tabular-nums` để thẳng cột.
- Bootstrap 5 chạy ở chế độ `data-bs-theme="dark"`, các component được override bằng design system riêng.

## 3. Thành phần UI mới

- **Navbar dùng chung (`nav.css`)**: sticky trên Dashboard, hiện diện đồng bộ trên cả 7 trang báo cáo cũ; đánh dấu trang hiện tại; cuộn ngang trên mobile; các trang cũ trước đây dùng nav pill inline-style mỗi trang một kiểu nay đã thống nhất.
- **5 KPI Cards** đầu trang (chỉ dùng dữ liệu có sẵn):
  - Regime thị trường (từ `ai_report_latest.json`, tô màu bull/neutral/bear)
  - Rủi ro danh mục (low/medium/high)
  - Breadth % mã trên MA200 (tính từ CSV, có progress bar)
  - % mã cấu trúc UP (tính từ CSV, có progress bar)
  - Số mã thanh khoản cao GTGD20 ≥ 50 tỷ
- **Watchlist hôm nay**: render `stock_notes` từ JSON thành danh sách mở rộng được (ticker + badge stance màu: MUA THĂM DÒ / CHỜ SETUP / THEO DÕI / TRÁNH + logic vào lệnh + cờ rủi ro).
- **Kế hoạch hành động**: render `action_plan` từ JSON.
- **2 biểu đồ Chart.js** (tính từ CSV, không thêm dữ liệu mới):
  - Bar ngang: % mã trên MA200 theo ngành (top 10, ngành ≥ 8 mã, tô màu theo ngưỡng)
  - Doughnut: phân bố cấu trúc giá UP/SIDE/DOWN
- **10 nút lọc nhanh (chips)** cho screener + nút xóa lọc: Top RS ≥ 90, CANSLIM, SMC UP, Gần Swing Low ≤ 10%, Thanh khoản ≥ 50 tỷ, Room ngoại > 20%, PE < 15, ROE > 15%, RSI < 30, RSI > 70. Các chip kết hợp theo logic AND và hoạt động cùng bộ lọc sàn/ngành + ô tìm kiếm.
- **Nút Xem đầy đủ / Thu gọn** cho báo cáo AI (mặc định thu gọn có hiệu ứng mờ dần).

## 4. Bảng screener (phong cách TradingView)

- Header cố định khi cuộn dọc (`scrollY` + sticky), cuộn ngang khi thiếu chỗ.
- Zebra rows + hover highlight xanh.
- **Conditional formatting**:
  - `rs_rating`: badge xanh (>90) / vàng (80–90) / xám (<80)
  - `rsi14`: xanh đậm (<30 quá bán) / đỏ (>70 quá mua)
  - `structure`: badge UP xanh / SIDE vàng / DOWN đỏ
  - `gtgd20_ty`: xanh đậm (≥100 tỷ), làm mờ (<3 tỷ)
  - Cột % biến động (`chg_today_pct`, `ret_*`, `macd_hist`...): xanh/đỏ theo dấu
  - Cột boolean (`above_sma50/200`, `golden_cross`, `near_52w_high`): ✓ / ·
  - `ticker`: in đậm màu xanh nhạt
- Sort icon của DataTables được tô màu primary; phân trang, ô tìm kiếm, select đều theo dark theme.

## 5. Tối ưu đã áp dụng

- **Gom CSS dùng chung**: nav của 8 trang trước đây là inline-style lặp lại từng trang (mỗi pill ~200 ký tự style) → một file `nav.css` + class ngữ nghĩa; đã gỡ toàn bộ inline nav cũ.
- CSS component hóa (`.kpi`, `.chip`, `.badge-soft`, `.watch-item`, `.archive-list`...), không còn style lặp.
- Escape HTML mọi dữ liệu động trước khi chèn DOM (chống vỡ layout/XSS từ dữ liệu).
- Animation nhẹ: fade-in card, hover nâng KPI card, hover đổi màu dòng bảng/nút — không dùng animation nặng.
- Responsive kiểm tra ở 375px (mobile): không tràn ngang, KPI xếp dọc, bảng và nav cuộn ngang trong container riêng.
- Class prefix `vs-` cho nav để không xung đột với Tailwind/CSS nội bộ các trang báo cáo cũ.

## 6. Không thay đổi (đúng cam kết)

- Toàn bộ ID mà JS sử dụng giữ nguyên: `ai-report`, `report-date`, `last-updated`, `filter-exchange`, `filter-industry`, `market-table`, `table-status`.
- Logic fetch/parse (marked.js, PapaParse, DataTables) và cách lọc theo sàn/ngành giữ nguyên.
- Liên kết giữa các trang giữ nguyên đường dẫn tương đối (an toàn GitHub Pages).
- Nội dung các báo cáo lịch sử không bị đụng đến (chỉ thêm navbar).

## 7. Đề xuất nâng cấp tiếp theo

1. **Cột tùy chọn cho screener**: cho phép ẩn/hiện nhóm cột (kỹ thuật / cơ bản / thanh khoản) bằng DataTables `colvis` để bớt cuộn ngang.
2. **Lưu trạng thái bộ lọc** vào `localStorage` để giữ nguyên bộ lọc giữa các lần mở trang.
3. **Trang chi tiết mã**: click ticker mở modal tổng hợp các chỉ số của mã đó từ CSV (không cần dữ liệu mới).
4. **Tự động hóa kho lưu trữ**: sinh file `reports_manifest.json` trong `sync_and_push.bat` để sidebar và navbar tự cập nhật danh sách báo cáo, khỏi sửa tay HTML.
5. **Sparkline cột ret_1m/3m/6m/12m**: vẽ mini-bar ngay trong ô để đọc xu hướng nhanh hơn.
6. **PWA nhẹ**: thêm manifest + icon để "cài" dashboard lên màn hình điện thoại.
