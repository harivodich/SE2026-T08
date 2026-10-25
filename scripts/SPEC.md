# SPEC — scripts

Scripts vận hành/build/test có logic, không là application services. Owner: Backend; Lead review.

- [ci](ci/SPEC.md): CI checks và gate của increment hiện có.
- Không secrets, credential helpers, model weights, business DB writes hoặc deploy tự động trong scripts CI.
- Lệnh chạy và bằng chứng: [CI/CD](../docs/cicd.md). Mỗi script thay đổi phải chạy focused tests/lint phù hợp.
