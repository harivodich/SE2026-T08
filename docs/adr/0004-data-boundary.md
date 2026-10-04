# ADR-0004: Synthetic Việt main, public data phụ trợ có audit

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Context

Đề chỉ tiếng Việt và synthetic/sample; public KIE Việt không luôn có full JSON/PII-safe. Access không được là dependency bắt buộc của timeline.

## Decision

Generator có gold labels, layout-disjoint splits và independent mock; ReceiptVQA optional QA support sau audit. Không dùng field chưa annotate làm absent/null gold.

## Alternatives và consequences

Public-only phụ thuộc access/schema; gán nhãn nhiều dữ liệu thật không hợp time/privacy; tiếng Anh ngoài scope. Chấp nhận synthetic domain gap, report rõ, không claim production generalization.

## Validation và reversibility

Rendered-label QA, parent/template leakage checks, provenance/terms/PII audit và holdout coverage. Có thể thêm dataset thật được phép với version/split mới nếu scope cho phép.
