# SPEC — backend

## Purpose và owner

Backend sở hữu business Java API, Thymeleaf UI, job runner, persistence, review/export và Flyway. Foundation `manual`/`demo` đã có implementation chạy được; Python OCR/extraction thuộc AI-1/AI-2.

## Source và authority

Java ở `src/main/java/vn/vietdoc`; Thymeleaf ở `src/main/resources/templates`, viewer/editor JavaScript/CSS ở `src/main/resources/static`, Flyway ở `src/main/resources/db/migration`, Java tests ở `src/test/java`. Schema trung lập tại `../specs/contracts/`; `ContractValidator` hiện đọc bản classpath trong `src/main/resources/contracts/`, cần kiểm parity khi sửa. OpenAPI public hiện đóng gói tại `src/main/resources/openapi.json`.

## Ranh giới

Java là business DB writer và approval authority duy nhất. HTTP compute của Python chạy ngoài DB transaction, nhưng `AI_MODE=http` vẫn fail-fast cho đến khi Java/Python dùng chung compute contract và canonical assets theo run. Không load model weights hay viết OCR/model trong API. Completion vẫn cần fencing, idempotency và kiểm approval theo revision hiện hành.

## Workflow và kiểm tra

Chạy `./mvnw test`, `./mvnw package`, `./mvnw spring-boot:run -Dspring-boot.run.profiles=demo` (Windows dùng `mvnw.cmd`). Kiểm review/approve/export, CAS, migration và static assets khi sửa. Ghi actual commands/results và limitations; không commit runtime, `.env` hoặc `target`.

## Liên quan

[Scope](../specs/scope.md), [Backend guide](../docs/team/backend.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md), [compute protocol](../specs/contracts/compute-api.md). Các mốc PostgreSQL/actual-provider E2E chưa được chứng minh bởi tests H2/demo.
