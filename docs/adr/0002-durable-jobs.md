# ADR-0002: PostgreSQL source of truth, outbox và Celery/Redis

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Lưu ý redesign 07/10/2026

Đề xuất v1, giữ để truy nguyên. Thiết kế đích hiện ở [ADR-0009](0009-java-python-thymeleaf.md); không dùng shared Python services/Celery/Pydantic authority làm implementation mới. Status vẫn Proposed cho tới quyết định Lead, chưa tự đánh dấu Accepted/Superseded.

## Context

API có thể chết giữa DB commit/publish; retry có duplicate delivery. Không được mất job hoặc committed result bị nhân bản.

## Decision

Job/outbox cùng transaction; dispatcher/recovery và lease fencing; Redis chỉ delivery. At-least-once execution, một committed run/job qua DB invariant, không claim exactly-once execution.

## Alternatives và consequences

BackgroundTasks thiếu durable reconciliation/process isolation; DB-only queue phải tự làm execution plumbing; RabbitMQ thêm operational stack. Chấp nhận outbox/recovery overhead để giữ invariant.

## Validation và reversibility

Test publish gap, duplicate delivery, stale worker và Redis restart. Broker adapter có thể đổi, DB job semantics giữ nguyên.
