# Java public API và Thymeleaf routes: thiết kế đích v1

Chưa endpoint/OpenAPI implementation. Owner Backend; Lead domain/approval reviewer. HTML/REST gọi cùng services. Scope/policy/schema authority ở [scope](../scope.md), [approval](../approval-policy.md), [contracts](README.md).

## Session và stable errors

Thymeleaf login session, CSRF token cho form và JavaScript mutations. Cookie HttpOnly/SameSite, Secure khi HTTPS; API expired session401 JSON, không redirect HTML vào fetch; HTML page redirect login có safe return path. Foreign owner private IDs trả404 để không enumerate resources; admin quyền rõ không bypass approval.

Error envelope đề xuất: code,message,request_id,details (field/issue paths đã sanitize); không stack trace/raw OCR/secret. Structural request422, stale head/version409; missing total/blocking/current-state violation409 CANNOT_APPROVE, thiếu confirmation/ack format422. Contract status cần actual integration tests, không đổi HTTP codes theo frontend convenience.

## Routes và behavior

| Route | Input chính | Success và guard |
|---|---|---|
| POST /api/v1/documents | multipart file + selected type | 201 document_id,type,version,head=null; auth/profile |
| GET /api/v1/documents | bounded pagination | 200 owned docs/status/head |
| GET /api/v1/documents/{id} | owner | 200 document metadata/head/version; no private filesystem path |
| POST /api/v1/documents/{id}/jobs | optional Idempotency-Key | 202 job_id/state/pinned release; same key+hash reuse, mismatch409; no key+active job409 |
| GET /api/v1/jobs/{id} | owner | 200 state/stage/attempt/error; no live stage claim without signal |
| POST /api/v1/jobs/{id}/cancel | CSRF/owner | 200 CANCELLED; repeated cancel idempotent, succeeded/failed409; revoke current fence |
| GET /api/v1/documents/{id}/runs | owner | 200 immutable runs/candidates |
| GET /api/v1/documents/{id}/runs/{run}/page | same document/owner | 200 canonical image, checksum; run-specific |
| GET /api/v1/documents/{id}/revisions | owner | 200 history/approval markers |
| GET /api/v1/documents/{id}/revisions/{revision} | same document/owner | 200 payload/metadata/run/approval/version |
| PATCH /api/v1/documents/{id}/review | full payload,base_revision_id,expected_version,reason | 201 appended draft + head/version/issues; CAS, stale409 |
| POST /api/v1/documents/{id}/adopt | run_id,base_revision_id,expected_version,reason | 201 new draft; candidate same document, CAS |
| POST /api/v1/documents/{id}/approve | revision_id,expected_version,review_confirmed,acknowledged_issue_ids,reason | 201 approval; current head/revalidate/blockers/completeness |
| POST /api/v1/documents/{id}/exports | explicit revision_id,format=json | 201 new artifact or200 existing; approved, deterministic exporter version |
| GET /api/v1/documents/{id}/exports/{export}/download | same owner | 200 exact persisted bytes/checksum |
| GET /api/v1/admin/model-releases | admin | approved/verified manifests available locally |
| POST /api/v1/admin/model-releases/{release}/activate | admin + CSRF | 200 new-job profile points to verified immutable manifest; old jobs unchanged |

Job failure không HTTP success giả cho compute; create202 là accepted durable record, không prediction succeeded. Renderer/AI URL không đi ra browser. Metadata issues/human row IDs ngoài export business payload.

## Thymeleaf UI đích

Pages /login, /documents (list/upload), /documents/{id} (viewer/editor/status), history fragments ở detail. Không tạo SPA/router/frontend toolchain riêng.

Scalar editor nhận string/null; item add/delete giữ stable row_id_map; default row không fill missing thành0. JavaScript giữ dirty buffer/base version,409 giữ edits và cho compare/reload/reconcile có chủ ý. Polling stop khi terminal/unload, backoff khi hidden/error; OCR/model text escaped.

All source overlay trên canonical page đúng revision.run_id. Save/adopt approved head tạo new draft, không làm mất old export. Approve controls không là validator authority.

## Verification cần tạo

B2 admission/ownership/session/CSRF, B3 correlation/fencing/response loss, B4 CAS/approve/export, B5 browser editor/escaping/two-tab/canonical, B6 actual boundary failures, B7 clean-env. Public OpenAPI do Java implementation tạo và compare reviewed contract, chưa có ở lượt thiết kế.
