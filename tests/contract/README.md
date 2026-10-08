# Shared contract fixtures

compute-request/response/error.json là tiny fictional fixtures cho JSON shape; không output OCR/model, không approved data hoặc asset files thật. IDs/provenance/hash0/size/dimensions là fixture declarations. No canonical.png hay ocr.json bytes kèm: runtime hash/containment/correlation tests phải tạo actual temporary assets riêng; schema pass không chứng minh declaration đúng.

Backend và Python producers dùng cùng fixtures/negative mutations. Schema source ở [contracts](../../specs/contracts/README.md), [compute protocol](../../specs/contracts/compute-api.md). Java/Python typed adapters và tests chưa implement; fixtures chỉ đầu vào task B1.2/M2.3.
