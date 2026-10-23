# Backend Java — implementation

Owner: Full Stack. Spring Boot REST/business persistence nằm trong thư mục này; Python OCR/extraction vẫn thuộc hai vai trò AI.

Schema nguồn: `../specs/contracts/`. API Web: `../specs/web-api.openapi.json`. Code đồng bộ schema qua `scripts/sync-contracts.py`; types Web sinh từ OpenAPI. Xem `../docs/fullstack-implementation.md` cho kiến trúc hiện hành và phần cần tích hợp AI.

Commands: `./mvnw test`, `./mvnw package`, `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo`. Windows dùng `mvnw.cmd`. Không commit runtime, .env hoặc target.

Review/approve/export và fencing phải được kiểm tra khi sửa. Không viết thuật toán OCR/model trong API.
