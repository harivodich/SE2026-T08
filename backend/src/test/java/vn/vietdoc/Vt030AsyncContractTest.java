package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Entities.Job;
import vn.vietdoc.persistence.Store;

/** Individual VT-030 cases: independent contract oracles, not copied team test results. */
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:vt030;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=15000",
    "vietdoc.worker-enabled=false", "vietdoc.mode=demo",
    "vietdoc.pipeline-manifest=fictional-fixtures.v1", "vietdoc.storage=./target/vt030-storage",
    "logging.level.root=ERROR"
})
@AutoConfigureMockMvc
class Vt030AsyncContractTest {
  @Autowired MockMvc mvc;
  @Autowired AuthService auth;
  @Autowired DocumentService documents;
  @Autowired JobService jobs;
  @Autowired Store store;
  @Autowired AiClient ai;
  @Autowired Json json;
  @Autowired PlatformTransactionManager transactionManager;
  AuthService.Identity owner;
  MockHttpSession session;
  String documentId;

  @BeforeEach
  void fixture() throws Exception {
    String username = "vt030-" + Store.id();
    auth.seed(username, "vt030-fixture-password");
    Map<String, Object> login = auth.login(username, "vt030-fixture-password");
    owner = (AuthService.Identity) login.get("user");
    session = new MockHttpSession();
    session.setAttribute("vietdoc-token", login.get("access_token"));
    documentId = upload("receipt");
  }

  String upload(String type) throws Exception {
    var file = new MockMultipartFile("file", type + ".png", "image/png",
        Files.readAllBytes(Path.of("../samples/" + type + "-demo.png")));
    return documents.upload(owner.id(), file, type, Store.id()).id();
  }

  JsonNode submit(String key) throws Exception {
    var result = mvc.perform(post("/api/v1/documents/{id}/jobs", documentId)
        .session(session).with(csrf()).header("Idempotency-Key", key))
        .andExpect(status().isAccepted()).andReturn();
    return json.read(result.getResponse().getContentAsString());
  }

  long count(String entity, String doc) {
    return new TransactionTemplate(transactionManager).execute(status -> store.em()
        .createQuery("select count(x) from " + entity + " x where x.documentId=:d", Long.class)
        .setParameter("d", doc).getSingleResult());
  }

  @Test
  void tc01AcceptedResponseProvidesCorrectMonitorAndIdentity() throws Exception {
    var result = mvc.perform(post("/api/v1/documents/{id}/jobs", documentId)
        .session(session).with(csrf()).header("Idempotency-Key", "lost-response-01"))
        .andExpect(status().isAccepted()).andReturn();
    JsonNode body = json.read(result.getResponse().getContentAsString());
    String jobId = body.path("id").asText();
    assertFalse(jobId.isBlank());
    assertNotEquals(documentId, jobId);
    assertEquals(documentId, body.path("document_id").asText(), "response field must map to owning document");
    assertEquals("QUEUED", body.path("state").asText());
    assertEquals("WAITING", body.path("stage").asText());
    assertEquals("/api/v1/jobs/" + jobId, result.getResponse().getHeader("Location"), "monitor must address job, not document");
    assertTrue(result.getResponse().getHeader("Cache-Control").contains("no-store"));
    assertEquals(0, count("ExtractionRun", documentId), "202 is acceptance, not inference success");
  }

  @Test
  void tc02PollingUsesNoStoreAndMatchesPersistedProgress() throws Exception {
    JsonNode created = submit("poll-01");
    var response = mvc.perform(get("/api/v1/jobs/{id}", created.path("id").asText()).session(session))
        .andExpect(status().isOk()).andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("no-store")))
        .andExpect(jsonPath("$.document_id").value(documentId))
        .andExpect(jsonPath("$.state").value("QUEUED")).andReturn();
    assertFalse(response.getResponse().getContentAsString().contains("lease_token"));
  }

  @Test
  void tc03LostResponseRetryReusesJobAndCreateAudit() throws Exception {
    JsonNode first = submit("retry-one");
    JsonNode retry = submit("retry-one");
    assertEquals(first.path("id"), retry.path("id"));
    assertEquals(first.path("result_run_id"), retry.path("result_run_id"));
    assertEquals(1, count("Job", documentId));
    assertEquals(2, count("AuditEvent", documentId), "one upload audit and one CREATE_JOB audit only");
  }

  @Test
  void tc04DifferentKeyWhileActiveIsConflictWithoutInsert() throws Exception {
    submit("first-key");
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(session).with(csrf())
        .header("Idempotency-Key", "second-key"))
        .andExpect(status().isConflict()).andExpect(jsonPath("$.error.code").value("ACTIVE_JOB_EXISTS"));
    assertEquals(1, count("Job", documentId));
  }

  @Test
  void tc05MalformedKeyRejectedBeforeSideEffects() throws Exception {
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(session).with(csrf())
        .header("Idempotency-Key", "invalid key /"))
        .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("INVALID_IDEMPOTENCY_KEY"));
    assertEquals(0, count("Job", documentId));
  }

  @Test
  void tc06MissingCsrfIsForbiddenWithoutInsert() throws Exception {
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(session))
        .andExpect(status().isForbidden());
    assertEquals(0, count("Job", documentId));
  }

  @Test
  void tc07AnonymousCannotReadProgress() throws Exception {
    String id = submit("private-job").path("id").asText();
    mvc.perform(get("/api/v1/jobs/{id}", id)).andExpect(status().isUnauthorized());
  }

  @Test
  void tc08ForeignOwnerCannotReadOrEnqueue() throws Exception {
    String id = submit("owner-key").path("id").asText();
    String name = "foreign-" + Store.id();
    auth.seed(name, "vt030-fixture-password");
    var login = auth.login(name, "vt030-fixture-password");
    MockHttpSession foreign = new MockHttpSession();
    foreign.setAttribute("vietdoc-token", login.get("access_token"));
    mvc.perform(get("/api/v1/jobs/{id}", id).session(foreign)).andExpect(status().isNotFound());
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(foreign).with(csrf())
        .header("Idempotency-Key", "owner-key")).andExpect(status().isNotFound());
    assertEquals(1, count("Job", documentId));
  }

  @Test
  void tc09SameKeyOnDifferentDocumentsIsIndependent() throws Exception {
    String first = submit("same-scoped-key").path("id").asText();
    String secondDoc = upload("invoice");
    var second = jobs.create(secondDoc, owner.id(), "same-scoped-key");
    assertNotEquals(first, second.id());
    assertEquals(secondDoc, second.documentId());
    assertEquals(1, count("Job", documentId));
    assertEquals(1, count("Job", secondDoc));
  }

  @Test
  void tc10RetryAfterCompletionDoesNotDuplicateRunOrAudit() throws Exception {
    String id = submit("completed-key").path("id").asText();
    var claim = jobs.claim(id);
    assertNotNull(claim);
    var output = ai.extract(claim); // explicitly synthetic demo fixture, not native OCR
    assertTrue(jobs.complete(claim, output));
    long audits = count("AuditEvent", documentId);
    assertFalse(jobs.complete(claim, output));
    assertEquals(id, submit("completed-key").path("id").asText());
    assertEquals(1, count("Job", documentId));
    assertEquals(1, count("ExtractionRun", documentId));
    assertEquals(audits, count("AuditEvent", documentId));
    mvc.perform(get("/api/v1/jobs/{id}", id).session(session))
        .andExpect(jsonPath("$.state").value("SUCCEEDED"));
  }

  @Test
  void tc11TransientFailureAndStaleCompletionKeepOneLogicalJob() throws Exception {
    String id = submit("transient-key").path("id").asText();
    var old = jobs.claim(id);
    jobs.fail(old, "UPSTREAM_BUSY", "synthetic transient failure", true);
    assertEquals("RETRYING", jobs.get(id, owner.id()).state());
    assertEquals(id, submit("transient-key").path("id").asText());
    var current = jobs.claim(id);
    assertNotEquals(old.token(), current.token());
    assertFalse(jobs.complete(old, ai.extract(old)));
    assertTrue(jobs.complete(current, ai.extract(current)));
    assertEquals(1, count("ExtractionRun", documentId));
  }

  @Test
  void tc12CancelledJobRejectsLateCompletion() throws Exception {
    String id = submit("cancel-key").path("id").asText();
    var claim = jobs.claim(id);
    jobs.cancel(id, owner.id(), "RUNNING");
    assertFalse(jobs.complete(claim, ai.extract(claim)));
    assertEquals(0, count("ExtractionRun", documentId));
    mvc.perform(get("/api/v1/jobs/{id}", id).session(session))
        .andExpect(jsonPath("$.state").value("CANCELLED"));
  }

  @Test
  void tc13ExpiredLeaseIsRecoveredWithoutSleep() throws Exception {
    String id = submit("expired-lease").path("id").asText();
    var old = jobs.claim(id);
    new TransactionTemplate(transactionManager).executeWithoutResult(status -> {
      Job job = store.job(id, true);
      job.leaseUntil = Instant.EPOCH;
    });
    jobs.recover();
    assertEquals("RETRYING", jobs.get(id, owner.id()).state());
    var current = jobs.claim(id);
    assertFalse(jobs.complete(old, ai.extract(old)));
    assertTrue(jobs.complete(current, ai.extract(current)));
    assertEquals(1, count("ExtractionRun", documentId));
  }

  @Test
  void tc14NoKeyCreatesOnceThenActiveConflict() throws Exception {
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(session).with(csrf()))
        .andExpect(status().isAccepted());
    mvc.perform(post("/api/v1/documents/{id}/jobs", documentId).session(session).with(csrf()))
        .andExpect(status().isConflict());
    assertEquals(1, count("Job", documentId));
  }

  @Test
  void tc15FailedJobRetryReturnsOriginalTerminalState() throws Exception {
    String id = submit("permanent-key").path("id").asText();
    var claim = jobs.claim(id);
    jobs.fail(claim, "OUTPUT_INVALID", "synthetic invalid output", false);
    JsonNode retried = submit("permanent-key");
    assertEquals(id, retried.path("id").asText());
    assertEquals("FAILED", retried.path("state").asText());
    assertEquals(1, count("Job", documentId));
    assertEquals(0, count("ExtractionRun", documentId));
  }
}
