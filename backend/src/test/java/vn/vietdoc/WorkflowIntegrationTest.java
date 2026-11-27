package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.*;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.*;
import vn.vietdoc.document.*;
import vn.vietdoc.export.*;
import vn.vietdoc.integration.*;
import vn.vietdoc.job.*;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.*;
import vn.vietdoc.review.*;

@SpringBootTest(
    properties = {
      "spring.datasource.url=jdbc:h2:mem:workflow;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
      "vietdoc.worker-enabled=false",
      "vietdoc.mode=demo",
      "vietdoc.pipeline-manifest=fictional-fixtures.v1",
      "vietdoc.storage=./target/test-storage"
    })
@AutoConfigureMockMvc
class WorkflowIntegrationTest {
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired ReviewService review;
  @Autowired ExportService exports;
  @Autowired ContractValidator contracts;
  @Autowired AiClient ai;
  @Autowired Json json;
  @Autowired Store store;
  @Autowired MockMvc mvc;
  @Autowired PlatformTransactionManager tm;
  AuthService.Identity owner, other;

  @BeforeEach
  void users() {
    owner = seed("owner-" + Store.id());
    other = seed("other-" + Store.id());
  }

  AuthService.Identity seed(String name) {
    auth.seed(name, "integration-password");
    return (AuthService.Identity) auth.login(name, "integration-password").get("user");
  }

  MockMultipartFile sample(String type, String extension) throws Exception {
    return new MockMultipartFile(
        "file",
        type + "-demo." + extension,
        extension.equals("pdf") ? "application/pdf" : "image/png",
        Files.readAllBytes(Path.of("../samples/" + type + "-demo." + extension)));
  }

  DocumentService.DocumentView extracted(String type) throws Exception {
    var d = documents.upload(owner.id(), sample(type, "png"), type, Store.id());
    var job = jobs.create(d.id(), owner.id(), Store.id());
    var c = jobs.claim(job.id());
    assertNotNull(c);
    assertTrue(jobs.complete(c, ai.extract(c)));
    return documents.get(d.id(), owner.id());
  }

  List<String> rowIds(DocumentService.DocumentView d) {
    List<String> result = new ArrayList<>();
    d.head().rowIds().forEach(v -> result.add(v.asText()));
    return result;
  }

  List<String> warnings(DocumentService.DocumentView d) {
    List<String> result = new ArrayList<>();
    d.head()
        .issues()
        .forEach(
            i -> {
              if (i.path("severity").asText().equals("warning")) result.add(i.path("id").asText());
            });
    return result;
  }

  Requests.Save edit(DocumentService.DocumentView d, String total) {
    ObjectNode payload = d.head().payload().deepCopy();
    payload.put("total_amount", total);
    return new Requests.Save(
        d.headRevisionId(),
        d.version(),
        payload,
        "Đối chiếu ảnh và sửa tổng tiền",
        rowIds(d),
        List.of());
  }

  DocumentService.DocumentView approve(DocumentService.DocumentView d) {
    return review.approve(
        d.id(),
        owner.id(),
        new Requests.Approve(
            d.headRevisionId(), d.version(), true, warnings(d), "Đã đối chiếu toàn bộ chứng từ"));
  }

  @Test
  void reviewAndApprovalRetryReplayOriginalResponseWithoutDuplicateRevision() throws Exception {
    var initial = extracted("receipt");
    var saveInput = edit(initial, "46000");
    String saveKey = Store.id();
    var saved = review.save(initial.id(), owner.id(), saveInput, saveKey);
    var replayed = review.save(initial.id(), owner.id(), saveInput, saveKey);
    assertEquals(saved.headRevisionId(), replayed.headRevisionId());
    assertEquals(saved.version(), replayed.version());
    assertEquals(2, documents.revisions(initial.id(), owner.id()).items().size());

    var differentInput = edit(initial, "47000");
    assertEquals("IDEMPOTENCY_CONFLICT", assertThrows(ApiException.class,
        () -> review.save(initial.id(), owner.id(), differentInput, saveKey)).code);
    var approval = new Requests.Approve(saved.headRevisionId(), saved.version(), true,
        warnings(saved), "Đã đối chiếu toàn bộ chứng từ");
    String approveKey = Store.id();
    var approved = review.approve(initial.id(), owner.id(), approval, approveKey);
    var approvalReplay = review.approve(initial.id(), owner.id(), approval, approveKey);
    assertEquals(approved.version(), approvalReplay.version());
    assertEquals(approved.headRevisionId(), approvalReplay.headRevisionId());
    assertEquals(approved.version(), documents.get(initial.id(), owner.id()).version());
    assertEquals(saved.version(), review.save(initial.id(), owner.id(), saveInput, saveKey).version());
  }

  @Test
  void receiptSaveApproveExportAndRerunPreserveSnapshots() throws Exception {
    var d = extracted("receipt");
    String prediction = json.write(documents.runs(d.id(), owner.id()).items().get(0).result());
    assertEquals(
        409,
        assertThrows(
                ApiException.class,
                () ->
                    exports.create(
                        d.id(), owner.id(), new Requests.Export(d.headRevisionId(), "json")))
            .status);
    var saved = review.save(d.id(), owner.id(), edit(d, "46000"));
    assertNotEquals(d.headRevisionId(), saved.headRevisionId());
    assertEquals(
        prediction, json.write(documents.runs(d.id(), owner.id()).items().get(0).result()));
    var approved = approve(saved);
    var export =
        exports.create(d.id(), owner.id(), new Requests.Export(approved.headRevisionId(), "json"));
    byte[] bytes = exports.download(export.id(), owner.id());
    assertEquals(export.sha256(), Json.sha256(bytes));
    assertEquals(
        export.id(),
        exports
            .create(d.id(), owner.id(), new Requests.Export(approved.headRevisionId(), "json"))
            .id());
    var job = jobs.create(d.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    assertTrue(jobs.complete(claim, ai.extract(claim)));
    assertFalse(jobs.complete(claim, ai.extract(claim)));
    var after = documents.get(d.id(), owner.id());
    assertEquals(approved.headRevisionId(), after.headRevisionId());
    assertEquals("46000", after.head().payload().path("total_amount").asText());
    var adopted =
        review.adopt(
            d.id(),
            owner.id(),
            new Requests.Adopt(
                claim.runId(), after.headRevisionId(), after.version(), "Chọn kết quả mới"));
    assertEquals("DRAFT", adopted.head().state());
    assertArrayEquals(bytes, exports.download(export.id(), owner.id()));
    assertEquals(2, documents.runs(d.id(), owner.id()).items().size());
  }

  @Test
  void invoiceAndPdfUploadWork() throws Exception {
    var d = documents.upload(owner.id(), sample("invoice", "pdf"), "invoice", Store.id());
    assertTrue(d.imageWidth() > 0);
    assertTrue(documents.page(d.id(), owner.id()).length > 0);
    var j = jobs.create(d.id(), owner.id(), Store.id());
    var c = jobs.claim(j.id());
    assertTrue(jobs.complete(c, ai.extract(c)));
    var approved = approve(documents.get(d.id(), owner.id()));
    var exported =
        exports.create(d.id(), owner.id(), new Requests.Export(approved.headRevisionId(), "json"));
    JsonNode result = json.mapper.readTree(exports.download(exported.id(), owner.id()));
    assertEquals("invoice.v1", result.path("schema_version").asText());
    assertEquals("110000", result.path("payload").path("total_amount").asText());
  }

  @Test
  void twoConcurrentSavesHaveOneWinnerAndNoOrphanRevision() throws Exception {
    var d = extracted("receipt");
    var request = edit(d, "47000");
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(2);
    Callable<Integer> task =
        () -> {
          start.await();
          try {
            review.save(d.id(), owner.id(), request);
            return 201;
          } catch (ApiException e) {
            return e.status;
          }
        };
    Future<Integer> a = pool.submit(task), b = pool.submit(task);
    start.countDown();
    List<Integer> result = List.of(a.get(15, TimeUnit.SECONDS), b.get(15, TimeUnit.SECONDS));
    pool.shutdownNow();
    assertTrue(result.contains(201));
    assertTrue(result.contains(409));
    assertEquals(2, documents.revisions(d.id(), owner.id()).items().size());
    assertEquals(
        1,
        documents.audit(d.id(), owner.id()).items().stream()
            .filter(e -> e.action().equals("SAVE"))
            .count());
  }

  @Test
  void saveVersusApprovalHasOneWinner() throws Exception {
    var d = extracted("receipt");
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch start = new CountDownLatch(1);
    Future<Integer> a =
        pool.submit(
            () -> {
              start.await();
              try {
                review.save(d.id(), owner.id(), edit(d, "48000"));
                return 201;
              } catch (ApiException e) {
                return e.status;
              }
            });
    Future<Integer> b =
        pool.submit(
            () -> {
              start.await();
              try {
                approve(d);
                return 201;
              } catch (ApiException e) {
                return e.status;
              }
            });
    start.countDown();
    List<Integer> result = List.of(a.get(15, TimeUnit.SECONDS), b.get(15, TimeUnit.SECONDS));
    pool.shutdownNow();
    assertTrue(result.contains(201));
    assertTrue(result.contains(409));
  }

  @Test
  void ownershipCoversEveryObject() throws Exception {
    var d = approve(extracted("receipt"));
    var e = exports.create(d.id(), owner.id(), new Requests.Export(d.headRevisionId(), "json"));
    String run = documents.runs(d.id(), owner.id()).items().get(0).id();
    for (Runnable call :
        List.<Runnable>of(
            () -> documents.get(d.id(), other.id()),
            () -> documents.page(d.id(), other.id()),
            () -> documents.revision(d.headRevisionId(), other.id()),
            () -> documents.run(run, other.id()),
            () -> documents.audit(d.id(), other.id()),
            () -> exports.download(e.id(), other.id()),
            () -> jobs.get(d.job().id(), other.id()),
            () -> review.save(d.id(), other.id(), edit(d, "1"))))
      assertEquals(404, assertThrows(ApiException.class, call::run).status);
    assertTrue(documents.list(other.id(), null, null, null, 20).items().isEmpty());
  }

  @Test
  void validationKeepsNullAndRejectsMoneyNumbersUnknownKeysAndBadDates() throws Exception {
    ObjectNode payload = (ObjectNode) contracts.empty("receipt");
    contracts.business("receipt", payload);
    payload.put("total_amount", 123);
    assertThrows(ApiException.class, () -> contracts.business("receipt", payload));
    payload.put("total_amount", "01");
    assertThrows(ApiException.class, () -> contracts.business("receipt", payload));
    payload.put("total_amount", "123");
    payload.put("extra", "x");
    assertThrows(ApiException.class, () -> contracts.business("receipt", payload));
    payload.remove("extra");
    payload.remove("merchant_name");
    assertThrows(ApiException.class, () -> contracts.business("receipt", payload));
    var d = extracted("receipt");
    ObjectNode invalid = d.head().payload().deepCopy();
    invalid.put("transaction_date", "2026-02-31");
    var saved =
        review.save(
            d.id(),
            owner.id(),
            new Requests.Save(
                d.headRevisionId(),
                d.version(),
                invalid,
                "Ghi lại để kiểm tra",
                rowIds(d),
                List.of()));
    assertEquals("APPROVAL_BLOCKED", assertThrows(ApiException.class, () -> approve(saved)).code);
  }

  @Test
  void webShellAndAssetsArePublicWhileApiStillRequiresAuthentication() throws Exception {
    mvc.perform(get("/"))
        .andExpect(status().isOk());
    mvc.perform(get("/index.html"))
        .andExpect(status().isOk())
        .andExpect(content().string(org.hamcrest.Matchers.containsString("VietDoc")))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"vietdoc-mode\" content=\"demo\"")));
    mvc.perform(get("/app.js"))
        .andExpect(status().isOk())
        .andExpect(content().string(org.hamcrest.Matchers.containsString("uploadAndProcess")));
    mvc.perform(get("/api/v1/documents")).andExpect(status().isUnauthorized());
  }

  @Test
  void partialOcrPreservesReadableFieldsAndWarningButCannotBypassMissingTotal() throws Exception {
    var uploaded = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var job = jobs.create(uploaded.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    ObjectNode prediction = ai.extract(claim).deepCopy();
    ObjectNode payload = (ObjectNode) prediction.path("payload");
    String readableMerchant = payload.path("merchant_name").asText();
    payload.putNull("total_amount");
    prediction.putArray("field_metadata");
    ObjectNode unreadable = ((ArrayNode) prediction.path("issues")).addObject();
    unreadable.put("id", "OCR_UNREADABLE_REGIONS:/");
    unreadable.put("code", "OCR_UNREADABLE_REGIONS");
    unreadable.put("severity", "warning");
    unreadable.putArray("paths").add("/").add("/total_amount");
    unreadable.put("message", "Một vùng nguồn chưa đọc được; cần đối chiếu ảnh.");
    assertTrue(jobs.complete(claim, prediction));

    var missing = documents.get(uploaded.id(), owner.id());
    assertEquals(readableMerchant, missing.head().payload().path("merchant_name").asText());
    assertTrue(warnings(missing).contains("OCR_UNREADABLE_REGIONS:/"));
    assertEquals("APPROVAL_BLOCKED", assertThrows(ApiException.class, () -> approve(missing)).code);

    var corrected = review.save(uploaded.id(), owner.id(), edit(missing, "45000"));
    assertTrue(warnings(corrected).contains("OCR_UNREADABLE_REGIONS:/"));
    assertEquals("REVIEW_CONFIRMATION_REQUIRED", assertThrows(ApiException.class, () ->
        review.approve(corrected.id(), owner.id(), new Requests.Approve(
            corrected.headRevisionId(), corrected.version(), true, List.of(), "Đã sửa tổng"))).code);
    assertEquals("APPROVED", approve(corrected).head().state());
    assertTrue(documents.runs(uploaded.id(), owner.id()).items().get(0).result()
        .path("payload").path("total_amount").isNull());
  }

  @Test
  void missingTotalAndUnacknowledgedWarningsCannotApprove() throws Exception {
    var d = extracted("receipt");
    ObjectNode payload = d.head().payload().deepCopy();
    payload.putNull("total_amount");
    var missing =
        review.save(
            d.id(),
            owner.id(),
            new Requests.Save(
                d.headRevisionId(),
                d.version(),
                payload,
                "Tổng tiền chưa rõ",
                rowIds(d),
                List.of()));
    assertEquals("APPROVAL_BLOCKED", assertThrows(ApiException.class, () -> approve(missing)).code);
    var restored = review.save(d.id(), owner.id(), edit(missing, "45000"));
    ObjectNode blank = restored.head().payload().deepCopy();
    blank.putNull("merchant_name");
    var warning =
        review.save(
            d.id(),
            owner.id(),
            new Requests.Save(
                restored.headRevisionId(),
                restored.version(),
                blank,
                "Không có tên cửa hàng",
                rowIds(restored),
                List.of()));
    assertEquals(
        "REVIEW_CONFIRMATION_REQUIRED",
        assertThrows(
                ApiException.class,
                () ->
                    review.approve(
                        d.id(),
                        owner.id(),
                        new Requests.Approve(
                            warning.headRevisionId(),
                            warning.version(),
                            true,
                            List.of(),
                            "Đối chiếu")))
            .code);
    assertEquals("APPROVED", approve(warning).head().state());
  }

  @Test
  void idempotencyAndCancellationFenceLateCompletion() throws Exception {
    String uploadKey = Store.id();
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", uploadKey);
    assertEquals(
        d.id(), documents.upload(owner.id(), sample("receipt", "png"), "receipt", uploadKey).id());
    assertEquals(
        409,
        assertThrows(
                ApiException.class,
                () -> documents.upload(owner.id(), sample("invoice", "png"), "invoice", uploadKey))
            .status);
    String key = Store.id();
    var j = jobs.create(d.id(), owner.id(), key);
    assertEquals(j.id(), jobs.create(d.id(), owner.id(), key).id());
    assertEquals(
        "ACTIVE_JOB_EXISTS",
        assertThrows(ApiException.class, () -> jobs.create(d.id(), owner.id(), Store.id())).code);
    var c = jobs.claim(j.id());
    var cancelled = jobs.cancel(j.id(), owner.id(), "RUNNING");
    assertEquals("CANCELLED", cancelled.state());
    assertEquals("CANCELLED", jobs.cancel(j.id(), owner.id(), "RUNNING").state());
    assertFalse(jobs.complete(c, ai.extract(c)));
    assertNull(documents.get(d.id(), owner.id()).head());
    var completed = extracted("invoice").job();
    assertEquals("JOB_TERMINAL",
        assertThrows(ApiException.class, () -> jobs.cancel(completed.id(), owner.id(), "RUNNING")).code);
  }

  @Test
  void expiredLeaseCanRecoverAndOldWorkerCannotCommit() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var j = jobs.create(d.id(), owner.id(), Store.id());
    var old = jobs.claim(j.id());
    new TransactionTemplate(tm)
        .execute(
            s -> {
              var job = store.job(j.id(), true);
              job.leaseUntil = Instant.now().minusSeconds(5);
              return null;
            });
    jobs.recover();
    var current = jobs.claim(j.id());
    assertNotNull(current);
    assertNotEquals(old.token(), current.token());
    assertNotEquals(old.attemptId(), current.attemptId());
    assertNotEquals(old.runId(), current.runId());
    assertFalse(jobs.complete(old, ai.extract(old)));
    assertTrue(jobs.complete(current, ai.extract(current)));
  }

  @Test
  void exhaustedLeaseRecoveryReportsAttemptLimitAndRejectsLateCompletion() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var j = jobs.create(d.id(), owner.id(), Store.id());
    var claim = jobs.claim(j.id());
    new TransactionTemplate(tm).execute(s -> {
      var job = store.job(j.id(), true);
      job.attempts = 3;
      job.leaseUntil = Instant.now().minusSeconds(1);
      return null;
    });
    jobs.recover();
    var failed = jobs.get(j.id(), owner.id());
    assertEquals("FAILED", failed.state());
    assertEquals("ATTEMPTS_EXHAUSTED", failed.errorCode());
    assertFalse(jobs.complete(claim, ai.extract(claim)));
    assertTrue(documents.runs(d.id(), owner.id()).items().isEmpty());
  }

  @Test
  void busyRetryWaitsAndMintsNewAttemptAndRunWithoutResettingDeadline() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var j = jobs.create(d.id(), owner.id(), Store.id());
    var first = jobs.claim(j.id());
    var deadline = first.deadline();
    Instant earliest = Instant.now().plusSeconds(20);
    jobs.fail(first, "AI_BUSY", "Compute đang bận.", true, 20);
    assertEquals("RETRYING", jobs.get(j.id(), owner.id()).state());
    assertEquals(false, new TransactionTemplate(tm).execute(s ->
        store.job(j.id(), false).nextAttemptAt.isBefore(earliest)));
    assertNull(jobs.claim(j.id()));
    assertFalse(jobs.available().contains(j.id()));
    new TransactionTemplate(tm).execute(s -> {
      store.job(j.id(), true).nextAttemptAt = Instant.now().minusSeconds(1);
      return null;
    });
    var second = jobs.claim(j.id());
    assertNotNull(second);
    assertEquals(deadline, second.deadline());
    assertNotEquals(first.attemptId(), second.attemptId());
    assertNotEquals(first.runId(), second.runId());
    assertFalse(jobs.complete(first, ai.extract(first)));
    assertTrue(jobs.complete(second, ai.extract(second)));
  }

  @Test
  void invalidMediaAndMultipagePdfAreRejected() throws Exception {
    assertEquals(
        415,
        assertThrows(
                ApiException.class,
                () ->
                    documents.upload(
                        owner.id(),
                        new MockMultipartFile("file", "bad.png", "image/png", "hello".getBytes()),
                        "receipt",
                        Store.id()))
            .status);
    byte[] multi;
    try (var pdf = new org.apache.pdfbox.pdmodel.PDDocument();
        var bytes = new java.io.ByteArrayOutputStream()) {
      pdf.addPage(new org.apache.pdfbox.pdmodel.PDPage());
      pdf.addPage(new org.apache.pdfbox.pdmodel.PDPage());
      pdf.save(bytes);
      multi = bytes.toByteArray();
    }
    assertEquals(
        "PROFILE_UNSUPPORTED",
        assertThrows(
                ApiException.class,
                () ->
                    documents.upload(
                        owner.id(),
                        new MockMultipartFile("file", "two.pdf", "application/pdf", multi),
                        "invoice",
                        Store.id()))
            .code);
  }

  @Test
  void realHttpApiReturnsTypedErrorsAndRevokesSessions() throws Exception {
    mvc.perform(get("/"))
        .andExpect(status().isOk())
        .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"_csrf\"")));
    mvc.perform(get("/api/v1/documents"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("UNAUTHENTICATED"));
    mvc.perform(
            post("/api/v1/auth/session")
                .with(csrf())
                .contentType("application/json")
                .content(json.write(Map.of("username", owner.username(), "password", "wrong"))))
        .andExpect(status().isUnauthorized());
    var login =
        mvc.perform(
                 post("/api/v1/auth/session")
                     .with(csrf())
                    .contentType("application/json")
                    .content(
                        json.write(
                            Map.of(
                                "username", owner.username(), "password", "integration-password"))))
            .andExpect(status().isOk())
             .andReturn();
    String response = login.getResponse().getContentAsString();
    assertFalse(json.read(response).has("access_token"));
    MockHttpSession session = (MockHttpSession) login.getRequest().getSession(false);
    assertNotNull(session);
    mvc.perform(
            multipart("/api/v1/documents")
                .file(sample("receipt", "png"))
                .session(session)
                .param("document_type", "receipt"))
        .andExpect(status().isForbidden());
    mvc.perform(
            multipart("/api/v1/documents")
                 .file(sample("receipt", "png"))
                 .session(session)
                 .with(csrf())
                 .param("document_type", "receipt"))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.document_type").value("receipt"));
    mvc.perform(post("/api/v1/auth/logout").session(session).with(csrf()))
        .andExpect(status().isOk());
    mvc.perform(get("/api/v1/documents").session(session))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void thymeleafCsrfTokenAuthenticatesSessionAndRefreshesAfterLogout() throws Exception {
    var page = mvc.perform(get("/")).andExpect(status().isOk()).andReturn();
    var pattern = java.util.regex.Pattern.compile("name=\"_csrf\"[^>]*content=\"([^\"]+)\"");
    var matcher = pattern.matcher(page.getResponse().getContentAsString());
    assertTrue(matcher.find());
    String token = matcher.group(1);
    MockHttpSession session = (MockHttpSession) page.getRequest().getSession(false);
    assertNotNull(session);
    mvc.perform(post("/api/v1/auth/session")
            .session(session)
            .header("X-CSRF-TOKEN", token)
            .contentType("application/json")
            .content(json.write(Map.of("username", owner.username(), "password", "integration-password"))))
        .andExpect(status().isOk());
    mvc.perform(get("/api/v1/auth/me").session(session)).andExpect(status().isOk());
    String afterLogin = json.read(mvc.perform(get("/api/v1/auth/csrf").session(session))
        .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
        .path("token").asText();
    mvc.perform(post("/api/v1/auth/logout").session(session).header("X-CSRF-TOKEN", afterLogin))
        .andExpect(status().isOk());
    mvc.perform(get("/api/v1/auth/csrf"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.token").isNotEmpty());
  }

  @Test
  void arithmeticWarningsAreRecomputedWhenAnOperandChanges() throws Exception {
    var initial = extracted("invoice");
    ObjectNode payload = initial.head().payload().deepCopy();
    payload.put("subtotal", "100");
    payload.put("tax_amount", "10");
    payload.put("discount_amount", "0");
    payload.put("total_amount", "120");
    var mismatch = review.save(initial.id(), owner.id(),
        new Requests.Save(initial.headRevisionId(), initial.version(), payload,
            "Đối chiếu phép tính", rowIds(initial), List.of("/subtotal", "/tax_amount", "/discount_amount", "/total_amount")));
    assertTrue(mismatch.head().issues().toString().contains("TOTAL_ARITHMETIC"));
    ObjectNode corrected = mismatch.head().payload().deepCopy();
    corrected.put("subtotal", "110");
    var saved = review.save(initial.id(), owner.id(),
        new Requests.Save(mismatch.headRevisionId(), mismatch.version(), corrected,
            "Sửa tiền trước thuế theo ảnh", rowIds(mismatch), List.of("/subtotal")));
    assertFalse(saved.head().issues().toString().contains("TOTAL_ARITHMETIC"));
  }

  @Test
  void extractionRejectsDegenerateAndCrossedSourceQuads() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var job = jobs.create(d.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    ObjectNode result = (ObjectNode) ai.extract(claim);
    ObjectNode field = metadata("/total_amount", "");
    ArrayNode regions = (ArrayNode) field.get("source_regions");
    ObjectNode region = regions.addObject();
    region.put("page", 0);
    region.putArray("ocr_block_ids");
    ArrayNode quad = region.putArray("quad");
    for (int i = 0; i < 4; i++) quad.addArray().add(0.2).add(0.2);
    ((ArrayNode) result.get("field_metadata")).add(field);
    assertEquals("CONTRACT_INVALID", assertThrows(ApiException.class,
        () -> contracts.extraction(claim.type(), claim.runId(), claim.id(), claim.manifest(), result)).code);
    quad.removeAll();
    quad.addArray().add(0.1).add(0.1);
    quad.addArray().add(0.9).add(0.9);
    quad.addArray().add(0.9).add(0.1);
    quad.addArray().add(0.1).add(0.9);
    assertEquals("CONTRACT_INVALID", assertThrows(ApiException.class,
        () -> contracts.extraction(claim.type(), claim.runId(), claim.id(), claim.manifest(), result)).code);
  }

  @Test
  void ownerAdmissionLockKeepsConcurrentJobsWithinCap() throws Exception {
    List<DocumentService.DocumentView> uploads = new ArrayList<>();
    for (int i = 0; i < 6; i++)
      uploads.add(documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id()));
    for (int i = 0; i < 4; i++) jobs.create(uploads.get(i).id(), owner.id(), Store.id());
    var executor = Executors.newFixedThreadPool(2);
    var ready = new CountDownLatch(2);
    var go = new CountDownLatch(1);
    try {
      List<Future<String>> outcomes = new ArrayList<>();
      for (int i = 4; i < 6; i++) {
        String id = uploads.get(i).id();
        outcomes.add(executor.submit(() -> {
          ready.countDown();
          go.await();
          try {
            jobs.create(id, owner.id(), Store.id());
            return "accepted";
          } catch (ApiException e) {
            return e.code;
          }
        }));
      }
      assertTrue(ready.await(5, TimeUnit.SECONDS));
      go.countDown();
      List<String> results = List.of(outcomes.get(0).get(10, TimeUnit.SECONDS),
          outcomes.get(1).get(10, TimeUnit.SECONDS));
      assertEquals(1, results.stream().filter("accepted"::equals).count());
      assertEquals(1, results.stream().filter("JOB_LIMIT"::equals).count());
    } finally {
      go.countDown();
      executor.shutdownNow();
    }
  }

  ObjectNode metadata(String path, String flag) {
    ObjectNode m = json.mapper.createObjectNode();
    m.put("path", path);
    m.putNull("raw_value");
    m.put("value_origin", "prediction");
    m.putArray("source_regions");
    m.putNull("ocr_score");
    m.putNull("confidence");
    m.putNull("confidence_method");
    ArrayNode flags = m.putArray("review_flags");
    if (flag != null) flags.add(flag);
    return m;
  }

  @Test
  void ambiguousTotalRequiresExplicitHumanReviewAndMetadataStaysHonest() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var job = jobs.create(d.id(), owner.id(), Store.id());
    var c = jobs.claim(job.id());
    ObjectNode result = (ObjectNode) ai.extract(c);
    ((ArrayNode) result.get("field_metadata")).add(metadata("/total_amount", "ambiguous"));
    assertTrue(jobs.complete(c, result));
    var initial = documents.get(d.id(), owner.id());
    assertEquals("APPROVAL_BLOCKED", assertThrows(ApiException.class, () -> approve(initial)).code);
    var saved =
        review.save(
            d.id(),
            owner.id(),
            new Requests.Save(
                initial.headRevisionId(),
                initial.version(),
                initial.head().payload(),
                "Đã đối chiếu tổng tiền",
                rowIds(initial),
                List.of("/total_amount")));
    JsonNode total =
        saved.head().fieldMetadata().findParents("path").stream()
            .filter(m -> m.path("path").asText().equals("/total_amount"))
            .findFirst()
            .orElseThrow();
    assertEquals("human", total.path("value_origin").asText());
    assertTrue(total.path("confidence").isNull());
    assertEquals("APPROVED", approve(saved).head().state());
  }

  @Test
  void actualHttpWorkerClientSendsPinnedIdsAndReceivesValidatedResult() throws Exception {
    var d = documents.upload(owner.id(), sample("receipt", "png"), "receipt", Store.id());
    var job = jobs.create(d.id(), owner.id(), Store.id());
    var claim = jobs.claim(job.id());
    JsonNode expected = ai.extract(claim);
    var envelope = json.mapper.createObjectNode();
    envelope.put("contract_version", 1);
    envelope.put("attempt_id", claim.attemptId());
    envelope.set("result", expected);
    String prefix = "attempts/" + claim.id() + "/" + claim.attemptId() + "/";
    var canonical = envelope.putObject("canonical_page");
    canonical.put("page", 0);
    canonical.put("width", 10);
    canonical.put("height", 10);
    canonical.put("asset_key", prefix + "canonical.png");
    canonical.put("sha256", "0".repeat(64));
    var artifacts = envelope.putArray("artifacts");
    var page = artifacts.addObject();
    page.put("kind", "canonical_page");
    page.put("asset_key", prefix + "canonical.png");
    page.put("sha256", "0".repeat(64));
    page.put("size_bytes", 10);
    page.put("media_type", "image/png");
    var ocr = artifacts.addObject();
    ocr.put("kind", "ocr");
    ocr.put("asset_key", prefix + "ocr.json");
    ocr.put("sha256", "1".repeat(64));
    ocr.put("size_bytes", 10);
    ocr.put("media_type", "application/json");
    var server =
        com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
    java.util.concurrent.atomic.AtomicReference<String> received =
        new java.util.concurrent.atomic.AtomicReference<>();
    server.createContext(
        "/internal/v1/compute",
        exchange -> {
          received.set(
              new String(
                  exchange.getRequestBody().readAllBytes(),
                  java.nio.charset.StandardCharsets.ISO_8859_1));
          if (!"Bearer test-worker-secret"
              .equals(exchange.getRequestHeaders().getFirst("Authorization"))) {
            exchange.sendResponseHeaders(401, -1);
            exchange.close();
            return;
          }
          byte[] body = json.write(envelope).getBytes(java.nio.charset.StandardCharsets.UTF_8);
          exchange.getResponseHeaders().set("Content-Type", "application/json");
          exchange.sendResponseHeaders(200, body.length);
          exchange.getResponseBody().write(body);
          exchange.close();
        });
    server.start();
    try {
      AiClient http =
          new AiClient(
              json,
              contracts,
              new PrivateStorage("./target/test-storage", 20000000),
              "http://127.0.0.1:" + server.getAddress().getPort() + "/internal/v1/compute",
              "test-worker-secret");
      var request =
          new JobService.Claim(
              claim.id(),
              claim.documentId(),
              claim.runId(),
              claim.token(),
              claim.attemptId(),
              claim.type(),
              claim.hash(),
              "http",
              claim.manifest(),
              claim.deadline());
      JsonNode actual = http.compute(request);
      assertTrue(received.get().contains(claim.id()));
      assertTrue(received.get().contains(claim.manifest()));
      assertTrue(received.get().contains(claim.attemptId()));
      assertTrue(received.get().contains("remaining_budget_ms"));
      assertTrue(received.get().contains("contract_version"));
      assertTrue(received.get().contains("name=\"file\""));
      assertTrue(jobs.complete(claim, actual.path("result")));
    } finally {
      server.stop(0);
    }
  }
}
