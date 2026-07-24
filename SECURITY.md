# Chính sách bảo mật

## Phạm vi

Repository này chứa mã nguồn Producer, kiểm thử, data contract và tài liệu kỹ thuật. Database runtime, artifact sinh tự động, backup và thông tin xác thực phải nằm ngoài repository.

Dashboard runtime được chọn thông qua `STOCK_LOOKUP_RUNTIME_ROOT`. Không dùng đường dẫn tuyệt đối hoặc giả định về cấu trúc workspace sibling khi tái hiện vấn đề.

## Báo cáo vấn đề bảo mật

Hãy báo cáo riêng cho người duy trì repository khi phát hiện lỗ hổng hoặc nguy cơ rò rỉ dữ liệu. Không đăng công khai thông tin xác thực, database runtime, dữ liệu tài chính cá nhân, artifact vận hành hoặc nội dung nhạy cảm.

Báo cáo nên có mô tả, phạm vi ảnh hưởng, bước tái hiện tối thiểu và dữ liệu mẫu đã được loại bỏ thông tin nhạy cảm.

## Phiên bản được duy trì

Branch `main` là branch được duy trì. Các branch hoặc snapshot cũ không có cam kết vá lỗi độc lập.
