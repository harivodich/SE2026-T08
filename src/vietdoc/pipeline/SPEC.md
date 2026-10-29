# SPEC — src/vietdoc/pipeline

## Purpose và owner

Pure compute stage pipeline Owner: AI-2 wiring; AI-1 OCR/geometry/evidence.

## Đặt gì ở đây?

service.py (AI-2), preprocess/geometry/evidence (AI-1), extraction/normalization/confidence (AI-2) khi có increment.

## Ranh giới

No business DB/job claim/approval; canonical vsprocessed transform, field missing null/issues.

## Workflow và kiểm tra

Đọc [doc vai trò](../../../docs/team/ai-2-extraction.md), nhận một task có input/version/output/acceptance. O1–O5/M2/M5: no guessed boxes/values, versions/resource outcomes; M2.3 stage integration. Ghi actual commands/results và limitations, [Git Flow](../../../docs/git-flow.md); không tự commit/push/deploy.

## Liên quan

[Scope](../../../specs/scope.md), [structure](../../../docs/source-structure.md), [architecture](../../../docs/architecture.md).
- [extraction](extraction/SPEC.md)
- [ocr](ocr/SPEC.md)

File đích chưa implement không là code chạy được; tạo implementation/SPEC con theo increment được giao.
