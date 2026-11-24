# M1.2 — OCR adapter và Qwen3 inference: implementation plan

Owner AI-2, 23/11/2026. Theo task M1.2 người dùng giao trong phiên này.

## Kiến trúc và giới hạn

`OcrPage + PreparedPage + caller-verified provenance → structured messages → local Qwen3 → raw output → existing parser/normalizer → business JSON`.

Không thay shared schemas, AI-1, Data, Backend, B0 hoặc serving default. Chỉ load pretrained snapshot qua verifier hiện có; không provision hoặc train trong increment. Prompt separation/JSON escaping giảm injection surface, không chứng minh model miễn nhiễm prompt injection. Deadline là cooperative; không hứa ngắt GPU tức thì.

## Các bước thực thi

1. Viết tests OCR serialization: IDs/order/multiline, geometry, missing/empty/partial, provenance, budgets và special-token injection. Implement `ml/ocr_adapter.py`, dùng validator OCR hiện có.
2. Viết tests config và loader bằng doubles: local-only verify trước import/load, compatibility/device/dtype/memory, lifecycle/reuse/close, deterministic generation/deadline/OOM. Implement `ml/qwen_config.py`, `ml/model_loading.py`; không import model frameworks trong contracts.
3. Viết tests inference hai types: raw JSON/schema khác normalized schema, malformed/truncated/reasoning/overflow và typed failures. Implement `ml/qwen_inference.py`, reuse parser/normalizer.
4. Chạy focused tests, regression AI fixture gate, pip check và diff review. Không cài/nâng dependencies. YAML reader dùng optional PyYAML có sẵn nếu có; thiếu package báo typed config error, API nhận mapping vẫn dùng được.
5. Ghi handoff: files, lệnh, checks thực, provenance, limitations, native BLOCKED và điều kiện M1.3. Không dùng fixture evidence để claim native inference hoặc G0.

## Acceptance offline

Các tests bằng doubles pass, không network/model imports trong adapter/contracts, không runtime activation. Load từ verified local snapshot đúng pin; budget không truncate; model giữ một instance với serialized access; failures không chứa OCR/private exception details. Kết quả không tự sinh IDs/confidence/evidence.
