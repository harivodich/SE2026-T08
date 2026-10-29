import test from "node:test";
import assert from "node:assert/strict";
import { ApiClient } from "../../main/resources/static/api.js";

test("browser API uses same-origin session and CSRF without exposing bearer auth", async () => {
  const previousDocument = globalThis.document;
  const previousFetch = globalThis.fetch;
  const calls = [];
  globalThis.document = { querySelector: () => ({ content: "csrf-value" }) };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ user: { id: "u" } }) };
  };
  try {
    const client = new ApiClient();
    await client.login("operator", "secret");
    await client.me();
    assert.equal(calls[0].url, "/api/v1/auth/session");
    assert.equal(calls[0].options.credentials, "same-origin");
    assert.equal(calls[0].options.headers.get("X-CSRF-TOKEN"), "csrf-value");
    assert.equal(calls[0].options.headers.has("Authorization"), false);
    assert.equal(calls[1].options.headers.has("X-CSRF-TOKEN"), false);
  } finally {
    globalThis.document = previousDocument;
    globalThis.fetch = previousFetch;
  }
});
