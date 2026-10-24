# SPEC — infra

## Purpose và owner

Runtime/build deployment configuration Owner: Backend; AI-2 runtime reviewer.

## Đặt gì ở đây?

app,job-runner,ai-service,postgres Compose/Dockerfile when runnable increments exist.

## Ranh giới

No Redis/Celery/React container; AI/DB private, readonly model, attempt-only Python write volume, Java-only promoted committed assets.

## Workflow và kiểm tra

Đọc [doc vai trò](../docs/team/backend.md), nhận một task có input/version/output/acceptance. B1.3/B7.1 actual startup/health/clean-env/restore; deploy requires explicit request. Ghi actual commands/results và limitations, [Git Flow](../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../specs/scope.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
