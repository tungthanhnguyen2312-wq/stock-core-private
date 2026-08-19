# VALIDATION & AUDIT REPORT

Báo cáo chi tiết về logic tài chính, sơ đồ ngành, chuẩn hóa chu kỳ và kết quả kiểm thử snapshot đầu ra của hệ thống xử lý báo cáo tài chính.

## 1. Bảng Item Mapping (Static Item Mapping)

Bảng trích xuất tĩnh các chỉ tiêu tài chính từ tệp thô BCTC được cài đặt cố định trong code:

| Standardized Metric | Raw `item_id` Candidates (Coalesce Order) |
|---|---|
| `revenue` | `net_revenue, net_sales, revenue_from_securities_business_01_11, net_interest_income, interest_income_and_similar_income, total_net_revenue_from_insurance_business, revenue` |
| `net_profit` | `net_profit, profit_after_tax_for_shareholders_of_the_parents_company, profit_after_tax_for_shareholders_of_parent_company` |
| `gross_profit` | `gross_profit` |
| `operating_profit` | `operating_profit, net_profit_from_securities_business_20_50_40_60_61_62` |
| `total_assets` | `total_assets` |
| `total_liabilities` | `liabilities` |
| `equity` | `owners_equity` |
| `cash` | `cash_and_cash_equivalents, cash, cash_and_precious_metals` |
| `inventory` | `inventories, inventories_net` |
| `receivables` | `accounts_receivable` |
| `short_term_borrowings` | `short_term_borrowings` |
| `long_term_borrowings` | `long_term_borrowings` |
| `common_shares` | `common_shares` |
| `paid_in_capital` | `paid_in_capital` |
| `current_assets` | `current_assets` |
| `current_liabilities` | `current_liabilities` |
| `cost_of_goods_sold` | `cost_of_goods_sold` |
| `operating_cash_flow` | `operating_cash_flow` |
| `capex_raw` | `payment_for_fixed_assets_constructions_and_other_long_term_assets` |

## 2. Công thức tài chính đã được chuẩn hóa

Các công thức tài chính lõi được sử dụng trong `bctc_processor.py` để tính toán:

*   **Tốc độ tăng trưởng doanh thu YoY**:
    $$\text{Revenue Growth YoY} = \frac{\text{Revenue}_t - \text{Revenue}_{t-\text{prev}}}{\text{abs}(\text{Revenue}_{t-\text{prev}})}$$
    *Sử dụng hàm trị tuyệt đối ở mẫu số để đảm bảo tính đúng đắn khi doanh thu năm trước bị âm.*
*   **Dòng tiền tự do (Free Cash Flow - FCF)**:
    $$\text{Free Cash Flow} = \text{Operating Cash Flow} - \text{CAPEX}$$
    *Trong đó, CAPEX được lấy bằng trị tuyệt đối của chỉ tiêu thô `payment_for_fixed_assets_constructions_and_other_long_term_assets` (chỉ tiêu Tiền chi mua sắm tài sản cố định trong Báo cáo Lưu chuyển tiền tệ).*
*   **ROE (Return on Equity)**:
    $$\text{ROE} = \frac{\text{Net Profit}}{\text{Average Equity}}$$
    *Average Equity được tính bằng trung bình cộng Vốn chủ sở hữu kỳ này và kỳ trước liền kề ($(Equity_t + Equity_{t-1}) / 2.0$). Trường hợp thiếu dữ liệu kỳ trước, hệ thống tự động fallback sử dụng Ending Equity ($Equity_t$) nhằm tránh làm mất dòng dữ liệu.*
*   **EPS (Earnings per Share) — `eps_calc`, TỰ TÍNH (vá 12/07/2026)**:
    $$\text{EPS}_{\text{calc}} = \frac{\text{Net Profit}}{\text{Shares Outstanding}}$$
    *Đã bỏ cột `eps_quarterly` thô (nguồn KBS `earnings_per_share_vnd`): điều tra trên 10 mã đủ 4 loại hình cho thấy nguồn này thiếu hoàn toàn ở ngân hàng/chứng khoán/bảo hiểm (0/6 mã có số) và ở nhóm có số thì lệch scale không ổn định (chia 1000 chỉ đưa về đúng bậc độ lớn, lệch 0,6x–1,1x so với đối chứng, có kỳ lệch tới 40%) — xem `docs/AUDIT_REPORT.md` mục P0-2. `eps_calc` dùng `shares_outstanding` CUỐI KỲ (không phải bình quân gia quyền như EPS chuẩn VAS) nên là PROXY, có thể lệch với số công bố chính thức ở mã vừa phát hành/mua lại cổ phiếu giữa kỳ.*

## 3. Kết quả kiểm thử trên 10 mã (The Ultimate Validation Test)

Kết quả chạy thực tế trên tập 10 mã đại diện cho các ngành khác nhau:

| Ticker | Trạng thái Audit | Chu kỳ dữ liệu | Doanh thu | Biên Lợi nhuận gộp | Hệ số Thanh toán hiện hành | Hàng tồn kho |
|---|---|---|---|---|---|---|
| HPG | ✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) |
| FPT | ✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) |
| VNM | ✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) |
| SSI | ✅ HỢP LỆ (Ngành Chứng khoán - Revenue OK, Inventory NaN) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Không có (NaN) |
| VCB | ✅ HỢP LỆ (Ngành Ngân hàng - Graceful NaN) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Không có (NaN) | Không có (NaN) | Không có (NaN) |
| BID | ✅ HỢP LỆ (Ngành Ngân hàng - Graceful NaN) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Không có (NaN) | Không có (NaN) | Không có (NaN) |
| MBB | ✅ HỢP LỆ (Ngành Ngân hàng - Graceful NaN) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Không có (NaN) | Không có (NaN) | Không có (NaN) |
| BVH | ✅ HỢP LỆ (Ngành Bảo hiểm - Revenue OK) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Không có (NaN) | Đạt (Có giá trị) | Đạt (Có giá trị) |
| GAS | ✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) |
| MWG | ✅ HỢP LỆ (Ngành Sản xuất/Thương mại - Đầy đủ) | 2024-Q2 -> 2026-Q1 | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) | Đạt (Có giá trị) |

**Kết luận Audit:**
Hệ thống xử lý gracefully các giá trị trống (`NaN`) đối với các ngành đặc thù (Ngân hàng không có kho/thanh toán nhanh; Chứng khoán/Bảo hiểm không có biên gộp/kho), đảm bảo snapshot đầu ra có cấu trúc chuẩn hóa cao và tuyệt đối không xảy ra lỗi crash trong quá trình chạy.
