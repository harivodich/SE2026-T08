# VT-028 — Bulk document import

Baseline: `9cfe29509bab8fa375c5e352ff90f5cf7c1ef7c9` (`develop`).

`POST /api/v1/documents/batch-import` uses the existing session and CSRF checks.
Send repeated `files` parts (1–10) and one `document_type` (`receipt` or `invoice`).
Existing multipart limits still apply (20 MB/file and 21 MB/request in Spring configuration).
A parsed batch returns HTTP 200 and an ordered `items` array: `IMPORTED` with a
`document_id`, or `REJECTED` with a typed `error_code`. Row numbers are one-based.
Expected file errors are isolated; an unexpected exception aborts the response but
does not roll back earlier committed rows. The endpoint creates no OCR jobs.
`Idempotency-Key` is rejected for this route. Resubmitting a batch can create duplicates.
The existing single-upload endpoint and its idempotency behavior are unchanged.

## Verify (Java 17; run from `backend/`)

```powershell
mvn test
mvn '-Dtest=WorkflowIntegrationTest#batchMixedFilesCommitBothValidRowsAndPreserveLegacyState' test
mvn '-Dtest=WorkflowIntegrationTest#batchLoad150ConcurrentTasks' '-Dvt028.load=true' test
```

The load test starts 150 MockMvc tasks through one owner's session, with H2,
filesystem storage and fictional receipt PNGs. Each task uploads two valid files
around an empty file. It prints `VT028_LOAD` with nearest-rank p95 and error counts.
It omits real sockets, servlet multipart parsing, PostgreSQL, OCR and browser UI.
The normal test suite skips this opt-in experiment. No data or credentials are required.

RED is reproducible on `4e80324`; that commit adds tests only. The feature branch
must stay unmerged pending team review. AI helped draft the plan, tests and patch;
the transaction and idempotency assumptions were corrected against `DocumentService.upload`.
