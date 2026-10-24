# ADR 0009 — Web session và Thymeleaf

Status: Accepted — lựa chọn của Lead ngày 24/10/2026 khi xử lý review PR #1.

## Quyết định

Spring Boot render trang gốc bằng Thymeleaf. Browser dùng HTTP session cookie cùng origin; token xác thực nội bộ không trả về JavaScript. Các request POST/PATCH gửi CSRF token từ trang. Editor JavaScript hiện tại tiếp tục xử lý trạng thái tương tác, nhưng base revision cố định và mọi mutation vẫn qua API có CAS.

## Lý do và hệ quả

Hướng này khớp lựa chọn session/Thymeleaf của Lead mà vẫn giữ được workflow editor hiện có. Session ID được đổi khi đăng nhập; logout thu hồi token nội bộ và hủy session. Cần kiểm browser lifecycle, cookie policy và CSRF trong CI. Chạy nhiều API instance cần session store chung hoặc sticky session; cấu hình triển khai này chưa được chứng minh trong PR.
