# SPEC — scripts/ci

Owner Backend; Data/AI review boundary liên quan, Lead duyệt merge.

- `checks.py`: test inventory, portable Data matrix chuyển đúng PDF test sang job bắt buộc riêng (`tests data --separate-pdf` / `tests pdf`, cần Poppler và không skip), Data integration generation/verification, isolated installed-wheel smoke.
- `ai.py`: pytest AI1/AI2 fixture suites, mandatory inventory và skip policy fail-closed trong env `.[serve,test,ai1]` + NumPy pin; không model/weights.
- `gate.py`: đánh giá status của jobs và target branch từ GitHub event; fail khi required job missing/fail/cancel/skip.
- `application.py`: JUnit không skip + JAR/schema/assets/migration hashes, receipt đúng source và smoke đúng artifact đã test; không rebuild trong job smoke.
- `parity.py`: so cùng corpus qua Java/Python, oracle và corpus SHA phải trùng.
- `native_e2e.py`: runner PostgreSQL cô lập + JAR + native OCR/B0 thực + review/export, không giả model quality; explicit setup mới tải OCR weights đã pin checksum, inference không tải.
- `acceptance.py`: main fail closed khi thiếu frozen V1 quality/candidate packet; kiểm source fingerprint, report hashes, per-type metrics/support và actual candidate evidence. Lead cung cấp packet sau nghiệm thu, không tạo PASS mẫu.
- `lint.py`: tải binary actionlint/zizmor từ upstream bằng URL/version/SHA-256 cố định, chỉ đọc member binary trong archive, kiểm workflow.
- Schema tests dùng validator riêng trong `tests/contract/test_schemas.py`; không đổi renderer pin hay shared schema authority.
- Không model/DB/cloud credentials, không publish/deploy, không chạy privileged PR code.

Chạy regression [test_ci_gate.py](../../tests/unit/test_ci_gate.py), các lệnh trong [runbook](../../docs/cicd.md), rồi kiểm diff và hosted run của đúng SHA.
