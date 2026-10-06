# Folder specs: đọc ngay trong folder đang làm

Purpose/owner/content/boundaries/workflow/checks nằm trong SPEC.md của từng folder làm việc. Không cần mở một bảng chung rồi tìm module.

- [Python modules](../src/vietdoc/SPEC.md): mỗi module/submodule có SPEC riêng.
- [UI](../web/SPEC.md), [tests](../tests/SPEC.md), [migrations](../migrations/SPEC.md), [infra](../infra/SPEC.md).
- [Data](../datasets/SPEC.md), [model artifacts](../artifacts/SPEC.md), [runtime storage](../storage/SPEC.md).
- [Requirements](SPEC.md), [docs](../docs/SPEC.md), [Git/PR configuration](../.github/SPEC.md).

Root [SPEC.md](../SPEC.md) chỉ điều hướng. File này giữ link tương thích, không bản giải thích dài thứ hai.

Không thêm SPEC vào Git internals/cache/local tooling hoặc snapshot bất biến docs/design/v1; [docs/design/SPEC.md](../docs/design/SPEC.md) giải thích snapshot. Raw/model/runtime folders chỉ track đúng SPEC.md/.gitkeep, tài sản khác vẫn ignored.
