# Shared contract fixtures

OCR internal proposal có fixture v1 `ocr-page-proposal.json`, v2
`ocr-artifact-v2.json` (mixed/whitespace/all-unreadable/no-detection), và observed
`ocr-d1-native-handoff.json` (hai mẫu D1 hư cấu, hashes/prepared/native blocks,
renderer identity oracle, matched/ambiguous/unavailable evidence). File native là
output quan sát, không gold. Các fixture này không thay shared compute schema.
`OcrPage.from_dict` đọc strict v1/v2; v1 serialize giữ đúng shape cũ; migrate bằng
`dataclasses.replace(page, artifact_version=2)`. Partial không được downgrade về v1
và bỏ diagnostics. Consumer parse tests là local; actual AI-2/Backend acceptance
vẫn pending. Backend phải giữ blocker khi required field thiếu theo approval policy.

compute-request/response/error.json là tiny fictional fixtures cho JSON shape; không output OCR/model, không approved data hoặc asset files thật. IDs/provenance/hash0/size/dimensions là fixture declarations. No canonical.png hay ocr.json bytes kèm: runtime hash/containment/correlation tests phải tạo actual temporary assets riêng; schema pass không chứng minh declaration đúng.

Backend và Python producers dùng cùng fixtures/negative mutations. Schema source ở [contracts](../../specs/contracts/README.md), [compute protocol](../../specs/contracts/compute-api.md). Java/Python typed adapters và tests chưa implement; fixtures chỉ đầu vào task B1.2/M2.3.

`test_ocr_contracts.py` kiểm Python OCR/page types theo [proposal O1.1](../../docs/ocr-input-proposal.md), dùng `tests/fixtures/ocr-page-proposal.json` và negative mutations. Đây là proposal mới chờ consumer review, không phải compute DTO/schema parity đã có. Fixture chỉ metadata giả; kiểm image bytes/engine/Java/viewer thực thuộc các task tiếp theo.
