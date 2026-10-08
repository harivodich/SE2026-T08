# SPEC — tests/unit

## Purpose và owner

Python pure compute/Data unit checks Owner: Data/AI module owner.

## Đặt gì ở đây?

Pipeline/OCR/extraction/geometry/normalizer/data/evaluator unit cases.

## Ranh giới

documents/jobs/review Python subfolders legacy; Java domain tests backend.

## Workflow và kiểm tra

Đọc [doc vai trò](../../docs/team/ai-1-ocr.md), nhận một task có input/version/output/acceptance. Known expected outputs, invalid/boundary cases, no weakened tests for pass. Ghi actual commands/results và limitations, [Git Flow](../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../specs/scope.md), [structure](../../docs/source-structure.md), [architecture](../../docs/architecture.md).
- [documents](documents/SPEC.md)
- [jobs](jobs/SPEC.md)
- [pipeline](pipeline/SPEC.md)
- [review](review/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
