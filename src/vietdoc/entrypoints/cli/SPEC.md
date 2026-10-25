# SPEC — src/vietdoc/entrypoints/cli

## Purpose và owner

Offline Data/ML commands Owner: Data dataset/eval; AI-2 training/model.

## Đặt gì ở đây?

Generator/QA/splits/eval/train/reproduce CLI khi có implementation.

## Ranh giới

Không seed Java users, business DB mutation hoặc activate model tự động; no paid/model downloads ngoài quyền task.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../../docs/team/data-engineer.md), nhận một task có input/version/output/acceptance. Commands thật, config/seed/version/hashes + repeatable subset. Ghi actual commands/results và limitations, [Git Flow](../../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../../specs/scope.md), [structure](../../../../docs/source-structure.md), [architecture](../../../../docs/architecture.md).


File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
