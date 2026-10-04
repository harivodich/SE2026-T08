# 06 — Dữ liệu, model, fine-tune và evaluation

## 1. Data boundary

Chỉ tiếng Việt, chữ in, receipt/invoice một trang, profile VND. Dữ liệu main là synthetic có giá trị giả lập. Không dùng thông tin khách hàng/bệnh nhân thật trong generator/demo. Public không đồng nghĩa phù hợp privacy/terms; Data Engineer audit trước dùng sample.

### Data sources và quyết định

| Source | Evidence đã kiểm | Quyết định |
|---|---|---|
| Synthetic của nhóm | Sẽ tạo ảnh+JSON+box+template/source IDs | Nguồn main; phải kiểm labels bằng rendered page |
| ReceiptVQA/LiGT | Tác giả công bố 9.500 images, 64.812 QA, research-only CC BY-NC-SA; link Drive | Optional phụ trợ/read-eval; chưa download/audit; QA không là full JSON |
| Vietnamese Bill Extraction | HF viewer 982 rows, `master_data` có row fields; nhiều mẫu là y tế/dược | Không đưa core do provenance/PII/label audit chưa xong |
| MC-OCR | 4 fields và yêu cầu đăng ký nghiên cứu | Optional; không để timeline phụ thuộc access |
| FATURA/SROIE/CORD | Dataset khác ngôn ngữ | Không dùng training/evaluation chính trong scope chỉ Việt |

Nguồn: [ReceiptVQA](https://github.com/phong-lt/LiGT_VQA), [paper](https://arxiv.org/html/2502.19202v1), [Bill Extraction](https://huggingface.co/datasets/minhduc168/dataset-origin-vlm-extract-bill), [MC-OCR](https://www.rivf2021-mc-ocr.vietnlp.com/dataset).

ReceiptVQA đã dùng một phần ảnh MC-OCR. Nếu dùng cả hai, source lineage/hash phải group cùng split; không dùng MC train và ReceiptVQA test như độc lập. Partial annotation không chuyển các field chưa hỏi thành absent/null gold.

## 2. Generator và schema supervision

Target lập kế hoạch sau G0: khoảng 3.000–6.000 clean documents tổng hai loại, thêm bounded augmentation. Đếm **base documents và template families**, không quảng cáo ảnh biến thể như dữ liệu độc lập. Nếu train capacity thấp, dùng subset stratified, giữ final holdout.

Template target mỗi loại 10 families: 6 train, 2 dev, 2 final-test; thêm 2–3 independent mock families mỗi loại được người khác thiết kế. Đây là target, Data Engineer có thể điều chỉnh trước freeze tuần 5 dựa complexity. Một font/color change không tự là family mới; family phải khác spatial structure/label vocabulary/table arrangement.

Generated fields: fake merchant/seller/buyer, dates, document numbers, prices/quantity/unit; Việt Unicode NFC. Tên business fake rõ, không số định danh có thể vô tình trùng người thật; không chữ ký/con dấu thật. Sinh missing fields, zero/discount/service charges và multi-line descriptions có chủ đích.

Mỗi sample chứa image/PDF, canonical ground truth business JSON, regions, optional table row/cell IDs; metadata: sample_id, base_id, template_id, family_id, seed, generator_version, schema_version, language, source_kind, license, split, labels_status, sha256. Render truth từ cùng data object; không chạy OCR rồi lấy prediction làm gold.

Nếu augmentation crop/rotate làm mất field, cần update visible-label/evidence hoặc đánh dấu obscured, không giữ gold unseen như ảnh sạch mà không ghi slice. Noise/blur có severity cap; nội dung vẫn readable trong main evaluation, unreadable là failure slice riêng.

## 3. Split và leakage controls

1. Assign family split trước sinh values. Tất cả variants cùng base/family ở cùng split.
2. Không cross templates clone bằng thay màu/fonts giữa train/test.
3. Dedupe SHA-256 và perceptual/content signatures; report ambiguous near-duplicate groups.
4. Dev dùng chọn checkpoint/hyperparams; tách dev-tuning và dev-calibration khi đủ mẫu.
5. Final-test manifest frozen/hash từ W5; engineer tune model không xem final predictions cho đến W10. Xem để sửa có nghĩa cần test mới, không tiếp tục gọi tập đó là untouched.
6. Independent mock được author khác generator tạo, không copy coordinates từ templates train.
7. Human corrections không tự vào train. Phải consent/data audit/label QA/source group/version trước dùng.

## 4. Ground-truth QA checklist

- Đọc rendered image: nhãn/date/amount và Unicode đúng, text không overflow hoặc bị clip bất ngờ.
- Decimal semantics có locale rõ; totals sinh nhất quán theo rule, nhưng không mọi sample có cùng arithmetic pattern.
- Required-for-approval field có visible gold; optional field absent được đánh dấu rõ.
- Bảng có row identity, wrap và empty cells; không align bằng thứ tự OCR mặc định.
- Bbox/quad theo canonical viewer geometry; page 0; [0,1] finite.
- Gold field có `present/absent/obscured/unlabeled`; metrics chỉ tính labels được phép.
- Dataset report có counts theo type/family/field, missing rate, max rows, average tokens và exclusion reasons.

Data Engineer sample-check mỗi family, boundary cases và ngẫu nhiên theo seed. AI engineers review các lỗi ảnh nhãn phát hiện được; giữ correction history.

## 5. Pipeline baseline và model spike

**B0**: OCR có sẵn + label-aware rules + table grouping đơn giản + cùng normalization/validation. Rules không hard-code tọa độ duy nhất; vẫn là baseline để đo value fine-tune.

**M0**: Một pretrained extractor candidate dùng OCR/image context và output JSON trước fine-tune. Candidate có thể là VLM nhỏ. Qwen2.5-VL-3B-Instruct là **ứng viên spike**, chưa được chứng minh phù hợp tiếng Việt/hardware của nhóm; audit model card/license, tokenizer, processor và memory trước chọn. Model không có tools. [Model card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct).

**M1**: Fine-tuned extractor, output business schema như B0/M0. Adapter giữ vendor-specific types ngoài contracts. G0 có 20 sample, inference + một train-step, output-validity/latency/peak memory có số đo. Nếu không chạy được, chọn OCR-text model nhỏ hơn; không thêm paid API mặc định. Không pin model name là chất lượng cam kết.

OCR spike dùng PaddleOCR `vi`, pin engine/package/OCR models sau smoke. Không assume `lang=vi` trên mọi version chọn đúng model; docs có mapping theo OCR release. [PaddleOCR](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html).

## 6. Training workflow

1. Load immutable dataset manifest, kiểm hash/labels/schema/split.
2. Build training input gồm type/schema instruction, image và OCR context nếu architecture cần. Context giữ order/coordinates và token budget; overflow không truncate field giữa chừng âm thầm.
3. Target output là canonical JSON, optional field absent là null; unlabeled samples không dùng như full supervision. ReceiptVQA chỉ QA được label → auxiliary experiment riêng hoặc manual mapping + audit, không mặc định toàn bộ dataset thành JSON.
4. Fine-tune bằng PEFT/LoRA nếu selected model hỗ trợ và spike phù hợp. Base weights frozen, adapter trained; batch/sequence/image resolution/quantization/gradient checkpointing chọn từ hardware, không hứa VRAM trước đo.
5. Checkpoint chọn trên dev, lưu seeds/config/code commit/library versions/model/tokenizer/processor revisions. Không chọn bằng train loss duy nhất.
6. Run bounded cycles: baseline, run #1, run #2 targeted. Cycle #3 chỉ khi hypothesis mới có evidence; không quét hyperparameter vô hạn.
7. Export weights/adapter + manifest; inference script chạy sample, hash output và verify schema.
8. Model registry lifecycle `CANDIDATE → VERIFIED → ACTIVE → RETIRED`. Activation sau regression/eval gate, rollback release pointer khi có regression. Không tự deploy trong training script.

Các metric trong design là mục tiêu/chọn phương pháp, không phải kết quả. Model card report measured model size/config, latency/VRAM/hardware và limitations khi implementation hoàn thành.

## 7. Evidence và confidence

Evidence mapping match raw extracted text với OCR blocks, resolve bằng label/context/geometry. Không chỉ chọn occurrence đầu tiên khi số tiền lặp. Nhiều candidate khó phân biệt → issue; không tự sửa giá trị nguồn bằng arithmetic.

Field confidence là khả năng value đúng theo definition đã chọn. Features có thể gồm OCR score vùng, evidence ambiguity, schema/semantic validity, model score nếu adapter có meaningful score. Fit calibrator trên dev-calibration bằng correctness labels, report Brier/ECE/coverage-error khi đủ sample.

Không dùng model tự viết `confidence:0.99` làm probability. Với field/type quá ít support, confidence null và explicit flags. Phần confidence của MVP phải có workflow review và báo cáo calibration; null fallback là limitation chứ không khẳng định đã có xác suất đáng tin.

## 8. Metric definitions

| Metric | Định nghĩa/ý nghĩa |
|---|---|
| JSON validity | Raw output parse và schema pass trước human correction; không che bằng repair |
| Field exact match | Gold/pred sau cùng normalization; giữ dấu; denominator annotated fields |
| Field precision/recall/F1 | Present gold/pred value matching; sai value tính FP và FN; báo absent handling riêng |
| Critical total/date EM | Per-type critical fields; không để nullable/absent chiếm metric |
| Missing/false-fill rate | Present field bị null / absent field bị model điền sai |
| Table row matching | Match rows bằng gold descriptions/values theo policy, báo exact-row accuracy và unmatched/duplicate rows |
| Cell accuracy | So field từng matched row; qty/unit price/total riêng; row reorder không penalty nếu semantic order không required |
| Evidence accuracy | Bbox overlap/text association khi gold regions có; coverage và ambiguous cases |
| OCR CER/WER | Trên visible transcription có gold; không dùng QA đáp án như toàn bộ transcription |
| Document pass rate | Tất cả annotated business fields và items đúng; rất nghiêm, báo support |
| Review correction rate | Số field/row user sửa; usability metric, không model truth nếu chưa có gold |

Không strip dấu tiếng Việt để tăng metric chính. Có thể report relaxed case/whitespace score song song, ghi rule rõ. Date/money ambiguity không silently convert khác convention. Failure jobs tính trong end-to-end denominator, không drop outlier để accuracy đẹp.

## 9. Experiment matrix

E0 B0 baseline; E1 M0 pretrained extraction; E2 M1 fine-tuned; E3 M1 with/without OCR context nếu model hỗ trợ; E4 same model gold OCR vs predicted OCR trên subset có transcription; E5 familiar-layout vs unseen-layout + independent mock; E6 confidence/review prioritization.

Không yêu cầu tất cả combinations hoặc train lại mọi variant. Một variable chính mỗi so sánh, cùng schema/normalizer/test profile. Public QA benchmark được report riêng, không gộp vào invoice JSON metric.

## 10. Gate chất lượng đề xuất

Khóa tiêu chí sau baseline W4, trước mở final test; target sau đây để lập kế hoạch, không đảm bảo đạt:

- Raw JSON validity ≥98% trên profile hợp lệ.
- Present scalar normalized EM mục tiêu ≥85% mỗi type; total amount EM mục tiêu ≥95%.
- Matched row cell accuracy mục tiêu ≥85%; exact row accuracy ≥75%; báo unmatched rows và duplicate rows.
- Fine-tuned score không thấp hơn baseline cho critical totals trên dev; nếu không tốt hơn phải giải thích error/cost và tiêu chí fine-tune còn chưa đạt.
- Bố cục mới và independent mock report riêng, không đạt aggregate nhờ các template dễ.
- Confidence threshold chỉ được dùng khi holdout validation cho thấy error/coverage; không autoapprove.
- UI/retry/concurrency/export invariants bắt buộc pass bất kể model quality.

Final holdout target 200–400 base documents tổng hai types, cân bằng layout/quality/missing/table slices; có support từng slice. Small samples report counts/intervals, không tuyên bố độ chính xác doanh nghiệp production.

## 11. Handoff artifacts

Dataset manifest/data card, generator seed/version, split IDs/hash, model manifest/model card, evaluator version, sample errors, per-type tables, hardware/time/memory, code commit, locked env và commands đã thực thi. Raw dataset/model binaries không commit Git; git lưu manifests/tiny fictional fixtures.
