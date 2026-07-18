# AI Context

> File này dành cho AI/agent làm việc trên codebase VNSTOCK. Nội dung phản ánh code thực tế
> tại 2026-07-17. Không chứa secret. Tài liệu người đọc: `README.md` + `docs/`.

## Mục tiêu project

Pipeline Python chạy local thu thập và phân tích dữ liệu chứng khoán Việt Nam (~1.700 mã):
giá OHLCV hằng ngày, metadata cơ bản, vĩ mô, tin tức, cổ đông lớn, báo cáo tài chính quý (BCTC),
chỉ báo kỹ thuật và báo cáo AI — rồi xuất snapshot cho một dashboard tĩnh publish lên GitHub
Pages. **Thư mục này đồng thời là repo web `market-dashboard`**: git chỉ track website + tài
liệu (114 file); toàn bộ `*.py` và kho dữ liệu bị gitignore có chủ đích.

## Entry point

Chạy từ thư mục gốc (nhiều script mở `vn_stock.db` theo đường dẫn tương đối với CWD):

- Hằng ngày (đúng thứ tự): `python vn_stock_pipeline.py update` → `python macro_sync.py` →
  `python news_sync.py` → `python vn_indicators.py` → `python candle_scan.py` →
  `python publish_dashboard.py --live`
- Điều phối gọn (local, tùy chọn): `python run.py --task daily` / `python run.py --list`
- Định kỳ: `blacklist_sync.py` + `meta_sync.py --blacklist-only` (tuần) ·
  `shareholders_sync.py` (tháng) · `meta_sync.py --refresh`, `bctc_sync.py scrape` +
  `bctc_processor.py` (quý) · `ai_analyzer.py` (1-2 lần/tuần — GỌI API TỐN PHÍ, `--dry-run` miễn phí)
- Phân tích offline (0 request): `stock_analyzer.py --strategy all | --tickers ... | --scan-market`
- Publish web: `sync_and_publish.bat` (dry-run mặc định; chỉ `--live` mới commit/push)
- Toàn bộ lệnh + lịch chạy: `docs/CLI_REFERENCE.md`

## Thành phần quan trọng

| Module | Trách nhiệm |
|---|---|
| `vn_stock_pipeline.py` | OHLCV → bảng `ohlcv` + bảng tiến độ `meta` (KHÔNG đụng `meta` từ file khác) |
| `meta_sync.py` | Metadata cơ bản → bảng `metadata` (PK ticker, resume qua cột `updated`) |
| `vn_indicators.py` | Thư viện ~27 hàm chỉ báo + mixer: chỉ báo LEFT JOIN metadata → `screen_snapshot.csv`, `market_breadth.csv` |
| `macro_sync.py` | Vĩ mô thế giới/VN → bảng `macro` + `macro_snapshot.csv` + `data/macro_snapshot.json/.js` |
| `news_sync.py`, `blacklist_sync.py` | RSS → bảng `news` (PK link); lớp Auto của `blacklist.csv` từ trading_status VCI |
| `shareholders_sync.py` + `shareholder_pipeline.py` | Cổ đông lớn → bảng `shareholders`/`shareholders_progress` |
| `candle_scan.py` + `candlestick_patterns.py` | 31 mẫu nến 1D/1W/1M + SMC + heatmap → `ta_signals.*`, `data/*.json(.js)` |
| `stock_analyzer.py` | Quant engine offline: 10 chiến lược + ScoreEngine 0-100 → `analysis_latest.json/.md`, bảng `watchlist_history` (bảng DUY NHẤT analyzer được ghi) |
| `ai_analyzer.py` | Chưng cất 4 CSV + VNINDEX → Claude (Structured Outputs) → `ai_report_*.json/.md` |
| `bctc_sync.py` → `bctc_processor.py` + `financial_mapping.py` + `snapshot_rebuild.py` | Nhánh BCTC: cào `data_bctc/` → chuẩn hóa → `financial_snapshot.csv/.parquet` |
| `news_ticker_mapping.py`, `source_schema_guards.py` | Alias mã ↔ tin tức; guard schema nguồn (fail sớm khi cột đổi) |
| `publish_dashboard.py` | Publisher duy nhất: validate CSV, build fallback `.js`, whitelist tự bóc từ HTML — KHÔNG BAO GIỜ `git add .` |
| `tools/build_ai_bundle.py` | Đóng gói bản sao sạch (không data nặng/secret) sang `../ai-bundles/vnstock-ai/` |

Import phẳng giữa các file ở gốc (vd. `stock_analyzer` import `vn_indicators`;
`candle_scan` import `candlestick_patterns`; `snapshot_rebuild`/`bctc_processor` import
`financial_mapping`) — **không được di chuyển lẻ một file .py**.

## Luồng xử lý dữ liệu

```
nguồn (vnstock: VCI/KBS · FRED · Yahoo · World Bank · RSS)
  → script sync (7 chân kiềng)          → vn_stock.db (SQLite, ~177MB)
  → vn_indicators.py (mixer)            → screen_snapshot.csv + market_breadth.csv
  → candle_scan.py / macro_sync.py      → data/*.json + *.js (fallback file://)
  → stock_analyzer.py / ai_analyzer.py  → analysis_latest.json · ai_report_latest.*
  → publish_dashboard.py --live         → GitHub Pages (whitelist-only)
nhánh riêng: bctc_sync → data_bctc/*.csv/.parquet → bctc_processor → financial_snapshot.*
```

## Cấu trúc dữ liệu

- `vn_stock.db` — bảng: `ohlcv`, `meta` (tiến độ giá), `metadata` (PK ticker, có
  `dividend_yield`: -1 = nguồn không có), `macro` (PK series+date), `news` (PK link),
  `shareholders`, `shareholders_progress`, `watchlist_history`.
- `screen_snapshot.csv` — 29 cột (ticker, date, close, rsi14, macd_hist, bb_pctb, structure,
  rs_rating, exchange, industry, pe/pb/roe...). **Schema bị khóa**: `stock_analyzer.py` có guard
  dừng nếu thiếu cột; `publish_dashboard.py` validate trước khi đẩy.
- `analysis_latest.json` — bị test khóa cứng: 8 khóa top-level, `scores` 7 phần tử/mã,
  `explain` 6 mục. KHÔNG thêm cấu phần điểm mới.
- `data/*.json` luôn kèm bản `.js` (`window.__X = {...}`) làm fallback khi mở `file://`.
- `config/` — mapping BCTC/news/cổ đông (CSV/JSON, có `.meta.json` mô tả); `config.json` —
  tham số bctc_sync.

## Quy tắc khi chỉnh sửa

- Không thay đổi schema đầu ra (`screen_snapshot.csv`, `analysis_latest.json`,
  `financial_snapshot.*`) nếu chưa được yêu cầu — có test + guard khóa schema.
- Không ghi secret vào source code. `ANTHROPIC_API_KEY` chỉ nằm trong biến môi trường
  (xem `.env.example` — project KHÔNG tự đọc file `.env`).
- Không thay đổi crawler logic nếu không có test hoặc bằng chứng lỗi; luôn kiểm chứng API
  bằng request nhỏ (`--limit`) trước khi viết code; không chạy cào hàng loạt khi test.
- Cột `exchange` là `HSX` chứ KHÔNG phải `HOSE` (so sánh dùng `.isin(("HSX","HOSE"))`).
  Bảng `meta` (tiến độ) ≠ bảng `metadata` (fundamentals) — đừng nhầm.
- Mọi script phải `sys.stdout.reconfigure(encoding="utf-8")` (console Windows cp1252).
- Repo là web GitHub Pages: KHÔNG di chuyển HTML/CSV/data/ khỏi gốc (gãy URL + fetch path);
  KHÔNG `git add .`; KHÔNG force push; publish chỉ qua `publish_dashboard.py`.
- `.gitignore` được xây kỹ theo từng đợt có ghi ngày — chỉ bổ sung, không viết lại.
- Python 3.13, dependency pin tối thiểu trong `requirements.txt` — không nâng cấp đồng loạt.
