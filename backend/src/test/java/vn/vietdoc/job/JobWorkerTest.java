package vn.vietdoc.job;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import vn.vietdoc.document.ArtifactPromoter;
import vn.vietdoc.integration.AiClient;

class JobWorkerTest {
  private JobService jobs;
  private JobWorker worker;
  private ExecutorService originalExecutor;

  @BeforeEach
  void setUp() {
    jobs = mock(JobService.class);
    worker = new JobWorker(jobs, mock(AiClient.class), mock(ArtifactPromoter.class));
    originalExecutor = (ExecutorService) ReflectionTestUtils.getField(worker, "executor");
  }

  @AfterEach
  void tearDown() {
    if (originalExecutor != null) originalExecutor.shutdownNow();
  }

  @Test
  void clearsCurrentAndBusyAndStopsHeartbeatWhenSubmitIsRejected() {
    var claim = sampleClaim("11111111-1111-4111-8111-111111111111");
    ExecutorService rejected = mock(ExecutorService.class);
    when(jobs.available()).thenReturn(List.of(claim.id()), List.of());
    when(jobs.claim(claim.id())).thenReturn(claim);
    doThrow(new RejectedExecutionException("executor rejected"))
        .when(rejected)
        .submit(any(Runnable.class));
    ReflectionTestUtils.setField(worker, "executor", rejected);

    worker.poll();

    assertNull(ReflectionTestUtils.getField(worker, "current"));
    assertFalse(((AtomicBoolean) ReflectionTestUtils.getField(worker, "busy")).get());

    worker.heartbeat();
    verify(jobs, never()).heartbeat(any());

    worker.poll();
    verify(jobs, times(2)).recover();
    verify(jobs, times(2)).available();
  }

  @Test
  void preservesRunningTaskWhenRecoverThrowsDuringPoll() {
    var running = sampleClaim("22222222-2222-4222-8222-222222222222");
    ((AtomicBoolean) ReflectionTestUtils.getField(worker, "busy")).set(true);
    ReflectionTestUtils.setField(worker, "current", running);
    doThrow(new RuntimeException("temporary db error")).when(jobs).recover();

    worker.poll();

    assertSame(running, ReflectionTestUtils.getField(worker, "current"));
    assertTrue(((AtomicBoolean) ReflectionTestUtils.getField(worker, "busy")).get());

    worker.heartbeat();
    verify(jobs).heartbeat(running);
  }

  private JobService.Claim sampleClaim(String jobId) {
    return new JobService.Claim(
        jobId,
        "55555555-5555-4555-8555-555555555555",
        "33333333-3333-4333-8333-333333333333",
        "66666666-6666-4666-8666-666666666666",
        "44444444-4444-4444-8444-444444444444",
        "receipt",
        "a".repeat(64),
        "http",
        "receipt.v1",
        Instant.now().plusSeconds(60));
  }
}
