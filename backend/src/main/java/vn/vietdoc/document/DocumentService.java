package vn.vietdoc.document;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.*;

@Service
public class DocumentService {
  public record Page<T>(List<T> items, String nextCursor) {}

  public record JobView(
      String id,
      String documentId,
      String state,
      String stage,
      String errorCode,
      String errorMessage,
      int attempts,
      Instant createdAt,
      Instant updatedAt,
      String resultRunId,
      String pipelineManifest,
      String mode) {}

  public record RevisionView(
      String id,
      String documentId,
      String parentId,
      String runId,
      JsonNode payload,
      JsonNode fieldMetadata,
      JsonNode issues,
      JsonNode rowIds,
      String origin,
      String reason,
      Instant createdAt,
      String state,
      Instant approvedAt,
      String approvalReason) {}

  public record DocumentView(
      String id,
      String filename,
      String documentType,
      long fileBytes,
      int imageWidth,
      int imageHeight,
      Instant createdAt,
      long version,
      String headRevisionId,
      RevisionView head,
      JobView job) {}

  public record RunView(
      String id, String documentId, String jobId, JsonNode result, Instant createdAt) {}

  public record ExportView(
      String id,
      String documentId,
      String revisionId,
      int exporterVersion,
      String sha256,
      Instant createdAt) {}

  public record AuditView(String id, String action, JsonNode details, Instant createdAt) {}

  private final Store store;
  private final Json json;
  private final PrivateStorage storage;
  private final ContractValidator validator;
  private final TransactionTemplate uploadTransaction;

  public DocumentService(
      Store store, Json json, PrivateStorage storage, ContractValidator validator,
      PlatformTransactionManager transactionManager) {
    this.store = store;
    this.json = json;
    this.storage = storage;
    this.validator = validator;
    this.uploadTransaction = new TransactionTemplate(transactionManager);
  }

  public DocumentView upload(String user, MultipartFile file, String type, String key) {
    validator.type(type);
    String requestKey = key(key);
    Document d = new Document();
    d.id = Store.id();
    PrivateStorage.Asset asset = storage.put(d.id, file);
    try {
      DocumentView result = uploadTransaction.execute(status -> {
        if (store.em().find(UserAccount.class, user,
            jakarta.persistence.LockModeType.PESSIMISTIC_WRITE) == null) throw ApiException.missing();
        if (requestKey != null) {
          List<Document> existing = store.em()
              .createQuery("select d from Document d where d.ownerId=:u and d.uploadKey=:k", Document.class)
              .setParameter("u", user).setParameter("k", requestKey).getResultList();
          if (!existing.isEmpty()) {
            if (!existing.get(0).documentType.equals(type)
                || !existing.get(0).fileHash.equals(asset.hash()))
              throw new ApiException(409, "IDEMPOTENCY_CONFLICT",
                  "Khóa upload đã được dùng cho file khác.");
            return view(existing.get(0));
          }
        }
        d.ownerId = user;
        d.documentType = type;
        d.filename = filename(file.getOriginalFilename());
        d.contentType = asset.contentType();
        d.fileHash = asset.hash();
        d.fileBytes = asset.size();
        d.imageWidth = asset.width();
        d.imageHeight = asset.height();
        d.version = 1;
        d.createdAt = Instant.now();
        d.uploadKey = requestKey;
        store.em().persist(d);
        store.audit(d, user, "UPLOAD", Map.of("document_type", type));
        return view(d);
      });
      if (!result.id().equals(d.id)) storage.remove(d.id);
      return result;
    } catch (RuntimeException e) {
      storage.remove(d.id);
      throw e;
    }
  }

  @Transactional(readOnly = true)
  public DocumentView get(String id, String user) {
    return view(store.owned(id, user, false));
  }

  @Transactional(readOnly = true)
  public Page<DocumentView> list(String user, String type, String state, String cursor, int limit) {
    limit = Math.max(1, Math.min(100, limit));
    String where = " where d.ownerId=:u";
    if (type != null && !type.isBlank()) {
      validator.type(type);
      where += " and d.documentType=:t";
    }
    if (state != null && !state.isBlank()) {
      if (!Set.of("DRAFT", "APPROVED", "PROCESSING", "FAILED").contains(state))
        throw new ApiException(400, "INVALID_FILTER", "Bộ lọc trạng thái không hợp lệ.");
      where +=
          switch (state) {
            case "APPROVED" ->
                " and exists(select r.id from Revision r where r.id=d.headRevisionId and"
                    + " r.approvedAt is not null)";
            case "DRAFT" ->
                " and exists(select r.id from Revision r where r.id=d.headRevisionId and"
                    + " r.approvedAt is null)";
            case "PROCESSING" -> " and d.activeJobId is not null";
            default ->
                " and exists(select j.id from Job j where j.documentId=d.id and j.state='FAILED'"
                    + " and not exists(select j2.id from Job j2 where j2.documentId=d.id and"
                    + " j2.createdAt>j.createdAt))";
          };
    }
    Document previous = null;
    if (cursor != null && !cursor.isBlank()) {
      previous = store.owned(cursor, user, false);
      where += " and (d.createdAt<:time or (d.createdAt=:time and d.id<:id))";
    }
    var query =
        store
            .em()
            .createQuery(
                "select d from Document d" + where + " order by d.createdAt desc,d.id desc",
                Document.class)
            .setParameter("u", user)
            .setMaxResults(limit + 1);
    if (type != null && !type.isBlank()) query.setParameter("t", type);
    if (previous != null)
      query.setParameter("time", previous.createdAt).setParameter("id", previous.id);
    List<Document> rows = query.getResultList();
    boolean more = rows.size() > limit;
    if (more) rows = rows.subList(0, limit);
    return new Page<>(
        rows.stream().map(this::view).toList(), more ? rows.get(rows.size() - 1).id : null);
  }

  @Transactional(readOnly = true)
  public byte[] page(String id, String user) {
    store.owned(id, user, false);
    return storage.readPage(id);
  }

  @Transactional(readOnly = true)
  public Page<RunView> runs(String id, String user) {
    store.owned(id, user, false);
    return new Page<>(
        store
            .em()
            .createQuery(
                "select r from ExtractionRun r where r.documentId=:d order by r.createdAt desc",
                ExtractionRun.class)
            .setParameter("d", id)
            .setMaxResults(100)
            .getResultList()
            .stream()
            .map(this::runView)
            .toList(),
        null);
  }

  @Transactional(readOnly = true)
  public RunView run(String id, String user) {
    ExtractionRun r = store.em().find(ExtractionRun.class, id);
    if (r == null) throw ApiException.missing();
    store.owned(r.documentId, user, false);
    return runView(r);
  }

  @Transactional(readOnly = true)
  public Page<RevisionView> revisions(String id, String user) {
    store.owned(id, user, false);
    return new Page<>(
        store
            .em()
            .createQuery(
                "select r from Revision r where r.documentId=:d order by r.createdAt desc",
                Revision.class)
            .setParameter("d", id)
            .setMaxResults(100)
            .getResultList()
            .stream()
            .map(this::revisionView)
            .toList(),
        null);
  }

  @Transactional(readOnly = true)
  public RevisionView revision(String id, String user) {
    Revision r = store.em().find(Revision.class, id);
    if (r == null) throw ApiException.missing();
    store.owned(r.documentId, user, false);
    return revisionView(r);
  }

  @Transactional(readOnly = true)
  public Page<AuditView> audit(String id, String user) {
    store.owned(id, user, false);
    return new Page<>(
        store
            .em()
            .createQuery(
                "select a from AuditEvent a where a.documentId=:d order by a.createdAt desc",
                AuditEvent.class)
            .setParameter("d", id)
            .setMaxResults(100)
            .getResultList()
            .stream()
            .map(a -> new AuditView(a.id, a.action, json.read(a.detailsJson), a.createdAt))
            .toList(),
        null);
  }

  @Transactional(readOnly = true)
  public Page<ExportView> exports(String id, String user) {
    store.owned(id, user, false);
    return new Page<>(
        store
            .em()
            .createQuery(
                "select e from ExportArtifact e where e.documentId=:d order by e.createdAt desc",
                ExportArtifact.class)
            .setParameter("d", id)
            .setMaxResults(100)
            .getResultList()
            .stream()
            .map(this::exportView)
            .toList(),
        null);
  }

  public DocumentView view(Document d) {
    Revision head =
        d.headRevisionId == null ? null : store.em().find(Revision.class, d.headRevisionId);
    List<Job> jobs =
        store
            .em()
            .createQuery(
                "select j from Job j where j.documentId=:d order by j.createdAt desc", Job.class)
            .setParameter("d", d.id)
            .setMaxResults(1)
            .getResultList();
    return new DocumentView(
        d.id,
        d.filename,
        d.documentType,
        d.fileBytes,
        d.imageWidth,
        d.imageHeight,
        d.createdAt,
        d.version,
        d.headRevisionId,
        head == null ? null : revisionView(head),
        jobs.isEmpty() ? null : jobView(jobs.get(0)));
  }

  public JobView jobView(Job j) {
    return new JobView(
        j.id,
        j.documentId,
        j.state,
        j.stage,
        j.errorCode,
        j.errorMessage,
        j.attempts,
        j.createdAt,
        j.updatedAt,
        j.resultRunId,
        j.pipelineManifest,
        j.mode);
  }

  public RevisionView revisionView(Revision r) {
    return new RevisionView(
        r.id,
        r.documentId,
        r.parentId,
        r.runId,
        json.read(r.payloadJson),
        json.read(r.metadataJson),
        json.read(r.issuesJson),
        json.read(r.rowIdsJson),
        r.origin,
        r.reason,
        r.createdAt,
        r.approvedAt == null ? "DRAFT" : "APPROVED",
        r.approvedAt,
        r.approvalReason);
  }

  public RunView runView(ExtractionRun r) {
    return new RunView(r.id, r.documentId, r.jobId, json.read(r.resultJson), r.createdAt);
  }

  public ExportView exportView(ExportArtifact e) {
    return new ExportView(
        e.id, e.documentId, e.revisionId, e.exporterVersion, e.sha256, e.createdAt);
  }

  public static String key(String value) {
    if (value == null || value.isBlank()) return null;
    if (!value.matches("[A-Za-z0-9_.:-]{1,100}"))
      throw new ApiException(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key không hợp lệ.");
    return value;
  }

  private String filename(String value) {
    String name = Objects.toString(value, "document").replace('\\', '/');
    name = name.substring(name.lastIndexOf('/') + 1).replaceAll("[\\p{Cntrl}]", "");
    return name.isBlank() ? "document" : name.substring(0, Math.min(255, name.length()));
  }
}
