// Synthetic 100-client check of the browser API request path. No server or DB is involved.
import { performance } from "node:perf_hooks";
import { setTimeout as delay } from "node:timers/promises";
import { ApiClient } from "../../main/resources/static/api.js";
import { emptyPayload } from "../../main/resources/static/domain.js";

globalThis.document = { querySelector: () => ({ content: "synthetic-csrf" }) };
let accepted = 0;
globalThis.fetch = async (url, request) => {
  const id = Number(url.split("/").at(-2));
  const body = JSON.parse(request.body);
  if (request.method !== "PATCH" || request.credentials !== "same-origin" ||
      request.headers.get("X-CSRF-TOKEN") !== "synthetic-csrf" ||
      body.base_revision_id !== `r-${id}-1` || body.expected_document_version !== 1)
    return new Response(JSON.stringify({ error: { code: "BAD_REQUEST" } }), { status: 400 });
  await delay(20 + (id % 5) * 10);
  accepted++;
  return new Response(JSON.stringify({ id, version: 2 }), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
};

const latencies = await Promise.all(Array.from({ length: 100 }, async (_, id) => {
  const start = performance.now();
  const payload = { ...emptyPayload("receipt"), total_amount: String(id + 1) };
  await new ApiClient().save(String(id), {
    base_revision_id: `r-${id}-1`, expected_document_version: 1,
    payload, reason: "synthetic load", row_ids: [], reviewed_paths: ["/total_amount"],
  });
  return performance.now() - start;
}));
latencies.sort((a, b) => a - b);
const p95 = latencies[Math.ceil(latencies.length * 0.95) - 1];
console.log(JSON.stringify({ concurrent_tasks: 100, accepted, p95_ms: Number(p95.toFixed(2)),
  target_ms: 3000, meets_synthetic_target: p95 <= 3000,
  scope: "fake fetch with fixed 20-60 ms delay; no Spring, PostgreSQL, network, or browser rendering" }, null, 2));
