# SPEC — scripts

Scripts vận hành/build/test có logic, không là application services. Owner: Backend; Lead review.

- [ci](ci/SPEC.md): CI checks và gate của increment hiện có.
- Không secrets, credential helpers, model weights, business DB writes hoặc deploy tự động trong scripts CI.
- `preserve_pr_history.py`: inventory và tạo một history-only merge trên **local release ref mới**, tree không đổi; nhận merged primary PRs hoặc feature-chain có integration witness. Lịch sử revert cần chọn explicit và ghi historical-only. Không push/overwrite refs/check out/sửa index, không nhận PR đang mở. Native E2E runner chỉ dùng DB test loopback/caller-owned, không business DB chung.
- Lệnh chạy và bằng chứng: [CI/CD](../docs/cicd.md). Mỗi script thay đổi phải chạy focused tests/lint phù hợp.
