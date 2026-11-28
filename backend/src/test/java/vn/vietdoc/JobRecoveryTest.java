package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import vn.vietdoc.common.Json;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.persistence.Entities.Document;
import vn.vietdoc.persistence.Entities.Job;
import vn.vietdoc.review.ReviewService;

/** Controls the interleaving between expired selection and locked row refresh. */
class JobRecoveryTest {
  private final Store store = mock(Store.class);
  private final EntityManager em = mock(EntityManager.class);
  private final Document document = new Document();

  @Test
  void staleSelectionDoesNotFailAFreshFinalAttempt() {
    Job current = currentJob("RUNNING", 3, Instant.now().plusSeconds(120));
    recoverAfterStaleSelection(current);
    assertEquals("RUNNING", current.state);
    assertEquals("current-fence", current.leaseToken);
    assertEquals("current-attempt", current.attemptId);
    assertEquals("job", document.activeJobId);
    assertEquals(1, document.version);
    assertNull(current.errorCode);
  }

  @Test
  void staleSelectionDoesNotFailAnAlreadyRecoveredRetry() {
    Job current = currentJob("RETRYING", 3, null);
    recoverAfterStaleSelection(current);
    assertEquals("RETRYING", current.state);
    assertEquals("job", document.activeJobId);
  }

  @Test
  void actuallyExpiredFinalLeaseStillFailsAndClearsFence() {
    Job current = currentJob("RUNNING", 3, Instant.now().minusSeconds(30));
    recoverAfterStaleSelection(current);
    assertEquals("FAILED", current.state);
    assertEquals("ATTEMPTS_EXHAUSTED", current.errorCode);
    assertNull(current.leaseToken);
    assertNull(current.attemptId);
    assertNull(document.activeJobId);
    assertEquals(2, document.version);
  }

  @Test
  void deadlineStillTerminatesAJobWithAFreshLease() {
    Job current = currentJob("RUNNING", 1, Instant.now().plusSeconds(120));
    current.deadline = Instant.now().minusSeconds(30);
    recoverAfterStaleSelection(current);
    assertEquals("FAILED", current.state);
    assertEquals("DEADLINE_EXCEEDED", current.errorCode);
    assertNull(document.activeJobId);
  }

  @Test
  void expiredLeaseWithAttemptsRemainingIsRecovered() {
    Job current = currentJob("RUNNING", 2, Instant.now().minusSeconds(30));
    recoverAfterStaleSelection(current);
    assertEquals("RETRYING", current.state);
    assertNull(current.leaseToken);
    assertNull(current.attemptId);
    assertNotNull(current.nextAttemptAt);
    assertEquals("job", document.activeJobId);
  }

  private Job currentJob(String state, int attempts, Instant leaseUntil) {
    Job job = new Job();
    job.id = "job";
    job.documentId = "doc";
    job.state = state;
    job.attempts = attempts;
    job.leaseUntil = leaseUntil;
    job.deadline = Instant.now().plusSeconds(600);
    job.leaseToken = "current-fence";
    job.attemptId = "current-attempt";
    return job;
  }

  private void recoverAfterStaleSelection(Job current) {
    @SuppressWarnings("unchecked")
    TypedQuery<Job> query = mock(TypedQuery.class);
    when(store.em()).thenReturn(em);
    when(em.createQuery(anyString(), eq(Job.class))).thenReturn(query);
    when(query.setParameter(eq("now"), any())).thenReturn(query);
    when(query.setMaxResults(30)).thenReturn(query);
    Job stale = currentJob("RUNNING", 2, Instant.now().minusSeconds(30));
    when(query.getResultList()).thenReturn(List.of(stale));
    document.id = "doc";
    document.activeJobId = "job";
    document.version = 1;
    when(store.locked("doc")).thenReturn(document);
    when(store.job("job", true)).thenReturn(current);
    JobService service = new JobService(store, mock(Json.class), mock(ContractValidator.class),
        mock(DocumentService.class), mock(ReviewService.class), "demo", "fixture", 180, 60, 3,
        "", "", "unused-attempts", "unused-storage");
    service.recover();
    verify(em).refresh(current);
  }
}
