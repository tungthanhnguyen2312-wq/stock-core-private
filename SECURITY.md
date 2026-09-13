# Chính sách bảo mật

## Phạm vi

Repository này là public open-core và chứa mã nguồn Producer, kiểm thử, data contract và tài liệu kỹ thuật có thể công khai. Database runtime, artifact sinh tự động, backup, thông tin xác thực, dữ liệu bị hạn chế tái phân phối và private operational state phải nằm ngoài repository.

Dashboard runtime được chọn thông qua `STOCK_LOOKUP_RUNTIME_ROOT`. Không dùng đường dẫn tuyệt đối hoặc giả định về cấu trúc workspace sibling khi tái hiện vấn đề.

Xem thêm [Public / Open-Core Boundary](docs/PUBLIC_OPEN_CORE_POLICY.md).

## Secrets và thông tin xác thực

Không commit:

- `.env` có secret;
- API key/secret, access token, cookie, certificate/private key;
- broker/account credential;
- recovery code hoặc secret-bearing log;
- credential-bearing URL hoặc command history.

Nếu một secret từng được commit hoặc đăng công khai, hãy coi secret đó đã bị lộ: revoke/rotate tại provider trước, sau đó mới xử lý lịch sử Git nếu cần. Xóa secret khỏi HEAD không làm secret cũ trở nên an toàn.

Không yêu cầu người dùng paste secret vào issue, pull request hoặc chat công khai.

## Dữ liệu và operational assets

Không đưa lên repository public:

- paid/licensed/provider-restricted raw data nếu không có quyền tái phân phối;
- retained private evidence payloads;
- production database hoặc backup;
- private portfolio, holdings, order history hoặc position sizes;
- execution config, private risk limits hoặc proprietary calibration;
- log/artifact làm lộ machine-specific sensitive state.

Dữ liệu minh họa nên là synthetic, redacted hoặc có quyền tái phân phối rõ ràng.

## Báo cáo vấn đề bảo mật

Hãy báo cáo riêng cho người duy trì repository khi phát hiện lỗ hổng hoặc nguy cơ rò rỉ dữ liệu. Nếu GitHub Private Vulnerability Reporting được bật cho repository, ưu tiên kênh đó. Không đăng công khai thông tin xác thực, database runtime, dữ liệu tài chính cá nhân, artifact vận hành hoặc nội dung nhạy cảm.

Báo cáo nên có mô tả, phạm vi ảnh hưởng, bước tái hiện tối thiểu và dữ liệu mẫu đã được loại bỏ thông tin nhạy cảm.

## Dependency và supply-chain

Pull request thêm dependency mới phải nêu rõ nguồn, license và mục đích. Không thêm package chỉ để thay thế một primitive nhỏ nếu không có lý do kỹ thuật rõ ràng. Không chạy script cài đặt hoặc binary không rõ nguồn trên máy có credentials/runtime data.

## Phiên bản được duy trì

Branch `main` là branch được duy trì. Các branch hoặc snapshot cũ không có cam kết vá lỗi độc lập.
