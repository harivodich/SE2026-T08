import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import * as domain from "../src/domain.js";

const source = readFileSync(new URL("../src/app.js", import.meta.url), "utf8")
  .replace(/import \{[\s\S]*?\} from "\.\/(?:api|domain)\.js";/g, "")
  + "\nglobalThis.hooks = { state, openDocument, refreshDocuments, pollJob, rerun, saveReview, approve, adoptCandidate, uploadAndProcess, login, logout, apiFailure, updateBoundValue, render };";

class ApiError extends Error {
  constructor(status) { super("API error"); this.status = status; }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((r, j) => { resolve = r; reject = j; });
  return { promise, resolve, reject };
}

async function harness(routes = {}) {
  const controls = {
    '[data-action="save"]': { disabled: true },
    '[data-action="rerun"]': { disabled: false },
    '[data-action="approve"]': { disabled: true },
  };
  const root = {
    innerHTML: "",
    addEventListener() {},
    querySelector(selector) { return controls[selector] ?? null; },
    querySelectorAll() { return []; },
    contains() { return false; },
  };
  const meta = { content: "csrf" };
  const mode = { content: routes.mode ?? "demo" };
  const document = {
    activeElement: null,
    querySelector(selector) { return selector === "#app" ? root : selector === 'meta[name="vietdoc-mode"]' ? mode : meta; },
    addEventListener() {},
  };
  class ApiClient {
    me() { return Promise.reject(new ApiError(401)); }
    login(username, password) { return routes.login(username, password); }
    document(id) { return routes.document(id); }
    revisions(id) { return routes.revisions?.(id) ?? Promise.resolve({ items: [] }); }
    runs(id) { return routes.runs?.(id) ?? Promise.resolve({ items: [] }); }
    page(id) { return routes.page?.(id) ?? Promise.resolve({ url: id }); }
    listDocuments() { return routes.listDocuments(); }
    save(id, body) { return routes.save(id, body); }
    request(path) { return routes.request?.(path) ?? Promise.resolve({ state: "QUEUED" }); }
    createJob(id) { return routes.createJob?.(id) ?? Promise.resolve({ id: "job", state: "QUEUED" }); }
    approve(id, body) { return routes.approve?.(id, body) ?? Promise.resolve(doc(id, 2)); }
    adoptRun(id, body) { return routes.adoptRun?.(id, body) ?? Promise.resolve(doc(id, 2)); }
    upload(file, type) { return routes.upload?.(file, type) ?? Promise.resolve(doc("new", 1)); }
    logout() { return routes.logout?.() ?? Promise.resolve({ ok: true }); }
    csrf() { return routes.csrf?.() ?? Promise.resolve({ token: "new-csrf" }); }
  }
  const context = {
    ...domain, ApiClient, ApiError, document, root, window: { confirm: () => true },
    URL: { createObjectURL: blob => blob.url, revokeObjectURL() {} },
    crypto: { randomUUID: () => "00000000-0000-4000-8000-000000000001" },
    structuredClone, AbortController, setInterval: () => 1, clearInterval() {}, setTimeout,
    Intl, Date, console,
  };
  runInNewContext(source, context, { filename: "app.js" });
  await new Promise(setImmediate);
  context.hooks.state.user = { id: "u", username: "operator" };
  return { ...context.hooks, root, document, controls };
}

function doc(id, version, total = "100", items = []) {
  return {
    id, filename: `${id}.png`, document_type: "receipt", created_at: "2026-10-24T00:00:00Z",
    version, head_revision_id: `${id}-r${version}`, job: null,
    head: {
      id: `${id}-r${version}`, run_id: `${id}-run`, state: "DRAFT", issues: [],
      row_ids: items.map((_, i) => `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`),
      payload: { ...domain.emptyPayload("receipt"), total_amount: total, items },
    },
  };
}

test("polling preserves editor base and prevents silent save over a newer head", async () => {
  const old = doc("A", 1), newer = doc("A", 2, "300");
  let saves = 0;
  const app = await harness({
    document: async () => old,
    listDocuments: async () => ({ items: [newer] }),
    save: async () => { saves++; return newer; },
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  await app.refreshDocuments();
  assert.equal(app.state.editorBase.version, 1);
  assert.equal(app.state.payload.total_amount, "200");
  assert.equal(app.state.remoteDocument.version, 2);
  await app.saveReview();
  assert.equal(saves, 0);
  assert.match(app.root.innerHTML, /data-remote-notice >Chứng từ đã thay đổi/);
});

test("late detail and image responses cannot replace the selected document", async () => {
  const a = deferred(), b = deferred();
  const app = await harness({
    document: id => (id === "A" ? a.promise : b.promise),
    listDocuments: async () => ({ items: [] }),
  });
  const first = app.openDocument("A");
  const second = app.openDocument("B");
  b.resolve(doc("B", 1));
  await second;
  a.resolve(doc("A", 1));
  await first;
  assert.equal(app.state.selectedId, "B");
  assert.equal(app.state.document.id, "B");
  assert.equal(app.state.imageUrl, "B");
});

test("saving a remaining row remaps reviewed path after deleting an earlier row", async () => {
  const item = { ...domain.emptyItem(), description: "B" };
  const original = doc("A", 1, "100", [{ ...item, description: "A" }, item]);
  let sent;
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
    save: async (_, body) => { sent = body; return doc("A", 2, "100", body.payload.items); },
  });
  await app.openDocument("A");
  const remainingId = app.state.rowIds[1];
  app.state.changedItemFields.set(remainingId, new Set(["description"]));
  app.state.payload.items.splice(0, 1);
  app.state.rowIds.splice(0, 1);
  app.state.changedPaths.add("/items");
  await app.saveReview();
  assert.deepEqual(Array.from(sent.reviewed_paths), ["/items", "/items/0/description"]);
  assert.equal(sent.payload.items[0].description, "B");
});

test("unchanged field review creates a metadata-only revision", async () => {
  const original = doc("A", 1);
  let sent;
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
    save: async (_, body) => { sent = body; return doc("A", 2); },
  });
  await app.openDocument("A");
  app.state.changedPaths.add("/total_amount");
  await app.saveReview();
  assert.equal(sent.payload.total_amount, "100");
  assert.deepEqual(Array.from(sent.reviewed_paths), ["/total_amount"]);
});

test("editor inputs are locked while save is pending", async () => {
  const original = doc("A", 1);
  original.head.issues = [{ id: "warn-1", severity: "warning", code: "REVIEW", message: "Check" }];
  const pending = deferred();
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
    save: async () => pending.promise,
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  const saving = app.saveReview();
  assert.match(app.root.innerHTML, /data-scalar="total_amount"[^>]*disabled/);
  assert.match(app.root.innerHTML, /data-reason[^>]*disabled/);
  assert.match(app.root.innerHTML, /data-reviewed[^>]*disabled/);
  assert.match(app.root.innerHTML, /data-ack="warn-1"[^>]*disabled/);
  pending.resolve(doc("A", 2, "200"));
  await saving;
  assert.equal(app.state.payload.total_amount, "200");
});

test("failed job polling cannot unlock or overwrite a pending save", async () => {
  const original = doc("A", 1);
  original.job = { id: "job", state: "QUEUED" };
  const pending = deferred();
  let saves = 0;
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
    request: async () => { throw new ApiError(503); },
    save: async () => { saves++; return pending.promise; },
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  const saving = app.saveReview();
  await app.pollJob();
  assert.equal(app.state.busy, true);
  assert.equal(app.state.busyAction, "save");
  assert.match(app.root.innerHTML, /data-scalar="total_amount"[^>]*disabled/);
  await app.saveReview();
  assert.equal(saves, 1);
  pending.resolve(doc("A", 2, "200"));
  await saving;
  assert.equal(app.state.busy, false);
  assert.equal(app.state.payload.total_amount, "200");
});

test("failed list polling preserves pending mutation locks; owner finally releases them", async () => {
  const original = doc("A", 1);
  const pending = deferred();
  let listFails = false;
  const app = await harness({
    document: async () => original,
    listDocuments: async () => {
      if (listFails) throw new ApiError(503);
      return { items: [original] };
    },
    save: async () => pending.promise,
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  const saving = app.saveReview();
  listFails = true;
  await app.refreshDocuments().catch(error => app.apiFailure(error));
  assert.equal(app.state.busy, true);
  assert.match(app.root.innerHTML, /data-scalar="total_amount"[^>]*disabled/);
  pending.reject(new ApiError(503));
  await saving;
  assert.equal(app.state.busy, false);
  assert.equal(app.state.payload.total_amount, "200");
});

test("401 during a pending save clears session and ignores its late response", async () => {
  const original = doc("A", 1);
  const pending = deferred();
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
    save: async () => pending.promise,
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  const saving = app.saveReview();
  app.apiFailure(new ApiError(401));
  pending.resolve(doc("A", 2, "200"));
  await saving;
  assert.equal(app.state.user, null);
  assert.equal(app.state.document, null);
  assert.equal(app.state.busy, false);
  assert.match(app.root.innerHTML, /Phiên đăng nhập đã hết hạn/);
});

test("rerun rejects unsaved payload and review marks, then works after save", async () => {
  const original = doc("A", 1);
  let latest = original;
  let jobs = 0;
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [latest] }),
    save: async () => { latest = doc("A", 2, "200"); return latest; },
    createJob: async () => { jobs++; return { id: "job", state: "QUEUED" }; },
  });
  await app.openDocument("A");
  app.state.payload.total_amount = "200";
  await app.rerun();
  assert.equal(jobs, 0);
  assert.match(app.root.innerHTML, /data-action="rerun"[^>]*disabled/);
  app.state.payload.total_amount = "100";
  app.state.changedPaths.add("/total_amount");
  await app.rerun();
  assert.equal(jobs, 0);
  app.state.changedPaths.clear();
  app.state.changedItemFields.set("row-1", new Set(["description"]));
  await app.rerun();
  assert.equal(jobs, 0);
  app.state.changedItemFields.clear();
  app.state.payload.total_amount = "200";
  await app.saveReview();
  await app.rerun();
  assert.equal(jobs, 1);
});

test("typing updates Save and Rerun immediately without rebuilding the focused editor", async () => {
  const original = doc("A", 1);
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [original] }),
  });
  await app.openDocument("A");
  const html = app.root.innerHTML;
  app.updateBoundValue({ dataset: { scalar: "total_amount" }, value: "200" });
  assert.equal(app.controls['[data-action="save"]'].disabled, false);
  assert.equal(app.controls['[data-action="rerun"]'].disabled, true);
  assert.equal(app.root.innerHTML, html);
});

test("focused editor keeps its draft but disables Save when polling finds a remote version", async () => {
  const original = doc("A", 1), newer = doc("A", 2, "300");
  const app = await harness({
    document: async () => original,
    listDocuments: async () => ({ items: [newer] }),
  });
  await app.openDocument("A");
  app.updateBoundValue({ dataset: { scalar: "total_amount" }, value: "200" });
  assert.equal(app.controls['[data-action="save"]'].disabled, false);
  const html = app.root.innerHTML;
  app.root.contains = () => true;
  app.document.activeElement = { matches: () => true };
  await app.refreshDocuments();
  assert.equal(app.root.innerHTML, html);
  assert.equal(app.state.payload.total_amount, "200");
  assert.equal(app.state.remoteDocument.version, 2);
  assert.equal(app.controls['[data-action="save"]'].disabled, true);
  assert.equal(app.controls['[data-action="rerun"]'].disabled, true);
});

for (const action of ["approve", "adopt", "rerun", "upload"]) {
  test(`${action} keeps its lock through background failure and releases it on request error`, async () => {
    const original = doc("A", 1);
    const pending = deferred();
    let calls = 0;
    const request = () => { calls++; return pending.promise; };
    const app = await harness({
      document: async () => original,
      listDocuments: async () => ({ items: [original] }),
      approve: request, adoptRun: request, createJob: request, upload: request,
    });
    if (action !== "upload") await app.openDocument("A");
    if (action === "approve") app.state.reviewed = true;
    if (action === "upload") app.state.uploadFile = { name: "receipt.png", type: "image/png" };
    const startAction = () => ({
      approve: () => app.approve(),
      adopt: () => app.adoptCandidate("run-2"),
      rerun: () => app.rerun(),
      upload: () => app.uploadAndProcess({ preventDefault() {} }),
    })[action]();
    const inFlight = startAction();
    app.apiFailure(new ApiError(503));
    assert.equal(app.state.busy, true);
    await startAction();
    assert.equal(calls, 1);
    pending.reject(new ApiError(503));
    await inFlight;
    assert.equal(app.state.busy, false);
  });
}

test("the visible mode identifies demo fixtures and manual operation", async () => {
  const demo = await harness({ listDocuments: async () => ({ items: [] }) });
  assert.match(demo.root.innerHTML, /Demo · kết quả giả lập/);
  const manual = await harness({
    mode: "manual", document: async () => doc("A", 1),
    listDocuments: async () => ({ items: [] }),
  });
  await manual.openDocument("A");
  assert.match(manual.root.innerHTML, /Manual · không chạy AI/);
});

test("passive polling keeps the active editor DOM and filters the current run", async () => {
  const original = doc("A", 1);
  const app = await harness({
    document: async () => original,
    runs: async () => ({ items: [{ id: "A-run", created_at: original.created_at }] }),
    listDocuments: async () => ({ items: [original] }),
  });
  await app.openDocument("A");
  assert.doesNotMatch(app.root.innerHTML, /Kết quả xử lý khác/);
  const html = app.root.innerHTML;
  app.root.contains = () => true;
  app.document.activeElement = { matches: () => true };
  await app.refreshDocuments();
  assert.equal(app.root.innerHTML, html);
});

test("logout resets busy and refreshes CSRF for login without page reload", async () => {
  const app = await harness({ listDocuments: async () => ({ items: [] }) });
  await app.logout();
  assert.equal(app.state.busy, false);
  assert.equal(app.state.user, null);
  assert.equal(app.document.querySelector('meta[name="_csrf"]').content, "new-csrf");
  assert.match(app.root.innerHTML, /Đăng nhập/);
  assert.doesNotMatch(app.root.innerHTML, /Đang đăng nhập/);
});

test("login refreshes CSRF before and after session rotation", async () => {
  let refreshes = 0;
  const app = await harness({
    listDocuments: async () => ({ items: [] }),
    csrf: async () => ({ token: `csrf-${++refreshes}` }),
    login: async () => ({ user: { id: "u", username: "operator" } }),
  });
  app.state.user = null;
  app.state.username = "operator";
  app.state.password = "secret";
  await app.login({ preventDefault() {} });
  assert.equal(refreshes, 2);
  assert.equal(app.document.querySelector('meta[name="_csrf"]').content, "csrf-2");
  assert.equal(app.state.user.username, "operator");
});
