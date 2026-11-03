package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

import java.time.Instant;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.transaction.PlatformTransactionManager;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.persistence.Entities.Job;

class Vt030MappingTest {
  @ParameterizedTest
  @ValueSource(strings = {"QUEUED", "RUNNING", "RETRYING", "SUCCEEDED", "FAILED", "CANCELLED"})
  void tc16JobViewPreservesSemanticIdentityForEachState(String state) {
    Job job = new Job();
    job.id = "11111111-1111-4111-8111-111111111111";
    job.documentId = "22222222-2222-4222-8222-222222222222";
    job.resultRunId = "33333333-3333-4333-8333-333333333333";
    job.state = state;
    job.stage = state.equals("RUNNING") ? "EXTRACTION" : "WAITING";
    job.createdAt = Instant.parse("2026-11-04T00:00:00Z");
    job.updatedAt = job.createdAt;
    job.pipelineManifest = "vt030.fixture.v1";
    job.mode = "demo";
    DocumentService mapper = new DocumentService(null, null, null, null,
        mock(PlatformTransactionManager.class));
    var result = mapper.jobView(job);
    assertEquals("11111111-1111-4111-8111-111111111111", result.id());
    assertEquals("22222222-2222-4222-8222-222222222222", result.documentId());
    assertEquals("33333333-3333-4333-8333-333333333333", result.resultRunId());
    assertEquals(state, result.state());
    assertEquals(job.stage, result.stage());
    assertEquals("vt030.fixture.v1", result.pipelineManifest());
  }
}
