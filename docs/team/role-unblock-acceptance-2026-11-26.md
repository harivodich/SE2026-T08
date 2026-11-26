# Gỡ phụ thuộc giữa các role — kết quả 26/11/2026

PR nền: [AI2 #92](https://github.com/harivodich/SE2026-T08/pull/92), head
`95648361ffc24c72efd16898994d85ee4ca7c786`, CI PR run `45674964555` thành công.
PR hỗ trợ dùng branch `fix/v1-role-unblock`, xây trên cùng head này. Lead review
và merge #92 trước rồi PR hỗ trợ bằng **Create a merge commit**; không tự merge.
CI của bản hỗ trợ phải kiểm trên head cuối, không lấy kết quả #92 thay thế.

## Đã thực hiện, không phải kế hoạch

| Ranh giới | Evidence thực | Phạm vi kết luận |
|---|---|---|
| Data → AI1/AI2 | Pilot 40 base/160 variants, 960 assets; canonical rerender và fresh-root archive receiver đạt | Inputs train/dev thật, không có final |
| Group/split | AI kiểm 40 ảnh clean, đối chiếu nội dung/seed/assignment, 410 cặp screened có witnesses; reviewed plan train80/dev80, không quarantine | Đề xuất nhận grouping cho Lead review PR; không giả human sign-off |
| AI1 → AI2 | Native attempted160, ok160, failed0/not_run0; 144 complete,12 partial,4 unreadable; bridge xuất train80/dev80 | OCR/geometry/reader cache có pins; không phải accuracy/model acceptance |
| Token/profile | D22 profile cũ: eligible train38/40,dev36/40 vừa; profile7168/7936/1536/9472:80/80 eligible vừa | Tokenizer thật, không load weights, chưa GPU-fit hoặc quality |
| Python partial consumer | Controlled OCR + real HTTP/decode/extract/artifact/validation suite đạt; native HTTP3/3 gồm receipt/invoice partial | Partial transport/producer behavior có kiểm thực; defaultv1 không đổi |
| Python → Java | Response của3 native calls thành fixture `tests/contract/native-compute-v2.json`, Java contract9/9 đạt | Cross-language envelope/geometry/IDs/issue scope; không claim live PG |
| Review/approve | Workflow20/20, AiClient10/10: readable fields giữ nguyên; warning toàn chứng từ giữ qua sửa field; thiếu total vẫn block | Java business policy không bị bypass bởi OCR partial |

Các suite Python liên quan đã chạy gồm132 tests trước review,133 sau sửa đầu,
30 tests cuối cho adapter/HTTP/parity và141 tests Qwen/composition; có overlap,
không cộng thành số test duy nhất. Data67 methods đạt, readiness8 methods được
kiểm lại sau sửa imports/context. Ruff các file mới và diff-check đạt.

Independent review bằng GPT-6.1 Sol high qua worker_runner tìm2 finding thật:
locale normalizer đổi decimal canonical và mixed document/field issue bị mất.
Đã sửa, thêm unit+HTTP decimal regression và Java workflow mixed-scope regression.
Controller bổ sung parity check toàn inference-config fingerprint đã sanitize
execution flags; model/tokenizer/schema/prompt/base pins riêng vẫn bắt buộc.
Không gọi cùng checkpoint với config/budget khác là train/inference parity.

## Inputs bất biến và cách phân biệt các gói

Manifest pilot SHA256:
`99a66a13f555892b61abb93272b582a042d26947bd0af45210ee50ad2319619d`.

1. **Data packet**: `pilot-inputs.zip`, 142675606 bytes,
   SHA256 `284fb0604d8df15eb2b70e1cad12eb2fa23e29be7be02223469bd41acb1b03c1`;
   `transfer.json` SHA256 `bb28e3c4070350af9a297cc58fbfbbb71b3f2d0285790ba12cd9d292711126d9`.
   Giữ nguyên review/plan pending ở snapshot gốc; không sửa lịch sử producer.
2. **AI2 nhẹ**: `pilot-ai2-inputs.tar.gz`,1232113 bytes,
   SHA256 `6e7ff1b0ed9426bbeb76a0e5653c1404484a20a17b42b029f3814ce9c2153744`.
   Có OCR train/dev, records/gold/labels/manifest, pins, tokenizer receipts và
   config token-only. Không chứa raw PNG/PDF hoặc model weights. Full asset
   verification nằm trong receipt producer/native bridge; muốn verify lại raw
   assets phải lấy Data packet đầy đủ, không dùng gói nhẹ với receiver đầy đủ.
3. **Native evidence**: `pilot-native-evidence.tar.gz`,292989445 bytes,
   SHA256 `4c8de673d14633c00ed2c12bdf9c27e5a21414ab7a1f61f36e1ce97b95f22c00`.
   Có canonical/processed/overlay/preview/OCR/prepared/run/report, không weights.
4. **Review supplement**: các manifest `datasets/manifests/pilot-20261126-*`;
   `pilot-pair-evidence.json` và5 contact sheets ở gói ngoài Git. Hash của pair
   evidence được pin trong `pilot-20261126-review-evidence-index.json`.

Archive/hash đã kiểm lại sau download local. Source dùng cho native được đóng
trong archive và pin riêng; các sửa model consumer về sau không được gọi là đã
chạy native nếu không cùng owning OCR/source hashes. Model base/adapter D22 cũ
ở gói artifacts AI2 đã gửi trước, không được đổi manifest cũ để ép hash khớp.

## Những điều vẫn phải nghiệm thu thật

- **AI2 model quality chưa đạt**: M0/M1 D22 raw serving0/16; checkpoint/loss/CI
  không thay kết quả này. Không autoactivate model, B0/v1 vẫn default.
- Nhãn full-JSON đủ80/160 (train40/dev40);80 mẫu obscured có accounting, không
  biến thành absent/null targets. Toàn bộ160 vẫn cần hiện diện trong evaluation.
- Native OCR có15 empty và4 all-unreadable inputs. Model prompt từ chối rõ
  `OCR_EMPTY`/`OCR_UNREADABLE`; AI2 cần hoàn thiện abstention/error semantics,
  không bỏ IDs để báo thành công. Đây không phải thiếu đầu vào từ Data/AI1.
- Profile token mới vừa population này, không bảo đảm mọi chứng từ30 hàng hoặc
  GPU12GB vừa. AI2 phải đo memory/latency/training/generation trước release.
- Live Java→PostgreSQL→candidate model E2E và frozen final benchmark phải chạy
  với accepted candidate; fixture/native B0 không chứng minh model mới đạt.
  Ba role còn lại có thể hoàn thành implementation/test runner ngay với inputs
  đã cung cấp, không phải chờ AI2 viết API hoặc gửi thêm mapping.

## Files giao việc hiện hành

- [AI2](ai2-v1-completion-2026-11-26.md): chất lượng, capacity thực, checkpoint,
  serving candidate và release acceptance; nhận thêm pilot nhẹ và reviewed plan.
- [Data](data-v1-final-work-2026-11-26.md): QA/evaluator/protocol automation.
- [AI1](ai1-v1-final-work-2026-11-26.md): OCR/preprocess/geometry/evidence/native release.
- [Backend/Web](backend-web-v1-final-work-2026-11-26.md): PG/security/UI/export/E2E/release runner.

Các file là nhiệm vụ tiếp theo có đối chiếu regression cũ, không phải chỉ chép
review cũ. Hoàn thành code độc lập không tự đóng gate chất lượng/final release.
