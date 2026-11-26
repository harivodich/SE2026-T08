# AI2 — hoàn thiện model và tích hợp đến nghiệm thu V1

Ngày bắt đầu lượt nghiệm thu: 25/11/2026; công việc tiếp tục qua ngày 26/11. Đây là phần việc tiếp theo, thay cho các yêu cầu G0 cũ đã được thực hiện; không yêu cầu làm lại phần đã có bằng chứng. Kết quả dev đo trong lượt hiện tại được ghi ở `AI-2/2026-11-26-model-dev-acceptance.md` cùng thư mục khi hoàn tất.

## Ưu tiên ngay sau khi nhận file

**Chưa promote M1.** Lượt host đã hoàn tất: M0 raw-schema 0/16, normalized 6/16; M1 raw-schema 0/16, normalized 4/16. Replay qua `QwenInference` hiện hành nhận 0/16 ở cả hai model. Scalar M1 17/48 so M0 15/48 nhưng table end-to-end giảm 37/112 → 13/112; total không cải thiện (đều 3/8). Một output M1 bị cắt ở 1.280 tokens. 363 tests đạt chỉ xác nhận implementation, không thay quality acceptance.

Làm nhóm B trước C: đọc raw outputs và `scalar-errors.csv`, sửa schema/duplicate keys/canonical format, header-as-item/quantity-price mapping, abstention/evidence trên crop/unreadable. Kiểm decoded targets/masks và tiny-train generation trước khi chọn một hypothesis cho run #2. Không bỏ strict gate hoặc tăng epoch/budget vô điều kiện. Case cụ thể, IDs và acceptance chi tiết ở `AI-2/2026-11-26-model-dev-acceptance.md`. Nhóm D/E và tests có thể làm song song theo ownership trong khi chờ packet Data lớn hơn; không để tất cả việc dừng theo dataset.

## 1. Phần đã có để nhận và dùng ngay

- Model: `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; đầu vào OCR text/layout, không nhận ảnh trực tiếp.
- OCR native: 48 mẫu train, 16 mẫu dev. Train có 24 mẫu đủ nhãn full-JSON; 24 mẫu obscured được loại có thống kê, không biến obscured/unlabeled thành absent. Dev giữ đủ 16 mẫu khi đánh giá.
- G0/full D22 một epoch đã chạy: 24/24 mẫu eligible, mỗi mẫu một lần, 6 optimizer steps. Checkpoint adapter-only và reload process mới đạt. Đây là kiểm chứng đường chạy, chưa chứng minh chất lượng V1.
- Dùng serializer `vietdoc_ocr_context_v2` chung train/inference. Ngân sách đã chạy: OCR 6.784 tokens; input 7.424; output 1.280; sequence 8.704. Giữ toàn bộ OCR text, không cắt hàng hay âm thầm bỏ mẫu dài.
- Archive training: `full-d22-finetune-evidence.tar.gz` trong gói artifacts gửi kèm; SHA-256 `3a3db9ae71f08af2610e783aadd0afc6c702c1f34dac8665d94c553d2718d9fc`.
- Run manifest SHA-256 `5888ddf148d1f74c99b9968b68a66059ba6dc4e107cd217ef2a0019de9a1e907`; checkpoint manifest SHA-256 `eb8ceaec95985c26951c00cc4fe1b69b8d7efded0b1765a0ba629550b8cce268`.
- Source hỗ trợ training/evaluation nằm trong branch bàn giao cùng tài liệu này; chưa tự vào develop trước merge. Nếu branch chưa merge, tạo branch cá nhân từ branch bàn giao để bắt đầu ngay; sau merge đồng bộ develop. Không nhận weights/raw dataset vào Git.
- Lượt nghiệm thu phục hồi base từ đúng immutable upstream revision sau khi thư mục host cũ đã dọn. Nếu envelope provisioning khác, dùng proof `base-reprovision.json` có hash đi kèm để xác minh tất cả bytes upstream; giữ nguyên training manifest hash cũ. Không tự đổi pin để chạy qua lỗi. Proof chỉ dành cho snapshot cụ thể, cần tạo lại khi tái provision có metadata khác.

## 2. Thứ tự thực hiện và ranh giới

Nếu branch bàn giao đã merge, tạo branch riêng từ develop mới nhất. Nếu chưa merge, tạo branch cá nhân từ `origin/fix/ai2-v1-training-evaluation`; không chờ merge để đọc report, sửa logic hoặc chạy tests. Patch trong packet là cách nhận thay thế cho máy đang ở develop; không áp lại patch nếu đã branch từ source bàn giao. Patch cố ý không mang các thay đổi cũ của `pipeline/ocr/handoff.py` hoặc Backend để giữ code mới đã merge. Giữ một PR cho một increment có thể nghiệm thu. Mỗi nhóm dưới đây là một hoặc vài commit có logic/test hoàn chỉnh; không chia commit hình thức để tăng số lượng. PR trỏ develop, người phụ trách không tự merge.

Không chờ Data/AI1 hoàn tất toàn bộ V1 để làm phần độc lập: dùng ngay D22/OCR đã pin để xây reader, error analysis, lifecycle, API adapter, tests, release validator và rollback. Dataset lớn hơn chỉ là đầu vào thay thế đã version hóa. Chất lượng cuối và holdout cuối vẫn cần dữ liệu/evidence thật; không đóng các mục này bằng fixture.

### A — Nhận source và tái lập baseline

1. So branch/HEAD với develop, kiểm diff và file mới của training/evaluation. Giữ nguyên code mới của các role khác. Chỉ giải conflict theo hành vi và schema, không chọn ours/theirs toàn file.
2. Chạy bộ ML tests, contract tests và bộ test artifact runner. Kiểm test chạy được trên checkout sạch, không tham chiếu đường dẫn `D:/SE/output` từ test được commit.
3. Kiểm config/model/tokenizer/schema/OCR/evaluator hashes với run manifest. Base hoặc adapter khác revision phải fail trước load.
4. Chạy lại B0 trên native dev bằng CLI bàn giao và đối chiếu per-sample outputs/denominators. M0/M1 chỉ chạy khi môi trường/model đúng pin; không thay dependency/model âm thầm.

**Đạt:** checkout sạch chạy tests; có run manifest và report tái lập; thiếu artifact được báo tên/hash cụ thể. Commit đề xuất: tiếp nhận training/eval support + kiểm tái lập.

### B — Phân tích lỗi trước khi train thêm

1. Đọc toàn bộ lỗi dev theo từng `sample_id`, loại chứng từ, biến thể, base/family. Tách lỗi OCR, nhãn, mapping, normalization, malformed/truncated JSON, thiếu/thừa dòng, sai tổng, timeout/OOM/context.
2. Với mỗi lỗi, ghi OCR quan sát được, giá trị model, nhãn được phép chấm, nguyên nhân có bằng chứng và cách kiểm chứng giả thuyết. Không lấy OCR/model predictions làm gold.
3. Kiểm các lỗi lịch sử: tiền khách đưa bị hiểu thành tổng; header bảng thành item; unit không có trong OCR bị tự điền; amount lặp gắn sai trường; receipt không có item; zero-value total; invoice thiếu thuế/chiết khấu; crop/unreadable; tiền và số lượng dạng decimal strings; input chứa câu lệnh giả trong OCR.
4. Mẫu có OCR sai có thể làm diagnostic bằng transcript chuẩn trên một tập riêng, ghi nhãn rõ. Không thay transcript chuẩn vào benchmark native OCR rồi báo chất lượng runtime.
5. Viết regression tests cho lỗi logic sửa được. Lỗi model phải có dev case và tiêu chí so sánh, không hard-code output theo ID của mẫu.

**Đạt:** bảng lỗi có phân loại và ưu tiên; sửa semantic/parser/evidence logic có test. Không kết luận fine-tune hữu ích chỉ từ training loss. Commit đề xuất: error taxonomy/regression fixtures; sửa từng cụm lỗi cùng test.

### C — Pilot và lựa chọn checkpoint bằng dev

1. Giữ D22 làm smoke/regression; dữ liệu này nhỏ và có các biến thể cùng base, không coi 16 mẫu dev là 16 chứng từ độc lập.
2. Nhận pilot Data theo yêu cầu đã giao: archive/manifest immutable; membership train/dev/final theo base/source/template; đủ nhãn/status và duplicate/grouping decisions. Kiểm actual coverage thay vì chỉ kiểm tên file. Mốc pilot 40 base/160 variants là kế hoạch dữ liệu, không phải evidence đã có.
3. Nhận OCR bundle đúng membership và canonical/engine/profile hashes. Adapter tự xác minh inputs, không phụ thuộc người khác trả lời từng mẫu.
4. Đo token toàn bộ population trước GPU allocation. Có accounting cho bất kỳ sample không đủ supervision. Không cắt text/rows để làm report xanh. Thay budget/model phải tạo config/run mới và đánh giá lại train/inference parity.
5. Chọn một giả thuyết có cơ sở cho run tiếp: cấu hình LoRA/số epoch/cách biểu diễn/độ phủ dữ liệu. Seed, optimizer, scheduler, dtype, package/model/tokenizer/OCR/schema/evaluator/source hashes phải có trong manifest.
6. Giới hạn số vòng thử. Chọn checkpoint bằng dev scalar/table/critical-total metrics và failure rate; so B0/M0/M1 trên cùng input và evaluator. Không chọn chỉ bằng loss thấp nhất. Sau ba vòng không tiến bộ phải báo nguyên nhân và phương án, không tiếp tục tiêu GPU vô hạn.
7. Nếu cần resume đúng giữa chừng, lưu và khôi phục optimizer/scheduler/scaler/RNG/sampler position; checkpoint hiện tại chỉ đã nghiệm thu adapter reload. Không gọi metadata optimizer là exact resume.

**Đạt:** pilot đủ evidence, có report so sánh và quyết định chọn/loại candidate có lý do. Chưa đạt thì giữ B0/manual review; không tự giảm ngưỡng để gọi đạt. Commit đề xuất: pilot config/run manifest; error-driven run #2; checkpoint-selection report.

### D — Evidence và confidence trung thực

1. Output model chỉ là business payload. Mọi bbox/evidence phải bind về OCR/canonical đã xác minh; không cho model tự tạo bbox hoặc confidence rồi xem là bằng chứng.
2. Không tìm được evidence hoặc nhiều vị trí không phân biệt được: trả null/unavailable/ambiguity flags theo contract. Không chọn vị trí đầu tiên cho mọi amount giống nhau.
3. Test đầy đủ tiền lặp, merchant/seller nhiều dòng, item description trùng, evidence ở crop, geometry unavailable, OCR partial failures và trường bắt buộc thiếu.
4. Khi chưa đủ support calibration, confidence = null kèm method/flags. Không copy OCR score thành xác suất field đúng. Nếu fit calibrator: chỉ dùng partition calibration đã chốt, report support/Brier/ECE/coverage-error và không dùng final để fit.

**Đạt:** downstream không hiểu nhầm confidence; không có evidence bịa; required-field blockers vẫn chặn approve. Commit đề xuất: evidence binding/ambiguity; confidence fallback hoặc calibrator có report.

### E — Model adapter thật trong private compute service

1. Giữ opt-in rõ ràng: B0 là fallback/default khi candidate chưa được nghiệm thu. Không bật model chỉ vì có weights trên đĩa.
2. Load base + adapter đúng manifest; không tải ngầm khi startup/request. Verify file path/hash/schema/revision/serialization trước readiness; thiếu/hỏng/mismatch phải not-ready với mã lỗi ổn định.
3. Lifecycle: load/warm-up/ready/busy/draining/close; capacity một GPU slot. Request busy trả 503/Retry-After theo contract; không chạy song song thêm instance để né admission.
4. Inference ngoài Java DB transaction, giữ attempt correlation/deadline và artifact boundaries. Python không ghi business DB/callback business state. Không để model trong Java process.
5. Kiểm timeout/token-limit/OOM/invalid output/cancel cleanup; giải phóng model/adapter/optimizer references đúng. Hủy job không đồng nghĩa GPU kernel dừng tức thì; stale/cancelled/expired attempt không được commit kết quả.
6. Không sửa shared schemas âm thầm. Nếu cần contract đổi, đề xuất diff và consumer tests trước.

**Đạt:** HTTP thật gọi model thật, hai loại receipt/invoice; lifecycle/failure tests và peak memory/latency được đo; không bypass readiness. Commit đề xuất: verified adapter lifecycle; serving selection; admission/error tests.

### F — Tích hợp và đóng V1

1. Chạy actual path Java → PostgreSQL job/lease → private Python OCR+extractor → verified canonical assets → revision/review → approve/export. Ít nhất receipt và invoice; không dùng fixture để thay inference ở lượt nghiệm thu.
2. Chạy thêm busy/retry, lost response, stale attempt, cancel, rerun khi đã có head, invalid schema, hash mismatch, CAS conflict và export revision cũ. Không cần tự viết lại tests Backend đã có; nhận lệnh/runnable suite và ghi kết quả đúng snapshot ghép.
3. Đóng gói release candidate với base/adapter/tokenizer/config/preprocess/schema/evaluator/dataset/source hashes, known limits, điều kiện phần cứng, startup commands và rollback. Hash weights nhưng không commit weights.
4. Candidate freeze trước final holdout. Data/custodian chấm final theo policy đã khóa; AI2 nhận report, không chỉnh prompt/config theo final. Nếu dùng final để tune phải công bố hỏng holdout và lập version/protocol mới.
5. V1 quality targets trong `docs/team/workflow.md` hiện là đề xuất cần chốt trước final: raw JSON ≥98%; present scalar normalized EM ≥85% mỗi type; total EM ≥95% mỗi type; matched-row cell accuracy ≥85% kèm unmatched/duplicate; exact-row accuracy ≥75%; critical-total dev không thấp hơn B0. Không báo đạt nếu chưa có denominator/report hoặc policy chưa được xác nhận.
6. Rollback phải đổi lại đúng model/config/pipeline manifest đã biết tốt và chạy smoke; không chỉ ghi câu “có thể rollback”. Không autoapprove document khi model đạt quality.

**Đạt cuối:** candidate đã frozen; quality/failure/capacity/integration reports có thể chạy lại; model card ghi rõ synthetic/generalization limits; rollback kiểm được; không còn finding bắt buộc; người review xác nhận snapshot. Chưa có final/quality evidence thì giữ trạng thái chưa nghiệm thu V1.

## 3. Packet yêu cầu khi cần phối hợp

Gửi một lần theo packet, không hỏi lẻ từng biến:

| Nguồn | Cần nhận | AI2 kiểm ngay | Có thể làm trong lúc chờ |
|---|---|---|---|
| Data | pilot archive + manifest hashes, split/group/duplicate policy, label statuses, evaluator/report mẫu | IDs/type/hash/coverage/group leakage, schema và denominator | B/D/E và tests trên D22; sửa error taxonomy |
| AI1 | bundle native OCR đủ membership, canonical assets + engine/profile/config/source pins | input hash, dimensions, correlation, order/geometry, diagnostics | adapter/lifecycle/failure tests; B0/M0/M1 trên bundle đã có |
| Backend | suite/lệnh actual-provider E2E và private service config mẫu không secrets | request/response contract, lease/fence/cancel/retry, promote assets | Python adapter và negative tests; không cần chờ UI mới train |
| Lead | snapshot được review, metric policy/final custodian/host authority | không đổi ngưỡng sau mở final; không publish trước duyệt | hoàn thiện candidate packet và rollback trước final |

Pilot Data và OCR tương ứng là dependency **trước quality run mở rộng**, không chỉ trước nghiệm thu cuối. Frozen candidate/policy/final report là dependency của gate cuối. Chúng không chặn sửa P1, tests và lifecycle trên D22 hiện có. Khi một packet thiếu, ghi đúng file/hash/consumer check còn thiếu và phần việc độc lập đang làm.

### Bàn giao ngược sớm để ba role không phải đợi AI2 làm xong V1

1. **Cho Data ngay khi nhận packet:** trả receipt/ACK với exact IDs, manifest/archive/index hashes, counts đã đọc, label-status checks, exclusions và token measurements theo population. D22 đã có run/report; dùng lại evidence đúng pin, không yêu cầu gửi lại G0. Data có thể dùng prediction packet B0/M0/M1 hiện tại để thử re-score ngay, dù model chưa đạt quality. Final evaluation vẫn chờ candidate frozen.
2. **Cho AI1 trước đợt fine-tune tiếp theo:** chạy consumer tests `complete/partial/all-unreadable/no-detection`, unknown version và invalid geometry/provenance; trả ACK ghi rõ artifact version/engine/profile và trường hợp nào đã chạy thật. Tách ACK reader/OCR cache đã có evidence khỏi ACK serving/partial semantics còn cần kiểm. Không ký thay Backend hoặc gọi test reader là toàn bộ acceptance partial-v2/default migration.
3. **Cho Backend/Web sớm:** gửi opt-in extractor interface/config, pipeline/model manifest draft có version/hash, error fixtures và lệnh chạy service. Ghi readiness/capacity, busy/timeout/cancel/OOM, warning/required-field behavior. Backend dựng client/UI/fault tests trước; không đợi model đạt quality mới trao interface.
4. **Nhận lại Backend ACK:** correlation/schema/error mapping, partial warnings và server-side approval blockers. Sau đó mới đề xuất default migration nếu đúng phạm vi đã được Lead nhận. Actual model E2E và model quality vẫn là hai evidence riêng, không thay bằng fixtures.

Các ACK phải do đúng consumer kiểm và trả bằng chứng, không tự đánh dấu Accepted cho role khác. Việc còn chưa có quality pilot không phải lý do trì hoãn bốn handoff nhỏ này.

## 4. Nội dung PR và bàn giao bắt buộc

Mỗi PR ghi requirement/task hoàn thành, before/after, model/data/source pins, tests đã chạy và skip có lý do, per-type/per-condition reports, known limits, cách chạy lại. Link artifacts thay vì đưa raw dataset/weights vào Git. Tiến độ Project: đang làm → In progress; đã có candidate chờ review → In review; chỉ Done sau merge và kiểm post-merge theo quy trình nhóm.

Không claim: một epoch là model tốt; 16 variants là 16 independent documents; JSON hợp lệ là extraction đúng; 342 tests là quality score; offline metrics là HTTP/E2E pass; AI review thay actual runtime hoặc bằng chứng còn thiếu.
