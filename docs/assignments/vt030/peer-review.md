# VT-030 – quyết định sau peer review

Claude review read-only snapshot `e3b3850` + draft docs/evidence, context `20014992a14d2bf2ffc21c9c2cb662f841f5919b73e00231cb70752ae77e095f`. [Phản hồi nguyên văn](evidence/ai-final-review.md), [receipt](evidence/ai-final-receipt.json), [prompt](evidence/ai-final-prompt.md).

Verdict của Claude: **acceptable with residuals**, không phát hiện confirmed P1 logic; P1 còn lại là publish branch/evidence và PDF QA. Codex đối chiếu source/raw reports, xử lý findings dưới đây; đây không phải một lần Claude review mới của snapshot sau sửa và không phải human acceptance.

| Finding | Quyết định và evidence |
|---|---|
| P1 branch/README chưa publish | Hoàn thiện commit tài liệu/evidence và publish riêng nhánh bài tập theo yêu cầu link GitHub trong đề; không merge. Kết quả xác minh remote được ghi lúc bàn giao. |
| P1 PDF chưa render | PDF đúng tên, 8 main +3 appendix; render từng trang, kiểm font/bounds/caption/footer. QA artifacts ở output/bt3-vt030 của workspace, không nhận PDF draft là final trước kiểm này. |
| P2 EP implicit | report §3 thêm class → TC ID tường minh; test matrix giữ input/expected/priority. |
| P2 S/P gộp và metadata thiếu SHA | Chỉ rõ S có TC01–18; P thêm TC19–21/browser; R siết TC21. history.txt và source-baseline-proof.json đối chiếu blobs/timestamps; không bịa SHA đã capture cho run lịch sử. |
| P2 flags và mutation kill yếu | Disclose barrier_ready/all_outcomes là declarations được assertions hỗ trợ, peak là phép đo; timer request/timeout có mốc khác. Public mutation tool chuyển sang fresh JUnit XML, không suy từ dòng “Running”. windows-mutation.json xác nhận 1+6 failures, 0 errors, restore đúng bytes. |
| P2 chênh p95 | Ghi warm-up/order có thể ảnh hưởng nhưng chưa chứng minh nhân quả. Không nhận scenario này nhanh/chậm hơn scenario kia một cách tổng quát; giữ hai fresh-JVM runs chính thay chọn số nhanh nhất. Không nhận giả thuyết “cold JVM nên conservative” là fact đo được. |
| P2 random order chưa chứng minh | order-comparison.json so testcase order trong XML, hai seeds khác nhau và khác green. final-order-seed17/83 đều25pass sau R, class-order cũng đổi theo log; không claim hết flaky. |
| P2 TC21 replay yếu | R=a1055c3 kiểm same job/reserved run ID và count Job/CREATE_JOB sau replay; full suite50/coverage/build và Windows focused25 chạy lại đạt. |
| P2 README chưa dùng Windows command | Chạy đúng focused .\mvnw.cmd command,25pass; public mutation dùng cmd/mvnw.cmd killed7+restore. JSON ghi JAVA_HOME/cache env. Các biến thể còn lại được ghi là portable equivalents, exact argv lịch sử giữ nguyên trong metadata. |
| P2 planned files thiếu | Report §2 liệt kê plan controller GET/POST/OpenAPI/tests so với actual controller POST/OpenAPI; GET/CacheControl/queue không triển khai. |
| P2 dangling files/stale scope | Tạo peer-review này; manifest chỉ tạo sau curation cuối; red-native ghi15 API/service, chưa6unit; hai stale XML loại có curation/hash. |

## Codex verification và phần còn giới hạn

- OpenAPI additive Location header: diff9 dòng, schema/body không đổi; pattern khớp route quan sát trong browser. Claude không đọc diff đó nên không gán kết luận này cho Claude.
- Profile/task/receipts được giữ; không giả đã dùng một Codex worker riêng hoặc Claude đã chạy tests. Parent là bên chạy toàn bộ checks.
- Các slide được đối chiếu từ PPTX đã trích text: L06 slides9/10/14/18/26 và L07 slides13/18/21/23/24 đúng nội dung dẫn trong report. Không dùng kết quả BT2 thay số đo VT-030.
- Location hiện là root-relative `/api/v1/jobs/{id}`; app hiện chạy root. Deploy sau reverse proxy/context prefix khác phải chốt URL prefix và kiểm lại, không tự nhận hỗ trợ mọi subpath.
- PostgreSQL multi-runner/crash-after-effect, UI automatic retry reuse key, actual model/TCP load và notification delivery khi có module vẫn chưa kiểm. Bài công bố giới hạn đúng phạm vi executable harness mà đề cho phép.
- Không tạo/merge PR hoặc nộp Classroom. Handoff ở `awaiting-human-review`; người nộp đọc lại nội dung và quyết định nộp.
- Diff whitespace check đạt với source và tài liệu tự viết. Raw Maven logs giữ các dòng `[INFO] ` có trailing spaces; đây là output gốc được bảo toàn, được loại riêng khỏi check whitespace, không sửa log/assertion để đạt check.
- Kiểm manifest trên committed blobs phát hiện Git normalize CRLF/LF. Thêm `.gitattributes` chỉ trong evidence để giữ exact bytes, regenerate manifest rồi kiểm lại Git blobs. Đây là sửa packaging evidence, không sửa counts/assertions hay production code.
