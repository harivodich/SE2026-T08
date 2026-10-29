# Tests ownership

Các test hiện chạy được gồm Java/H2/MockMvc trong `backend/src/test/java`, Node UI/API trong `backend/src/test/js`, và Python schema/Data/CI gate trong `tests/`. Chúng không chứng minh PostgreSQL race, actual Python provider hoặc OCR/model quality.

- Java unit/integration/Flyway/DB/CAS tests ở `backend/src/test/java`, Backend sở hữu. Shared business vectors ở `fixtures/contracts/business-validation.json`; chạy `./mvnw -Dtest=BusinessContractTest test` từ `backend/` (Windows: `mvnw.cmd`).
- `backend/src/test/js` kiểm các asset JavaScript ở `backend/src/main/resources/static`; dùng `node --test` từ `backend/src/test/js/`.
- Python unit/pipeline/data/extraction/compute tests ở đây, provider sở hữu.
- `contract/`: shared valid/invalid fixtures và cross-language parse; Backend + AI producers.
- `e2e/`: actual-provider upload→job→review→approve→export, browser two-tab/CSRF/escape khi provider sẵn sàng.
- `architecture/`: Python không import business DB; Java rules kiểm tại backend tests.
- `fixtures/`: chỉ tiny fictional audited data, không raw dataset hay weights.

`tests/unit/documents,jobs,review` và `integration/persistence,queue,storage` là legacy Python locations, không đặt Java tests tại đó. `integration/api` dành cho private Python compute, không phải public FastAPI business API. Đọc [architecture failure matrix](../docs/architecture.md) và [compute semantic checks](../specs/contracts/compute-api.md) khi mở rộng integration tests.
