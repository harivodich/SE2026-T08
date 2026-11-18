# M-N3 — measured constraints và candidate proposal, 01/11/2026

Status: **BLOCKED cho model G0 execution**, không phải đạt G0. Chưa có approved
candidate/profile hoặc local verified weights/tokenizer release. Không download
weights/tokenizer/dataset, không thuê GPU, không chạy model/training trong lượt này.
Chỉ đọc public model metadata/model cards để chuẩn bị proposal reviewable.

## Hardware/runtime đã đo

| Môi trường | Facts |
|---|---|
| Windows host | Windows 11 build 26200; Ryzen 7 7840H, 8 cores/16 threads; RAM 16,312,553,472 bytes (~15.2 GiB) |
| GPU/driver | NVIDIA GeForce RTX 4060 Laptop, 8188 MiB, driver 560.94 qua nvidia-smi |
| Workspace disk E | Free 63,969,087,488 bytes tại lúc đo; đây là disk, không phải RAM/VRAM |
| AI serve/test venv | Python 3.13.5, FastAPI 0.162.0/jsonschema 4.26.0; torch/transformers/peft/Pillow chưa cài trong venv này |
| Train images đã có | `vietdoc-ai-train:cu126` 11 GB và `:dev` 1.74 GB (image disk size) |
| GPU train container probe | Python 3.12.15, torch 2.14.1+cu126, CUDA available=true, device memory 8,585,216,000 bytes; transformers 5.20.2, peft 0.21.2, accelerate 1.15.0, safetensors 0.8.0, Pillow 13.0.0 |
| Container memory domain | `/proc/meminfo` reported 7,897,509,888 bytes (~7.35 GiB); host RAM 16 GB không có nghĩa container dùng được toàn bộ |
| Releases | Không verified release trong repo `artifacts/models` hoặc image `/models` không mount weights |

Probe dùng image có sẵn, `--rm --network none --gpus all`, không model mount,
không khởi động service. CUDA readiness không chứng minh extractor inference,
train-step, checkpoint hoặc fitting trong VRAM. Không đồng nhất image size với RAM.

## Candidate metadata đã đọc, chưa chọn/pin training

Đây là đề xuất engineering để Lead/AI1/Data review, không benchmark recommendation.
Hai candidates là text-to-text: cần accepted serialization OCR text/layout/context
và business JSON targets; không trực tiếp nhận image hoặc sinh runtime metadata.

| Candidate | Observed repository revision | Model card license | Remote PyTorch weight bytes |
|---|---|---|---:|
| [VietAI/vit5-base](https://huggingface.co/VietAI/vit5-base) | `2209a38d735ede63e88f5aa52bcdc11a05a37b85` | MIT | 903,886,847 |
| [google/mt5-small](https://huggingface.co/google/mt5-small) | `73fb5dbe4756edadc8fbe8c769b0a109493acf7a` | Apache-2.0 | 1,200,794,589 |

ViT5 là Vietnamese encoder-decoder; mT5 là multilingual pretrained model gồm
Vietnamese. Đề xuất khảo sát ViT5 trước vì định hướng tiếng Việt và remote PyTorch
artifact nhỏ hơn; đây là inference từ metadata, chưa có bằng chứng quality/memory/
latency hoặc khả năng tuân thủ JSON. Không tự chuyển modality/labels được nhận.

Artifacts cần provision từ đúng revision: config, tokenizer config, special token
map, SentencePiece model, weights; mT5 thêm generation config nếu dùng. Không cần
tải các bản TF/Flax/ONNX khác để làm cùng spike PyTorch. Packaging/loading format,
safe local loading và dependency SentencePiece phải được smoke khi artifacts được cấp;
không tự bật remote code hoặc nhận model URL/path từ caller.

Remote LFS SHA256 references (chưa local-byte verified):

- ViT5 `pytorch_model.bin`: `6e666460219d3495e6437ac09061425ccf896532c92ec00cd3e6130cc94f3f44`;
  `spiece.model`: `59986b62f9f0b90edafb9b073ea7b93d21114a5841219a1ea2399ade73f729c6`.
- mT5 `pytorch_model.bin`: `9daa76f0231b96162833ebfee26e886a781b72e0d95ad1a1826b9147a74a939a`.
- Files nhỏ được API trả Git blob IDs, không giả chúng là SHA256 file bytes.
  Sau provision phải tính SHA256 mọi file local và tạo immutable allowlisted release.

Nguồn metadata: public [ViT5 API](https://huggingface.co/api/models/VietAI/vit5-base?blobs=true)
và [mT5 API](https://huggingface.co/api/models/google/mt5-small?blobs=true), model cards
ở các revision trên. JSON metadata snapshot đầy đủ ở ignored
`.verification/mn2/model-metadata.json`; không có model/tokenizer bytes được tải.

## Điều kiện unblock và acceptance tiếp theo

1. Lead chọn candidate/revision/license/use và đường provision; xác nhận profile
   OCR text/layout + target JSON với AI1/Data, không đổi supervision âm thầm.
2. Cấp allowlisted local artifacts và hashes; chốt pinned train environment từ
   compatibility smoke. Serving/OCR/training env giữ riêng: AI1 Pillow12 và train
   Pillow13 không tự thành một combined extra hợp lệ. Kiểm canonical/preprocess
   và tokenizer/input-output equivalence trước khi claim train/serve parity.
3. Tokenize tiny QA inputs/targets và đo overflow trước khi chọn max lengths.
   No silent row/token truncation. Unlabeled/obscured không thành null-supervision;
   chọn masking/filtering representation và ghi coverage bị loại.
4. Chạy model inference thật: raw JSON validity/schema/failure, warm/cold latency,
   peak RAM/VRAM, settings và same-input version pins. Không mặc định pretrained
   model đã instruction-tuned hoặc vừa 8 GB chỉ từ weight size.
5. Forward → finite loss → backward → gradient/parameter update → checkpoint →
   reload → inference. Microbatch/AMP/LoRA/accumulation chọn bằng số đo và support,
   không tự hứa full fine-tune trên CPU hoặc số giờ hoàn thành.
6. Checkpoint lưu optimizer/scheduler/RNG/data progress cần resume. Notebook chỉ
   gọi cùng source train entrypoint sau khi model được chọn; không dựng pipeline
   khác trong notebook. Chưa tạo fake train/collator scaffolds ở increment B0 này.
7. Đo step time/overhead rồi mới dự toán pilot/free GPU hoặc spending cap cần duyệt.
   So sánh B0/M0/M1 trên approved dev, final chỉ theo freeze protocol. Smoke D1
   đã nhìn không trở thành unseen dev/final.

Các bước inference/train/checkpoint trên là **NOT_RUN**, không phải planned PASS.
Không gửi thông điệp cho Lead hoặc thay provisioning/account settings trong lượt này.
