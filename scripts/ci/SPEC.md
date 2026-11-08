# SPEC — scripts/ci

Owner Backend; Data/AI review boundary liên quan, Lead duyệt merge.

- `checks.py`: test inventory, portable Data matrix chuyển đúng PDF test sang job bắt buộc riêng (`tests data --separate-pdf` / `tests pdf`, cần Poppler và không skip), Data integration generation/verification, isolated installed-wheel smoke.
- `ai.py`: pytest AI framework suites, inventory và skip policy fail-closed trong serve/test env riêng; không model/weights.
- `gate.py`: đánh giá status của jobs và target branch từ GitHub event; fail khi required job missing/fail/cancel/skip.
- `lint.py`: tải binary actionlint/zizmor từ upstream bằng URL/version/SHA-256 cố định, chỉ đọc member binary trong archive, kiểm workflow.
- Schema tests dùng validator riêng trong `tests/contract/test_schemas.py`; không đổi renderer pin hay shared schema authority.
- Không model/DB/cloud credentials, không publish/deploy, không chạy privileged PR code.

Chạy regression [test_ci_gate.py](../../tests/unit/test_ci_gate.py), các lệnh trong [runbook](../../docs/cicd.md), rồi kiểm diff và hosted run của đúng SHA.
