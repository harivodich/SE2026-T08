export const RECEIPT_FIELDS = [
  ["merchant_name", "Tên cửa hàng", "text"],
  ["merchant_address", "Địa chỉ", "text"],
  ["transaction_date", "Ngày giao dịch", "date"],
  ["transaction_time", "Giờ giao dịch", "time"],
  ["total_amount", "Tổng tiền", "decimal"],
];

export const INVOICE_FIELDS = [
  ["invoice_number", "Số hóa đơn", "text"],
  ["issue_date", "Ngày phát hành", "date"],
  ["seller_name", "Tên người bán", "text"],
  ["buyer_name", "Tên người mua", "text"],
  ["subtotal", "Cộng tiền hàng", "decimal"],
  ["tax_amount", "Tiền thuế", "decimal"],
  ["discount_amount", "Tiền giảm giá", "decimal"],
  ["total_amount", "Tổng thanh toán", "decimal"],
];

export const ITEM_FIELDS = [
  ["description", "Tên hàng hóa / dịch vụ", "text"],
  ["quantity", "Số lượng", "decimal"],
  ["unit", "Đơn vị", "text"],
  ["unit_price", "Đơn giá", "decimal"],
  ["line_total", "Thành tiền", "decimal"],
];

export function emptyPayload(type) {
  const fields = type === "receipt"
    ? RECEIPT_FIELDS
    : INVOICE_FIELDS;
  return Object.fromEntries([
    ...fields.map(([key]) => [key, null]),
    ["items", []],
  ]);
}

export function emptyItem() {
  return Object.fromEntries(ITEM_FIELDS.map(([key]) => [key, null]));
}

export function toBusinessPayload(type, value) {
  const fields = type === "receipt" ? RECEIPT_FIELDS : INVOICE_FIELDS;
  const result = Object.fromEntries(fields.map(([key]) => [key, stringOrNull(value?.[key])]));
  result.items = Array.isArray(value?.items)
    ? value.items.map((item) => Object.fromEntries(
        ITEM_FIELDS.map(([key]) => [key, stringOrNull(item?.[key])]),
      ))
    : [];
  return result;
}

export function isActiveJob(job) {
  return ["QUEUED", "RUNNING", "RETRYING"].includes(job?.state);
}

export function documentStatus(document) {
  if (isActiveJob(document?.job)) return "PROCESSING";
  if (document?.job?.state === "FAILED") return "FAILED";
  if (document?.head?.state === "APPROVED") return "APPROVED";
  if (document?.head && document?.job?.state === "SUCCEEDED") return "SUCCEEDED";
  if (document?.head) return "DRAFT";
  return "UPLOADED";
}

export function statusLabel(status) {
  return ({
    PROCESSING: "Đang xử lý",
    SUCCEEDED: "Đã xử lý",
    FAILED: "Lỗi xử lý",
    CANCELLED: "Đã hủy",
    APPROVED: "Đã duyệt",
    DRAFT: "Chờ duyệt",
    UPLOADED: "Chưa xử lý",
  })[status] ?? status;
}

function stringOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}
