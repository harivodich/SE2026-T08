# Private compute — lệnh kiểm candidate opt-in

B0/v1 vẫn chạy bằng entrypoint hiện hành. Lệnh dưới không tải weights, không
train, không activate production và không làm model kém chất lượng thành đạt.

```sh
PYTHONPATH=src python scripts/serve_compute_candidate.py --help
PYTHONPATH=src python scripts/serve_compute_candidate.py --ocr-artifact-version 2
```

Cấu hình runtime qua `VIETDOC_SERVICE_TOKEN` hoặc token file,
`VIETDOC_MODELS_DIR`, `VIETDOC_ATTEMPTS_DIR`, `VIETDOC_PIPELINE_MANIFEST_ID` và
`VIETDOC_HOST/PORT`. Không gửi secret trong task/report hoặc commit `.env`.
Release B0/v2 phải hash/size-pin mọi native OCR file cùng `pipeline.json`:

```json
{"profile_version":2,"extractor_version":"vi-label-header-b0.v3","normalizer_version":"vi-VND.v2","ocr_artifact_version":2,"model_root":"ocr"}
```

Candidate Qwen cần caller chọn rõ paths/pins, release mới và environment đủ
Torch/Transformers/PEFT/native OCR từ đầu; không install khi có request:

```sh
PYTHONPATH=src python scripts/serve_compute_candidate.py --extractor qwen-local --ocr-artifact-version 2 --config LOCAL_INFERENCE.yaml --config-sha256 CONFIG_SHA --snapshot LOCAL_BASE_REVISION_DIR --snapshot-manifest-sha256 BASE_MANIFEST_SHA --run-dir LOCAL_RUN --run-manifest-sha256 RUN_MANIFEST_SHA
```

Bỏ cả hai run arguments để kiểm M0. Với Qwen, pipeline profile_version2 dùng
extractor `qwen3-strict-local.v1`, normalizer
`schema-canonical-decimal-preserved.v1`, artifact version đã chọn và model_root
`ocr`. Giá trị model đã là canonical decimal strings theo schema; không đưa
qua locale OCR normalizer để đổi `1.234` thành `1234` hoặc mất quantity `2.000`.
Release hash/size-pin `extractor.json` gồm đúng:

```json
{"config_sha256":"CONFIG_SHA","snapshot_manifest_sha256":"BASE_MANIFEST_SHA","run_manifest_sha256":"RUN_MANIFEST_SHA"}
```

M0 dùng run_manifest_sha256=null. Config inference bật execution rõ ràng, nhưng
download/training/paid/runtime_activation vẫn false. Với adapter, nội dung config
phải khớp fingerprint config của run sau khi sanitize enabled/allow_training về
false; các budgets/template/device/profile/source keys còn lại không được đổi.
Copy training mapping rồi đổi đúng hai flags để inference, giữ manifest lịch sử
bất biến. Base envelope khác pin run phải reject; không rewrite pin checkpoint.

Multipart gồm field **request** JSON và **file**; Bearer auth service-to-service.
Lấy shape từ `tests/contract/compute-request.json`, thay canonical lowercase UUIDs,
input hash, selected release ID và remaining budget thực. Artifact key bắt đầu
`attempts/`; volume attempts_dir được đặt tại chính directory attempts, không
ghép prefix thêm một lần khi đọc file local. Java phải verify/promotion trước
commit; browser không gọi endpoint này trực tiếp.

Expected errors: invalid/missing release422 `MANIFEST_UNAVAILABLE`; unsupported
profile/model load không ready503; compute503 `AI_NOT_READY`; busy503 `AI_BUSY`;
deadline504 `COMPUTE_TIMEOUT`; OOM500 `MODEL_OOM`; invalid raw output422
`OUTPUT_INVALID`. Không repair/fallback thành success. Request cancelled không
đồng nghĩa GPU đã free; slot giữ đến worker cleanup.

Local consumer checks:

```sh
PYTHONPATH=src python -m pytest tests/integration/api/test_consumer_pipeline.py tests/integration/api/test_compute_api.py tests/unit/pipeline/test_compute_pipeline.py tests/unit/pipeline/test_composition.py tests/unit/ml/test_compute_extractor.py -q
```

HTTP controlled-engine tests kiểm wiring và negative cases. Native receipts và
recorded Python→Java fixture ở báo cáo gỡ dependency; không thay live PG/model
E2E hoặc final quality. Candidate chưa accepted chỉ chạy trong test/staging được
Lead cho phép, không đổi B0 default.
