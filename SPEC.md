# SPEC — VietDoc root

## Purpose và owner

Điểm vào repo và quy ước chung. Owner: Lead/Backend.

## Đặt gì ở đây?

README/AGENTS/pyproject/Git config files; source ở src/, UI ở web/, requirements ở specs/, workflow theo người ở docs/team/.

## Ranh giới và dữ liệu

Không đặt datasets/weights/runtime files ở root; không sửa .git thủ công. Scope chung: receipt/invoice tiếng Việt, chữ in một trang; prediction/revision bất biến, human approve trước export. File đích chưa có logic là task cần implement, không tự thêm fake implementation.

## Workflow và kết quả cần kiểm

1. Nhận một task nhỏ có input/version/output/acceptance từ Lead; xem [doc vai trò](docs/team/lead.md) khi cần task chi tiết.
2. Sửa đúng vùng này, báo affected consumer nếu contract/config/version đổi; không tự nhận phần module khác.
3. Đọc SPEC.md ngay trong folder định sửa, kiểm scope/owner/diff/ignore; không claim app chạy từ folders tồn tại.
4. Ghi commands/checks/output thật và limitations, peer review trước Lead duyệt; [Git Flow](docs/git-flow.md), không direct push main/develop.

## Folder liên quan

Root repo. [Scope](specs/scope.md).
- [.github](.github/SPEC.md)
- [artifacts](artifacts/SPEC.md)
- [datasets](datasets/SPEC.md)
- [docs](docs/SPEC.md)
- [infra](infra/SPEC.md)
- [migrations](migrations/SPEC.md)
- [specs](specs/SPEC.md)
- [src](src/SPEC.md)
- [storage](storage/SPEC.md)
- [tests](tests/SPEC.md)
- [web](web/SPEC.md)

SPEC.md là hướng dẫn local, không chứng minh app/model/CI đang chạy. .git/verification tooling/caches và immutable design snapshot không phải folders để team viết application code.
