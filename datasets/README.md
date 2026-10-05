# Datasets local

- raw/: dữ liệu tải/thu thập chưa xử lý; ignored.
- processed/: dữ liệu sau chuẩn hóa/render; ignored.
- manifests/: metadata/split/hash nhỏ có thể commit, không chứa PII hoặc đường dẫn máy cá nhân.

Data Engineer phụ trách. Dataset public cần audit terms/provenance/PII trước khi dùng. Source code generator ở src/vietdoc/data/, không đặt trong folder dữ liệu này.
