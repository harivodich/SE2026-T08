# 07 — ADR đề xuất

Tất cả ADR trong hồ sơ là **Proposed**, ngày 04/10/2026. Lead/team có thể chấp nhận và đưa từng ADR vào `docs/adr/` khi bắt đầu implementation. Không có architecture hiện hữu để migrate trong workspace đã kiểm.

## ADR-0001 — Modular monolith với API/worker riêng

Context: bốn IC, hai loại chứng từ, computation nặng và review transactional. Chọn một repo và public module boundaries; API/worker/dispatcher dùng chung services/contracts.

Alternatives: synchronous monolith đơn giản nhưng inference block/timeout; microservices tăng deployment/API/versioning/debug overhead khi chưa có independent teams. Chấp nhận thêm process để isolation, không thêm network boundary giữa business modules.

Validation: CPU API không import/load GPU model; import-cycle checks; one receipt E2E. Reversibility: sau này tách compute serving adapter nếu có scale evidence; giữ public contracts.

## ADR-0002 — PostgreSQL source of truth + outbox + Celery/Redis

Context: không mất job khi API chết giữa commit/publish, retry có duplicates. Chọn job/outbox transaction, dispatcher/recovery và fencing; Redis chỉ delivery.

Alternatives: FastAPI BackgroundTasks thiếu process isolation/durable reconciliation; DB-only queue giảm broker nhưng phải tự làm execution plumbing; RabbitMQ thêm operational stack. Chấp nhận outbox và recovery để giữ invariant, không claim exactly-once execution.

Validation: publish gap, duplicate delivery, stale worker, Redis restart tests; một run/job. Reversibility: broker adapter đổi, DB job semantics giữ nguyên.

## ADR-0003 — Immutable prediction/revision và approval snapshot

Context: rerun và edits có thể cạnh tranh; export phải đúng dữ liệu human approved. Chọn ExtractionRun bất biến, append ReviewRevision, Approval riêng, optimistic CAS head/version, export explicit revision.

Alternatives: một JSON record sửa in-place dễ mất provenance và audit; full event sourcing quá nặng. Chấp nhận thêm records/storage để traceability.

Validation: stale edits 409; rerun không overwrite; export hash stable; approval/save race. Reversibility: có thể compact nonapproved drafts sau retention policy, không sửa lịch sử approved.

## ADR-0004 — Synthetic Việt main, public data phụ trợ có audit

Context: đề chỉ Việt và synthetic/sample; public KIE Việt không luôn có full JSON/PII-safe. Chọn generator có labels tự động, layout-disjoint splits và independent mock; ReceiptVQA optional QA support.

Alternatives: public-only dễ phụ thuộc access/schema; tự gán nhãn nhiều dữ liệu thật không hợp time/privacy; tiếng Anh không hợp scope. Chấp nhận domain gap synthetic, report rõ, không claim production-generalization.

Validation: rendered-label QA, parent/template leakage tests, provenance/terms, final holdout coverage. Reversibility: thêm dataset thật đã được phép với version/split mới khi scope cho phép.

## ADR-0005 — OCR baseline + fine-tuned extraction, chọn model bằng spike

Context: chưa biết GPU/VRAM; extraction phải có schema và line items. Chọn OCR Vietnamese có sẵn, rule baseline và một extraction candidate fine-tune; engine-specific adapters, immutable manifest.

Alternatives: train OCR từ đầu không đủ dữ liệu/time; VLM lớn chưa biết cost; paid APIs cần authority/cost và không là default. Chấp nhận model name/version là quyết định mở đến G0; schema/process không chờ tên model.

Validation: 20-sample smoke + train step W2, dev metrics B0/M0/M1, peak memory/latency/license. Reversibility: thay adapter/checkpoint qua manifest; record outcomes.

## ADR-0006 — Canonical geometry và nullable calibrated confidence

Context: OCR preprocess ảnh khác ảnh viewer; score OCR không là field correctness. Chọn canonical page, inverse transform và evidence mapper, confidence null khi thiếu calibration.

Alternatives: trực tiếp dùng processed bbox sai highlight; VLM tự sinh confidence không đáng tin. Chấp nhận ambiguity/manual review thay source coordinates/probability bịa.

Validation: rotation/crop/deskew tests, bbox range/order, evidence coverage, validation calibration support. Reversibility: cải thiện mapper/calibrator giữ contract, tăng manifest version.

## ADR-0007 — Local private storage và UI polling trong MVP

Context: demo one instance, Backend phải làm cả UI. Chọn local volume adapter, authorized file stream và polling status. Một ORM/API style, không thêm vector DB hoặc WebSocket chưa cần.

Alternatives: S3 tăng setup nhưng phù hợp multiple hosts; SSE/WebSocket tăng cancellation/reconnect complexity. Chấp nhận capacity một instance và polling delay.

Validation: ownership file access, lost-object handling, API response target, filesystem path safety. Reversibility: S3 adapter hoặc push notifications khi có requirement mới.

## ADR-0008 — Business schema là contract, JSON là output approved

Context: dataset/vendor fields khác nhau; nullable data không đồng nghĩa complete label. Chọn receipt.v1/invoice.v1 và shared items, Pydantic source-of-truth khi code; schema refs trong hồ sơ là reference. UI metadata/evidence không trộn vào business payload.

Alternatives: arbitrary extraction schemas cần broader data/evaluation; dataset-specific JSON làm UI/backend phân mảnh. Chấp nhận fixed schema profile và explicit migration khi đổi.

Validation: schema examples/negative cases, dataset coverage labels, frontend generated types, exporter approved snapshot test. Reversibility: v2 qua migration + model/dataset/evaluator version đồng bộ.
