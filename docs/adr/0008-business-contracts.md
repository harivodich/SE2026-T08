# ADR-0008: Business schema cố định và JSON approved output

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Lưu ý redesign 07/10/2026

Đề xuất v1, giữ để truy nguyên. Thiết kế đích hiện ở [ADR-0009](0009-java-python-thymeleaf.md); không dùng shared Python services/Celery/Pydantic authority làm implementation mới. Status vẫn Proposed cho tới quyết định Lead, chưa tự đánh dấu Accepted/Superseded.

## Context

Dataset/vendor fields khác nhau; nullable data không là complete annotation. UI/backend/export cần contract ổn định.

## Decision

Receipt.v1/invoice.v1 và shared line items, Pydantic source-of-truth khi implementation; schema trong bootstrap là reference. Evidence/editor metadata ngoài business payload; output chỉ approved revision.

## Alternatives và consequences

Arbitrary extraction schemas cần broader data/eval; dataset-specific JSON phân mảnh consumers. Chấp nhận fixed profiles và migration rõ khi contract đổi.

## Validation và reversibility

Positive/negative schema examples, label coverage, generated frontend types và approved export checksum. V2 đồng bộ migration/model/dataset/evaluator.
