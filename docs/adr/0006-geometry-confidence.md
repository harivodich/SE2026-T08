# ADR-0006: Canonical geometry và nullable calibrated confidence

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

## Context

OCR preprocess image có thể khác viewer image; OCR score không là field correctness probability. Sai evidence có thể khiến reviewer tin sai vùng nguồn.

## Decision

Canonical page, inverse transform/evidence mapper; confidence null khi không đủ calibration. Human correction giữ original provenance, không score=1.0.

## Alternatives và consequences

Processed bbox trực tiếp có thể highlight sai; VLM tự sinh confidence không đáng tin. Chấp nhận ambiguity/manual review và limitation thay vì bịa coordinates/probability.

## Validation và reversibility

Rotation/crop/deskew, bbox range/order/evidence coverage, calibration support. Cải thiện mapper/calibrator giữ contract, tăng manifest version.
