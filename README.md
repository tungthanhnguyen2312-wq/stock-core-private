# Stock Lookup

**Hạ tầng nghiên cứu và hỗ trợ ra quyết định cho cổ phiếu Việt Nam, lấy evidence làm nền tảng.**

Stock Lookup chuyển dữ liệu thị trường, evidence tài chính, sự kiện doanh nghiệp, ngữ cảnh định giá, cấu trúc kỹ thuật và đầu vào rủi ro thành các sản phẩm nghiên cứu tất định cho chứng khoán trên HOSE, HNX và UPCoM.

Hệ thống được thiết kế theo một nguyên tắc:

> **Dữ kiện và phép tính số học phải xuất phát từ evidence được lưu giữ và các bộ máy tính toán tất định. AI giải thích, tổng hợp, phản biện và làm rõ sự không chắc chắn — AI không trở thành authority về dữ liệu.**

<a id="what-the-project-does"></a>
## Dự án làm gì

```text
Market / financial / corporate evidence
        ↓
Raw retention + provenance
        ↓
Canonical + temporal + fitness semantics
        ↓
Deterministic research engines
        ↓
Market / technical / fundamental / valuation / event context
        ↓
Integrated research decision + trigger / invalidation
        ↓
AI research handoff
        ↓
Human decision + Dashboard
        ↓
Prospective outcome feedback
```

Quy trình production hiện tại được vận hành qua luồng Owner Daily chuẩn và phát hành các artifact nghiên cứu theo quy tắc quản trị tới các Consumer AI và Dashboard ở hạ nguồn.

<a id="core-principles"></a>
## Nguyên tắc cốt lõi

- **Evidence là nền tảng.** Các trạng thái chưa biết, cũ, proxy, bị chặn và đủ điều kiện luôn được thể hiện rõ.
- **Authority số liệu thuộc tính toán tất định.** Các phép tính có thể mô hình hóa được triển khai bằng Python và kiểm chứng bằng kiểm thử có thể tái hiện.
- **Đánh giá mức phù hợp ở cấp đặc trưng.** Authority còn thiếu chỉ chặn cách sử dụng phụ thuộc vào nó; không làm mất giá trị của nghiên cứu không liên quan.
- **Kỷ luật point-in-time.** Nghiên cứu hiện tại, tái dựng lịch sử và authority cho PIT/backtest là các chế độ riêng biệt.
- **Phân tích theo đặc thù ngành.** Ngân hàng, công ty chứng khoán, doanh nghiệp công nghiệp và các ngành khác không bị ép vào một mẫu tài chính chung.
- **AI là lớp nghiên cứu.** AI có thể giải thích và phản biện luận điểm, nhưng không được tạo ra dữ kiện tài chính, ngày giao dịch không hưởng quyền, xác suất hoặc authority cho giá mục tiêu.
- **Con người phê duyệt cuối cùng.** Trạng thái hành động phục vụ nghiên cứu không phải lệnh thực thi giao dịch.

<a id="public-project-map"></a>
## Bản đồ dự án dành cho người đọc

| Mảng nội dung | Điểm bắt đầu |
|---|---|
| Định hướng sản phẩm | [docs/PRODUCT_NORTH_STAR.md](docs/PRODUCT_NORTH_STAR.md) |
| Lộ trình chiến lược | [docs/NORTH_STAR.md](docs/NORTH_STAR.md) |
| Trạng thái vận hành hiện tại | [docs/ACTIVE_STATE.md](docs/ACTIVE_STATE.md) |
| Trạng thái thực thi đọc được bằng máy | [docs/ROADMAP_STATE.json](docs/ROADMAP_STATE.json) |
| Lịch sử lộ trình / quan hệ phụ thuộc | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Quyết định kiến trúc | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Cấu trúc runtime cụ thể | [docs/SYSTEM_MAP.md](docs/SYSTEM_MAP.md) |
| Hợp đồng đặc trưng phân tích và quyết định | [docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md](docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md) |
| CI / các tầng dependency | [docs/CI_AND_DEPENDENCY_TIERS.md](docs/CI_AND_DEPENDENCY_TIERS.md) |
| Di chuyển cấu trúc repository | [docs/REPOSITORY_LAYOUT_MIGRATION.md](docs/REPOSITORY_LAYOUT_MIGRATION.md) |
| Triển khai thu thập dữ liệu | [stocklookup_core/acquisition/](stocklookup_core/acquisition/) |
| Evidence từ tài liệu chính thức | [stocklookup_core/evidence/](stocklookup_core/evidence/) |
| Bảng dữ liệu tài chính, Financial V2 và nghiên cứu cơ bản | [stocklookup_core/financial/](stocklookup_core/financial/) |
| Tính toán định giá, doanh nghiệp so sánh và mở rộng đầu vào hiện tại | [stocklookup_core/valuation/](stocklookup_core/valuation/) |
| Đầu vào quyết định, ngữ cảnh, gói dữ liệu, bản tóm tắt và bản chiếu workspace | [stocklookup_core/decision/](stocklookup_core/decision/) |
| Ngữ cảnh kỹ thuật và định tuyến V2 (các nền tảng đóng băng giữ đường dẫn gốc) | [stocklookup_core/tactical/](stocklookup_core/tactical/) |
| Nghiên cứu luận điểm và quy trình phân tích/hồ sơ/đánh giá/tình huống/học từ kết quả | [stocklookup_core/research/](stocklookup_core/research/) |

<a id="canonical-runtime-path"></a>
## Luồng runtime chuẩn

```text
stocklookup.ps1
  └─ stocklookup.py
      └─ Owner Daily workflow
          ├─ governed session resolution
          ├─ market-data acquisition / reuse
          ├─ canonical research materialization
          ├─ tactical + financial + valuation integration
          ├─ integrated decision products
          ├─ AI handoff publication
          └─ Dashboard release + verification
```

Luồng ở cấp module có authority được mô tả tại [docs/SYSTEM_MAP.md](docs/SYSTEM_MAP.md).

<a id="current-execution-boundary"></a>
## Ranh giới thực thi hiện tại

Cổng nghiệm thu trực tiếp cho luồng Owner Daily thông thường ngày 1 tháng 10 năm 2026 đã hoàn tất. PR production đóng cổng này đã vượt qua Producer CI và được merge vào `main`.

Ưu tiên tiếp theo của lộ trình là **Độ phủ Current Research và mức phù hợp cho quyết định**: đo lường chứng khoán nào hiện có ngữ cảnh sử dụng được về giá, kỹ thuật, cơ bản, định giá, doanh nghiệp/sự kiện và quyết định tích hợp; sau đó ưu tiên các khoảng trống làm giảm đáng kể chất lượng quyết định.

Các nhánh cần authority cao hơn như RAW_AS_TRADED lịch sử đầy đủ, PIT backtesting, thanh khoản đủ điều kiện thực thi và xác định quy mô vị thế trực tiếp vẫn tách biệt, không được chặn Current Research không liên quan.

<a id="repository-structure"></a>
## Cấu trúc repository

Repository có cấu trúc phẳng từ trước và hiện còn nhiều module Python ở cấp cao nhất. Đây là nợ kỹ thuật đã được ghi nhận, không phải cấu trúc package đích.

Chính sách di chuyển là **từng bước và dựa trên đồ thị lời gọi**:

- không viết lại toàn bộ sang `src/`;
- không gọi một module là thành phần cũ chỉ dựa vào tên file;
- chỉ di chuyển nhóm capability khi đã hiểu các Consumer production và kiểm thử của chúng;
- di chuyển đi cùng công việc capability hữu ích, với kiểm chứng tính tương đương;
- thu gọn dần thư mục gốc công khai thành một nhóm nhỏ các điểm truy cập chính.

Xem [docs/REPOSITORY_LAYOUT_MIGRATION.md](docs/REPOSITORY_LAYOUT_MIGRATION.md).

<a id="development"></a>
## Phát triển

<a id="requirements"></a>
### Yêu cầu

- Python 3.11+ (hỗ trợ Python 3.13)
- Trên Windows, nên bật đường dẫn dài:
  `git config --global core.longpaths true`

<a id="install-core--test-dependencies"></a>
### Cài dependency lõi và kiểm thử

```bash
python -m pip install -r requirements.txt -r requirements-test.txt -c constraints.txt
```

Runtime của các nhà cung cấp tùy chọn được chủ động tách khỏi tầng lõi hermetic. Xem [docs/CI_AND_DEPENDENCY_TIERS.md](docs/CI_AND_DEPENDENCY_TIERS.md).

<a id="run-focused-verification"></a>
### Chạy kiểm tra tập trung

```bash
python -m pytest -q tests/test_production_call_shape_smoke.py
python -m py_compile stocklookup.py canonical_daily_operation.py daily_producer_pipeline.py
python tools/stocklookup_roadmap.py --check
```

CI có các bước kiểm tra riêng cho cấu trúc, hồi quy hermetic, evidence được lưu giữ và dạng lời gọi production.

<a id="contributing"></a>
## Đóng góp

Dự án tiếp nhận các đóng góp có thể tái hiện và có phạm vi rõ ràng. Bắt đầu với:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [AGENTS.md](AGENTS.md) để xem quy tắc thực thi dành cho AI agent

<a id="license"></a>
## Giấy phép

MIT — xem [LICENSE](LICENSE).

---

**Lưu ý về nghiên cứu:** Stock Lookup tạo đầu ra nghiên cứu định lượng và hỗ trợ ra quyết định. Hệ thống không cung cấp tư vấn đầu tư cá nhân hóa hoặc thực thi giao dịch tự động.
