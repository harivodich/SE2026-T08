package vn.vietdoc.job;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.nio.file.*;
import java.net.URI;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.document.ArtifactPromoter.Promoted;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.*;
import vn.vietdoc.review.ReviewService;

@Service
public class JobService {
  public record Claim(
      String id,
      String documentId,
      String runId,
      String token,
      String attemptId,
      String type,
      String hash,
      String mode,
      String manifest,
      Instant deadline) {}

  private final Store store;
  private final Json json;
  private final ContractValidator validator;
  private final DocumentService documents;
  private final ReviewService review;
  private final String mode, manifest;
  private final int deadlineSeconds, leaseSeconds, maxAttempts;

  public JobService(
      Store store,
      Json json,
      ContractValidator validator,
      DocumentService documents,
      ReviewService review,
      @Value("${vietdoc.mode}") String mode,
      @Value("${vietdoc.pipeline-manifest}") String manifest,
      @Value("${vietdoc.job-deadline-seconds}") int deadlineSeconds,
      @Value("${vietdoc.lease-seconds}") int leaseSeconds,
      @Value("${vietdoc.max-attempts}") int maxAttempts,
      @Value("${vietdoc.worker-url}") String workerUrl,
      @Value("${vietdoc.worker-token}") String workerToken,
      @Value("${vietdoc.attempts-root}") String attemptsRoot,
      @Value("${vietdoc.storage}") String javaStorageRoot) {
    this.store = store;
    this.json = json;
    this.validator = validator;
    this.documents = documents;
    this.review = review;
    this.mode = mode;
    this.manifest = manifest;
    this.deadlineSeconds = deadlineSeconds;
    this.leaseSeconds = leaseSeconds;
    this.maxAttempts = maxAttempts;
    if (!Set.of("manual", "demo", "http").contains(mode))
      throw new IllegalStateException("AI_MODE must be manual, demo or http");
    if (mode.equals("http")) {
      URI uri = URI.create(workerUrl);
      if (!Set.of("http", "https").contains(uri.getScheme()) || uri.getHost() == null
          || !"/internal/v1/compute".equals(uri.getPath()) || uri.getQuery() != null
          || uri.getUserInfo() != null || workerToken.isBlank())
        throw new IllegalStateException("AI_MODE=http requires a fixed compute URL and service token");
      Path attempts = Path.of(attemptsRoot).toAbsolutePath().normalize();
      Path committed = Path.of(javaStorageRoot).toAbsolutePath().normalize();
      if (attempts.startsWith(committed) || committed.startsWith(attempts))
        throw new IllegalStateException("AI attempts and Java storage must be separate roots");
      if (!Files.isDirectory(attempts, LinkOption.NOFOLLOW_LINKS))
        throw new IllegalStateException("AI_MODE=http requires a mounted attempts directory");
    }
  }

  @Transactional
  public DocumentService.JobView create(String id, String user, String requestKey) {
    Document d = store.owned(id, user, true);
    // Serialize admission across different documents owned by the same user.
    store.em().find(UserAccount.class, user, LockModeType.PESSIMISTIC_WRITE);
    String key = DocumentService.key(requestKey);
    if (key != null) {
      List<Job> old =
          store
              .em()
              .createQuery(
                  "select j from Job j where j.documentId=:d and j.requestKey=:k", Job.class)
              .setParameter("d", id)
              .setParameter("k", key)
              .getResultList();
      if (!old.isEmpty()) return documents.jobView(old.get(0));
    }
    if (d.activeJobId != null)
      throw new ApiException(409, "ACTIVE_JOB_EXISTS", "Chứng từ đã có job đang chạy.");
    long active =
        store
            .em()
            .createQuery(
                "select count(j) from Job j,Document d where j.documentId=d.id and d.ownerId=:u and"
                    + " j.state in ('QUEUED','RUNNING','RETRYING')",
                Long.class)
            .setParameter("u", user)
            .getSingleResult();
    if (active >= 5)
      throw new ApiException(
          429, "JOB_LIMIT", "Bạn đang có quá nhiều job. Hãy đợi một job hoàn tất.");
    Job j = new Job();
    j.id = Store.id();
    j.resultRunId = Store.id();
    j.documentId = id;
    j.state = "QUEUED";
    j.stage = "WAITING";
    j.createdAt = Instant.now();
    j.updatedAt = j.createdAt;
    j.deadline = j.createdAt.plusSeconds(deadlineSeconds);
    j.nextAttemptAt = j.createdAt;
    j.attempts = 0;
    j.requestKey = key;
    j.pipelineManifest = manifest;
    j.mode = mode;
    store.em().persist(j);
    d.activeJobId = j.id;
    d.version++;
    store.audit(
        d,
        user,
        "CREATE_JOB",
        Map.of("job_id", j.id, "manifest", j.pipelineManifest, "mode", j.mode));
    return documents.jobView(j);
  }

  @Transactional(readOnly = true)
  public DocumentService.JobView get(String id, String user) {
    Job j = store.job(id, false);
    store.owned(j.documentId, user, false);
    return documents.jobView(j);
  }

  @Transactional
  public DocumentService.JobView cancel(String id, String user, String expectedState) {
    Job current = store.job(id, false);
    Document d = store.owned(current.documentId, user, true);
    Job j = store.job(id, true);
    if (!Set.of("QUEUED", "RUNNING", "RETRYING").contains(j.state))
      throw new ApiException(409, "JOB_TERMINAL", "Job đã kết thúc.");
    if (!j.state.equals(expectedState))
      throw new ApiException(
          409, "JOB_STATE_CONFLICT", "Trạng thái job đã thay đổi. Hãy tải lại trước khi hủy.");
    terminal(d, j, "CANCELLED", null, null);
    store.audit(d, user, "CANCEL_JOB", Map.of("job_id", j.id));
    return documents.jobView(j);
  }

  @Transactional(readOnly = true)
  public List<String> available() {
    return store
        .em()
        .createQuery(
            "select j.id from Job j where j.state in ('QUEUED','RETRYING')"
                + " and (j.nextAttemptAt is null or j.nextAttemptAt<=:now) order by j.createdAt",
            String.class)
        .setParameter("now", Instant.now())
        .setMaxResults(10)
        .getResultList();
  }

  @Transactional
  public Claim claim(String id) {
    Job current = store.job(id, false);
    Document d = store.locked(current.documentId);
    Job j = store.job(id, true);
    if (!Set.of("QUEUED", "RETRYING").contains(j.state) || !Objects.equals(d.activeJobId, j.id))
      return null;
    if (j.nextAttemptAt != null && j.nextAttemptAt.isAfter(Instant.now())) return null;
    if (j.attempts >= maxAttempts) {
      terminal(d, j, "FAILED", "ATTEMPTS_EXHAUSTED", "Job đã dùng hết số lần thử.");
      return null;
    }
    if (j.deadline.isBefore(Instant.now())) {
      terminal(d, j, "FAILED", "DEADLINE_EXCEEDED", "Job vượt thời gian xử lý; hãy chạy lại.");
      return null;
    }
    j.state = "RUNNING";
    j.nextAttemptAt = null;
    j.stage = "EXTRACTION";
    j.attempts++;
    // A recovered/retried compute attempt must never reuse an earlier result identity.
    j.resultRunId = Store.id();
    j.leaseToken = Store.id();
    j.attemptId = Store.id();
    j.leaseUntil = Instant.now().plusSeconds(leaseSeconds);
    j.updatedAt = Instant.now();
    return new Claim(
        j.id,
        d.id,
        j.resultRunId,
        j.leaseToken,
        j.attemptId,
        d.documentType,
        d.fileHash,
        j.mode,
        j.pipelineManifest,
        j.deadline);
  }

  @Transactional
  public void heartbeat(Claim claim) {
    Job current = store.job(claim.id, false);
    store.locked(current.documentId);
    Job j = store.job(claim.id, true);
    if (valid(j, claim)) {
      j.leaseUntil = Instant.now().plusSeconds(leaseSeconds);
      j.updatedAt = Instant.now();
    }
  }

  @Transactional
  public boolean complete(Claim claim, JsonNode result) {
    return complete(claim, result, null);
  }

  @Transactional
  public boolean complete(Claim claim, JsonNode result, Promoted promoted) {
    Document d = store.locked(claim.documentId);
    Job j = store.job(claim.id, true);
    if (!valid(j, claim)) return false;
    validator.extraction(claim.type, claim.runId, claim.id, claim.manifest, result);
    if (store.em().find(ExtractionRun.class, claim.runId) != null) return false;
    ExtractionRun run = new ExtractionRun();
    run.id = claim.runId;
    run.documentId = d.id;
    run.jobId = j.id;
    run.resultJson = json.write(result);
    if (j.mode.equals("http") && promoted == null)
      throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Thiếu canonical asset đã xác minh.");
    if (promoted != null) {
      if (!j.mode.equals("http") || !promoted.canonicalKey().startsWith("promoted/" + claim.runId() + "/"))
        throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Canonical asset không thuộc run hiện hành.");
      run.canonicalKey = promoted.canonicalKey();
      run.canonicalHash = promoted.canonicalHash();
      run.canonicalWidth = promoted.width();
      run.canonicalHeight = promoted.height();
    }
    run.createdAt = Instant.now();
    store.em().persist(run);
    review.initial(d, run);
    terminal(d, j, "SUCCEEDED", null, null);
    store.audit(d, null, "JOB_COMPLETED", Map.of("job_id", j.id, "run_id", run.id));
    return true;
  }

  @Transactional
  public void fail(Claim claim, String code, String message, boolean retryable) {
    fail(claim, code, message, retryable, 0);
  }

  @Transactional
  public void fail(Claim claim, String code, String message, boolean retryable, int retryAfterSeconds) {
    Document d = store.locked(claim.documentId);
    Job j = store.job(claim.id, true);
    if (!valid(j, claim)) return;
    Instant now = Instant.now();
    long delaySeconds = Math.max(Math.min(30, 1L << Math.min(j.attempts, 5)),
        Math.max(0, Math.min(retryAfterSeconds, 30)));
    if (retryable && j.attempts < maxAttempts && j.deadline.isAfter(now.plusSeconds(delaySeconds + 2))) {
      j.state = "RETRYING";
      j.stage = "WAITING";
      j.errorCode = code;
      j.errorMessage = message;
      j.leaseToken = null;
      j.attemptId = null;
      j.leaseUntil = null;
      j.nextAttemptAt = now.plusSeconds(delaySeconds);
      j.updatedAt = now;
    } else terminal(d, j, "FAILED", code, message);
    store.audit(d, null, "JOB_ERROR", Map.of("job_id", j.id, "code", code, "retryable", retryable));
  }

  @Transactional
  public void recover() {
    Instant now = Instant.now();
    List<Job> expired =
        store
            .em()
            .createQuery(
                "select j from Job j where j.state in ('QUEUED','RUNNING','RETRYING') and"
                    + " (j.deadline<:now or (j.state='RUNNING' and j.leaseUntil<:now))",
                Job.class)
            .setParameter("now", now)
            .setMaxResults(30)
            .getResultList();
    for (Job found : expired) {
      Document d = store.locked(found.documentId);
      Job j = store.job(found.id, true);
      store.em().refresh(j);
      if (!Set.of("QUEUED", "RUNNING", "RETRYING").contains(j.state)) continue;
      if (j.deadline.isBefore(now) || j.attempts >= maxAttempts) {
        terminal(
            d,
            j,
            "FAILED",
            "DEADLINE_EXCEEDED",
            "Job không hoàn tất trong giới hạn; hãy chạy lại.");
      } else if (j.state.equals("RUNNING") && j.leaseUntil != null && j.leaseUntil.isBefore(now)) {
        j.state = "RETRYING";
        j.stage = "WAITING";
        j.leaseToken = null;
        j.attemptId = null;
        j.leaseUntil = null;
        j.nextAttemptAt = now;
        j.updatedAt = now;
      }
    }
  }

  private boolean valid(Job j, Claim c) {
    Instant now = Instant.now();
    return j.state.equals("RUNNING")
        && Objects.equals(j.documentId, c.documentId)
        && Objects.equals(j.resultRunId, c.runId)
        && Objects.equals(j.leaseToken, c.token)
        && Objects.equals(j.attemptId, c.attemptId)
        && j.leaseUntil != null
        && j.leaseUntil.isAfter(now)
        && j.deadline.isAfter(now);
  }

  private void terminal(Document d, Job j, String state, String code, String message) {
    j.state = state;
    j.stage = "FINISHED";
    j.errorCode = code;
    j.errorMessage = message;
    j.leaseToken = null;
    j.attemptId = null;
    j.leaseUntil = null;
    j.nextAttemptAt = null;
    j.updatedAt = Instant.now();
    if (Objects.equals(d.activeJobId, j.id)) {
      d.activeJobId = null;
      d.version++;
    }
  }
}
