# 09 — Nguồn nghiên cứu và giới hạn xác minh

Ngày đối chiếu: 04/10/2026. Ưu tiên tài liệu chính thức; kỹ thuật được đề xuất cho project, không lấy benchmark công bố làm kết quả của nhóm.

| Nguồn | Điều đã dùng trong thiết kế |
|---|---|
| [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | Computation nặng ở process khác phù hợp task queue; tách inference khỏi API |
| [Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html) | Idempotency, late ack, retry và caveat worker loss |
| [Celery Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) | Visibility timeout/redelivery caveats |
| [SQLAlchemy versioning](https://docs.sqlalchemy.org/en/20/orm/versioning.html) | Version checks và giới hạn đường ORM; explicit CAS policy |
| [PaddleOCR usage](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) | Vietnamese `vi`, language support theo version; pin model/package |
| [Qwen2.5-VL-3B model card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct) | Candidate model để spike; không là guarantee tiếng Việt/VRAM |
| [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | Draft cho schemas tham chiếu |
| [ReceiptVQA/LiGT repo](https://github.com/phong-lt/LiGT_VQA) | Dataset access link, research use/license và implementation tham khảo |
| [ReceiptVQA paper](https://arxiv.org/html/2502.19202v1) | QA labels, 9.500/64.812, image grouping và nguồn MC-OCR |
| [Vietnamese Bill Extraction](https://huggingface.co/datasets/minhduc168/dataset-origin-vlm-extract-bill) | Viewer 982 samples, row schema; audit/provenance chưa đủ để làm core |
| [MC-OCR dataset](https://www.rivf2021-mc-ocr.vietnlp.com/dataset) | Điều kiện access và nhãn receipt |

Không có benchmark GPU, training run, download/audit toàn dataset hoặc production code trong task thiết kế này. Không cài stack backend/model vào máy người dùng; không tạo PR/push/deploy. Giá trị deadline, dataset size, throughput và metric là mục tiêu hoặc giả định có gate xác minh.

Các ADR/API/schema/diagram là quyết định thiết kế của nhóm, không là trích nguyên văn từ nguồn. Phiên bản dependencies thực tế phải lock sau smoke tuần 2; không gắn mọi source code với latest documentation mà không test.
