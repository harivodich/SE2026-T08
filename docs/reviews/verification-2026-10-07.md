# VietDoc — xác minh thực tế và SPEC từng folder

> Evidence/kiểm kê của thiết kế Python-only trước redesign. Kiến trúc hiện hành và checks mới ở [redesign report](architecture-redesign-2026-10-07.md); không dùng kết quả cũ làm Java/Thymeleaf runtime proof.

Ngày: 07/10/2026, Asia/Saigon. Báo cáo này thay trạng thái unverified trong [audit trước](repository-readiness-2026-10-07.md). Kết quả là kiểm tra tài liệu/contracts/design assets hiện có, không nghiệm thu ứng dụng chưa implement.

## 1. Spec ngay trong folder

- 80/80 folder làm việc có `SPEC.md`: purpose, owner, nội dung đặt ở đây, boundaries, workflow, task/checks và link folder cha/con.
- Ví dụ: [OCR](../../src/vietdoc/pipeline/ocr/SPEC.md), [training](../../src/vietdoc/ml/SPEC.md), [data generator](../../src/vietdoc/data/generator/SPEC.md), [API routes](../../src/vietdoc/entrypoints/api/routes/SPEC.md), [unit pipeline tests](../../tests/unit/pipeline/SPEC.md).
- Không cần đọc một bảng chung rồi tìm module; repository-layout chỉ còn index tương thích.
- Không thêm specs vào `.git`, caches, `.verification` tooling hoặc snapshot bất biến `docs/design/v1`; spec ở [docs/design](../design/SPEC.md) giải thích vùng frozen.
- `.gitignore` chỉ thêm exceptions đúng SPEC.md trong raw/processed/models/evaluation/storage. Data/weights/runtime probes vẫn ignored. `.verification` tools/outputs cũng ignored.
- Final check: 80/80 local specs, 611 relative document links tồn tại, fences/whitespace pass, 48 task IDs unique, 10 compiled SVG XML parse và localhost QA server đã dừng.

## 2. JSON Schema: PASS

Chạy `jsonschema 4.26.0` với `Draft202012Validator.check_schema`, validators, offline `referencing.Registry` và `FormatChecker` theo [tài liệu validator chính thức](https://python-jsonschema.readthedocs.io/en/stable/validate/).

- 8 schemas: 4 active + 4 snapshot, meta-schema checks pass.
- 50/50 expected positive/negative cases pass: receipt/invoice/result/export/job, optional null, decimal quantity, required/extra keys, money types/patterns, date format, 31 rows, schema/type mismatch, confidence/bbox/page bounds, UUID và broker payload extra fields.
- `$ref` đăng ký local, không fetch URN qua network. Snapshot và active contracts không sửa.
- Calendar-invalid `2026-02-31` vẫn qua structural regex như định nghĩa schema hiện có. Test xác nhận đây là application-semantic validation ở review service, không claim schema kiểm calendar/ownership/approval/arithmetic/evidence association.

Command đã chạy trên venv local tách app:

```powershell
& '.\.verification\python\Scripts\python.exe' -B .verification/verify_schemas.py
```

Verifier ở local ignored `.verification/verify_schemas.py`; chưa đưa dependencies hoặc tests giả vào app. Backend B1.1/B1.2 vẫn phải tạo typed models/project contract tests khi implementation bắt đầu.

## 3. PlantUML: PASS

- PlantUML 1.2026.8, portable Temurin JRE 17.0.20.1+1, không Java global/PATH changes.
- Tải từ official PlantUML/Adoptium releases và kiểm SHA256 theo metadata nguồn trước chạy; zip extraction targets được kiểm trong `.verification/tools/java17`.
- Compiler `--check-syntax --stop-on-error` chạy cả 20 `.puml` active/snapshot: exit 0.
- `--format svg --output-dir D:\SE\.verification\plantuml-svg` render 10 active diagrams: exit 0, đủ 10 SVG outputs.
- Outputs ignored, không ghi đè tracked presentation SVG hoặc bytes snapshot. Compiler pass không chứng minh implementation phù hợp diagram.

Nguồn tools: [PlantUML official download](https://plantuml.com/download), [Adoptium archive installation](https://adoptium.net/installation/archives/).

Commands tương ứng đã thực thi, `<java>` là portable executable được phát hiện sau hash/extraction check:

```text
<java> -Djava.awt.headless=true -Dfile.encoding=UTF-8 -jar plantuml-1.2026.8.jar --check-syntax --stop-on-error <20 source paths>
<java> -Djava.awt.headless=true -Dfile.encoding=UTF-8 -jar plantuml-1.2026.8.jar --format svg --output-dir <ignored output> <10 active source paths>
```

## 4. Browser QA: PASS cho trang thiết kế HTML

Playwright 1.62.1/headless Chrome với context mới, HTTP helper chỉ `127.0.0.1:8767` và chỉ serve `docs/design/v1`. Browser UI tool bị lỗi sandbox initialization nên dùng test framework local; không user profile/login/settings và không gửi tài liệu ngoài máy.

Các assertions chạy thật:

| Check | Kết quả |
|---|---|
| HTTP/title/default overview | 200, đúng page và overview |
| Theme toggle | Dark/light classes đúng |
| Navigation | 11 views đúng visible section và active link |
| Lazy-loaded diagrams | 10/10 SVG ảnh load với dimensions >0 |
| Source details | Mở nội dung PlantUML được |
| Download .puml | File tải local byte-identical nguồn |
| Open SVG/zoom link | Popup có SVG document |
| Unknown hash | Fallback overview đúng |
| Mobile 390×844 | Không overflow toàn trang; bảng/diagram scroll trong panel |
| Page errors/request failures | 0/0 |
| Requests ngoài localhost | 0 |

Đã inspect screenshots desktop gallery, mobile overview và mobile gallery. Đây là browser QA của hồ sơ thiết kế, không UI React chưa tồn tại; gallery trên mobile có scroll nội bộ/link mở SVG để xem diagram rộng.

Warning nhỏ từ HTTP logs: Chrome tự hỏi `/favicon.ico` và nhận 404 vì snapshot không khai báo site icon. Đây không phải request failure/network exception; HTML và 10 SVG content assets trả 200. Không sửa frozen snapshot để che warning này.

Command thực:

```text
<bundled-node> .verification/browser_checks.cjs
```

Screenshots local ignored: `.verification/browser-desktop-gallery.png`, `browser-mobile-overview.png`, `browser-mobile-gallery.png`. Helper server được dừng sau kiểm tra; không service/deploy persistent.

## 5. Runtime tests: đã kiểm, chưa có implementation để chạy

Discovery thực xác nhận:

| Đường chạy cần có | Có hiện tại? |
|---|---|
| `vietdoc.entrypoints.api.app` | Không |
| `vietdoc.entrypoints.worker.app` | Không |
| `vietdoc.entrypoints.dispatcher.main` | Không |
| `vietdoc.ml.train_extractor` | Không |
| `vietdoc.pipeline.service` | Không |
| `web/package.json` | Không |
| `alembic.ini` | Không |
| Application `test_*.py` | 0 |
| Web test sources | 0 |

Pytest collection thực bằng Python 3.13 có pytest, với plugin autoload tắt cho discovery:

```text
<Python 3.13 đã cài pytest> -m pytest --collect-only -q -p no:cacheprovider tests web/tests
no tests collected in 0.01s
exit 5
```

25 Python source files chỉ docstrings scaffolds. Kết quả runtime là **không có executable implementation/tests**, không phải tests pass và không phải chưa thử kiểm tra. User request này là spec/xác minh, không cấp scope triển khai toàn bộ app/train model. Không tạo fake API/test để báo hoàn tất.

## 6. Git/file scope và bước tiếp theo

- Không stage/commit/push/PR/merge/deploy; không thay GitHub settings hoặc Git config global.
- `pyproject.toml` và frozen design snapshot giữ nguyên. Runtime source chỉ docs/scaffolds, không implementation mới.
- Tool venv/JRE/JAR/checkers/screenshots/compiled SVG ở ignored `.verification`, không deps runtime/project artifacts.
- 48 task cá nhân còn nguyên: Data tạo data/gold/evaluator, AI-1 preprocess/OCR/evidence, AI-2 fine-tune/extraction, Backend app/DB/jobs/UI/review/export, Lead thiết kế/review/merge.
- Bắt đầu task B1.1/B1.2/B1.3, D1.1/D1.2, O1.1/O1.2/O1.3 và M1.1/M1.2/M1.3 theo doc cá nhân. Runtime readiness chỉ đạt sau code/tests tương ứng có thật và được chạy.
