# Tests ownership

Chưa application tests executable.

- Java unit/integration/module/Flyway/DB/CAS tests ở backend/src/test/java, Backend owns.
- Python unit/pipeline/data/extraction/compute tests ở đây, provider owns.
- contract/: shared valid/invalid fixtures và cross-language parse; Backend + AI producers.
- e2e/: actual-provider upload→job→review→approve→export, browser two-tab/CSRF/escape.
- architecture/: Python no business DB imports, Java rules tại backend tests.
- fixtures/: tiny fictional audited data only.

tests/unit/documents,jobs,review và integration/persistence,queue,storage là legacy Python locations, không đặt Java tests tại đó. integration/api giờ là private Python compute tests, không public FastAPI business API.

Test fixtures để wiring không là measured OCR/model quality. Read [architecture failure matrix](../docs/architecture.md) và [compute semantic checks](../specs/contracts/compute-api.md).
