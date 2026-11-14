"""Build the Vietnamese VT-029 report from recorded, local execution evidence.

Run with a Python environment containing reportlab and pypdf after the experiments.
The report records the published code branch and marks student review as pending.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/reviews/vt029-evidence"
BASELINE = "e5326f34549a23570ecf935f469a1f0082ed8a11"
BRANCH = "feature/VT-029_search_contract"

REFLECTION = """Điều làm tôi tin tưởng hơn vào thay đổi này là sự kết hợp giữa oracle độc lập và lỗi có chủ đích. Khi q chưa được triển khai, các test tìm kiếm thất bại vì kết quả chứa cả tên file không khớp. Sau patch, cùng kỳ vọng đó được thỏa mãn, còn response được kiểm bằng schema lấy từ baseline. Việc dùng timestamp bằng nhau giúp kiểm tie-breaker bằng dữ liệu cụ thể thay vì chỉ đọc câu lệnh order by.

Hai lỗi trong phần AI hỗ trợ nhắc tôi rằng test cũng cần được review. Kỳ vọng HTTP 400 cho type sai đã mâu thuẫn với hành vi 422 hiện hữu. Fixture metadata dùng object lại không khớp schema yêu cầu array. Nếu chỉ nhìn test xanh hoặc tên trường giống nhau, tôi có thể bỏ sót cả hai vấn đề. Vì vậy, tôi giữ log lỗi và sửa assumption dựa trên source, không sửa contract để hợp thức hóa dữ liệu sai.

Mutation làm confidence tăng thêm: khi exception bị nuốt và thay bằng trang rỗng, TC12 thất bại ngay tại HTTP status. Điều này bảo vệ sự khác nhau giữa không có kết quả và hệ thống gặp lỗi. Tuy nhiên, một mutation bị phát hiện chưa chứng minh suite bắt được mọi lỗi, và line coverage cao không đo được chất lượng oracle.

Tải HTTP trên H2 chỉ chứng minh workload cục bộ được mô tả. Nó chưa chứng minh độ trễ với PostgreSQL, nhiều tài khoản, dữ liệu lớn hoặc browser thật. Test tiếp theo có giá trị cao nhất là chạy cùng contract và tải trên PostgreSQL với dữ liệu đủ lớn, đối chiếu collation tiếng Việt và query plan. Trước khi nộp, tôi cần tự đọc patch, chạy lại các lệnh và xác nhận reflection này phản ánh đúng phần việc mình hiểu."""


def build():
    history = json.loads((EVIDENCE / "git-history.json").read_text())
    code_commit = history["implementation_commit"]
    mutation_commit = history["mutation_commit"]
    manifest_paths = [
        "backend/src/main/java/vn/vietdoc/document/DocumentController.java",
        "backend/src/main/java/vn/vietdoc/document/DocumentService.java",
        "backend/src/main/resources/openapi.json",
        "backend/src/test/resources/vt029-v1-contract.json",
        "backend/src/test/java/vn/vietdoc/DocumentSearchContractTest.java",
        "backend/src/test/java/vn/vietdoc/DocumentSearchUnitTest.java",
        "backend/src/test/java/vn/vietdoc/DocumentSearchLoadTest.java",
        "specs/contracts/document-search.md",
        "scripts/vt029_contract.py", "scripts/vt029_experiment.py", "scripts/vt029_report.py",
        "docs/reviews/VT-029-plan.md", "docs/reviews/VT-029-README.md",
    ]
    manifest = {"baseline_commit": BASELINE, "branch": BRANCH,
                "implementation_commit": code_commit, "published": history["remote_verified"],
                "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in manifest_paths}}
    (EVIDENCE / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    load = json.loads((EVIDENCE / "load-result.json").read_text())
    mutation = json.loads((EVIDENCE / "mutation-result.json").read_text())
    coverage = json.loads((EVIDENCE / "coverage-summary.json").read_text())
    run = (EVIDENCE / "java-regression.txt").read_text()
    summaries = re.findall(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", run)
    summary = summaries[-1]
    assert "BUILD SUCCESS" in run and mutation["killed"]
    assert 250 <= len(REFLECTION.split()) <= 350, len(REFLECTION.split())
    for name, font in [("DV", "DejaVuSans.ttf"), ("DV-Bold", "DejaVuSans-Bold.ttf")]:
        pdfmetrics.registerFont(TTFont(name, "/usr/share/fonts/truetype/dejavu/" + font))
    body = ParagraphStyle("body", fontName="DV", fontSize=9.5, leading=13.9,
                          textColor=colors.HexColor("#203044"), spaceAfter=7)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11.4, spaceAfter=3)
    title = ParagraphStyle("title", parent=body, fontName="DV-Bold", fontSize=21, leading=27, spaceAfter=13)
    h2 = ParagraphStyle("h2", parent=body, fontName="DV-Bold", fontSize=12, leading=17, spaceBefore=9, spaceAfter=7)
    story, source = [], []

    def p(text, style=body):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), style)); source.append(text)
    def head(number, text, subtitle):
        if story: story.append(PageBreak())
        p(number, small); p(text, title); p(subtitle, body)
    def h(text): p(text, h2)
    def table(headers, rows, widths):
        values = [[Paragraph(escape(str(x)), small) for x in row] for row in [headers, *rows]]
        t = Table(values, colWidths=[x * mm for x in widths], repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), colors.HexColor("#e7eef6")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LINEBELOW",(0,0),(-1,0),0.8,colors.HexColor("#a9bbd0")),
            ("LINEBELOW",(0,1),(-1,-1),0.3,colors.HexColor("#dce3eb")),
        ])); story.append(t); story.append(Spacer(1,7))
        source.append(" | ".join(headers))
        source.extend(" | ".join(map(str,row)) for row in rows)

    head("01 / SPECIFICATION", "Tìm kiếm chứng từ có lọc", "BT cá nhân 3 - AI-02 - VT-029 | Bản chuẩn bị nộp, ngày 14/11/2026")
    p("Nguyễn Tiến Đạt | MSSV 23001863 | Thành viên | SE2026-T08")
    p("Repository sử dụng: https://github.com/harivodich/SE2026-T08\nĐề ghi SE2026.AI-02.1; người dùng đã xác nhận dùng workspace hiện tại.", small)
    p("Baseline (origin/develop local): " + BASELINE, small)
    p("Nhánh nộp: " + BRANCH + "\nLink: https://github.com/harivodich/SE2026-T08/tree/feature/VT-029_search_contract\nImplementation commit: " + code_commit + "\nNhánh đã push; không merge trước review.", small)
    h("Problem statement")
    p("Người vận hành cần tìm chứng từ của mình theo tên file, kết hợp bộ lọc và duyệt nhiều trang có thứ tự ổn định, đồng thời client đang dùng API v1 tiếp tục hoạt động.")
    table(["AC", "Điều kiện chấp nhận"], [
        ["AC1", "q optional: filename substring literal, trim/case; AND type/status/owner."],
        ["AC2", "Giữ cursor/limit; thứ tự createdAt DESC,id DESC; không lặp/mất trên dữ liệu cố định."],
        ["AC3", "Giữ Page {items,next_cursor}, Document và nullability của baseline v1."],
        ["AC4", "Lỗi query/filter/cursor rõ ràng; lỗi provider không thành 200 empty page."],
        ["AC5", "80 tác vụ đồng thời; đo HTTP p95 so với 2500 ms và kiểm kết quả mỗi request."],
    ], [16,158])
    p("Constraints: bảo vệ owner bằng query/cursor và bind parameter; page clamp [1,100], q tối đa 128 UTF-16 code units sau trim; không migration/dependency runtime mới. Tải H2 chỉ có giá trị cho workload công bố.")
    p('Cam kết cần sinh viên xác nhận: “Tôi chịu trách nhiệm về toàn bộ code, test và nội dung bài làm; tôi đã khai báo việc sử dụng AI.”', small)

    head("02 / PLAN & REVIEW", "Contract trước implementation", "Plan gốc: docs/reviews/VT-029-plan.md, được ghi trước patch production.")
    h("Invariant quan trọng nhất")
    p("Request cũ tiếp tục nhận đúng Page/Document v1, chỉ chứa tài nguyên của owner. q là tham số bổ sung, không thay response schema hoặc cursor. Không có kết quả và lỗi hệ thống phải phân biệt được bằng HTTP status.")
    p("Search giữ dấu tiếng Việt; không hứa bỏ dấu hoặc Unicode normalization. %, _ và ! là literal. Client giữ nguyên bộ lọc khi đi trang tiếp; đổi bộ lọc phải bỏ cursor. Keyset không cung cấp snapshot khi dữ liệu đổi giữa requests.")
    table(["Draft AI", "Sửa/bác bỏ bằng repository thật"], [
        ["Thêm route Python documents", "Bác bỏ: AGENTS.md, backend/SPEC.md và DocumentController xác định Java là business authority; Python business scaffold legacy."],
        ["Đổi page/size/total, sort timestamp", "Bác bỏ: DocumentService.list đã có cursor và tie-breaker id; static/api.js gọi limit=50. Giữ keyset/Page v1."],
        ["Docs nói chưa có app nên dùng harness độc lập", "Sửa: Java source, OpenAPI, WorkflowIntegrationTest đã có. JDK sẵn có; chạy Spring/H2 và HTTP thật."],
        ["Invalid type phải 400", "Sửa sau RED đầu: ContractValidator.invalid trả 422 CONTRACT_INVALID. Không đổi behavior cũ để chiều test AI."],
    ], [58,116])
    h("Plan và file được sử dụng")
    p("Spec → Test RED → patch nhỏ → Verify → Review. Sửa DocumentController.java, DocumentService.java, openapi.json; thêm document-search.md và tests/fixture. Evidence, scripts và báo cáo là file hỗ trợ. Production diff: 25 dòng thêm, 2 dòng bỏ trong 3 file.")
    p("Review diff của agent: q chỉ vào named parameter, escape ! trước %/_; owner luôn trong WHERE; cursor/order và DTO giữ nguyên; không migration, không đụng model hoặc business revision. Đây là self-review của agent; review độc lập của sinh viên/nhóm vẫn chờ.")

    head("03 / TEST CASES", "Thiết kế theo risk", "P0: rò dữ liệu/contract/lỗi bị che; P1: chức năng/boundary; P2: phép đo môi trường.")
    table(["ID / AC", "Level / input hoặc precondition", "Expected result / priority"], [
        ["TC01 / AC3", "Contract/API; request cũ limit=50; baseline schema", "Page/Document đúng fields; schemas không đổi; P0"],
        ["TC02 / AC1", "API; q='  HÓA  ', type=invoice; 2 owners", "Chỉ invoice khớp tên của owner; P0"],
        ["TC03 / AC1", "API; q+type+APPROVED/DRAFT/PROCESSING; FAILED", "AND đúng status; FAILED fixture không có kết quả; P1"],
        ["TC04 / AC1", "API; q='50%_!' và tên gần giống", "Chỉ literal match, không wildcard expansion; P1"],
        ["TC05 / AC1,3", "API; q blank / tên không tồn tại", "Blank = omit; no-match items=[]; P1"],
        ["TC06 / AC2", "API; cùng timestamp, limit=2, giữ q", "Duyệt đủ 5 IDs, đúng thứ tự, không trùng; P0"],
        ["TC07 / AC4", "Negative API; type=letter, status=UNKNOWN", "422 type; 400 INVALID_FILTER status; P0"],
        ["TC08 / AC4", "Negative API; q dài129, limit=NaN/0/101", "400 query/NaN; clamp min1, kết quả nhỏ hợp lệ; P1"],
        ["TC09 / AC4", "Negative API; cursor foreign/missing", "404 NOT_FOUND, không enumerate owner khác; P0"],
        ["TC10 / AC4", "Negative API; không authentication", "401; P0"],
        ["TC11 / AC1,4", "Negative API; q chứa quote/OR/comment", "Chuỗi là dữ liệu; không trả toàn bộ records; P0"],
        ["TC12 / AC4", "Failure API; materialization ném exception", "500 INTERNAL_ERROR; không items/default/detail riêng; P0"],
        ["TC13 / AC5", "HTTP E2E; session thật; 80 workers ×3 waves", "240 responses đúng; p95/errors được ghi; P2"],
        ["TC14-15 / AC4", "Unit; q129 trước DB; q128/no rows", "Reject trước DB / empty page, null cursor; P1"],
        ["TC16-17 / AC2", "API; timestamp khác nhau; 113 rows, limit10000", "createdAt trước id; cap thực tế100 + cursor; P1"],
    ], [26,77,71])

    head("04 / STRATEGY & DATA", "Contract testing có oracle độc lập", "Không dùng schema mới sinh từ patch làm oracle duy nhất.")
    h("Phân tầng test")
    p("Unit: TC14-15 kiểm boundary độ dài trước DB và empty result. Integration/API: TC01-12,16-17 dùng Spring MockMvc, security, service, JPA và Flyway trên H2; chỉ TC12 spy vào materialization để tiêm lỗi. HTTP E2E: TC13 qua random port, CSRF/login/session và SQL thật, không mock response.")
    p("Không thêm OCR/model/training, approval/export cases mới vì slice chỉ đọc filename. Regression suite hiện có vẫn chạy. Chưa có browser search E2E vì chưa triển khai search controls; HTTP E2E không được gọi là browser evidence. Real PostgreSQL vẫn cần bước tiếp theo.")
    h("Chọn dữ liệu")
    p("Synthetic, không dữ liệu train/gold hoặc PII. Mỗi case có namespace owner riêng; 8 documents thuộc owner và 1 foreign trong fixture cơ bản. Tên hóa đơn/biên lai, tên có dấu, khác hoa-thường, %, _, !, chuỗi SQL-looking; revision APPROVED/DRAFT và job PROCESSING có FK hợp lệ. Timestamp cố định, suffix ID xác định. TC17 thêm105 rows để thật sự kiểm cap100; load riêng240 rows.")
    h("Hai lớp bảo vệ compatibility")
    p("Java giữ bản đóng băng v1 schemas (closure DocumentPage/ErrorEnvelope) từ baseline, so với OpenAPI hiện tại và kiểm key sets trên response. scripts/vt029_contract.py dùng Draft202012Validator + FormatChecker validate hai JSON response thực tế được MockMvc xuất ra. Không gọi server giả để tự định nghĩa behavior search.")
    p("Lần validate đầu phát hiện metadataJson='{}' trong fixture AI, trong khi field_metadata phải là array. Giữ schema baseline, sửa fixture thành '[]'; lưu schema-fixture-error.txt. Sau sửa, cả legacy/search response validate thành công.")
    h("Coverage theo phạm vi")
    for item in coverage["methods"]:
        p(item["label"] + ": " + item["line"] + " lines; " + item["branch"] + " branches.")
    p("Bốn nhánh chưa cover: blank type (hai chỗ kiểm), blank status và blank cursor. Đây là khoảng trống của bộ lọc cũ; chưa chạy ma trận đầy đủ collation/Unicode.", small)
    p("Coverage lấy từ full Java regression + JaCoCo 0.8.14. Risk coverage: AC1/2/3/4 có oracle chức năng/contract/fault; AC5 chỉ workload cục bộ. Một mutation bị kill không đồng nghĩa mutation score toàn hệ thống. Không kết luận chất lượng chỉ từ phần trăm coverage.")

    head("05 / RED → CHANGE → GREEN", "Evidence có thể chạy lại", "Full logs trong docs/reviews/vt029-evidence; commands đầy đủ ở README và phụ lục.")
    table(["Mốc", "Evidence và kết quả"], [
        ["Baseline", BASELINE + "; nhánh từ origin/develop local; không dùng nhánh Data làm baseline."],
        ["RED đầu", "12 tests, 7 failures, 0 errors. Có 1 lỗi assumption: invalid type kỳ vọng400, baseline trả422."],
        ["RED đã hiệu chỉnh", "12 tests, 6 failures, 0 errors; production chưa sửa. q bị bỏ qua nên trả rows không khớp; q129 trả200."],
        ["PATCH", "Controller nhận q optional; overload service giữ Java callers cũ; named LIKE với escape ! và lower; OpenAPI chỉ thêm query q."],
        ["GREEN đầu", "12 tests, 0 failures/errors. coverage-tests.txt: 14 tests pass (thêm2 unit). Sau đó bổ sung TC16/17 và sửa fixture metadata."],
        ["Regression cuối", f"{summary[0]} Java tests, {summary[1]} failures, {summary[2]} errors, {summary[3]} skipped; BUILD SUCCESS. Load chạy riêng."],
        ["Schema", "legacy.json và search.json validate PASS theo frozen baseline. Schema Document/Page và các schema dependency không đổi."],
    ], [34,140])
    h("Các lệnh trọng tâm")
    p("cd backend\nbash mvnw -Dtest=DocumentSearchContractTest,DocumentSearchUnitTest test\ncd ..\npython3 scripts/vt029_contract.py", small)
    p("Môi trường thực thi đã dùng JAVA_HOME=/opt/pycharm/jbr; MAVEN_USER_HOME=/tmp/vietdoc-vt029-maven; Maven local repo /tmp/vietdoc-vt029-m2. Maven Wrapper3.9.11; Java target17, runtime25.0.4.1. Dependency được tải bằng bước có xin quyền; không cài service.")
    p("Implementation commit: " + code_commit + ". Người dùng đã cấp quyền commit/push sau khi xem kết quả. Branch trên GitHub có code/test; không tạo PR hoặc merge. File hashes trong source-manifest.json cố định code đã kiểm; peer review độc lập vẫn cần thực hiện.")
    p("Asset regression hiện có: 29 Node tests pass (api1, app24, domain4); log node-regression.txt.", small)

    head("06 / WHO TESTS THE TESTS?", "Mutation và kiểm flaky", "Code lỗi thật có commit ở nhánh riêng; nhánh nộp giữ implementation đúng.")
    h("Deliberate bug bắt buộc")
    p("Mutation bọc lời gọi documents.list trong try/catch RuntimeException và trả new Page<>(List.of(), null). Đây là lỗi nuốt exception, làm outage trông như tìm kiếm không có kết quả.")
    p("TC12 tiêm IllegalStateException khi service materialize row. Controller, ErrorHandler và serialization vẫn chạy thật. Bản đúng trả500 với error.code=INTERNAL_ERROR; bản mutation trả200. Test fail: " + mutation["failure"] + ".")
    p("Kết quả: KILLED, 1 test chạy, 1 assertion failure, 0 compile/runtime setup errors. scripts/vt029_experiment.py kiểm chính failure message và số test để tránh gọi mọi Maven exit≠0 là kill. Hash controller trước/sau giống nhau: " + mutation["controller_sha256_before"], small)
    p("Sau khi có quyền Git, lặp lại mutation trên nhánh local feature/VT-029_mutation_exception_swallow, commit " + mutation_commit + ". TC12 tiếp tục fail500/200 (mutation-branch.txt); quay về nhánh nộp và TC12 pass (restored-tc12.txt). Nhánh mutation không push; mutation.patch cùng script/log nằm ở nhánh nộp để tái lập.")
    h("Flaky risks đã rà soát")
    table(["Nguy cơ", "Kiểm soát và giới hạn"], [
        ["Time/order", "Timestamp cố định, IDs có suffix xác định; TC06 tie và TC16 timestamp khác nhau. Không sleep để chờ dữ liệu, không dựa wall-clock để sort."],
        ["Shared state/random", "Namespace owner riêng từng test, transaction seed có FK; random UUID chỉ chống trùng, không là oracle order. Mutation không chạm source chính."],
        ["Network/concurrency", "Functional cases dùng MockMvc. Load loopback có timeouts/barrier80, verify status+IDs mỗi response, không assert timing trong correctness suite."],
    ], [34,140])
    p("Chưa chạy chiến dịch nhiều seed hoặc lặp hàng trăm lần để ước lượng flaky rate. Nhiều lần focused/regression cho thấy các checks liên quan pass, không đủ để tuyên bố không có flaky tests.")

    head("07 / PERFORMANCE & TRACEABILITY", "80 tác vụ HTTP đồng thời", "Kết quả đo thực tế, không dùng fake latency hoặc thời gian xử lý mảng thay HTTP.")
    p(f"p95 = {load['p95_ms']:.1f} ms | mục tiêu ≤2500 ms | đạt trong workload này: {'CÓ' if load['target_met'] else 'KHÔNG'}", h2)
    p(f"80 threads đồng bộ start barrier, 3 waves, {load['successes']} responses đúng / {load['failures']} lỗi; warmup10. Nearest-rank p95 = phần tử ceil(0.95×N) của latencies đã sort. Duration đo từ send đến khi parse/assert response hoàn tất.")
    p("240 synthetic documents, một session authenticated, invoice/receipt 1:1, một first-page query q=HÓA&type=invoice&limit=20. H2 memory + Flyway V1, Tomcat random port, pool DB mặc định. Login và CSRF có thật nhưng ngoài đoạn đo; 80 tác vụ không đồng nghĩa 80 tài khoản.")
    p(f"Máy: Intel Core i5-11400H 2.70GHz, RAM host khoảng15.3GiB; {load['processors']} processors khả dụng; {load['os']}, JDK {load['jdk']}. Không bật JaCoCo trong phép đo tải. Timestamp UTC: {load['timestamp_utc']}.", small)
    p("Không suy rộng sang PostgreSQL, cold start, large dataset, WAN/TLS, mixed users/filters, browser hoặc sustained arrival rate. Filename contains/LOWER có thể scan; view có query bổ sung cho từng document. Kết quả hiện tại không chứng minh index/capacity production.")
    table(["AC / risk", "Test → file → evidence", "Commit / kết quả"], [
        ["AC1 / search", "TC02-05,11 → DocumentSearchContractTest → java-regression.txt", code_commit[:7] + "; PASS"],
        ["AC2 / order/page", "TC06,16,17 → cùng file → java-regression.txt", code_commit[:7] + "; PASS"],
        ["AC3 / old client", "TC01 + vt029_contract.py → frozen JSON → schema-validation.txt", "Baseline e5326f3; PASS"],
        ["AC4 / errors/owner", "TC07-12 + TC14-15 UnitTest → mutation-result.json", code_commit[:7] + "; PASS/KILLED"],
        ["AC5 / latency", "TC13 → DocumentSearchLoadTest → load-result.json", code_commit[:7] + "; measured"],
    ], [32,100,42])
    p("Các file test ở backend/src/test/java/vn/vietdoc/. README chỉ rõ lệnh và log; source-manifest.json liên kết hash source/test/fixture; git-history.json ghi code/mutation commits. AC3 kiểm trên implementation5405dbc so với baseline e5326f3. Không có PR hoặc merge được claim.", small)

    head("08 / REFLECTION & HANDOFF", "Confidence đến từ evidence", "Bản nháp reflection có AI hỗ trợ; sinh viên phải tự đối chiếu trước khi xác nhận/nộp.")
    for paragraph in REFLECTION.split("\n\n"): p(paragraph)
    p(f"Reflection: {len(REFLECTION.split())} từ theo whitespace count.", small)
    h("Phần còn phải hoàn tất trước nộp")
    p("Sinh viên review patch và các assumption về filename/search, tự chạy lại test và xác nhận cam kết/reflection. Nhánh nộp đã push; lịch sử mutation ở nhánh local riêng và có patch/log tái lập. Không merge khi nhóm chưa review. Chưa có evidence browser E2E hoặc PostgreSQL.")
    p("Nộp một PDF đúng tên BT3_23001863_VT-029.pdf và một URL GitHub branch/PR trên Google Classroom. Báo cáo gồm8 trang chính; hai trang tiếp theo là phụ lục AI Usage Log và evidence.")

    head("PHỤ LỤC A / AI USAGE LOG", "Khai báo việc sử dụng AI", "Phụ lục không tính vào 8 trang nội dung chính.")
    p("Công cụ: Codex trong phiên chat này; shell/apply_patch, Maven/JUnit/MockMvc, Node test runner, Python jsonschema, JaCoCo0.8.14, ReportLab/pypdf/Poppler. Không gọi model API trả phí, không tải model/dataset; không dùng subagent.")
    table(["Input/prompt thực tế", "Output được dùng / review / evidence"], [
        ["Toàn bộ đề VT-029 trong Pasted text.txt; 'Yêu cầu AI giải thích contract và invariants trước'", "Giải thích contract trước code; plan VT-029-plan.md. Agent tự đối chiếu source và bác bỏ Python route/offset pagination. Chưa claim human review."],
        ["AGENTS.md do người dùng cung cấp: Java authority, inspect→criteria→smallest change→verify", "Java API slice, không Python business writes, không inference/model, không migration. Production diff25+/2-."],
        ["User reply: 'Dùng workspace SE2026-T08 hiện tại'", "Dùng origin hiện tại; PDF công khai khác biệt URL so với đề, không tự đổi remote."],
        ["User reply: 'Cho phép commit và push nhánh nộp'", "Commit code/test5405dbc; nhánh mutation riêng3f3d3e8; push nhánh nộp, không merge. Hoàn tất README/evidence và link GitHub."],
        ["Đề: test-first, contract testing; exception swallowing mutation", "12 RED tests trước patch; sửa400→422 vì baseline evidence; thêm unit/boundaries. Frozen schema phát hiện metadata fixture sai, sửa{}→[]."],
        ["Đề: 80 concurrent, p95≤2.5s, coverage/flaky/traceability", "Load HTTP session thật +240 rows; JaCoCo method counters; mutation kill chính xác; limitations ghi trong báo cáo. Không bịa PostgreSQL/browser results."],
        ["Đề: PDF, AI log và reflection250-350 từ", "Agent soạn báo cáo/reflection, render PNG và kiểm bố cục. Sinh viên cần review/xác nhận nội dung cá nhân."],
    ], [65,109])
    h("Hai output có vẻ hợp lý nhưng chưa đáng tin")
    p("(1) Test mặc định invalid type là400: sai so với ContractValidator trả422. (2) Fixture metadata={} trông hợp kiểu JSON nhưng schema yêu cầu array. Hai lỗi đã được execution evidence phát hiện; không dùng lời AI để chứng minh correctness.")
    p("Không có prompt riêng được gửi tới một agent khác. Các draft/correction trong plan là self-review của cùng agent; log này không giả mạo một vòng review của sinh viên hay đồng đội.", small)

    head("PHỤ LỤC B / REPRODUCIBILITY", "Lệnh chạy và log gốc", "README: docs/reviews/VT-029-README.md; evidence: docs/reviews/vt029-evidence/.")
    p("Từ root, đặt JAVA_HOME trỏ JDK17+ của máy. Môi trường này dùng /opt/pycharm/jbr (runtime25, compile release17). bash wrapper vì executable bit trong repo chưa bật.")
    p("cd backend\nbash mvnw -Dtest=DocumentSearchContractTest,DocumentSearchUnitTest test\nbash mvnw test\nbash mvnw -Dvt029.load=true -Dtest=DocumentSearchLoadTest test\ncd ..\npython3 scripts/vt029_contract.py\npython3 scripts/vt029_experiment.py --maven-repo /tmp/vietdoc-vt029-m2 --output docs/reviews/vt029-evidence", small)
    p("Coverage: bash mvnw org.jacoco:jacoco-maven-plugin:0.8.14:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.14:report\nNode: cd backend/src/test/js && node --test", small)
    table(["File evidence", "Nội dung"], [
        ["red.txt", "12 tests /6 failures /0 errors; q đang bị bỏ qua trước patch"],
        ["initial-red-with-assumption-error.txt", "Lần đầu có thêm expectation sai400/422"],
        ["green.txt; coverage-tests.txt", "GREEN12; focused+unit14 pass"],
        ["java-regression.txt; schema-validation.txt", "Regression cuối và validate2 real responses"],
        ["mutation.txt; mutation-result.json", "Assertion500/200 kill, exit1, hashes trước/sau"],
        ["mutation-branch.txt; restored-tc12.txt; mutation.patch", "Mutation trên nhánh local; commit3f3d3e8; TC12 pass sau khi quay về5405dbc"],
        ["load.txt; load-result.json", "HTTP run; toàn bộ240 latencies, p95, errors và environment"],
        ["coverage-summary.json; source-manifest.json", "Line/branch counters theo method; SHA256 file source/test"],
    ], [75,99])
    p("Lưu ý tái lập: RED log là lịch sử trước patch. Để tái tạo RED, cần baseline + bản tests trước source patch trong checkout riêng; không checkout/reset trên workspace có thay đổi. Mutation script chỉ copy backend sang /tmp và xoá bản sao do chính nó tạo.")

    out = ROOT / "output/pdf/BT3_23001863_VT-029.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    def decorate(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#2c5c8d")); canvas.setLineWidth(1.5)
        canvas.line(18*mm, 283*mm, 192*mm, 283*mm)
        canvas.setFont("DV", 8); canvas.setFillColor(colors.HexColor("#5d6f82"))
        canvas.drawString(18*mm, 287*mm, "VIETDOC  /  SOFTWARE QUALITY ENGINEERING")
        canvas.drawString(18*mm, 12*mm, "23001863  ·  VT-029  ·  14/11/2026")
        canvas.drawRightString(192*mm, 12*mm, f"{doc.page} / 10")
    doc = SimpleDocTemplate(str(out), pagesize=(210*mm,297*mm), leftMargin=18*mm,
        rightMargin=18*mm, topMargin=20*mm, bottomMargin=20*mm,
        title="BT3 23001863 VT-029 - Tìm kiếm chứng từ có lọc", author="Nguyễn Tiến Đạt (AI-assisted draft)")
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    reader = PdfReader(out)
    assert len(reader.pages) == 10, f"Unexpected pagination: {len(reader.pages)}"
    for index, expected in enumerate(["01 /", "02 /", "03 /", "04 /", "05 /", "06 /", "07 /", "08 /", "PHỤ LỤC A", "PHỤ LỤC B"]):
        assert expected in reader.pages[index].extract_text(), (index, expected)
    (ROOT / "docs/reviews/VT-029-report.txt").write_text("\n\n".join(source) + "\n")
    print(f"Created {out}: 8 main pages + 2 appendices; reflection {len(REFLECTION.split())} words")


if __name__ == "__main__":
    build()
