# Tests

- unit/: domain và pipeline logic.
- integration/: API/DB/queue/storage boundaries.
- contract/: schema và input/output giữa các module. Shared business vectors nằm tại `fixtures/contracts/business-validation.json`; backend contract test chạy từ `backend/` bằng `./mvnw -Dtest=BusinessContractTest test` (Windows: `mvnw.cmd`).
- architecture/: kiểm module dependencies khi source có logic.
- e2e/: upload → processing → review → approve → export.
- fixtures/: chỉ tiny fictional samples; không đặt dữ liệu cá nhân, dataset đầy đủ hoặc weights.

Mỗi việc triển khai bổ sung tests cho hành vi thực sự thay đổi; backend integration tests hiện nằm trong `backend/src/test/`.
