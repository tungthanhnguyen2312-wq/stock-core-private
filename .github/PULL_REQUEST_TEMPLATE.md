<a id="summary"></a>
## Tóm tắt

Mô tả thay đổi và vấn đề được giải quyết.

<a id="scope"></a>
## Phạm vi

- Những nội dung nào được chủ động thay đổi?
- Những nội dung nào được xác định rõ là ngoài phạm vi?

<a id="validation"></a>
## Kiểm chứng

Liệt kê các kiểm thử tập trung, bước kiểm tra hoặc evidence có thể tái hiện đã dùng để kiểm chứng thay đổi.

<a id="data--authority-impact"></a>
## Tác động đến dữ liệu / authority

Nếu thay đổi liên quan đến dữ liệu thị trường, ngữ nghĩa nguồn, hành vi point-in-time hoặc điều kiện sử dụng trong phân tích, hãy nêu authority hiện có làm căn cứ và xác nhận thay đổi không âm thầm mở rộng authority đó. Dùng `UNKNOWN` / hành vi fail-closed khi evidence chưa đủ.

<a id="safety-checklist"></a>
## Danh sách kiểm tra an toàn

- [ ] Không có thông tin xác thực, cơ sở dữ liệu runtime, bản sao lưu hoặc artifact sinh tự động trong thay đổi.
- [ ] Các kiểm thử/bước kiểm tra liên quan đều đạt.
- [ ] `git diff --check` đạt.
- [ ] Chỉ cập nhật tài liệu ở những nơi cần thiết.
- [ ] Mọi thay đổi ảnh hưởng authority hoặc production đều có phê duyệt rõ ràng của người duy trì.
