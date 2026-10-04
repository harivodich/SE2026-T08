# ADR-0003: Immutable prediction/revision và approval snapshot

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Context

Rerun/edits/approve có thể cạnh tranh. Export phải đúng dữ liệu human approved và không mất provenance.

## Decision

ExtractionRun bất biến; append ReviewRevision; Approval riêng; optimistic CAS head/version; export explicit revision. Rerun không overwrite head đang review/approved.

## Alternatives và consequences

Một JSON record sửa in-place dễ mất provenance/audit; full event sourcing quá nặng. Chấp nhận thêm records/storage để traceability.

## Validation và reversibility

Stale save 409; approval/save race; rerun không overwrite; export hash stable. Có thể compact nonapproved drafts sau retention policy được duyệt, không sửa lịch sử approved.
