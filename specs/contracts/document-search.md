# Document search - VT-029 additive API increment

Runtime contract bổ sung cho `GET /api/v1/documents`; không thay thiết kế đích
toàn bộ public API. OpenAPI runtime: `backend/src/main/resources/openapi.json`.

- `q`: optional filename substring, trim bằng Java String.trim, lower theo
  Locale.ROOT/DB lower; giữ dấu tiếng Việt, không hứa Unicode normalization.
  `%`, `_`, `!` là literal. Tối đa 128 UTF-16 code units sau trim; vượt trả
  `400 INVALID_QUERY`. Omit/empty/blank tương đương request cũ.
- Kết hợp AND với owner hiện hành và type/status đã có. Không tìm OCR/payload.
- `limit`: default 20, clamp [1,100] giữ baseline; non-integer 400 INVALID_REQUEST.
  Invalid type giữ 422 CONTRACT_INVALID; invalid status 400 INVALID_FILTER.
- `cursor`: document ID của owner (missing/foreign trả 404 NOT_FOUND).
  Thứ tự cố định `createdAt DESC,id DESC`; trang tiếp theo strict tuple less-than.
  Client giữ nguyên q/type/status khi đi tiếp; khi đổi bộ lọc phải bỏ cursor.
- Response giữ đúng `items`, `next_cursor` (string hoặc null); Document schema
  và nullability giữ nguyên. Không thêm total/page/sort hay offset pagination.
- Keyset ổn định trên dataset cố định; không cung cấp snapshot isolation giữa
  requests. Insert mới trước cursor không làm lặp các dòng đã xem.
- Lỗi query/materialization phải propagate tới handler 500 INTERNAL_ERROR;
  không biến lỗi thành 200 empty page, không expose exception details.

Contract tests: `DocumentSearchContractTest`, frozen v1 schemas trong
`backend/src/test/resources/vt029-v1-contract.json`, schema validator
`scripts/vt029_contract.py`. Đây là API slice; chưa thêm search controls vào UI.
