# AI1 — phần việc còn lại đến V1

Đây là nhiệm vụ tiếp theo sau các PR AI1 đã merge, có đầu vào pilot/OCR và
consumer seam được Lead chuẩn bị. Không phải làm lại UUID, D22 native smoke hoặc
finetune extraction model. AI1 sở hữu preprocess/OCR/geometry/evidence; AI2 sở
hữu extraction model, training và serving chất lượng model.

## Đầu vào và giới hạn

- Pilot `v0.2-pilot-20261126`: 40 base/160 variants, train/dev, 8 families, 4
  variants/base, 0/1/3/12/30 hàng. Nhận archive/transfer và hash từ gói chung.
- Đã có native OCR của population này, prepared/canonical/observed OCR, source
  input/engine/profile pins và reader receipts. Đọc kết quả trước khi chạy lại.
- OCR artifact v2 là opt-in. B0/v1 vẫn là default. Python HTTP consumer tests và
  Java partial-warning/approval tests được cung cấp; không dùng ACK fixture để
  kết luận native OCR accuracy hoặc default migration đã được duyệt.
- D22 trước đây là exposed smoke, không phải final. Không mở final để chọn OCR
  profile. Không dùng OCR score thay field correctness.

## O1 — Nhận inputs và phân tích lỗi có hệ thống

1. Verify archive/manifest/sample/canonical/engine/profile pins. So đủ 160 IDs với
   report, giữ failed/not_run/partial/unreadable/no-detection trong accounting.
2. Tạo bảng lỗi per-type, base/family, variant, row count: detection thiếu/thừa,
   recognition, Vietnamese marks, orientation/skew, line order, geometry, crop,
   timeout, memory. Mỗi lỗi có sample ID và evidence path, không chỉ screenshot.
3. Tách OCR thiếu vùng với model mapping sai. OCR chưa thấy không chứng minh
   field absent; không tự điền transcript/gold vào output nhận dạng.
4. Prioritize lỗi làm mất tổng, sai chữ số, mất hàng, evidence gắn nhầm vùng;
   chọn một giả thuyết sửa trước benchmark, không thử vô hạn nhiều model.

**Đạt:** report có denominator, cases tái hiện và lựa chọn xử lý; không chạy lại
train hoặc làm model extraction. Commit diagnostic tooling/fixtures có nghĩa.

## O2 — Đóng preprocess và geometry

1. Test PNG/JPEG/PDF một trang theo scope, alpha/EXIF/ICC/grayscale, portrait/
   landscape/skew, resize/padding/crop, file giả/truncated, pixel/byte limits.
2. Giữ canonical viewer frame khác processed OCR frame. Transform/inverse phải
   round-trip trong tolerance của contract; geometry unavailable phải explicit,
   không vẽ quad suy đoán. Test edges, projective points, non-convex/NaN/outside.
3. Xác minh canonical PNG/pixels/hash/dimensions của cùng run; không dùng ảnh
   processed như canonical vì nhìn gần giống.
4. Timeout/exception phải đóng images/temp handles; invalid inputs reject trước
   gọi native engine. Test failure đúng stage và không để artifacts thành valid.

**Đạt:** geometric regression và resource-bound tests; kiểm trên ảnh thật trong
gói đã có, không chỉ toy identity transform. Commit từng cụm preprocess/geometry.

## O3 — Native OCR quality và partial contract

1. So B0 profile hiện tại với một cấu hình sửa có lý do trên exposed dev; giữ
   engine/model/dtype/threads/hardware/dependency/source pins và same membership.
2. Đo OCR CER/WER/region recall theo evaluator/annotation support thực; báo cases
   không đủ transcript/quad labels, không lấy gold business JSON làm transcript.
3. Partial OCR phải giữ readable blocks + unreadable regions/reasons. All-unreadable
   và no detections là hai trạng thái khác nhau; không biến một phần lỗi thành
   trang OCR rỗng hoặc tự fill field.
4. Run tests producer/reader/HTTP trên v1, v2 complete/partial/all-unreadable/
   no-detection, unknown version, bad geometry/hash/provenance. Fixture receipt
   phải ghi scope fixture; native receipt phải chỉ đúng provider calls thật.
5. Default migration chỉ đề xuất sau acceptance có thật của consumer và Lead.
   Không tự đổi default, không đồng nghĩa merge opt-in là đã bật toàn hệ thống.

**Đạt:** report so sánh/giữ hoặc loại profile có evidence; v2 tương thích consumer,
v1 không regression. Commit profile/test/report metadata, không commit weights.

## O4 — Evidence binding và viewer packet

1. Kiểm raw match qua nhiều OCR blocks, duplicate amounts/descriptions, decimal
   normalization, Unicode marks, currency/quantity và table row boundaries.
2. Ambiguous/unavailable evidence giữ flags/null; không chọn vùng đầu tiên tùy
   ý, không suy bbox từ gold và không dùng OCR score làm confidence đã calibration.
3. Với partial page, field gắn readable region vẫn giữ warning nguồn; field chưa
   đọc được giữ unknown/unavailable đúng contract. Test total đang ambiguous
   không được approval vì model nói confidence cao.
4. Chuẩn bị tiny fictional fixtures canonical/OCR/prepared + expected evidence
   cho Backend chạy viewer, không phụ thuộc weights hoặc runtime của AI1.
5. Đối chiếu API artifact keys/run/revision/provenance, làm viewer trên committed
   canonical copies, không đọc mutable attempt files từ Python.

**Đạt:** evidence regressions có expected geometry độc lập, packet runnable trên
checkout sạch. Commit logic/test/fixtures cùng nhau.

## O5 — Đóng native release và khả năng chạy lại

1. Verify model inventory/hash/license/config trước native load; thiếu/corrupt
   file phải fail closed, không request-time download hay fallback im lặng.
2. Đóng lệnh smoke có input paths, release pins và new output root. Run receipt
   receipt+invoice, clean/mild/crop/unreadable và 30-row stress; full accounting.
3. Đo cold/warm latency, RSS/VRAM, timeout/cleanup; concurrency phù hợp service
   capacity1. Không hứa GPU dừng ngay khi cancel HTTP waiter.
4. Run same artifact qua CLI handoff và private compute producer để đối chiếu
   geometry/status/pins. Dùng opt-in B0/v2 có sẵn, không chờ AI2 quality model.
5. Trả run manifest/reader receipt và release candidate OCR; chỉ đề xuất activate
   sau review. Có rollback về release trước và hashes để phục hồi.

**Đạt:** một lệnh kiểm release/smoke, source/deps/model pins, báo giới hạn thật.
Không gọi một tiny smoke là nghiệm thu toàn bộ OCR accuracy.

## Checks và cách bàn giao

Các suite đã có để bắt đầu (PYTHONPATH=src, environment đúng dependencies):

```sh
python -m pytest tests/contract/test_ocr_contracts.py tests/unit/pipeline/test_ocr_input.py tests/unit/pipeline/test_ocr_handoff.py tests/unit/pipeline/test_ocr_consumer.py tests/unit/pipeline/test_baseline.py -q
python -m pytest tests/integration/api/test_consumer_pipeline.py -q
```

Native suite đòi runtime thật, path/pins thật và platform cho phép DLL/so; không
skip rồi claim native acceptance. PR vào develop, CI head cuối xanh, bảng finding
cũ/task O1–O5 → file/test/evidence. Chia commit theo increment sửa có nghĩa,
không theo quota commit. Không sửa schema/approval/backend DB ngoài ownership.

Mọi input làm O1–O5 đã có trong gói; AI2 candidate chưa đạt không chặn công việc
OCR/geometry/evidence/native B0 của AI1. Model quality/final release là gate riêng.
