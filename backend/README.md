# VietDoc Spring Boot

Java 17+, Maven Wrapper 3.9.11, Spring Boot 3.5.16, Hibernate/JPA, Flyway. Profile demo dùng H2 file; deployment dùng PostgreSQL.

## Chạy trên Windows (PowerShell)

```powershell
cd backend
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=demo"
```

API chạy tại `http://localhost:8080`. Demo account `demo / demo-change-me` chỉ dành cho local. H2 và file nguồn nằm trong `backend/runtime/`, giữ qua restart, bị Git ignore.

Giao diện Web được Maven đóng gói từ `../web/src/` và phục vụ tại `http://localhost:8080/`; API giữ nguyên xác thực bearer.

Linux/macOS: `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo`.

## Bật AI thật

Đặt `AI_MODE=http`, `PIPELINE_MANIFEST=<release đã thống nhất>`, `AI_WORKER_URL=<endpoint /extract>`, `AI_WORKER_TOKEN=<secret riêng>`. Worker HTTP cần chạy trước; xem [contract AI](../docs/ai-worker-contract.md). Có thể chạy API với `WORKER_ENABLED=false`, rồi một process dùng cùng database/storage với `--spring.main.web-application-type=none --vietdoc.worker-enabled=true`.

## Chạy ngoài demo

`SEED_USERNAME`, `SEED_PASSWORD` (tối thiểu 10 ký tự) tạo tài khoản khi username chưa tồn tại. Thay SEED_PASSWORD không đổi mật khẩu tài khoản đã có. Không có đăng ký công khai, reset password hoặc quản trị user trong scope v1. Không bật profile demo khi triển khai dữ liệu thật.

Database dùng `DATABASE_URL=jdbc:postgresql://.../vietdoc`, `DATABASE_USER`, `DATABASE_PASSWORD`. Flyway tự chạy khi khởi động; Hibernate chỉ validate schema. Cấu hình local đầy đủ trong [hướng dẫn Full Stack](../docs/fullstack-implementation.md).

Health: `/health/live`, `/health/ready`. OpenAPI authenticated: `/api/v1/openapi` (bản tham chiếu nằm trong `specs/web-api.openapi.json`). Login trả opaque bearer token, lưu hash và hạn dùng trong database; logout thu hồi token.
