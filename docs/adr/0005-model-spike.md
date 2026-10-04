# ADR-0005: OCR baseline và fine-tuned extraction, chọn model bằng spike

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Context

Chưa biết GPU/VRAM; extraction cần schema và line items. Chưa đủ evidence để cam kết một VLM hoặc latency cụ thể.

## Decision

OCR Vietnamese có sẵn, rule baseline và extraction candidate fine-tune; vendor-specific adapters, immutable manifest. Model name/version quyết định ở G0/W2; schema/process không chờ tên model.

## Alternatives và consequences

Train OCR từ đầu thiếu time/data; VLM lớn chưa biết cost; paid APIs cần authority/cost và không là default. Chấp nhận spike trước lock dependencies/resources.

## Validation và reversibility

20-sample smoke và train step, license/peak memory/latency; B0/M0/M1 dev metrics. Thay adapter/checkpoint qua manifest, ghi outcomes; không silently bỏ fine-tune objective.
