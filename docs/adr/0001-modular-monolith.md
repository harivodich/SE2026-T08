# ADR-0001: Modular monolith với API/worker riêng

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Lưu ý redesign 07/10/2026

Đề xuất v1, giữ để truy nguyên. Thiết kế đích hiện ở [ADR-0009](0009-java-python-thymeleaf.md); không dùng shared Python services/Celery/Pydantic authority làm implementation mới. Status vẫn Proposed cho tới quyết định Lead, chưa tự đánh dấu Accepted/Superseded.

## Context

Bốn IC, hai loại chứng từ, computation nặng và review transactional. API/worker/dispatcher cần isolation nhưng không có independent teams để vận hành microservices.

## Decision

Một repository, public module boundaries, API/worker/dispatcher process riêng dùng chung services/contracts. Không thêm HTTP boundary giữa business modules.

## Alternatives và consequences

Synchronous monolith dễ timeout/block inference; microservices tăng deployment/API/versioning/debug overhead. Chấp nhận thêm process để isolation, giữ một codebase và transaction boundary.

## Validation và reversibility

CPU API không import/load GPU model; import-cycle checks; receipt E2E. Sau này tách compute serving adapter khi có scale evidence, giữ public contracts.
