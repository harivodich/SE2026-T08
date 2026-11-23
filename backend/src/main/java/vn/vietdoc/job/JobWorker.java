package vn.vietdoc.job;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.integration.AiClient;
import vn.vietdoc.document.ArtifactPromoter;

@Component
@ConditionalOnProperty(name = "vietdoc.worker-enabled", havingValue = "true")
public class JobWorker {
  private static final Logger log = LoggerFactory.getLogger(JobWorker.class);
  private final JobService jobs;
  private final AiClient client;
  private final ArtifactPromoter promoter;
  private final AtomicBoolean busy = new AtomicBoolean();
  private final ExecutorService executor = Executors.newSingleThreadExecutor();
  private volatile JobService.Claim current;

  public JobWorker(JobService jobs, AiClient client, ArtifactPromoter promoter) {
    this.jobs = jobs;
    this.client = client;
    this.promoter = promoter;
  }

  @Scheduled(fixedDelay = 1000)
  public void poll() {
    try {
      jobs.recover();
      if (!busy.compareAndSet(false, true)) return;
      JobService.Claim claim = null;
      for (String id : jobs.available()) {
        claim = jobs.claim(id);
        if (claim != null) break;
      }
      if (claim == null) {
        busy.set(false);
        return;
      }
      current = claim;
      JobService.Claim captured = claim;
      executor.submit(() -> process(captured));
    } catch (Exception e) {
      if (current == null) busy.set(false);
      log.warn("worker_poll error_type={}", e.getClass().getSimpleName());
    }
  }

  @Scheduled(fixedDelay = 10000)
  public void heartbeat() {
    JobService.Claim c = current;
    if (c != null) {
      try {
        jobs.heartbeat(c);
      } catch (Exception e) {
        log.warn("heartbeat job_id={} error_type={}", c.id(), e.getClass().getSimpleName());
      }
    }
  }

  private void process(JobService.Claim c) {
    boolean promotedAsset = false;
    try {
      if (c.mode().equals("http")) {
        var envelope = client.compute(c);
        var promoted = promoter.promote(c, envelope);
        promotedAsset = true;
        if (!jobs.complete(c, envelope.path("result"), promoted))
          log.warn("promotion_orphan job_id={} run_id={} reason=stale_completion", c.id(), c.runId());
      } else jobs.complete(c, client.extract(c));
    } catch (ApiException e) {
      if (promotedAsset) log.warn("promotion_orphan job_id={} run_id={} reason=completion_error", c.id(), c.runId());
      jobs.fail(
          c,
          e.code.equals("CONTRACT_INVALID") ? "MODEL_OUTPUT_INVALID" : e.code,
          e.getMessage(),
          e.status == 503,
          e.details.get("retry_after_seconds") instanceof Number delay ? delay.intValue() : 0);
    } catch (Exception e) {
      if (promotedAsset) log.warn("promotion_orphan job_id={} run_id={} reason=completion_error", c.id(), c.runId());
      log.warn("compute job_id={} error_type={}", c.id(), e.getClass().getSimpleName());
      jobs.fail(
          c,
          "OCR_RUNTIME_ERROR",
          "Không kết nối hoặc đọc được kết quả AI. Hãy kiểm tra worker rồi thử lại.",
          true);
    } finally {
      current = null;
      busy.set(false);
    }
  }

  @PreDestroy
  void stop() {
    executor.shutdownNow();
  }
}
