# Training configs

Model đã được người dùng chọn ngày 23/11/2026: `Qwen/Qwen3-1.7B`
kết hợp PEFT (LoRA/QLoRA), theo [ADR-0005](../../../../docs/adr/0005-model-spike.md).

Config của experiment cần pin model/tokenizer revision, schema, dataset
manifest, seed, image/token budget và training settings; thêm target modules,
rank/alpha/dropout, precision/quantization và checkpoint rules. LoRA hay QLoRA cùng
GPU config cụ thể còn chờ G0 measured smoke; chưa có runnable training config
trong folder này. Không ghi token, máy cá nhân hoặc weights vào Git.

[qwen-g0.yaml](qwen-g0.yaml) dùng profile `ocr_text_layout_v1`: chỉ OCR text/layout từ AI-1 + instruction, không nhận ảnh. M1.2 đã có config consumer, OCR adapter, local verified loader và CLI `python -m vietdoc.ml.qwen_smoke --help`. Execution trong file vẫn tắt; native inference đã chạy trong Docker với artifact-local budget override (4/4 JSON/schema PASS), nhưng semantic extraction chưa nghiệm thu; training chưa chạy. YAML reader cần optional PyYAML; API `QwenConfig.from_mapping` không cần package này. Xem [handoff M1.2](../../../../docs/team/AI-2/2026-11-24-qwen3-inference-handoff.md).
