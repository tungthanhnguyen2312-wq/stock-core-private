# Đóng góp

## Phạm vi

Đóng góp cho repository này có thể bao gồm mã nguồn Producer, kiểm thử, data contract và tài liệu kỹ thuật portable nằm trong [public/open-core boundary](docs/PUBLIC_OPEN_CORE_POLICY.md).

Không đưa database runtime, artifact sinh tự động, backup, thông tin xác thực, dữ liệu có hạn chế tái phân phối, portfolio cá nhân, execution config hoặc quy trình phụ thuộc máy cá nhân vào repository. Runtime phải được chọn qua `STOCK_LOOKUP_RUNTIME_ROOT` hoặc cấu hình đã được phê duyệt; không giả định có workspace sibling.

## Quyền sở hữu và license của đóng góp

Khi gửi contribution, người đóng góp xác nhận rằng họ có quyền gửi nội dung đó và đồng ý rằng phần contribution được chấp nhận vào repository sẽ được phân phối theo MIT License của repository, trừ khi có thỏa thuận bằng văn bản khác trước khi merge.

Không sao chép source code, dataset, tài liệu, model output hoặc nội dung bên thứ ba nếu quyền tái phân phối không rõ ràng. Nếu contribution dựa trên tài liệu hoặc chuẩn bên ngoài, hãy dẫn nguồn và chỉ đưa vào phần mà license/terms cho phép.

Đối với source-code contribution lớn hoặc contribution có thể ảnh hưởng đáng kể đến quyền sở hữu trí tuệ, maintainer có thể yêu cầu contributor agreement bổ sung trước khi merge. Việc mở pull request không mặc nhiên buộc maintainer phải chấp nhận contribution đó.

## Public / private boundary

Repository public không phải là nơi lưu toàn bộ operational moat của Stock Lookup. Không commit:

- API keys, secrets, token, cookies, certificates hoặc credential-bearing config;
- raw/provider data không có quyền tái phân phối;
- production databases, retained private evidence hoặc machine-specific state;
- portfolio/holdings/order history/position sizing của cá nhân;
- execution credentials, broker config hoặc private risk limits;
- proprietary calibration, live ranking thresholds hoặc private operating policy được owner giữ ngoài public core;
- nội dung làm lộ private infrastructure hoặc recovery material.

Nếu không chắc một artifact có được public hay không, dừng và yêu cầu maintainer phân loại trước khi đưa vào Git.

## Tài liệu

- Giữ tiếng Việt là ngôn ngữ chính của các tài liệu hiện đang dùng tiếng Việt.
- Dùng đường dẫn tương đối cho tài nguyên trong repository.
- Đặt hướng dẫn dành riêng cho một máy hoặc một operator bên ngoài repository.
- Chỉ sửa phần cần thiết; không viết lại toàn bộ tài liệu khi một patch nhỏ đã đủ.
- Không biến tài liệu public thành nơi mô tả secrets, private runtime paths hoặc live portfolio state.

## Trước khi gửi thay đổi

Chạy các kiểm thử trực tiếp liên quan, kiểm tra diff, chạy `git diff --check` và xác nhận không có dữ liệu sinh tự động, database, backup, thông tin xác thực hoặc nội dung ngoài public boundary trong thay đổi.

Pull request nên nêu rõ:

- capability nào thay đổi;
- authority có thay đổi hay không;
- test/validation đã chạy;
- có thêm dependency hoặc dữ liệu bên thứ ba hay không;
- contribution có chứa hoặc yêu cầu asset không thể tái phân phối hay không.

**Kiểm thử toàn bộ (Integration)**: Các bài kiểm thử toàn bộ vòng đời release yêu cầu có clone của repository `ai-core-private` (Consumer) nằm cùng cấp (sibling) với thư mục này. Nếu thiếu repository này, các bài test tích hợp liên quan sẽ tự động bị bỏ qua (skipped) mà không gây lỗi thu thập (collection error).

**Người dùng Windows**: Phải cấu hình `git config --global core.longpaths true` để tránh lỗi chiều dài đường dẫn khi pull các artifact kiểm tra.
