# Stock Look Up — Producer

Codex governance source of truth: [docs/STATE.md](docs/STATE.md), [docs/ROADMAP.md](docs/ROADMAP.md), [docs/DECISIONS.md](docs/DECISIONS.md), and [docs/AI_RULES.md](docs/AI_RULES.md). Producer owns source qualification, canonicalization, and artifact authority; its active responsibility is P0 market-data basis and lineage.

Repository này chứa mã nguồn phía Producer của Stock Look Up. Producer thu thập, chuẩn hóa, kiểm tra và xuất dữ liệu thị trường cùng các artifact phục vụ Consumer và dashboard.

## Phạm vi repository

- Mã nguồn Producer, kiểm thử, data contract và tài liệu kỹ thuật portable được quản lý tại đây.
- Database runtime, artifact sinh tự động, backup, thông tin xác thực và lệnh phụ thuộc máy cá nhân không thuộc repository.
- Consumer, dashboard/runtime và AI runtime được quản lý trong các workspace riêng.
- Biến `STOCK_LOOKUP_RUNTIME_ROOT` phải trỏ tới dashboard runtime được chọn cho phiên chạy; không suy luận runtime từ thư mục sibling.

## Thiết lập phát triển

**Yêu cầu hệ thống trên Windows**: Repository này chứa một số đường dẫn dài (đặc biệt trong thư mục `operations-review`). Người dùng Windows phải bật `core.longpaths` trước khi clone để tránh lỗi `Filename too long`:
```powershell
git config --global core.longpaths true
```

Chạy lệnh từ thư mục gốc của repository và cấu hình dashboard runtime trước các tác vụ đọc hoặc ghi dữ liệu vận hành.

```powershell
Set-Location <producer-repository>
$env:STOCK_LOOKUP_RUNTIME_ROOT = '<dashboard-runtime-root>'
python -m pip install -r requirements.txt

# Post-close local dry run with canonical financial facts enabled:
python tools/operate_stocklookup.py --runtime-root <dashboard-runtime-root> --include-canonical-financial-facts
```

Xem [CONTRIBUTING.md](CONTRIBUTING.md) về phạm vi đóng góp, [SECURITY.md](SECURITY.md) về báo cáo vấn đề bảo mật và thư mục [docs/](docs/) về contract dữ liệu cùng tài liệu kỹ thuật.

> Dữ liệu và kết quả phân tích chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.
