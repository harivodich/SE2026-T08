# Backend Java — implementation

Owner: Full Stack. Spring Boot REST/business persistence nằm trong thư mục này; Python OCR/extraction vẫn thuộc hai vai trò AI.

Schema nguồn: `../specs/contracts/`. OpenAPI Web hiện được đóng gói tại `src/main/resources/openapi.json`. Các bản schema đóng gói cần được đối chiếu với `../specs/contracts/` khi sửa contract. Giao thức compute HTTP và canonical artifacts cần được chốt với AI-1/AI-2 trước khi nhận tích hợp provider thật.

Commands: `./mvnw test`, `./mvnw package`, `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo`. Windows dùng `mvnw.cmd`. Không commit runtime, .env hoặc target.

Review/approve/export và fencing phải được kiểm tra khi sửa. Không viết thuật toán OCR/model trong API.
