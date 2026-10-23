package vn.vietdoc.persistence;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Repository;
import vn.vietdoc.common.*;
import vn.vietdoc.persistence.Entities.*;

@Repository
public class Store {
  @PersistenceContext private EntityManager em;

  public EntityManager em() {
    return em;
  }

  private final Json json;

  public Store(Json json) {
    this.json = json;
  }

  public static String id() {
    return UUID.randomUUID().toString();
  }

  public Document owned(String id, String owner, boolean lock) {
    Document d =
        lock
            ? em.find(Document.class, id, LockModeType.PESSIMISTIC_WRITE)
            : em.find(Document.class, id);
    if (d == null || !d.ownerId.equals(owner)) throw ApiException.missing();
    return d;
  }

  public Document locked(String id) {
    Document d = em.find(Document.class, id, LockModeType.PESSIMISTIC_WRITE);
    if (d == null) throw ApiException.missing();
    return d;
  }

  public Job job(String id, boolean lock) {
    Job j = lock ? em.find(Job.class, id, LockModeType.PESSIMISTIC_WRITE) : em.find(Job.class, id);
    if (j == null) throw ApiException.missing();
    if (lock) em.refresh(j, LockModeType.PESSIMISTIC_WRITE);
    return j;
  }

  public Revision revision(String id, Document doc) {
    Revision r = id == null ? null : em.find(Revision.class, id);
    if (r == null || !r.documentId.equals(doc.id)) throw ApiException.missing();
    return r;
  }

  public ExtractionRun run(String id, Document doc) {
    ExtractionRun r = em.find(ExtractionRun.class, id);
    if (r == null || !r.documentId.equals(doc.id)) throw ApiException.missing();
    return r;
  }

  public void audit(Document d, String actor, String action, Object details) {
    AuditEvent a = new AuditEvent();
    a.id = id();
    a.documentId = d.id;
    a.actorId = actor;
    a.action = action;
    a.detailsJson = json.write(details);
    a.createdAt = Instant.now();
    em.persist(a);
  }

  public void compare(Document d, String base, long version) {
    if (d.version != version || !Objects.equals(d.headRevisionId, base))
      throw new ApiException(
          409,
          "REVISION_CONFLICT",
          "Tài liệu đã thay đổi. Nội dung đang sửa của bạn vẫn được giữ; hãy đối chiếu với bản"
              + " mới.",
          Map.of(
              "current_document_version",
              d.version,
              "current_head_revision_id",
              Objects.toString(d.headRevisionId, "")));
  }
}
