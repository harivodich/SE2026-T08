# VietDoc Spring Boot

Java 17+, Maven Wrapper 3.9.11, Spring Boot 3.5.16, Hibernate/JPA, Flyway. Profile demo dùng H2 file; deployment dùng PostgreSQL.

## Chạy trên Windows (PowerShell)

```powershell
cd backend
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=demo"
```

Khi đổi nhánh có thay đổi migration/resource, dùng `.\mvnw.cmd clean test` trước khi đóng gói; `target/classes` cũ có thể giữ resource không còn trong source.

API chạy tại `http://localhost:8080`. Demo account `demo / demo-change-me` chỉ dành cho local. H2 và file nguồn nằm trong `backend/runtime/`, giữ qua restart, bị Git ignore.

Giao diện dùng Thymeleaf cho trang gốc; JavaScript/CSS chạy từ `src/main/resources/static/`. Mở `http://localhost:8080/`; API dùng HTTP session cùng origin và `X-CSRF-TOKEN` cho POST/PATCH. Node tests cho các asset này nằm tại `src/test/js/`.

PDF được render bằng child JVM (heap 384 MiB, timeout 15 giây, tối đa hai renderer cùng lúc) trước khi giữ DB transaction. Đây là giới hạn ứng dụng; môi trường production vẫn cần giới hạn tài nguyên ở OS/container.

Linux/macOS: `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo`.

## Bật AI thật

`AI_MODE=http` hiện fail-fast khi khởi động: [compute protocol](../specs/contracts/compute-api.md) đã có trên `develop`, nhưng Java client cũ chưa tương thích và canonical assets theo run chưa được tích hợp. Chỉ `manual` và `demo` khả dụng; `demo` dùng fixture giả lập, không chạy OCR/model thật. Khi tích hợp provider cần sửa client, kiểm chung contract fixtures/semantic rules và chạy HTTP smoke thật trước khi gỡ gate. Có thể chạy API với `WORKER_ENABLED=false`, rồi một process dùng cùng database/storage với `--spring.main.web-application-type=none --vietdoc.worker-enabled=true`.

## Chạy ngoài demo

`SEED_USERNAME`, `SEED_PASSWORD` (tối thiểu 10 ký tự) tạo tài khoản khi username chưa tồn tại. Thay SEED_PASSWORD không đổi mật khẩu tài khoản đã có. Không có đăng ký công khai, reset password hoặc quản trị user trong scope v1. Không bật profile demo khi triển khai dữ liệu thật.

Database dùng `DATABASE_URL=jdbc:postgresql://.../vietdoc`, `DATABASE_USER`, `DATABASE_PASSWORD`. Flyway tự chạy khi khởi động; Hibernate chỉ validate schema. Docker build từ repository root bằng `docker build -f backend/Dockerfile .` để đóng gói cả web assets.

Health: `/health/live`, `/health/ready`. OpenAPI authenticated: `/api/v1/openapi` (source ở `backend/src/main/resources/openapi.json`). Login `/api/v1/auth/session` tạo HTTP session, token nội bộ lưu hash và hạn dùng trong database; logout thu hồi token. Session cookie là HttpOnly, SameSite=Lax; bật `server.servlet.session.cookie.secure=true` khi phục vụ qua HTTPS.

Xem [SPEC](SPEC.md), [Backend guide](../docs/team/backend.md) và [source structure](../docs/source-structure.md) để phân biệt foundation đang chạy với các mốc tích hợp còn lại.
