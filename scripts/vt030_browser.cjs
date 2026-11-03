// Individual VT-030: real browser/TCP/session/UI smoke on a task-owned local app.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const base = process.argv[2];
const evidence = process.argv[3];
const sample = path.resolve(__dirname, "../samples/receipt-demo.png");
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || "")) throw new Error("Local test URL required");
const result = { scope: "Chrome + real TCP + packaged Spring/H2/demo; worker disabled; no native OCR/model", tests: [] };
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    await page.goto(base);
    await page.locator("#username").fill("demo");
    await page.locator("#password").fill("demo-change-me");
    await page.locator("[data-login] button[type=submit]").click();
    await page.locator("[data-upload]").waitFor();
    await page.locator("#upload-file").setInputFiles(sample);
    const accepted = page.waitForResponse(r => r.request().method() === "POST" && /\/documents\/[^/]+\/jobs$/.test(r.url()));
    await page.locator("[data-upload] button[type=submit]").click();
    const response = await accepted;
    assert.equal(response.status(), 202);
    const body = await response.json();
    const headers = await response.allHeaders();
    assert.notEqual(body.id, body.document_id);
    assert.equal(headers.location, `/api/v1/jobs/${body.id}`);
    assert.match(headers["cache-control"], /no-store/);
    await page.locator(".job-progress").waitFor();
    assert.match(await page.locator(".job-progress").innerText(), /Đang chờ runner/);
    const polled = page.waitForResponse(r => r.request().method() === "GET" && r.url().endsWith(headers.location));
    const polling = await polled; // condition-based wait; no fixed sleep to fake progress
    assert.equal((await polling.json()).id, body.id);
    assert.match((await polling.allHeaders())["cache-control"], /no-store/);
    await page.screenshot({ path: path.join(evidence, "browser-queued.png"), fullPage: true });
    result.tests.push({ id: "E2E01", status: "PASS", observed: "login/upload202/Location/persisted QUEUED shown and polled through real UI" });

    const csrf = (await (await context.request.get(base + "/api/v1/auth/csrf")).json()).token;
    const requestHeaders = await response.request().allHeaders();
    const key = requestHeaders["idempotency-key"];
    assert.ok(key);
    const retry = await context.request.post(response.url(), { headers: { "X-CSRF-TOKEN": csrf, "Idempotency-Key": key } });
    assert.equal(retry.status(), 202);
    assert.equal((await retry.json()).id, body.id);
    const detail = await context.request.get(`${base}/api/v1/documents/${body.document_id}`);
    assert.equal((await detail.json()).job.id, body.id);
    result.tests.push({ id: "E2E02", status: "PASS", observed: "same browser session/key retry reuses job; no duplicated active operation" });

    const cancelled = await context.request.post(base + headers.location + "/cancel", {
      headers: { "X-CSRF-TOKEN": csrf }, data: { expected_state: "QUEUED" }
    });
    assert.equal(cancelled.status(), 200);
    assert.equal((await cancelled.json()).state, "CANCELLED");
    await page.locator(".job-progress").waitFor({ state: "hidden" });
    await page.screenshot({ path: path.join(evidence, "browser-after-cancel.png"), fullPage: true });
    result.tests.push({ id: "E2E03", status: "PASS", observed: "real cancelled job stops active-progress UI after polling" });
  } finally { await browser.close(); }
})().catch(e => { result.error = String(e); process.exitCode = 1; }).finally(() => {
  fs.writeFileSync(path.join(evidence, "browser.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
});
