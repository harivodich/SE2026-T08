# SPEC — src/vietdoc

## Purpose và owner

Compute và offline Data/ML Python Owner: AI-1/AI-2/Data.

## Đặt gì ở đây?

contracts/pipeline/data/ml/evaluation/entrypoints/api/cli + attempt storage; 25 init docstrings hiện tại.

## Ranh giới

Legacy business/queue/worker/dispatcher chỉ reference; Python no business DB/approve/export.

## Workflow và kiểm tra

Đọc [doc vai trò](../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. Actual OCR/extraction HTTP phải có evidence; fixtures chỉ wiring. Ghi actual commands/results và limitations, [Git Flow](../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../specs/scope.md), [structure](../../docs/source-structure.md), [architecture](../../docs/architecture.md).
- [data](data/SPEC.md)
- [contracts](contracts/SPEC.md)
- [exports](exports/SPEC.md)
- [evaluation](evaluation/SPEC.md)
- [documents](documents/SPEC.md)
- [identity](identity/SPEC.md)
- [entrypoints](entrypoints/SPEC.md)
- [infrastructure](infrastructure/SPEC.md)
- [ml](ml/SPEC.md)
- [review](review/SPEC.md)
- [jobs](jobs/SPEC.md)
- [pipeline](pipeline/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
