# M1.1 — Qwen3-1.7B Feasibility & Configuration

Ngày cập nhật: **24/11/2026**. Owner: AI-2. **M1.1/G0 training vẫn proposed; M1.2 native đã chạy, schema PASS nhưng semantic quality chưa nghiệm thu**. Xem [native handoff](2026-11-24-qwen3-inference-handoff.md).

## Quyết định hiện hành

Theo yêu cầu mới nhất của người dùng, chọn **`Qwen/Qwen3-1.7B` + LoRA/QLoRA**, thay Qwen2.5-VL-3B-Instruct. Đầu vào từ AI-1 chỉ là **OCR text/layout**; AI-2 thêm selected type/schema instruction. Không truyền ảnh hoặc pixel tensors. Output là business JSON đúng schema hiện có; không sửa AI-1, Data, Backend hoặc shared contracts.

[qwen-g0.yaml](../../../src/vietdoc/ml/configs/qwen-g0.yaml) là proposal, **đã có M1.2 config consumer/loader; native đã chạy bằng artifact-local budget override, không phải exact profile này**; execution/download/training/activation vẫn tắt. B0 vẫn là runtime hiện hành. Đổi config không tự kích hoạt Qwen inference.

## Upstream, revision, license và tokenizer

- Model: `Qwen/Qwen3-1.7B`, text causal LM, class `Qwen3ForCausalLM`, `model_type=qwen3`, BF16.
- Revision pin: **`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`**, đọc từ API upstream ngày 23/11. Không dùng `main` khi provision/runtime.
- License **Apache-2.0**, thay điều kiện Qwen Research License của VL cũ. Giữ license/attribution/notices áp dụng khi phân phối; approval provision của Lead vẫn riêng, chưa được xác nhận.
- Allowlist **11 files**: LICENSE, README.md, config.json, generation_config.json, tokenizer_config.json, tokenizer.json, vocab.json, merges.txt, model.safetensors.index.json và hai safetensors shards. Không có `preprocessor_config.json` hoặc `chat_template.json` riêng; template nằm trong tokenizer_config.json.
- Upstream metadata báo BF16 tensor parameters **2,031,739,904**, hai weight files tổng **4,063,515,592 bytes**. Metadata đã được đối chiếu local snapshot: download và verify 11 files hoàn tất ngày24/11, hashes/inventory được lưu trong native artifacts. Không dùng tên 1.7B để suy ra kích thước VRAM thực.
- Dùng `AutoTokenizer` và pinned tokenizer chat template. `enable_thinking=false` phải truyền khi apply template; greedy, batch 1. Template có thể thêm empty think prefix: prompt tokens không được đưa vào JSON output. Generated reasoning ngoài business JSON phải reject/record; adapter M1.2 reject reasoning trong generated output; chưa nối production runtime.

Nguồn: [model card](https://huggingface.co/Qwen/Qwen3-1.7B), [API metadata](https://huggingface.co/api/models/Qwen/Qwen3-1.7B?blobs=true), [pinned config](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/config.json), [pinned tokenizer](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/tokenizer_config.json), [pinned license](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/LICENSE).

## Implemented / missing / proposed

- **Implemented:** [model_provision.py](../../../src/vietdoc/ml/model_provision.py), Docker setup service, staging/retry/checksum/index verifier, inventory và existing release verifier; B0/parser/normalizer/private HTTP không đổi.
- **M1.2 implemented offline (24/11):** config consumer, OCR serializer, verified-local Qwen loader/lifecycle, inference adapter và smoke CLI; xem [handoff](2026-11-24-qwen3-inference-handoff.md). **Native đã chạy:** verified weights, BF16 GPU inference và metrics, 4/4 schema PASS. **Missing/chưa nghiệm thu:** semantic source/evidence guard, training dataset/collator/train/reload runner, LoRA update và quality acceptance.
- **Proposed:** YAML G0, serialization, budgets và hardware request. Không coi fixture tests hoặc Docker build là model acceptance.

## Input OCR text/layout

Profile `ocr_text_layout_v1` dùng cùng train/inference. Serialize ordered `{block_id,text,canonical_quad}` từ observed OCR của AI-1; giữ reading order, IDs, partial/unreadable flags, canonical frame/dimensions và input/canonical/engine/profile hashes. Chỉ metadata provenance, không nạp ảnh. Geometry thiếu giữ null/reason; không suy box, text hoặc confidence.

Caller chọn receipt/invoice; instruction chứa schema/type constraints. OCR là dữ liệu không tin cậy, không phải chỉ dẫn. Không đưa gold, label statuses hoặc tên file gợi đáp án vào prompt. Thiếu artifact/sai provenance/overflow → reject và record, không truncate hoặc fallback ảnh. Explicit empty OCR khác missing artifact, phải giữ diagnostics. `vietdoc_ocr_context_v1` là adapter proposal, không thay shared schema.

### Business target và validation

Schema authoritative vẫn là `urn:vietdoc:business:v1`, SHA-256 bytes hiện tại `0948307b0c274d565fbe89b25d69f1692d0d6a4241352939f424ce0eba6b3ded`. Chọn đúng `$defs/Receipt` hoặc `$defs/Invoice` theo selected type, không chỉ validate chung union.

| Type | Keys bắt buộc |
|---|---|
| receipt | `merchant_name`, `merchant_address`, `transaction_date`, `transaction_time`, `total_amount`, `items` |
| invoice | `invoice_number`, `issue_date`, `seller_name`, `buyer_name`, `subtotal`, `tax_amount`, `discount_amount`, `total_amount`, `items` |
| mỗi item | `description`, `quantity`, `unit`, `unit_price`, `line_total` |

Ví dụ fictional, chỉ minh họa target serialization, **không phải output model đã chạy hoặc gold mới**:

```json
{"merchant_name":"Cửa hàng mẫu","merchant_address":null,"transaction_date":"2026-01-02","transaction_time":null,"total_amount":"40000","items":[{"description":"Cà phê","quantity":"2","unit":"ly","unit_price":"20000","line_total":"40000"}]}
```

```json
{"invoice_number":"MAU-001","issue_date":"2026-01-02","seller_name":"Đơn vị bán mẫu","buyer_name":null,"subtotal":"40000","tax_amount":null,"discount_amount":null,"total_amount":"40000","items":[{"description":"Cà phê","quantity":"2","unit":"ly","unit_price":"20000","line_total":"40000"}]}
```

Giữ mọi required key, không extras; money/quantity decimal strings không âm hoặc null; ngày `YYYY-MM-DD`, giờ `HH:MM[:SS]`, tối đa 30 items. Null nghĩa chưa có giá trị đủ chắc chắn, không chứng minh nguồn absent. Không suy tổng bằng phép cộng hoặc coi missing item labels là bảng rỗng.

Giữ raw generated text/finish reason riêng. Model adapter tương lai cần kiểm strict raw schema validity trước normalizer và ghi parsed validity riêng: parser hiện có chấp nhận JSON number literals để normalize, vì vậy `parse_model_output.status=ok` chưa chứng minh raw output tuân thủ decimal-string schema. Reuse parser/`vi-VND.v2`, không sửa tests/schema để hợp thức hóa output. EOS do token limit → `truncated`, malformed output không repair/fill hàng loạt thành null success. Adapter map thất bại vào typed outcomes hiện có theo review, không tự thêm shared enum.

OCR text/layout input không tự bảo đảm evidence đúng: field không có raw OCR span đủ để xác nhận thì source_regions rỗng và flags thích hợp, confidence null. Vẫn phải kiểm raw/context qua evidence mapper, dựa trên OCR text/layout đã cung cấp. Model không sinh runtime IDs, confidence hoặc bbox được tin thẳng. Chưa calibrated không dùng OCR score làm correctness probability.


## G0: cấu hình dự kiến, chưa đo

| Tham số | Reference LoRA | Constrained QLoRA |
|---|---|---|
| GPU request | BF16, 24 GB (giữ headroom cũ, chưa tối ưu cho Qwen3) | BF16, 16 GB; local 8 GiB chưa có fit guarantee |
| Precision | BF16, SDPA, không offload | NF4 double quant/BF16 compute; audit modules/dependencies trước |
| Visual tokens | 0 | 0 |
| Input / OCR cap nằm trong input | 3072 / 1024 | 1536 / 512 |
| Output / sequence | 2048 / 5120 | 1024 / 2560 |
| LoRA | r8, alpha16, dropout0.05, q/k/v/o attention projections | Cùng LoRA, base quantized |
| Tiny train tương lai | microbatch1, accumulation4, 2 optimizer steps, LR1e-4 | Cùng settings, cap nhỏ hơn |

Regex `.*model\.layers\.[0-9]+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)$` phải kiểm bằng `named_modules()` trên env thực; zero/wrong matches phải fail. Freeze base embeddings/lm_head; Qwen3 text không có vision encoder/merger. Không thay dependency pins hiện tại; Torch/Transformers đã xác minh cho native BF16 inference; PEFT/bitsandbytes và training vẫn chưa xác minh.

RAM32 GiB/free disk40 GiB và GPU24/16 GB là planning request kế thừa, không phải minimum/measurement của Qwen3. Metadata BF16 cho lower bound weights khoảng3.78 GiB; còn activations/KV cache/optimizer/load temporaries. Không cam kết train vừa 8 GiB.

Loss chỉ assistant business JSON+EOS; prompt/OCR/PAD masked -100. Giữ `present/absent/obscured/unlabeled`; full JSON supervision chỉ khi toàn bộ field/item statuses rõ present/absent. Obscured/unlabeled exclude+count đến khi span masking được kiểm chứng, không biến null thành negative gold. Checkpoint pin base/tokenizer/template/thinking mode/serialization/schema/data lineage.

## Provisioning và checklist smoke tiếp theo

Storage mới: `artifacts/models/qwen/qwen3-1.7b/<revision>/`. Model cũ nếu có được giữ nguyên, không di chuyển hoặc ghi đè. Downloader vẫn tooling-only, không weights trong image; train base RO/checkpoints RW, consumers offline, không tự activate release. Xem [runbook](../../../infra/README.md).

- [x] Người dùng xác nhận Lead duyệt provision/Apache-2.0 ngày24/11; đã tải và verify model.
- [x] Snapshot đúng revision, 11 files/source/local hashes/sizes/index **VERIFIED/READY**, verify offline lại trên host PASS.
- [x] Implement loader/config validation và Qwen3 adapter, fixture checks cho template flags/output slicing/schema/overflow/malformed/reasoning. Native verification vẫn chưa chạy.
- [ ] Tiny receipt+invoice đã audit với observed OCR/provenance/split/label statuses; không final holdout.
- [ ] Đo env/GPU/RAM/VRAM/cold/warm runtime và failure outcomes; kiểm output schema/evidence/calibration trước quality claim.
- [ ] M1.3 kiểm finite loss/backward/update/checkpoint/clean reload riêng; inference xanh không là training acceptance.

## Verification

Lần đổi model này chỉ đọc upstream metadata/tokenizer/config qua Internet, không tải weights, không gọi GPU/inference/training. Kết quả tests/build/static checks được báo trong handoff; evidence Qwen2.5-VL trước đó là lịch sử, không thay bằng chứng Qwen3. Không commit/push/deploy.

Cập nhật native 24/11: BF16 base inference chạy trên RTX4060 Laptop8GB, Torch2.14.1+cu126/Transformers5.20.2/CUDA12.6. Hai demo observed OCR, 2 generations/type, raw/normalized schema4/4 PASS; peak RSS4.112GiB, Torch allocated peak VRAM3.733GiB. Prompt đã debug trên cùng demos; vẫn có unsupported units và header-as-item, không claim accuracy/semantic acceptance hoặc train-fit. Native dùng input4096/OCR3072/output2048/sequence6144, source G0 YAML execution vẫn tắt.
