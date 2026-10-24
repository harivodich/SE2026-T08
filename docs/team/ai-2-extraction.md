# AI Engineer 2 — Extraction model và fine-tuning

Bạn phụ trách model trích xuất và fine-tune, nhận image/OCR context và trả receipt/invoice business payload. Model feasibility bắt đầu ngay tuần 1–2; baseline làm song song để đo cải thiện và tích hợp sớm. Bạn cũng sở hữu training input, model adapter, normalization và confidence; Backend giữ runtime IDs, DB, revisions/approval.

## Baseline dùng chung schema, làm song song model spike M1

1. Review business/extraction contracts cùng Backend/AI-1. Các key theo [schema](../../specs/contracts/business.schema.json); mọi key hiện diện, giá trị string/null, items giữ quan hệ từng dòng.
2. Dùng vài OCR fixtures đúng contract để làm baseline trước khi OCR engine hoàn tất; sau đó chạy lại với output thật trên bộ 20 mẫu của Data.
3. Viết rules dựa label/text/geometry: tìm total/date/merchant/seller/buyer và nhóm row/cells. Không hard-code tọa độ một template duy nhất hoặc chọn số lớn nhất làm total.
4. Normalize tiền/ngày/quantity có locale rõ, giữ raw value. Không tìm thấy/mơ hồ thì null + issue; không suy ra field nguồn không ghi.
5. Tách structural invalid output và semantic warning. Payload parser có giới hạn, không dùng eval hoặc vòng LLM repair vô hạn.
6. Bàn giao adapter, output theo schema, error list theo sample/field/row và baseline report bằng evaluator của Data.

Xong khi hai types có cùng contract ổn định, Backend nhận được result thật, baseline có measured errors và missing handling rõ. API job/run IDs hoặc UUID row IDs không do model tự sinh.

## Model spike trước khi fine-tune

1. Ghi hardware có thật: GPU/VRAM hoặc CPU, RAM, disk và thời gian chạy được phép. Chọn một model phù hợp để thử, review license và input/output format.
2. Load/infer trên 20 samples; chạy một train step để đo memory, latency và JSON validity. Model name chưa là cam kết chất lượng.
3. So pretrained model với baseline trên cùng inputs/evaluator. Nếu image/OCR context vượt budget, có chính sách rõ; không truncate mất rows âm thầm.
4. Báo Lead phương án chạy được/cost/limitations. Chốt model/tokenizer/processor revision, image resolution, context budget và inference settings trước full training.

Model lớn không khả thi thì thử extractor nhỏ/OCR-text model bằng evidence, giữ scope và fine-tune objective. Paid API không là phương án mặc định của dự án.

## Fine-tune extraction

1. Đọc dataset manifest/splits do Data tạo; kiểm schema/version/hash và label coverage.
2. Xây training input từ type, instruction/schema, image và OCR context theo selected architecture. Target là business JSON; unlabeled fields không dùng như absent gold.
3. Fine-tune, dùng LoRA/PEFT nếu candidate/spike phù hợp. Config ghi seed, batch, learning rate, image/token budget, epochs/steps và checkpoint rules.
4. Chọn checkpoint bằng dev metrics; report loss và business errors. Final holdout chỉ dùng theo protocol của Lead/Data.
5. Có vòng sửa theo nguyên nhân: OCR sai, mapping sai, table grouping, missing hoặc JSON parse. Giữ experiment count bounded; mỗi vòng có hypothesis và dev comparison.
6. Export adapter/weights + tokenizer/processor/config + immutable manifest; gọi inference bằng cùng preprocessing đã eval.

## Normalization, evidence và confidence

- Bạn sở hữu normalization và extraction scoring; AI-1 sở hữu source geometry/evidence matching. Khi cần feature mới cho mapper, thống nhất contract, không cùng sửa file riêng của nhau.
- Dùng dữ liệu dev-calibration tách phù hợp để fit confidence theo correctness labels. Field/type thiếu support thì confidence null + flags.
- Không lấy model tự nói `0.99` hoặc OCR score làm xác suất đúng. Report coverage/error/calibration khi đủ mẫu; không autoapprove.
- Bạn sở hữu `pipeline/service.py` và Python ai-service ở M2.3; AI-1 review geometry/stage order. Backend viết Java HTTP client/runner/completion. Python không ghi business DB hoặc import approval logic.

## Code và bàn giao

| Nơi | Nội dung |
|---|---|
| `src/vietdoc/pipeline/extraction/` | Rule/model adapter và prompt templates |
| `src/vietdoc/pipeline/normalization.py`, `confidence.py` | Pure normalization/calibration helpers |
| `src/vietdoc/ml/` | Training dataset, train/loading và release manifest |
| `src/vietdoc/ml/configs/` | Versioned experiment configs |
| `src/vietdoc/entrypoints/api/`, `pipeline/service.py`, `infrastructure/storage/` | Private compute server/stage wiring/attempt artifacts (M2.3) |
| `artifacts/models/` | Weights local, ignored |

Bàn giao mỗi candidate: adapter/checkpoint location an toàn, manifest/hash, schema/model/OCR/normalizer versions, exact config/command, sample outputs/errors, dev comparison và measured memory/latency. Data chạy evaluator/final holdout độc lập; Backend pin release ID cho job.

Ví dụ chung: `3` → quantity `"3"`, `15.000` → unit_price `"15000"`, `45.000` → line_total và total_amount nếu nguồn ghi cả hai. Arithmetic chỉ giúp phát hiện warning, không tạo tax/discount hay đổi số trên ảnh.

## Cách dùng tài liệu và reviewer

Đọc [SPEC trong vùng phụ trách](../../src/vietdoc/ml/SPEC.md) và SPEC.md trong folder con định sửa; [workflow chung](workflow.md), [Git Flow](../git-flow.md) giữ cách bàn giao. Plan này chưa phải toàn bộ task đã giao; mỗi lần Lead giao subtask, ghi issue/PR/evidence ở đó, không folder tasks. Mã hướng dẫn không phải issue ID thật.

Thứ tự: M1.1 → M1.2 → M1.3; M2.1/M2.2 baseline nhỏ và M2.3 serving W2–3. Dành thêm4–8h W2–3 cho M2.3, giảm baseline polish/calibration trước khi cắt fine-tune pilot; không chờ UI mới training. Reviewer: AI-1 review image/OCR compatibility; Data review labels/eval; Backend review inference integration; Lead duyệt model/gates. Giữ một task coding chính đang làm, bàn giao increment nhỏ; không chờ hoàn tất cả vai trò mới tích hợp.

## Roadmap cá nhân theo tuần

Tuần tính từ kickoff. Kết quả dưới là mục tiêu cần tạo/kiểm chứng, chưa phải tính năng hiện đã chạy. Capacity giả định IC 12–16 giờ/tuần, Lead 4–8 giờ/tuần; model/hardware/profile chốt G0. W13–16 là buffer, không tự mở scope.

| Tuần | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 1 | M1: hardware/license/input; M2: baseline skeleton | Hardware/model/license proposal |
| 2 | M1 infer/train-step; M2.1 baseline nhỏ; M2.3 serving shape | G0 feasibility + protocol/health |
| 3 | M2.3 serving/wiring; M2.2 parser; M3 loader | Private HTTP actual OCR/B0 + training loader |
| 4 | M3: fine-tune pilot, kiểm overfit tiny train set | Fine-tune pilot/checkpoint/dev comparison |
| 5 | M4: full run #1 trên train, chọn bằng dev | Full run #1/manifests/dev errors |
| 6 | M4: run #2 theo lỗi #1; normalization | Run #2 theo hypothesis/normalization |
| 7 | M5: calibration, missing/false-fill analysis | Calibrator/support/missing analysis |
| 8 | M5–M6: candidate manifest, inference adapter freeze | Candidate release manifest/inference freeze |
| 9 | M4–M6: cải thiện cuối trên dev nếu có hypothesis | Improvement cuối có evidence hoặc gap |
| 10 | M6: model card/artifacts/hashes và chất lượng cuối | Final model card/versions/hashes |
| 11 | M6: tái chạy train subset, inference manifest | Inference + train subset reproduction |
| 12 | Hỗ trợ demo, chốt limitations | Handoff artifact location/report/limitations |
| 13–16 | Cải thiện có protocol test mới nếu test đã bị dùng để tune | Cải thiện theo test protocol mới nếu holdout đã dùng tune |

## Task chi tiết: input, bước làm, output và nghiệm thu

Folder: `src/vietdoc/pipeline/extraction/`, `normalization.py`, `confidence.py`, `ml/`; weights/checkpoints ở ignored `artifacts/models/`. B0 là OCR+rules, M0 pretrained extractor, M1 fine-tuned extractor; cả ba cùng business schema. AI-2 owns model tensor/token preprocessing, không giao phần đó sang AI-1 chỉ vì tên có chữ preprocessing.

### M1.1 — hardware, license và model proposal, tuần 1

Dependency và effort dự kiến: L1.1 + D1 fake samples/hardware; 3–4h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: hardware thực tế, schema, vài D1 fake samples.

1. Ghi GPU/VRAM/RAM/disk/OS/runtime, thời gian được dùng và privacy/cost constraints.
2. Chọn một candidate khả thi cho schema/items, kiểm official model card/license/input format và dependencies; tên model trong thiết kế là candidate, không cam kết chất lượng.
3. Định nghĩa input: selected type/schema instruction và image/OCR context tùy candidate, target JSON business payload, raw output riêng parsed result.
4. Đề xuất image/token budget, precision/tuning method để smoke, dựa hardware; không hứa model lớn train được trước đo.

Nộp: model/resource proposal và pinned revisions dự định thử. Xong khi Lead hiểu candidate/cost/license/risk; chưa coi là model đã chạy.

### M1.2 — load và inference smoke, tuần 1–2

Dependency và effort dự kiến: M1.1 + model access; 4–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Audit dependencies/serialization/remote code trust trước tải/chạy theo quyền task implementation; không thực thi text từ document như instructions.
2. Load đúng model/tokenizer/processor/chat format, pin revisions/config; giữ model frameworks ngoài contracts.
3. Chạy integration samples, lưu raw output và parsed payload/issues. Nếu dùng gold transcript để smoke, ghi rõ, không so như production OCR accuracy.
4. Đo cold load/warm latency/memory/JSON validity/errors. Context overflow phải explicit, không silent drop rows.

Nộp: model adapter prototype, raw/parsed actual outputs, hardware/runtime report. Xong khi Backend/Data dùng được artifact/output và failures rõ; Java public API không load weights; Python ai-service load có lifecycle/readiness.

### M1.3 — một train step thực và G0, tuần 2

Dependency và effort dự kiến: M1.2 + full-label tiny gold; 4–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Dùng tiny full-label gold batch, kiểm input/target tokens/images, collator và loss mask phù hợp model.
2. Chạy forward/backward/update, kiểm gradients ở parameters intended và state checkpoint thực.
3. Đo peak memory/train-step time; OOM thì giảm budgets/batch hoặc candidate theo evidence, không retry vô hạn.
4. Lead xác nhận candidate/config feasible trước full training; không dùng train loss một batch để claim accuracy.

Nộp: train-step code/config/command/report và candidate decision. Xong G0 khi train thực khả thi trong hardware/quyền cho phép; nếu không, có blocker/alternative rõ.

### M2.1 — rules baseline hai schemas, tuần 1–3

Dependency và effort dự kiến: B1.1/O1 fixture rồi O1.3; 6–10h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: OCR contract/fixture trước, O1 OCR thật sau, D1 gold.

1. Tìm fields bằng labels/context/geometry, không largest-number heuristic hoặc một tọa độ template hard-code.
2. Group description/quantity/unit/price/line_total theo row, giữ wrap/empty cells; không collapse cả table thành một string.
3. Key luôn theo schema; missing/ambiguous value null + issue. Mỗi số có role/evidence context, không tự tính ra tax/discount nguồn không ghi.
4. Dùng M2.2 normalizer chung, test scalar/items/unknown labels/repeated amounts. Bàn giao adapter early để Backend làm E2E.
5. Chạy D3 B0 report trên OCR thật; fixture chỉ wiring/tests, không benchmark.

Nộp: `rule_baseline.py`, tests, outputs/report. Xong khi Backend gọi adapter, Data chấm được; baseline vừa đủ không lấn hết thời gian fine-tune.

### M2.2 — parser, schema và normalization, tuần 2–4

Dependency và effort dự kiến: M1.2/M2.1/B1.1; 4–8h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Parse raw output an toàn với size/depth/token limits, không eval hoặc repair loop vô hạn; raw JSON validity report trước repair/human edits.
2. Validate type/schema/keys/rows; model không sinh UUID runtime. Invalid shape và missing business value là outcomes khác nhau.
3. Chuyển raw tiền/ngày/quantity theo locale sang canonical strings, giữ raw; ambiguity không normalize đoán.
4. Test `45.000`→`"45000"`, absent/null, decimal quantity, dates invalid/ambiguous, units và table boundaries. Monetary convention phải version, không float.
5. Reuse normalizer trong baseline/model/evaluator theo policy; review validation nghiệp vụ khi save/approve vẫn thuộc Backend.

Nộp: parser/normalizer/tests/policy/version. Xong khi B0/M0 trả cùng contract, bad output không thành silently successful payload.

### M2.3 — Private Python compute service và pipeline wiring, tuần 2–3

Dependency/input: B1.2/O1.2/O1.3/M2.1/M2.2; [compute protocol](../../specs/contracts/compute-api.md). Effort4–8h cho slice đầu, timeout isolation tiếp tục M6.1. Reviewer AI-1/Backend, Lead boundary.

1. Implement Python request/result/error adapters, cùng Java valid/invalid fixtures; IDs do Java cấp, model chỉ business payload.
2. FastAPI private multipart endpoint/health/service auth/body/hash/schema limits; no public business API/DB credentials.
3. Compose preprocess→OCR→extract→normalize→evidence/confidence trong pipeline/service.py, reuse AI-1 adapters, không viết lại OCR.
4. Model/OCR lifecycle giữ process, semaphore concurrency1/busy503/Retry-After; không blocking compute trực tiếp trên async event loop, không multiworkers mỗi worker một GPU model.
5. Attempt volume private: canonical/OCR/transform artifacts, key/hash/size/dimensions; không arbitrary URL/path/overwrite attempt, không write originals/exports.
6. Remaining budget kiểm từng stage; typed timeout/OOM/invalid errors. Async cancel không đảm bảo dừng CUDA; spike subprocess/restart isolation, slot giữ đến cleanup thật.
7. Test type/version/hash/manifest/auth/busy/oversize/response limits, actual OCR+baseline HTTP smoke trước G1. Fixture chỉ test wiring.
8. Gửi Backend endpoint/config/health/commands/hardware/actual response/assets/provenance. Java quyết completion/fence; Python không callback DB.

Nộp: runnable private server/pipeline/storage adapter, tests và actual HTTP evidence.

Xong khi Java client gọi actual provider, response correlation/assets đúng, second request không tạo unbounded queue.

### M3.1 — training dataset và model preprocessing, tuần 3

Dependency và effort dự kiến: D2.1/D2.2 pilot subset + G0; 6–10h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: D2 v0.1 manifest/splits/gold, candidate đã G0.

1. Verify IDs/hash/schema/split/label statuses; không tự resplit random theo ảnh.
2. Build model examples từ type/instruction/image/OCR order/coords; Data gold chuyển target JSON, không metadata/runtime IDs.
3. Viết tokenizer/processor/collator/loss masking theo selected model; padding/user prompt không vô tình chiếm loss objective.
4. Kiểm context/image budgets và trường/rows bị truncate; loại hoặc handle explicit. Training/inference transformations phải khớp.
5. Partial unlabeled không train thành absent/null; chỉ dùng separate supported supervision policy hoặc loại khỏi full-JSON training.
6. Inspect vài decoded input/target và batch thật, Data/AI-1 review label/image compatibility.

Nộp: training loader/config/tests và decoded batch examples. Xong khi target khớp gold, split không leak, batch đưa train step được.

### M3.2 — sanity overfit và fine-tune pilot, tuần 3–4

Dependency và effort dự kiến: M1.3/M3.1/D3.1; 6–10h active + GPU time đo. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Chọn tiny train subset có full labels, overfit để kiểm gradients/target masking/JSON learning; đây là training sanity, không evaluation.
2. Chạy pilot trên train subset lớn hơn theo capacity, LoRA/PEFT nếu G0 phù hợp; log seeds/config/code/data/model revisions.
3. Save/checkpoint/reload, inference dùng đúng adapter/processor/settings; không chỉ nhìn loss giảm.
4. Chấm dev khác train bằng D3, B0/M0/M1 cùng normalizer/evaluator; report fields/items/missing/errors/memory/time.

Nộp: runnable train code, pilot checkpoint/config/manifest/dev report. Xong G1 khi training path/reload thật tái lập và limitation rõ; chưa hứa final targets.

### M4.1 — full run #1, tuần 5

Dependency và effort dự kiến: D2.2/M3.2/L2.2; 4–8h active + GPU time. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Nhận dataset v1/frozen train/dev/test grouping, final không mở.
2. Chạy config chọn từ pilot/resource evidence, checkpoint theo dev metrics; track loss/JSON/field/table errors và failure rate.
3. Ghi immutable run manifest/code/environment/seed/data/model/OCR/preprocess/evaluator versions.
4. Chọn checkpoint bằng dev business metrics, report critical totals và table unmatched/duplicates, không train loss duy nhất.

Nộp: run #1 artifacts/manifests/dev predictions/report. Xong khi Data tái chấm được cùng checkpoint, no final tuning, candidate có known gaps.

### M4.2 — error analysis và run #2, tuần 6–9

Dependency và effort dự kiến: M4.1/D3.2; 6–12h active, bounded cycles. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Gom dev errors theo OCR/gold/extractor/JSON/table/missing/normalization; có sample IDs và raw vs gold, không chỉ score.
2. Gold lỗi → Data; OCR/geometry lỗi → AI-1; mapping/training lỗi → bạn. Không sửa gold cho khớp prediction.
3. Diagnostic gold OCR vs predicted OCR trên subset có transcript, ghi riêng khỏi runtime benchmark.
4. Chọn một hypothesis chính cho run #2, so cùng evaluator/dataset/preprocess. Critical total không được regression bị giấu trong aggregate.
5. Cycle #3 chỉ với evidence mới; sau ba vòng không giảm lỗi Lead reassess data/model/hardware.

Nộp: error taxonomy/hypothesis, run #2/config/dev comparison, candidate selection reason. Xong khi measured improvement hoặc unresolved gap rõ; không tune final holdout.

### M5.1 — confidence và missing handling, tuần 6–8

Dependency và effort dự kiến: D3.2/O4.1; 4–8h hoặc null fallback. Refine sau smoke; đây không là SLA/deadline đã cam kết.

Input: dev-calibration correctness labels D3, O4 evidence/ambiguity/score features.

1. Define field correctness label/features cùng Data/AI-1; fit on calibration partition theo protocol, không final.
2. Report support/Brier/ECE/coverage-error phù hợp; ít support thì confidence null/method/flags, không copy OCR/model tự nói 0.99.
3. Test absent/obscured/ambiguous/repeated values; không tự fill missing hay autoapprove.
4. Backend hiển thị review priority/limitations, approval rules vẫn server/human review.

Nộp: calibrator/config/tests/report hoặc explicit null fallback limitation. Xong khi confidence có evidence/traceability hoặc unavailable rõ, consumer không hiểu score thô là xác suất đúng.

### M6.1 — inference release và handoff, tuần 8–12

Dependency và effort dự kiến: M2.3/M4/M5/O5.1/D5.1 protocol; 8–12h. Refine sau smoke; đây không là SLA/deadline đã cam kết.

1. Export checkpoint/adapter+tokenizer/processor/settings/normalizer/calibrator và immutable manifest/hashes.
2. Cùng Backend test Python ai-service lifecycle/private HTTP/timeout/busy/invalid/OOM và Java pin release; training script không activate production.
3. W10 nhận final report Data theo protocol, viết model card quality/hardware/memory/latency/license/synthetic-to-real gaps.
4. W11 người khác chạy inference và train reproduction subset từ commands/config thực; note nondeterminism/environment deviations nếu có.
5. Candidate verified/active/rollback theo Lead gate, giữ jobs cũ pinned; no remote latest runtime, weights không Git.

Nộp: release artifact pack/model card/reproduction report. Xong khi adapter consumer smoke pass, versions/hash khớp và thiếu target được ghi, không claim chỉ prompt/rules là fine-tune hoàn tất.

## Git Flow cho AI-2 — Extraction/Fine-tuning

1. Nhận một subtask/acceptance từ Lead; tạo hoặc dùng issue thật, branch feature/bug từ develop theo [Git Flow](../git-flow.md). Không push trực tiếp main/develop.
2. Sửa đúng ownership ở trên; shared contract/lockfile/migration cần báo owner/consumer trước. Không stage datasets/weights/secrets/runtime hoặc unrelated edits.
3. Chạy focused checks thật, inspect diff, ghi command/config/versions/input-output mẫu và limitations. Chưa có check executable thì ghi phần chưa xác minh; không tự báo CI pass.
4. PR đích develop, peer reviewer theo mục reviewer, Lead duyệt cuối. Tác giả không tự approve; đổi logic/contract sau approval cần review lại.
5. Conflict: tác giả đọc cả hai thay đổi cùng consumer, merge origin/develop vào branch đã chia sẻ, không force-push hoặc chọn ours/theirs toàn file. Chạy lại checks sau resolve.
6. Sau merge, consumer smoke trên develop; issue ghi evidence rồi mới Done. Release main/hotfix theo quy trình riêng, không suy ra quyền deploy từ task.

Một PR giải quyết một kết quả nhỏ; các outputs lớn ở local ignored, chỉ manifests an toàn/tiny fictional fixtures/reports đã review được đưa Git.

## Checklist bàn giao

- Code/output thực, input/output đúng contract và version/manifest rõ.
- Consumer chạy được sample, tests/report/commands thực và failed cases có sample IDs.
- Không raw dataset/weights/secrets/PII/runtime trong diff; không hard-coded demo output thay inference.
- Peer review/Lead review nội dung cuối, post-merge smoke và limitations đã ghi.
- Gate/quality targets dùng [workflow chung](workflow.md), không tự đổi ngưỡng sau mở final test.
