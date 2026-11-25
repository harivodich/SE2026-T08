# Training configs

Cập nhật 26/11/2026: đã chạy D22 một epoch (24 eligible samples/6 updates),
checkpoint/reload và dev B0/M0/M1; xem [acceptance hiện hành](../../../../docs/team/AI-2/2026-11-26-model-dev-acceptance.md).
Model chưa đạt raw-schema/quality để bật serving. Các mô tả M1.2 dưới đây là
lịch sử 24/11, không dùng để kết luận training hiện chưa chạy.

Model đã được người dùng chọn ngày 23/11/2026: `Qwen/Qwen3-1.7B`
kết hợp PEFT (LoRA/QLoRA), theo [ADR-0005](../../../../docs/adr/0005-model-spike.md).

Config của experiment cần pin model/tokenizer revision, schema, dataset
manifest, seed, image/token budget và training settings; thêm target modules,
rank/alpha/dropout, precision/quantization và checkpoint rules. LoRA hay QLoRA cùng
GPU config cụ thể còn chờ G0 measured smoke; chưa có runnable training config
trong folder này. Không ghi token, máy cá nhân hoặc weights vào Git.

[qwen-g0.yaml](qwen-g0.yaml) dùng profile `ocr_text_layout_v1`: chỉ OCR text/layout từ AI-1 + instruction, không nhận ảnh. M1.2 đã có config consumer, OCR adapter, local verified loader và CLI `python -m vietdoc.ml.qwen_smoke --help`. Execution trong file vẫn tắt; native inference đã chạy trong Docker với artifact-local budget override (4/4 JSON/schema PASS), nhưng semantic extraction chưa nghiệm thu; training chưa chạy. YAML reader cần optional PyYAML; API `QwenConfig.from_mapping` không cần package này. Xem [handoff M1.2](../../../../docs/team/AI-2/2026-11-24-qwen3-inference-handoff.md).

Local training configs may explicitly select
`input.ocr_context.serialization_version: vietdoc_ocr_context_v2`; absent means
legacy v1. V2 uses prompt `qwen3-business-json.v3`, ordered arrays with unchanged
text and canonical normalized quads rounded half-up to integers /1000 (maximum
coordinate error 0.0005). Geometry is a prompt hint; original artifact hashes,
null reasons and unreadable diagnostics are retained. Original metadata and
strict business validators are unchanged. Dataset/prompt hashes differ from v1;
v1 adapters do not establish v2 parity. Use the same explicit serialization and
budgets for training and any later offline adapter evaluation; serving stays off.

`training_g0.require_full_epoch: true` requires enough optimizer-step budget and
visits every eligible sample exactly once without wrapping the last microbatch.
Loss accumulation takes the mean over supervised causal tokens in each update.
Run manifests record per-sample visits and exclusions. Checkpoints are verified
adapter snapshots with optimizer summaries, **not exact resumable training state**.
