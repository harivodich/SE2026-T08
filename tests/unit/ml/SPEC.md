# SPEC — tests/unit/ml

## Purpose và owner

Unit checks cho `src/vietdoc/ml` Owner: AI-2.

## Đặt gì ở đây?

Release manifest verification, model loading/config/collator khi có implementation.

## Ranh giới

Chỉ tiny fictional bytes tạo trong `tmp_path`; không weights/checkpoints thật, không tải model.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md). Known expected outputs, invalid/boundary cases, no weakened tests for pass. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Folder cha](../SPEC.md). [ml SPEC](../../../src/vietdoc/ml/SPEC.md).
