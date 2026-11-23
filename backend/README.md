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

`AI_MODE=http` dùng [compute protocol](../specs/contracts/compute-api.md) và chỉ khởi động khi `AI_WORKER_URL` trỏ đúng `/internal/v1/compute`, `AI_WORKER_TOKEN` không rỗng và `AI_ATTEMPTS_ROOT` là directory đã mount. `PIPELINE_MANIFEST` phải là release ID đã pin ở Python. Java runner phải đọc **cùng** attempt volume mà Python ghi (Java read-only đối với volume này); `STORAGE_ROOT` là vùng riêng Java ghi promoted assets, originals và exports. `infra/compose.ai.yaml` hiện mount named volume chỉ vào Python; cấu hình host/container Java cần mount volume tương ứng trước khi bật HTTP. Không đặt token trong Git hoặc `.env` được commit.

Client giới hạn request/response, kiểm contract và copy hash/size/canonical PNG trước DB completion. OCR artifact tối đa 8 MiB; Java đối chiếu page/dimensions và `ocr_block_ids` của field metadata trên bản copy đã verify. H2 + fake HTTP test chỉ là software integration; cần PostgreSQL thật và actual provider/release để nghiệm thu receipt/invoice. `manual` và `demo` vẫn dùng behavior cũ; `demo` chỉ dùng fixture giả lập. Có thể chạy API với `WORKER_ENABLED=false`, rồi một process dùng cùng database/storage với `--spring.main.web-application-type=none --vietdoc.worker-enabled=true`.

Viewer có thể xem revision lịch sử ở chế độ chỉ đọc, lấy ảnh canonical theo run của revision đó và vẽ `source_regions` normalized trên ảnh. Không có geometry thì không vẽ vùng nguồn.

Dedicated PostgreSQL regression dùng `PostgresJobIT` trong DB test riêng. Local chạy `cd backend; .\mvnw.cmd -B '-Dtest=PostgresJobIT' test` khi đã cấp `VIETDOC_PG_TEST_URL`, `VIETDOC_PG_TEST_USER`, `VIETDOC_PG_TEST_PASSWORD`; CI chạy suite này bằng PostgreSQL 16.6 và chặn develop nếu job fail/skip/thiếu. H2 suite không thay thế kết quả này.

Actual-provider harness là `ActualProviderIT`, chỉ chạy trên host có runtime packet AI2 và DB test riêng: `cd backend; .\mvnw.cmd -B '-Dtest=ActualProviderIT' test`. Cần `VIETDOC_ACTUAL_DB_URL/USER/PASSWORD`, `VIETDOC_ACTUAL_URL/TOKEN/MANIFEST`, `VIETDOC_ACTUAL_ATTEMPTS_ROOT`, `VIETDOC_ACTUAL_JAVA_STORAGE`, `VIETDOC_ACTUAL_RELEASE_MANIFEST_PATH`, SHA-256 bytes của file đó trong `VIETDOC_ACTUAL_RELEASE_DIGEST`, và `VIETDOC_ACTUAL_SOURCE_SHA` khớp commit checkout. URL phải kết thúc bằng `/internal/v1/compute`; token lấy từ secret runtime. Harness kiểm readiness rồi đi qua receipt PNG và invoice PDF, promote, review, approve, export; output chỉ ghi IDs/digest/hash, không ghi OCR text/token. Chưa có runtime packet/weights thì trạng thái suite là **NOT_RUN**, không dùng fake HTTP thay thế.

## Chạy ngoài demo

`SEED_USERNAME`, `SEED_PASSWORD` (tối thiểu 10 ký tự) tạo tài khoản khi username chưa tồn tại. Thay SEED_PASSWORD không đổi mật khẩu tài khoản đã có. Không có đăng ký công khai, reset password hoặc quản trị user trong scope v1. Không bật profile demo khi triển khai dữ liệu thật.

Database dùng `DATABASE_URL=jdbc:postgresql://.../vietdoc`, `DATABASE_USER`, `DATABASE_PASSWORD`. Flyway tự chạy khi khởi động; Hibernate chỉ validate schema. Docker build từ repository root bằng `docker build -f backend/Dockerfile .` để đóng gói cả web assets.

Health: `/health/live`, `/health/ready`. OpenAPI authenticated: `/api/v1/openapi` (source ở `backend/src/main/resources/openapi.json`). Login `/api/v1/auth/session` tạo HTTP session, token nội bộ lưu hash và hạn dùng trong database; logout thu hồi token. Session cookie là HttpOnly, SameSite=Lax; bật `server.servlet.session.cookie.secure=true` khi phục vụ qua HTTPS.

Xem [SPEC](SPEC.md), [Backend guide](../docs/team/backend.md) và [source structure](../docs/source-structure.md) để phân biệt foundation đang chạy với các mốc tích hợp còn lại.
