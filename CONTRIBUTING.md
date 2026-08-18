# Đóng góp

## Phạm vi

Đóng góp cho repository này có thể bao gồm mã nguồn Producer, kiểm thử, data contract và tài liệu kỹ thuật portable.

Không đưa database runtime, artifact sinh tự động, backup, thông tin xác thực hoặc quy trình phụ thuộc máy cá nhân vào repository. Runtime phải được chọn qua `STOCK_LOOKUP_RUNTIME_ROOT` hoặc cấu hình đã được phê duyệt; không giả định có workspace sibling.

## Tài liệu

- Giữ tiếng Việt là ngôn ngữ chính của các tài liệu hiện đang dùng tiếng Việt.
- Dùng đường dẫn tương đối cho tài nguyên trong repository.
- Đặt hướng dẫn dành riêng cho một máy hoặc một operator bên ngoài repository.
- Chỉ sửa phần cần thiết; không viết lại toàn bộ tài liệu khi một patch nhỏ đã đủ.

## Trước khi gửi thay đổi

Chạy các kiểm thử trực tiếp liên quan, kiểm tra diff, chạy `git diff --check` và xác nhận không có dữ liệu sinh tự động, database, backup hoặc thông tin xác thực trong thay đổi.

**Kiểm thử toàn bộ (Integration)**: Các bài kiểm thử toàn bộ vòng đời release yêu cầu có clone của repository `ai-core-private` (Consumer) nằm cùng cấp (sibling) với thư mục này. Nếu thiếu repository này, các bài test tích hợp liên quan sẽ tự động bị bỏ qua (skipped) mà không gây lỗi thu thập (collection error).

**Người dùng Windows**: Phải cấu hình `git config --global core.longpaths true` để tránh lỗi chiều dài đường dẫn khi pull các artifact kiểm tra.
