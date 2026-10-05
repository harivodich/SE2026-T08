# Tests

- unit/: domain và pipeline logic.
- integration/: API/DB/queue/storage boundaries.
- contract/: schema và input/output giữa các module.
- architecture/: kiểm module dependencies khi source có logic.
- e2e/: upload → processing → review → approve → export.
- fixtures/: chỉ tiny fictional samples; không đặt dữ liệu cá nhân, dataset đầy đủ hoặc weights.

Chưa có app tests. Mỗi việc triển khai bổ sung tests cho hành vi thực sự thay đổi.
