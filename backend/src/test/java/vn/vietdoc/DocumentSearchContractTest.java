package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.persistence.Entities.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:vt029;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
    "vietdoc.worker-enabled=false", "vietdoc.mode=manual",
    "vietdoc.storage=./target/vt029-storage"})
@AutoConfigureMockMvc
class DocumentSearchContractTest {
  @Autowired MockMvc mvc;
  @Autowired ObjectMapper mapper;
  @Autowired Store store;
  @Autowired AuthService auth;
  @Autowired PlatformTransactionManager tm;
  @Autowired vn.vietdoc.common.Json json;
  @Autowired vn.vietdoc.contracts.ContractValidator contracts;
  @MockitoSpyBean DocumentService documents;
  AuthService.Identity owner, foreign;
  String prefix;
  final Instant timestamp = Instant.parse("2026-01-02T03:04:05Z");

  @BeforeEach void fixture() {
    // Unique namespace per test, fixed timestamps and deterministic suffixes.
    prefix = UUID.randomUUID().toString().substring(0, 24);
    owner = user(prefix + "-owner"); foreign = user(prefix + "-foreign");
    new TransactionTemplate(tm).executeWithoutResult(tx -> {
      row("a", owner.id(), "HÓA đơn Hà Nội.png", "invoice", null);
      row("b", owner.id(), "hóa đơn Hà Nội.png", "receipt", null);
      row("c", owner.id(), "khác.png", "invoice", null);
      row("d", owner.id(), "giảm 50%_!.png", "invoice", null);
      row("e", owner.id(), "giảm 500xx.png", "invoice", null);
      row("f", foreign.id(), "HÓA đơn Hà Nội.png", "invoice", null);
      row("g", owner.id(), "HÓA đơn Hà Nội.png", "invoice", "APPROVED");
      row("h", owner.id(), "HÓA đơn Hà Nội.png", "invoice", "DRAFT");
      row("i", owner.id(), "HÓA đơn Hà Nội.png", "invoice", "PROCESSING");
    });
  }

  AuthService.Identity user(String name) {
    auth.seed(name, "vt029-fictional-password");
    return (AuthService.Identity) auth.login(name, "vt029-fictional-password").get("user");
  }

  void row(String suffix, String user, String filename, String type, String state) {
    Document d = new Document();
    d.id = prefix + "-" + suffix; d.ownerId = user; d.filename = filename;
    d.documentType = type; d.contentType = "image/png"; d.fileHash = "0".repeat(64);
    d.fileBytes = 128; d.imageWidth = 10; d.imageHeight = 10;
    d.createdAt = timestamp; d.version = 1;
    store.em().persist(d);
    Job job = null;
    if (state != null) {
      job = new Job(); job.id = prefix + "-j-" + suffix; job.documentId = d.id;
      job.state = "PROCESSING".equals(state) ? "RUNNING" : "SUCCEEDED";
      job.stage = "fixture"; job.createdAt = timestamp; job.updatedAt = timestamp;
      job.deadline = timestamp.plusSeconds(180); job.pipelineManifest = "synthetic.v1";
      job.mode = "manual"; job.resultRunId = prefix + "-run-" + suffix;
      store.em().persist(job);
    }
    if (Set.of("APPROVED", "DRAFT").contains(Objects.toString(state, ""))) {
      ExtractionRun run = new ExtractionRun(); run.id = job.resultRunId;
      run.documentId = d.id; run.jobId = job.id; run.resultJson = "{}"; run.createdAt = timestamp;
      store.em().persist(run);
      Revision r = new Revision(); r.id = prefix + "-rev-" + suffix;
      r.documentId = d.id; r.runId = run.id; r.actorId = user;
      r.payloadJson = json.write(contracts.empty(type)); r.metadataJson = "[]";
      r.issuesJson = "[]"; r.rowIdsJson = "[]"; r.origin = "HUMAN";
      r.reason = "fictional search fixture"; r.createdAt = timestamp;
      r.approvedAt = "APPROVED".equals(state) ? timestamp : null;
      store.em().persist(r); d.headRevisionId = r.id;
    }
    if ("PROCESSING".equals(state)) d.activeJobId = job.id;
  }

  MockHttpServletRequestBuilder request() {
    return get("/api/v1/documents").with(authentication(
        new UsernamePasswordAuthenticationToken(owner, null, List.of())));
  }
  JsonNode page(MockHttpServletRequestBuilder request) throws Exception {
    return mapper.readTree(mvc.perform(request).andExpect(status().isOk())
        .andReturn().getResponse().getContentAsString());
  }
  List<String> ids(JsonNode page) {
    List<String> result = new ArrayList<>();
    page.path("items").forEach(x -> result.add(x.path("id").asText())); return result;
  }

  @Test void tc01_legacyEnvelopeAndSchemasStayCompatible() throws Exception {
    JsonNode body = page(request().param("limit", "50"));
    assertEquals(8, body.path("items").size());
    assertEquals(Set.of("items", "next_cursor"), keys(body));
    JsonNode frozen = mapper.readTree(getClass().getResourceAsStream("/vt029-v1-contract.json"));
    JsonNode current = mapper.readTree(getClass().getResourceAsStream("/openapi.json"));
    var names = frozen.path("components").path("schemas").fields();
    while (names.hasNext()) {
      var entry = names.next();
      assertEquals(entry.getValue(), current.path("components").path("schemas").path(entry.getKey()), entry.getKey());
    }
    Set<String> fields = keys(frozen.path("components").path("schemas").path("Document").path("properties"));
    for (JsonNode item : body.path("items")) assertEquals(fields, keys(item));
    Files.createDirectories(Path.of("target/vt029-contract"));
    Files.writeString(Path.of("target/vt029-contract/legacy.json"), body.toString());
    Files.writeString(Path.of("target/vt029-contract/search.json"), page(request().param("q", "hóa")).toString());
  }
  Set<String> keys(JsonNode node) {
    Set<String> result = new HashSet<>(); node.fieldNames().forEachRemaining(result::add); return result;
  }

  @Test void tc02_searchCombinesTypeAndOwner() throws Exception {
    assertEquals(List.of(prefix + "-i", prefix + "-h", prefix + "-g", prefix + "-a"),
        ids(page(request().param("q", "  HÓA  ").param("type", "invoice"))));
  }
  @Test void tc03_searchCombinesStatus() throws Exception {
    for (var pair : Map.of("APPROVED", "g", "DRAFT", "h", "PROCESSING", "i").entrySet())
      assertEquals(List.of(prefix + "-" + pair.getValue()),
          ids(page(request().param("q", "HÓA").param("type", "invoice").param("status", pair.getKey()))));
    assertTrue(ids(page(request().param("q", "HÓA").param("status", "FAILED"))).isEmpty());
  }
  @Test void tc04_wildcardsAreLiteral() throws Exception {
    assertEquals(List.of(prefix + "-d"), ids(page(request().param("q", "50%_!"))));
  }
  @Test void tc05_blankSearchAndNoMatches() throws Exception {
    assertEquals(page(request()), page(request().param("q", "   ")));
    assertTrue(page(request().param("q", "không tồn tại")).path("items").isEmpty());
  }
  @Test void tc06_tiedTimestampsKeysetHasNoGapsOrDuplicates() throws Exception {
    List<String> collected = new ArrayList<>(); String cursor = null;
    for (int guard = 0; guard < 5; guard++) {
      var r = request().param("q", "HÓA").param("limit", "2");
      if (cursor != null) r.param("cursor", cursor);
      JsonNode p = page(r); collected.addAll(ids(p));
      if (p.path("next_cursor").isNull()) break;
      cursor = p.path("next_cursor").asText();
    }
    assertEquals(List.of("i", "h", "g", "b", "a").stream().map(s -> prefix + "-" + s).toList(), collected);
  }
  @Test void tc07_invalidTypeAndStatus() throws Exception {
    // Baseline ContractValidator.type uses 422; preserve it for old clients.
    mvc.perform(request().param("type", "letter")).andExpect(status().isUnprocessableEntity());
    mvc.perform(request().param("status", "UNKNOWN")).andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_FILTER"));
  }
  @Test void tc08_invalidLengthAndLimit() throws Exception {
    mvc.perform(request().param("q", "x".repeat(129))).andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_QUERY"));
    mvc.perform(request().param("limit", "NaN")).andExpect(status().isBadRequest());
    assertEquals(1, page(request().param("limit", "0")).path("items").size());
    assertEquals(8, page(request().param("limit", "101")).path("items").size());
  }
  @Test void tc09_foreignAndMissingCursorAre404() throws Exception {
    for (String cursor : List.of(prefix + "-f", "missing"))
      mvc.perform(request().param("cursor", cursor)).andExpect(status().isNotFound())
          .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
  }
  @Test void tc10_unauthenticatedRequestIs401() throws Exception {
    mvc.perform(get("/api/v1/documents")).andExpect(status().isUnauthorized());
  }
  @Test void tc11_sqlLookingTextIsData() throws Exception {
    assertTrue(ids(page(request().param("q", "' OR 1=1 --"))).isEmpty());
  }
  @Test void tc12_providerFailureIsNotSuccessfulEmptyPage() throws Exception {
    // Inject a provider failure during real row materialization.
    doThrow(new IllegalStateException("private database detail"))
        .when(documents).view(any(Document.class));
    String body = mvc.perform(request()).andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"))
        .andExpect(jsonPath("$.items").doesNotExist()).andReturn().getResponse().getContentAsString();
    assertFalse(body.contains("private database detail"));
  }

  @Test void tc16_createdAtPrecedesIdAndCursorAcceptsOlderRows() throws Exception {
    new TransactionTemplate(tm).executeWithoutResult(tx -> {
      row("0", owner.id(), "HÓA mới.png", "invoice", null);
      store.em().find(Document.class, prefix + "-0").createdAt = timestamp.plusSeconds(1);
    });
    JsonNode first = page(request().param("q", "HÓA").param("limit", "1"));
    assertEquals(List.of(prefix + "-0"), ids(first));
    JsonNode second = page(request().param("q", "HÓA").param("limit", "1")
        .param("cursor", first.path("next_cursor").asText()));
    assertEquals(List.of(prefix + "-i"), ids(second));
  }

  @Test void tc17_limitIsActuallyBoundedToOneHundred() throws Exception {
    new TransactionTemplate(tm).executeWithoutResult(tx -> {
      for (int i = 0; i < 105; i++) row(String.format("n%03d", i), owner.id(), "thêm.png", "receipt", null);
    });
    JsonNode body = page(request().param("limit", "10000"));
    assertEquals(100, body.path("items").size()); assertTrue(body.path("next_cursor").isTextual());
  }
}
