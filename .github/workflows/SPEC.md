# SPEC — .github/workflows

Owner Backend; Lead duyệt workflow/permissions/required checks.

`ci.yml` chạy read-only trên PR vào main/develop và push hai branch, không top-level paths filter. Job `ci-gate` luôn đánh giá kết quả bắt buộc; release-readiness được yêu cầu khi target main.

Actions pin full SHA; PR không publish/deploy hoặc nhận secrets. Không tự mở quyền merge cho teammates/automation. Chi tiết job names, bootstrap settings và giới hạn ở [docs/cicd.md](../../docs/cicd.md).

Kiểm `python -m scripts.ci.lint`, schema/Data/package/gate tests và hosted run. Gate ứng dụng thiếu executable evidence phải đỏ, không dùng stub/demo thay cho release-ready.
