# Web

Giao diện VietDoc dùng browser ES modules thuần, không cần cài package. `src/` chứa login, upload receipt/invoice, status polling, image viewer, business field/line-item editor, revision review/approval, candidate adoption và approved JSON export.

Spring Boot render trang gốc bằng Thymeleaf và đóng gói các module trong `web/src/` thành static resources; mở `http://localhost:8080/` sau khi backend khởi động. API calls cùng origin dùng HTTP session và CSRF token từ trang. Dùng `node --test` để chạy web tests.
