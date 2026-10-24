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

Giao diện dùng Thymeleaf cho trang gốc và đóng gói các module JavaScript/CSS từ `../web/src/`. Mở `http://localhost:8080/`; API dùng HTTP session cùng origin và `X-CSRF-TOKEN` cho POST/PATCH.

PDF được render bằng child JVM (heap 384 MiB, timeout 15 giây, tối đa hai renderer cùng lúc) trước khi giữ DB transaction. Đây là giới hạn ứng dụng; môi trường production vẫn cần giới hạn tài nguyên ở OS/container.

Linux/macOS: `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo`.

## Bật AI thật

`AI_MODE=http` hiện fail-fast khi khởi động vì repo chưa có compute contract chung và canonical assets theo run. Các biến `AI_MODE`/`PIPELINE_MANIFEST` vẫn được đọc trong profile `demo`, nhưng chỉ `manual` và `demo` khả dụng. Sau khi chốt contract và tích hợp Python thật, cần gỡ gate này cùng với contract fixtures và smoke test. Có thể chạy API với `WORKER_ENABLED=false`, rồi một process dùng cùng database/storage với `--spring.main.web-application-type=none --vietdoc.worker-enabled=true`.

## Chạy ngoài demo

`SEED_USERNAME`, `SEED_PASSWORD` (tối thiểu 10 ký tự) tạo tài khoản khi username chưa tồn tại. Thay SEED_PASSWORD không đổi mật khẩu tài khoản đã có. Không có đăng ký công khai, reset password hoặc quản trị user trong scope v1. Không bật profile demo khi triển khai dữ liệu thật.

Database dùng `DATABASE_URL=jdbc:postgresql://.../vietdoc`, `DATABASE_USER`, `DATABASE_PASSWORD`. Flyway tự chạy khi khởi động; Hibernate chỉ validate schema. Docker build từ repository root bằng `docker build -f backend/Dockerfile .` để đóng gói cả web assets.

Health: `/health/live`, `/health/ready`. OpenAPI authenticated: `/api/v1/openapi` (source ở `backend/src/main/resources/openapi.json`). Login `/api/v1/auth/session` tạo HTTP session, token nội bộ lưu hash và hạn dùng trong database; logout thu hồi token. Session cookie là HttpOnly, SameSite=Lax; bật `server.servlet.session.cookie.secure=true` khi phục vụ qua HTTPS.
