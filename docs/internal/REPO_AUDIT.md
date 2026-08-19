# Ghi chú kiểm toán repository

## Trạng thái

Bản kiểm toán ngày 2026-07-12 được thực hiện cho repository public `market-dashboard` trước khi Producer được tách sang repository private riêng. Các số liệu, cấu trúc file, remote và kết luận trong bản đó không còn đại diện cho repository hiện tại.

Tài liệu này không phục hồi hoặc tái sử dụng các kết luận cũ để tránh tạo thông tin sai lệch.

## Phạm vi cần kiểm toán lại

Một lần kiểm toán read-only mới nên kiểm tra riêng:

- file tracked, modified, untracked và ignored;
- ranh giới giữa source và dashboard runtime;
- database, artifact, backup và dữ liệu runtime có nguy cơ lọt vào Git;
- thông tin xác thực, đường dẫn phụ thuộc máy cá nhân và liên kết tài liệu;
- file lớn, file trùng lặp và dữ liệu sinh tự động;
- trạng thái remote, branch, tag và repository visibility.

Không xóa, di chuyển, hoàn nguyên hoặc thay đổi ignore rule chỉ dựa trên tài liệu này. Mọi hành động dọn dẹp phải được review riêng sau khi có bằng chứng kiểm toán mới.
