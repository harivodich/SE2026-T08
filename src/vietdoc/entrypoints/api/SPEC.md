# SPEC — src/vietdoc/entrypoints/api

## Purpose và owner

Private compute HTTP process Owner: AI-2; AI-1 stage reviewer.

## Đặt gì ở đây?

FastAPI app/lifecycle/request/response/errors/compute/health.

## Ranh giới

Khác Java public API; load model lifecycle ở process này, compute ngoài async event loop, semaphore1.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3 actual OCR HTTP, auth/hash/schema/busy/timeout/OOM/cleanup; no DB credentials. Ghi actual commands/results và limitations, [Git Flow](../../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../../specs/scope.md), [structure](../../../../docs/source-structure.md), [architecture](../../../../docs/architecture.md).
- [routes](routes/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
