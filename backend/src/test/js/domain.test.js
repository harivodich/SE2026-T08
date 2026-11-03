import test from "node:test";
import assert from "node:assert/strict";
import {
  documentStatus,
  emptyItem,
  emptyPayload,
  isActiveJob,
  toBusinessPayload,
} from "../../main/resources/static/domain.js";

test("receipt payload keeps exact business schema keys and unknown values null", () => {
  assert.deepEqual(emptyPayload("receipt"), {
    merchant_name: null,
    merchant_address: null,
    transaction_date: null,
    transaction_time: null,
    total_amount: null,
    items: [],
  });
});

test("money and quantity stay decimal strings; empty input maps to null", () => {
  const item = emptyItem();
  item.quantity = "2";
  item.unit_price = "85000";
  item.line_total = "170000";
  const normalized = toBusinessPayload("receipt", {
    ...emptyPayload("receipt"),
    total_amount: "170000",
    items: [item],
  });
  assert.equal(normalized.total_amount, "170000");
  assert.equal(normalized.items[0].quantity, "2");
  assert.equal(normalized.items[0].unit_price, "85000");
  assert.equal(normalized.items[0].description, null);
  assert.equal(typeof normalized.items[0].quantity, "string");
});

test("invoice empty payload follows invoice.v1 keys without substituting zeros", () => {
  const payload = emptyPayload("invoice");
  assert.deepEqual(Object.keys(payload), [
    "invoice_number", "issue_date", "seller_name", "buyer_name", "subtotal",
    "tax_amount", "discount_amount", "total_amount", "items",
  ]);
  assert.equal(payload.subtotal, null);
  assert.equal(payload.total_amount, null);
});

test("document statuses distinguish active, draft, approved and failed jobs", () => {
  assert.equal(isActiveJob({ state: "RETRYING" }), true);
  assert.equal(documentStatus({ job: { state: "RUNNING" } }), "PROCESSING");
  assert.equal(documentStatus({ job: { state: "FAILED" } }), "FAILED");
  assert.equal(documentStatus({ job: { state: "SUCCEEDED" }, head: { state: "DRAFT" } }), "SUCCEEDED");
  assert.equal(documentStatus({ head: { state: "APPROVED" } }), "APPROVED");
  assert.equal(documentStatus({ head: { state: "DRAFT" } }), "DRAFT");
});
