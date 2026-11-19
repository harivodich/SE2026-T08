# VT-031 autosave checks

From the repository root, run:

```powershell
node --test backend/src/test/js/*.test.js
```

The `VT-031` cases in `app.test.js` use a deterministic clock and a fake API to check debounce, compare-and-swap request fields, a newer edit arriving during an older save, HTTP 409, manual save deduplication, and document navigation. The fake API verifies browser behavior; it is not a real PostgreSQL or browser end-to-end test.

The existing `WorkflowIntegrationTest` covers server-side revision conflicts with the demo test database:

```powershell
cd backend
./mvnw.cmd -q -Dtest=WorkflowIntegrationTest test
```

Autosave uses the existing `PATCH /api/v1/documents/{id}/review` contract. A conflict leaves the local draft visible and blocks further saves until the document is reloaded. Do not treat a synthetic load result as evidence of production latency.

For the 100-task synthetic request-path experiment, run `node backend/src/test/js/vt031-load.mjs` from the repository root. It uses fake `fetch` responses with fixed 20–60 ms latency and reports p95; it cannot establish the latency of Spring, PostgreSQL, or a real browser.
