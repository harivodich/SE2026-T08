# ADR-0005: OCR baseline và Qwen2.5-VL-3B-Instruct với PEFT

## Status

Proposed — 2026-10-04. [Nguồn](../design/v1/07-decisions.md).

Cập nhật 03/11/2026 theo yêu cầu trực tiếp của người dùng: hệ thống sử dụng
`Qwen/Qwen2.5-VL-3B-Instruct`, fine-tune bằng PEFT (LoRA/QLoRA). Lựa chọn này đã
được người dùng chốt; trạng thái Proposed của toàn ADR và acceptance G0 không tự đổi.

> Cập nhật yêu cầu người dùng 23/11/2026: model hiện chọn **Qwen/Qwen3-1.7B + LoRA/QLoRA**, đầu vào chỉ **OCR text/layout** từ AI-1 + instruction. Xem [feasibility hiện hành](../team/AI-2/qwen-feasibility.md). Nội dung Qwen2.5-VL dưới đây ghi quyết định trước đó; cần Lead review cập nhật ADR. Status vẫn **Proposed**, chưa có G0/model acceptance.
## Context

Extraction cần receipt/invoice business JSON và line items. Hardware đã có số đo
trong [model constraints](../team/AI-2/2026-11-01-model-constraints.md), nhưng chưa
có inference/train-step evidence để cam kết memory, latency hoặc chất lượng model.

## Decision

Giữ OCR Vietnamese và rule baseline B0 để tích hợp/đối chiếu. Model extraction
được chọn là `Qwen/Qwen2.5-VL-3B-Instruct`: M0 là pretrained model, M1 là model
fine-tune bằng PEFT (LoRA/QLoRA). Input gồm ảnh một trang và instruction theo
selected type/schema; OCR context bổ sung theo profile đã kiểm chứng. Target chỉ
là business JSON, không runtime IDs hoặc confidence tự khai báo.

G0 kiểm chứng feasibility của model đã chọn và chốt immutable model/tokenizer/
processor revisions, LoRA hoặc QLoRA, precision/quantization, target modules và
image/token budgets. G0 không còn là bước chọn lại model family. QLoRA là hướng
LoRA với base weights lượng tử hóa 4-bit; chọn cấu hình bằng compatibility smoke
và memory/quality evidence, không mặc định vừa GPU 8 GB. Adapter và base model
được pin trong immutable release manifest; schema/process không chờ model chạy.

## Alternatives và consequences

ViT5/mT5 từng được đề xuất trong báo cáo constraints nhưng không được chọn làm
model hệ thống. Không tự thay Qwen bằng text-only model khi gặp OOM; báo blocker
và xin quyết định thay đổi nếu cần. Train OCR từ đầu hoặc paid APIs không thuộc
quyết định này. Spike vẫn cần trước khi chốt cấu hình và full training.

## Validation và reversibility

20-sample smoke và train step, license/peak memory/latency; B0/M0/M1 dev metrics. Thay adapter/checkpoint qua manifest, ghi outcomes; không silently bỏ fine-tune objective.

Nguồn kỹ thuật: [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct),
[PEFT LoRA](https://huggingface.co/docs/peft/developer_guides/lora),
[QLoRA/quantization](https://huggingface.co/docs/transformers/quantization/bitsandbytes).
Lựa chọn model không phải bằng chứng đã provision, load, fine-tune hoặc đạt G0.
