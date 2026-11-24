# AI2 — Hai đợt giao việc đến nghiệm thu

**Bản mở rộng v2.** Cuối đợt 1 cần có model feasibility thật, loader/collator dùng pilot Data, checkpoint tiny/pilot reload được, dev comparison và HTTP handoff cho Backend. Đợt 2 hoàn tất training candidate, confidence policy, final report và service release. Dùng các gói chi tiết bên dưới, gửi từng output sớm để Data và Backend làm song song.

Bản này gộp việc tiếp từ roadmap và review đã đóng. #3/#83 đã merge; **HTTP Python native chưa được nghiệm thu**. PR #83 được merge ngày 19/11 nhưng phần native acceptance vẫn được hoãn. Cần chạy và bổ sung evidence native mới trước khi đóng milestone; không coi merge hoặc fixture HTTP pass là native acceptance. AI2 sở hữu extraction/model adapter/training/confidence/serving. Model OCR pretrained và preprocessing do AI1 giữ, muốn fine-tune recognizer OCR phải chốt thêm loại nhãn/crops và scope.

**Chốt nhiệm vụ ngày 22/11/2026 theo người dùng:** model extraction dùng **Qwen/Qwen3-1.7B + PEFT LoRA/QLoRA** (cập nhật model ngày 23/11/2026), nhận **OCR text/layout → business JSON**. OCR text/layout do AI1 tạo; gold của Data là target. Serialization phải nêu rõ text, block IDs, thứ tự đọc và tọa độ/context nào được đưa vào model. Cấu hình cụ thể và exact revision cần pin trong A1-A; không tự chọn lại model family. Đầu vào này là yêu cầu hiện hành cho gói việc, thay mô tả ảnh + instruction trong tài liệu model cũ ở điểm modality.

## Kế hoạch triển khai chi tiết đợt 1

### A1-A — Kiểm kê và chốt đúng nhiệm vụ model

1. Đọc lại model constraints và roadmap M1–M6. Triển khai extractor Qwen nhận OCR text/layout→JSON theo chốt nhiệm vụ trên; ghi rõ đây là training extractor. OCR recognition training là scope khác, chỉ làm khi có quyết định riêng. Thống nhất serialization input/target với Data/AI1 trước chạy.
2. Kiểm công việc local/Colab/Drive đã có. Gửi code/notebook SHA, tên model/revision/license, dataset members/splits/hashes, checkpoint/config/seed, log và replay command. Reviewer dùng để nhận phần đã làm, tránh làm lại.
3. Giữ Qwen + LoRA/QLoRA đã chọn; pin exact model revision/license và chọn cấu hình khả thi về quantization, token budget, batch size, adapter parameters. Báo phương án giảm tài nguyên trong cùng model đã chọn, kèm permission cần, VRAM/RAM/container/disk hiện tại và vị trí lưu checkpoint. Nếu cần đổi model family, trình Lead/người dùng quyết định riêng.
4. Lead #55 nhận scope/provision. Ngay khi đủ quyền và artifacts, chuyển A1-B, đồng thời gửi Data target contract và Backend runtime packet A1-E.

**Output** là một model/task/resource decision sheet có owner và pins. Proposal không thay evidence train-step. Các con số máy cũ phải đo lại hoặc gắn nhãn lịch sử.

### A1-B — Actual G0 trên model định dùng

Vị trí logic ở `src/vietdoc/ml/` theo SPEC hiện có, frameworks giữ ngoài contracts.

1. Audit tải model/config/tokenizer và dependencies theo quyền đã cấp. Pin artifact hashes, không bật remote code tùy tiện. Ghi env training riêng với serving/OCR.
2. Infer receipt/invoice tiny, giữ raw output, parsed output và typed failure. Input dài/rows nhiều/context overflow có outcome explicit.
3. Tạo batch thực với target, finite loss, backward, gradient hữu hạn và ít nhất một parameter update. Báo memory/time thực, batch/precision/config và lỗi OOM nếu có.
4. Save checkpoint gồm weights/adapters/config, tokenizer/processor và training state cần resume. Run manifest bắt buộc pin Data membership/hash, adapter/target-serialization version và OCR engine/model/profile/cache hashes đã tạo input. Reload vào process sạch rồi inference cùng input. Nếu dùng LoRA phải reload base đúng revision và adapter đúng run.
5. So output trước/sau reload theo cấu hình deterministic đã ghi, báo tolerance khi có yếu tố nondeterministic. Checkpoint corrupt/missing/config mismatch phải fail rõ.

**Output** là runnable entrypoint, exact command, env/model hashes, log G0 và reload report. **Đạt khi** Qwen đã thực infer→update→save/reload với OCR text/layout, không chỉ CUDA/torch import hoặc toy model. Khi bị OOM, gửi profile đo được và điều chỉnh config theo quyết định Lead; đổi model family cần quyết định riêng.

### A1-C — Training reader, serialization, collator và masks

1. Nhận Data adapter/status fixture #36. Extractor Qwen nhận OCR text/layout từ engine/profile AI1 đã pin, cùng preprocessing và serialization dùng lúc inference. AI1 bàn giao train/dev OCR cache gắn ID/hash/status, Data giữ gold làm target. Transcript gold chỉ dùng cho oracle hoặc ablation được ghi riêng, không báo quality như luồng OCR thật. Xác định đơn vị record và input gồm OCR text/layout/context nào; kiểm decoded input thực sự giữ geometry đã khai báo. Nếu thiếu geometry, báo thiếu input hoặc giới hạn, không tự coi text-only là đã đáp ứng layout. Thay modality cần quyết định riêng và contract input mới với Data/AI1 trước training.
2. Reader verify manifest/hash/type/schema/split trước yield. Giữ sample/base/group IDs cho trace. Dev và train không được lấy lẫn qua glob thư mục.
3. Chốt supervision: present có target, absent theo policy, obscured/unlabeled phải mask hoặc loại sample khỏi full-JSON target khi không có cơ chế mask đúng. Ghi cách encode missing vs null.
4. Inspect decoded inputs/targets và tensors cho cả hai type, nhiều rows, Unicode, repeated amounts, missing fields và dài gần cap. Kiểm padding/attention mask/loss ignore và giữ train/infer preprocessing giống nhau.
5. Test invalid labels/pointer, empty/corrupt input, wrong type/schema, truncation và target overflow. Nếu full rows không vừa context, outcome có lý do và support/exclusion, không silent drop.
6. Data nhận target/mask mapping và phản hồi lỗi gold bằng ID/path. Khi pilot thật đến, chạy cùng reader, báo actual counts/exclusions và batch thật.

**Output** là source dataset/collator/config, model-specific batch examples và consumer ACK của Data. Chưa có actual model thì phần model-specific còn pending, vẫn chuẩn bị record/status tests được.

### A1-D — Tiny overfit và pilot đầu tiên

1. Chọn tiny train subset có nhãn phù hợp, chạy sanity overfit để kiểm target mapping/gradient/reload. Báo train sanity riêng, không gọi đó là dev accuracy.
2. Nhận grouped train/dev pilot và evaluator từ Data. Kiểm membership overlap, version pins và số base độc lập mỗi type/slice trước training.
3. Chạy B0, M0 và M1 trên cùng dev IDs, normalizer và evaluator. Ghi JSON validity, critical totals, scalar/items, missing/false-fill, failures, latency và memory.
4. Chọn checkpoint theo criterion trên dev đã chốt. Lưu run manifest gồm Data/adapter/OCR input pins và per-sample predictions để Data chấm lại. Triển khai model adapter parse decimal strings/null/items, typed error/abstain cho malformed JSON/overflow ngay với checkpoint pilot, giữ inference transformation khớp training. Nếu chưa vượt B0, ghi gaps và failure taxonomy, vẫn giữ evidence pipeline train được.
5. Thử resume sau ngắt run bằng checkpoint, optimizer/scheduler/RNG cần thiết và báo epoch/step. Với Colab, kiểm checkpoint đã thật sự lên storage trước session hết. Không coi file checkpoint tồn tại là resume/reload đã đạt.

**Output** là pilot run/checkpoint/dev report, replay và resume evidence. Đây là phần triển khai của đợt 1 khi Data pilot/resource đủ, không để toàn bộ training dồn sang đợt 2.

### A1-E — Runtime v1 và consumer v2 bàn giao sớm

Vị trí chính ở `pipeline/service.py`, `pipeline/composition.py`, `entrypoints/api/`, `pipeline/extraction/ocr_consumer.py` và attempt writer.

1. Tái dùng source HTTP v1 từ #83 và gửi Backend fixture packet sẵn có, ghi rõ native acceptance chưa đạt. Khi có native env/model release được cấp, chạy mới OCR thật → B0 qua HTTP; bàn giao request/response/errors/artifacts có hashes cùng lệnh dựng và replay. Gắn evidence với exact code/release; kiểm lại khi changes chạm luồng này và chỉ ghi đã nghiệm thu sau khi consumer/Lead xác nhận.
2. Chạy #23 mixed/whitespace/all-unreadable/no-detection và repeated scoped/unscoped values. Giữ missing/ambiguity/source IDs và provenance đúng, không OCR-score→confidence.
3. Nối runtime v2 opt-in theo contract được nhận cùng AI1. Giao actual response v2 cho Backend, nhận ACK parse/viewer/blocker trước quyết định default. Không đòi AI1 default v2 trước mới viết consumer.
4. Đưa checkpoint pilot qua cùng HTTP compute path, có release manifest/hash, verify/load/readiness và clean-process reload. Gửi Backend một packet receipt/invoice, lấy ACK receipt đi xuyên Java; B0 vẫn dùng để mở software integration sớm. Không để việc nối trained model đầu tiên sang đợt 2.
5. Guard readiness/capacity/attempt identity, busy/deadline/input hash, output invalid và write failure. Model load/cancel/close không làm service success khi artifacts dở. Gửi Backend code/status/retry mapping cần dùng.

**Output** là runtime packet v1/v2 opt-in, pilot release/hash và actual HTTP/Java receipt evidence. **Đạt khi** Backend tự gọi được, clean process reload checkpoint pilot, lifecycle/error guards có tests và consumer ACK ghi rõ provider/release version.

**Chốt đợt 1** khi model G0/reader/pilot có bằng chứng đúng scope, Backend tự gọi được runtime packet và pilot checkpoint, hai consumer biết partial semantics và Data tái chấm được dev predictions. Mỗi thiếu input phải có ID/artifact/owner, không chỉ ghi đợi Data.

## Kế hoạch triển khai chi tiết đợt 2

### A2-A — Full run và một vòng cải thiện có đối chứng

1. Nhận dataset v1 train/dev đã QA, giữ final cách ly. Dùng config/resource từ pilot, pin mọi artifacts và train command.
2. Lưu checkpoint theo dev criterion. Report per-type/slice, không lấy average che critical-total regression hoặc mất rows.
3. Phân tích errors theo OCR/gold/extractor/parser/normalization/table. Gửi AI1/Data repro bằng ID và expected/actual, chọn một giả thuyết chính để run tiếp.
4. So candidate trên cùng IDs/evaluator/preprocess hoặc ghi rõ version thay đổi và chạy lại baseline. Nếu model vẫn không đạt, Lead nhận quality gap và quyết định scope, không tự bỏ milestone roadmap.

**Output** là run/checkpoint manifests, dev predictions/comparison và failure packet cho từng owner. **Đạt khi** run reload/resume được, split/profile pins đúng, candidate được chọn bằng dev criterion và quality gap có quyết định cụ thể, không lấy số train làm dev.

### A2-B — Confidence và serving model

1. Chốt correctness labels/calibration population với Data, fit ngoài final và ghi support theo type/slice. Không đủ support giữ null/flags, trình Lead policy và hạn chế.
2. Model adapter phải parse đúng decimal strings/null/items, không bịa field/source/confidence khi output lỗi. Typed errors/abstain cho overflow/malformed JSON và unsupported release.
3. Đóng gói tokenizer/processor/weights/config/normalizer/preprocess/model license và manifest hashes. Readiness chỉ ready khi release đã verify/load và slot dùng được.
4. Test cold/warm/reload/close, missing/corrupt release, OOM/permanent failure và busy/timeout. Đo latency/RSS/VRAM trên máy dùng thực, không thay bằng số toy model.

**Output** là release package nâng từ pilot, calibration report hoặc null/flags policy có support và runtime test log. **Đạt khi** fresh process verify/load/infer được, malformed output không thành business success và unsupported/corrupt release fail explicit. Parser/HTTP foundation đã làm ở đợt 1, đợt này harden candidate cuối.

### A2-C — Partial rollout và actual Java integration

Sau fixture và opt-in ACK, Lead #63 chốt rollout, AI1 #64 nhận default. Chạy lại hai type v1 lịch sử/v2 mới, scoped evidence và missing required với viewer/server. Backend kiểm byte promotion và fence, AI2 giữ attempt-scoped artifacts và error budget. Cùng ghi mismatch trước khi freeze candidate.

**Output** là matrix receipt/invoice×v1/v2, consumer ACK và rollout/rollback evidence. **Đạt khi** giữ readable evidence, missing required vẫn bị server chặn, lịch sử v1 đọc đúng và job cũ không bị mutate khi đổi default.

### A2-D — Freeze, final và bàn giao

1. Data #54/Lead #53 pin protocol, split và evaluator trước mở final. AI2 #59 pin checkpoint/release/config/code sau chọn trên dev, gồm Data membership/adapter và OCR engine/profile/cache versions, ghi hashes và known limitations. Giao runner noninteractive đã thử trên dev để Data chạy final trên host được cấp, AI2 không cần truy cập final để chạy hộ.
2. Data #61 chạy final, gửi report để AI2 #62 model card. Không chọn lại model bằng final errors âm thầm. Thay đổi sau freeze phải tạo candidate mới và xử lý protocol/contamination rõ.
3. Nhờ người khác chạy clean inference và checkpoint reload với artifact được cấp. Handoff gồm runtime/hardware/setup, request/output examples, model/data/license/provenance, metrics/support/latency, failure modes và rollback candidate.

Mỗi gói source đi kèm regression cho hành vi đã đổi. Chia commit theo model/G0, dataset-masks, train/checkpoint, dev comparison, runtime-v2, confidence/release, mỗi phần chỉ commit khi có implementation/evidence phù hợp. Không tạo các lớp placeholder chỉ để đủ mốc.

**Output** là frozen candidate, Data final report, model card và clean-replay report. **Đạt khi** sai base revision/adapter/manifest/profile bị reject, Data tái chấm được, người nhận reload được và ledger #23/#51/#52/#55–#59/#62 đối chiếu source/evidence, các mục liên quan #53/#54/#63 ghi đúng owner. Không close quality acceptance chỉ từ HTTP xanh.

## Cách triển khai và nộp review

Các entrypoint hiện có dùng từ repo root với env serving/test đã pin. Model-specific training/reload entrypoint là phần phải implement trong A1-B/A1-D, cần nộp command thật sau khi có source, không viết command chưa tồn tại để claim đã chạy.

```powershell
$env:PYTHONPATH='src'
python -m scripts.ci.ai
python -m scripts.ci.lint
python -m pip check
```

Windows chỉ dùng skip symlink flag đã có theo đúng policy khi môi trường cần, ghi rõ skip. Core fixture tests và actual model/native checks có scope riêng trong report. Model/data weights không đưa vào commit.

- Bắt đầu từ develop mới nhất, đọc task/review cũ và giữ unrelated changes. Source ngoài snapshot ngày 22/11 cần đối chiếu trước khi sửa.
- Mỗi increment trên có thể là một commit hoặc vài commit theo hành vi. Fix và regression đi cùng, không ép mỗi task thành một PR hoặc tách commit rỗng.
- Gửi output mở việc cho consumer ngay khi đạt. Ghi người nhận, artifact path/version/hash, lệnh verify và kết quả ACK hoặc case lỗi.
- PR ghi Issue refs, base/head, acceptance→source/test/evidence, commands/env, PASS/FAIL/SKIP/NOT_RUN và limitations. CI phải chạy candidate tích hợp. Lead duyệt/merge, sau đó consumer smoke develop trước Done.
- Blocked ghi đúng bước nào cần owner nào đưa artifact gì, phần còn làm độc lập và checkpoint đang có. Không đóng cả role chỉ từ một PR đã merge.
- Cuối đợt 1 nộp ledger từng increment. Phần thiếu có owner/acceptance rõ chuyển vào đợt 2 hoặc Lead nhận thay đổi scope công khai. Hai đợt là hai gói giao có kiểm ở giữa, không bảo đảm đúng hai lượt review sẽ hết lỗi.
