# Web tests và legacy scaffold

Spring Boot render trang gốc bằng Thymeleaf. Runtime JavaScript/CSS cho login, upload, polling, viewer, editor, review/approval và export nằm ở `../backend/src/main/resources/static/`; template ở `../backend/src/main/resources/templates/`. API calls cùng origin dùng HTTP session và CSRF. Không triển khai React/npm runtime song song trong `web/src/`.

Node tests cho các asset đang chạy nằm ở `../backend/src/test/js/`; chạy `node --test` từ đó. Các marker/SPEC trong `web/src/` và `web/tests/` giữ lịch sử scaffold, không là authority triển khai mới.

UI hiển thị `manual` để nhập liệu thủ công và `demo` cho fixture giả lập trên sample đã biết. Chưa có OCR/model thật; `AI_MODE=http` vẫn fail-fast cho đến khi Java/Python dùng chung compute protocol và canonical assets theo run. Xem [Backend guide](../docs/team/backend.md) và [source structure](../docs/source-structure.md).
