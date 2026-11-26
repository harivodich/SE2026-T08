# Handoff và dependency hiện hành — 26/11/2026

PR88/89/90/91 đã merge. Base đối chiếu là develop `594336013dbc122326169a7c7e6df09e1d9d22c6`. Các bảng blocker ngày 24/11 là lịch sử; không dùng trạng thái “chưa train/chưa có OCR D22” hoặc token profile cũ để giao lại việc.

Lượt D22 đã có native OCR train48/dev16; train 24 eligible samples một epoch/6 optimizer steps, checkpoint/reload; so B0/M0/M1 trên đủ 16 dev variants. Model vẫn chưa được nghiệm thu: raw serving contract nhận 0/16 ở cả M0/M1. Xem [báo cáo đo](AI-2/2026-11-26-model-dev-acceptance.md) và [task AI2](ai2-v1-completion-2026-11-26.md).

## Ai có thể làm ngay, ai cần chờ đầu vào nào

| Role | Làm ngay | Cạnh còn phụ thuộc | Packet/evidence cần nhận |
|---|---|---|---|
| AI2 | Sửa raw schema/duplicates/semantic table/abstention, target/mask checks, lifecycle/error tests, interface serving trên D22 | Quality run lớn hơn cần Data → AI1; E2E cuối cần Backend | Data pilot đã QA/grouping/labels + OCR cache đúng IDs/hash; suite/config E2E |
| Data | Phát hành pilot, QA/duplicate/group/split, evaluator oracles, protocol runner; re-score prediction D22 đã có | Final custodian chờ AI2 candidate frozen và policy/quyền chạy đã khóa | Manifest model/config/source/hash, inference command, candidate predictions/final protocol |
| AI1 | Dev OCR/geometry/stress/preprocess comparison và fixtures partial; D22 OCR64 đã có không làm lại vô ích | OCR pilot mới cần Data; acceptance partial-v2/default cần ACK AI2 + Backend thực | Pilot archive/membership; receipt reader/partial consumer; approval/warning tests Backend |
| Backend/Web | B0 native E2E, PostgreSQL/CAS/fencing, security/viewer/browser, release/rollback tooling | Actual E2E opt-in model cần AI2 verified serving candidate | Service interface/config/manifest/errors; model-enabled service đúng candidate |

Không role nào phải ngồi chờ AI2 hoàn tất toàn bộ V1 mới bắt đầu. Tuy vậy vẫn có các gate tích hợp cần output thật của nhau; không thể hứa mọi người hoàn thành độc lập mà không cần trao packet/ACK.

## Thứ tự trao packet nhỏ

1. **AI2 → Data/AI1/Backend ngay:** receipt D22 với IDs/hashes/accounting; consumer tests v1/v2 và partial-state scope; interface/config/error fixtures cho Backend. Những thứ này làm trước model-quality run mới.
2. **Data → AI1/AI2:** pilot archive immutable + inventory/hash; grouping/splits/base/variants/statuses; exact exclusions và evaluator oracle. Working target hiện tại là 40 base/160 variants theo kế hoạch; không gọi D22 16 train+dev bases là đã đủ pilot này.
3. **AI1 → AI2:** verify inputs rồi xuất native OCR train/dev cùng IDs, canonical/engine/profile pins và full accounting; không mở final để tune. OCR pilot chặn run mới, không chặn AI2 sửa P1 trên D22.
4. **Backend → AI2:** suite/lệnh actual-provider, config không secrets, expected errors và acceptance partial warnings/approval. Triển khai và thử client/failure cases sớm, không đợi chất lượng model mới trao contract.
5. **AI2 → Data/Backend sau dev selection:** frozen candidate + verified serving profile để độc lập re-score và chạy actual model E2E. Chỉ mở final sau freeze và policy; không dùng final để chọn epoch/prompt/model.

## Capacity gửi Data và AI1

- Model `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; text/layout, không nhận ảnh.
- Profile D22 thực đo: OCR **6.784**, input **7.424**, output **1.280**, sequence **8.704** tokens; serializer `vietdoc_ocr_context_v2`, prompt `qwen3-business-json.v3`.
- Profile `3072/4096/2048/6144` trong tài liệu 24/11 là mốc cũ, không dùng thay profile run này.
- Schema có `maxItems=30` không bảo đảm mọi trang 30 hàng vừa token budget. Capacity audit phải chạy trên population thật, báo IDs/rows/token lengths, không âm thầm truncate hoặc drop.
- M1 đã có một output chạm 1.280 tokens và bị cắt; trước khi tăng budget phải phân tích repetition/EOS/schema và đo lại resource/parity.

## Phân biệt ba loại ACK

**Reader/cache ACK**: đúng IDs, schema/hash/status/geometry đã kiểm, consumer đọc được. D22 đã có evidence cho phạm vi này.

**Partial-runtime ACK**: actual consumer giữ readable blocks và error regions, không tự fill, required fields thiếu vẫn chặn approve; phải có AI2 và Backend evidence riêng trước default migration. Cache đọc được không tự đóng ACK này.

**Model/release acceptance**: quality, capacity, candidate freeze, actual E2E, final protocol và rollback. Không lấy hai ACK đầu hoặc CI xanh để thay acceptance cuối.

## Tin nhắn nhóm chung

PR88–91 đã merge. Mọi người tiếp tục phần độc lập, không chờ model xong toàn bộ. Data ưu tiên gửi pilot đã QA và manifest/group/split; AI1 nhận pilot rồi xuất OCR đúng IDs/hash, đồng thời làm dev/stress/geometry trên dữ liệu hiện có. AI2 nhận bản training/eval hỗ trợ, sửa schema/logic, trả sớm reader/partial ACK và interface/error fixtures cho Backend. Backend/Web làm B0 native, PG/security/browser và trao suite/config E2E cho AI2. Chỉ phần quality run lớn, actual opt-in model E2E và final freeze mới cần các packet tương ứng; báo đúng file/hash còn thiếu khi để Blocked.
