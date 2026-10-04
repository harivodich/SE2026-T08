# ADR-0007: Local private storage và UI polling

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Context

Demo một instance; Backend làm cả UI. Cần private file access và job status, chưa cần multiple hosts hoặc push notifications.

## Decision

Local volume qua storage adapter, authorized file stream và status polling. Không thêm vector DB/WebSocket chưa có requirement.

## Alternatives và consequences

S3 tăng setup nhưng hợp multiple hosts; SSE/WebSocket thêm cancellation/reconnect complexity. Chấp nhận capacity một instance và polling delay.

## Validation và reversibility

File ownership/path safety, lost-object handling và measured API target. Đổi S3 adapter hoặc notifications khi có requirement, update deployment ADR.
