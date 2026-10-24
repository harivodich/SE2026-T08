# SPEC — src/vietdoc/infrastructure/storage

## Purpose và owner

Attempt artifacts của Python compute Owner: AI-2; Backend consumer.

## Đặt gì ở đây?

Canonical/OCR/preprocess/transform/raw outputs + manifest dưới attempts/job/attempt.

## Ranh giới

Server-config root, no absolute caller paths/symlinks/traversal, no overwrite attempt/original/export.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3/B3.2 hash/size/prefix/canonical dimensions; temp→atomic attempt publish, Java promotes verified copy trước DB commit; orphan cleanup reviewed. Ghi actual commands/results và limitations, [Git Flow](../../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../../specs/scope.md), [structure](../../../../docs/source-structure.md), [architecture](../../../../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
