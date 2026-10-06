# Source Python

Các package hiện giữ chỗ cho code theo thiết kế. Chưa có server/model chạy từ các folder này.

| Folder | Viết gì ở đây | Phụ trách |
|---|---|---|
| contracts/ | Kiểu dữ liệu/schema chung: receipt, invoice, OCR, result | Backend, Lead review |
| identity/ | Login và quyền truy cập | Backend |
| documents/ | Upload, metadata và head revision | Backend |
| jobs/ | Tạo job, lease, retry, completion | Backend |
| review/ | Sửa, validate và approve revision | Backend |
| exports/ | JSON của revision đã approve | Backend |
| pipeline/preprocess.py, geometry.py, evidence.py | Preprocessing/canonical transforms/evidence; files tạo khi triển khai | AI-1 |
| pipeline/ocr/ | OCR port/engine adapter | AI-1 |
| pipeline/extraction/ | Rule/model extraction adapters | AI-2 |
| pipeline/normalization.py, confidence.py | Normalization/calibration; files tạo khi triển khai | AI-2 |
| pipeline/service.py | Thin wiring, không viết lại algorithms | Đề xuất Backend, hai AI review, Lead chốt |
| data/ | Generator, dataset adapters, manifest và splits | Data Engineer |
| ml/ | Training, model loading/config và release manifest | AI-2 |
| evaluation/ | Metrics và báo cáo chất lượng | Data, hai AI review |
| infrastructure/ | DB, storage, broker adapters | Backend |
| entrypoints/ | Nơi khởi động API, worker, dispatcher, CLI | Backend |

Logic nghiệp vụ ở module sở hữu; routes chỉ gọi service. Model không ghi business DB và API không load weights. Training/evaluation đọc dataset snapshot riêng. Trước khi sửa interface chung, thống nhất với consumer và Lead.

Tạo file khi có việc cụ thể, không thêm TODO services. Mỗi module có SPEC.md; [spec package](SPEC.md) dẫn specs con. [Doc cá nhân](../../docs/team/README.md) giữ roadmap/task/Git Flow. Cây đích ở [source structure](../../docs/source-structure.md); file đích chưa implement không là thiếu scaffold.
