# SPEC — src/vietdoc/entrypoints

## Purpose và owner

Composition và process entrypoints Python Owner: AI-2 serving/training; Data offline CLI.

## Đặt gì ở đây?

api private compute/health và cli data/training/eval; worker/dispatcher legacy.

## Ranh giới

No public review/approval API/DB writer. Model lifecycle chỉ ai-service.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. M2.3 health/ready/busy/private auth/deadline, CLI actual config/version output. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../specs/scope.md), [structure](../../../docs/source-structure.md), [architecture](../../../docs/architecture.md).
- [cli](cli/SPEC.md)
- [api](api/SPEC.md)
- [dispatcher](dispatcher/SPEC.md)
- [worker](worker/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
