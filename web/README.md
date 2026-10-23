# Web

Giao diện VietDoc dùng browser ES modules thuần, không cần cài package. `src/` chứa login, upload receipt/invoice, status polling, image viewer, business field/line-item editor, revision review/approval, candidate adoption và approved JSON export.

Spring Boot đóng gói các file trong `web/src/` thành static resources khi chạy Maven; mở `http://localhost:8080/` sau khi backend khởi động. API calls cùng origin và cần bearer token; token chỉ lưu trong tab session. Dùng `node --test` để chạy domain tests.
