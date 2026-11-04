# Shared contract fixtures

compute-request/response/error.json là tiny fictional fixtures cho JSON shape; không output OCR/model, không approved data hoặc asset files thật. IDs/provenance/hash0/size/dimensions là fixture declarations. No canonical.png hay ocr.json bytes kèm: runtime hash/containment/correlation tests phải tạo actual temporary assets riêng; schema pass không chứng minh declaration đúng.

Schema source ở [contracts](../../specs/contracts/README.md), [compute protocol](../../specs/contracts/compute-api.md). Python Draft 2020-12 tests và Java `ComputeContractTest` cùng đọc ba fixture này; Java còn kiểm correlation/provenance/path semantics. Python typed adapter và kiểm actual HTTP/asset bytes chưa implement; fixtures không thay thế consumer acceptance của AI-2.
