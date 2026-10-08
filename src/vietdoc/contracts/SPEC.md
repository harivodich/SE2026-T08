# SPEC — src/vietdoc/contracts

## Purpose và owner

Python typed adapters cho shared contract Owner: AI-1 OCR/page; AI-2 compute.

## Đặt gì ở đây?

OCR/page/extraction/request/response/error types theo neutral schemas; Java DTO ở backend.

## Ranh giới

Không FastAPI/ORM/Paddle/Transformers imports; không Pydantic tự đổi authoritative schema.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. O1.1/M2.3 validate shared positive/negative fixtures, unknown/type/version/geometry errors. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../specs/scope.md), [structure](../../../docs/source-structure.md), [architecture](../../../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
