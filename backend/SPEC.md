# SPEC — backend

## Purpose và owner

Business Java API/UI/runner Owner: Backend.

## Đặt gì ở đây?

Java/Spring Boot/MVC/Thymeleaf features, JPA adapters, Flyway và Java tests khi task implementation được giao.

## Ranh giới

Java sole business DB writer/approval authority; HTTP AI ở runner ngoài DB transaction; stream-copy/hash/decode attempt assets sang Java-only committed storage; no ML weights.

## Workflow và kiểm tra

Đọc [doc vai trò](../docs/team/backend.md), nhận một task có input/version/output/acceptance. B1.1–B7.1: contract parity, PostgreSQL claim/CAS, CSRF/escaping, actual-provider E2E. Ghi actual commands/results và limitations, [Git Flow](../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../specs/scope.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
