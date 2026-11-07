# SPEC — web

## Purpose và owner

Legacy runtime/test scaffold; Backend giữ reference. Node tests hiện hành nằm ở `backend/src/test/js/`.

## Đặt gì ở đây?

Không thêm runtime code/dependencies ở đây. Đích: `backend/src/main/resources/templates`, `backend/src/main/resources/static` và `backend/src/test/js`.

## Ranh giới

Java/Thymeleaf + Python AI theo ADR-0009 thay stack v1; không chạy hai business/UI/migration implementations song song.

## Workflow và kiểm tra

Đọc [doc vai trò](../docs/team/backend.md), nhận một task có input/version/output/acceptance. Cleanup cần PR riêng sau verified Java slice; không xóa source người dùng trong lượt thiết kế. Ghi actual commands/results và limitations, [Git Flow](../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../specs/scope.md), [structure](../docs/source-structure.md), [architecture](../docs/architecture.md).
- [src](src/SPEC.md)
- [tests](tests/SPEC.md)

Legacy placeholders giữ nguyên để đối chiếu; chưa xóa.
