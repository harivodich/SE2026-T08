package vn.vietdoc.review;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.*;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.*;

@Service
public class ReviewService {
  private final Store store;
  private final Json json;
  private final ContractValidator validator;
  private final DocumentService documents;

  public ReviewService(
      Store store, Json json, ContractValidator validator, DocumentService documents) {
    this.store = store;
    this.json = json;
    this.validator = validator;
    this.documents = documents;
  }

  @Transactional
  public DocumentService.DocumentView save(String id, String user, Requests.Save input) {
    Document d = store.owned(id, user, true);
    store.compare(d, input.baseRevisionId(), input.expectedDocumentVersion());
    Revision old = store.revision(d.headRevisionId, d);
    validator.business(d.documentType, input.payload());
    validator.rowIds(input.payload(), input.rowIds());
    for (String path : input.reviewedPaths()) validator.pointer(input.payload(), path);
    ArrayNode metadata =
        updatedMetadata(old, input.payload(), input.rowIds(), input.reviewedPaths());
    JsonNode issues =
        combinedIssues(
            d.documentType,
            input.payload(),
            metadata,
            json.read(old.issuesJson),
            input.reviewedPaths(),
            json.read(old.payloadJson),
            json.read(old.rowIdsJson),
            input.rowIds());
    Revision revision =
        create(
            d,
            user,
            old.runId,
            input.payload(),
            metadata,
            issues,
            json.mapper.valueToTree(input.rowIds()),
            "human",
            input.reason());
    store.audit(
        d,
        user,
        "SAVE",
        Map.of("base_revision_id", old.id, "revision_id", revision.id, "reason", input.reason()));
    return documents.view(d);
  }

  @Transactional
  public DocumentService.DocumentView adopt(String id, String user, Requests.Adopt input) {
    Document d = store.owned(id, user, true);
    store.compare(d, input.baseRevisionId(), input.expectedDocumentVersion());
    ExtractionRun run = store.run(input.runId(), d);
    JsonNode result = json.read(run.resultJson);
    JsonNode payload = result.get("payload");
    ArrayNode rows = rows(payload);
    create(
        d,
        user,
        run.id,
        payload,
        result.get("field_metadata"),
        combinedIssues(
            d.documentType,
            payload,
            result.get("field_metadata"),
            result.get("issues"),
            List.of(),
            payload,
            rows,
            toStrings(rows)),
        rows,
        "adopt",
        input.reason());
    store.audit(
        d,
        user,
        "ADOPT_RUN",
        Map.of("run_id", run.id, "revision_id", d.headRevisionId, "reason", input.reason()));
    return documents.view(d);
  }

  @Transactional
  public DocumentService.DocumentView approve(String id, String user, Requests.Approve input) {
    Document d = store.owned(id, user, true);
    store.compare(d, input.revisionId(), input.expectedDocumentVersion());
    Revision r = store.revision(input.revisionId(), d);
    if (r.approvedAt != null)
      throw new ApiException(409, "ALREADY_APPROVED", "Phiên bản này đã được duyệt.");
    validator.business(d.documentType, json.read(r.payloadJson));
    ArrayNode issues = validator.issues(d.documentType, json.read(r.payloadJson));
    for (JsonNode issue : json.read(r.issuesJson)) merge(issues, issue);
    List<String> warningIds = new ArrayList<>();
    for (JsonNode issue : issues) {
      if (issue.path("severity").asText().equals("blocking"))
        throw new ApiException(
            409,
            "APPROVAL_BLOCKED",
            "Hãy xử lý các vấn đề chặn trước khi duyệt.",
            Map.of("issues", issues));
      if (issue.path("severity").asText().equals("warning"))
        warningIds.add(issue.path("id").asText());
    }
    if (!input.confirmedReview() || !input.acknowledgedIssueIds().containsAll(warningIds))
      throw new ApiException(
          409,
          "REVIEW_CONFIRMATION_REQUIRED",
          "Cần xác nhận đã đối chiếu và chấp nhận từng cảnh báo.");
    if (!new HashSet<>(warningIds).containsAll(input.acknowledgedIssueIds()))
      throw new ApiException(
          422, "UNKNOWN_WARNING", "Danh sách xác nhận có cảnh báo không thuộc revision hiện tại.");
    r.approvedAt = Instant.now();
    r.approvedBy = user;
    r.approvalReason = input.reason();
    r.acknowledgementsJson = json.write(input.acknowledgedIssueIds());
    d.version++;
    store.audit(
        d,
        user,
        "APPROVE",
        Map.of(
            "revision_id",
            r.id,
            "reason",
            input.reason(),
            "acknowledged_issue_ids",
            input.acknowledgedIssueIds()));
    return documents.view(d);
  }

  /** Called in the completion transaction. A rerun never replaces an existing head. */
  public void initial(Document d, ExtractionRun run) {
    if (d.headRevisionId != null) return;
    JsonNode result = json.read(run.resultJson);
    JsonNode payload = result.get("payload");
    ArrayNode rows = rows(payload);
    create(
        d,
        d.ownerId,
        run.id,
        payload,
        result.get("field_metadata"),
        combinedIssues(
            d.documentType,
            payload,
            result.get("field_metadata"),
            result.get("issues"),
            List.of(),
            payload,
            rows,
            toStrings(rows)),
        rows,
        "prediction",
        "Kết quả xử lý đầu tiên");
  }

  private Revision create(
      Document d,
      String user,
      String run,
      JsonNode payload,
      JsonNode metadata,
      JsonNode issues,
      JsonNode rows,
      String origin,
      String reason) {
    Revision r = new Revision();
    r.id = Store.id();
    r.documentId = d.id;
    r.parentId = d.headRevisionId;
    r.runId = run;
    r.payloadJson = json.write(payload);
    r.metadataJson = json.write(metadata);
    r.issuesJson = json.write(issues);
    r.rowIdsJson = json.write(rows);
    r.origin = origin;
    r.actorId = user;
    r.reason = reason;
    r.createdAt = Instant.now();
    store.em().persist(r);
    d.headRevisionId = r.id;
    d.version++;
    return r;
  }

  private ArrayNode rows(JsonNode payload) {
    ArrayNode rows = json.mapper.createArrayNode();
    for (JsonNode ignored : payload.path("items")) rows.add(Store.id());
    return rows;
  }

  private List<String> toStrings(JsonNode rows) {
    List<String> result = new ArrayList<>();
    rows.forEach(r -> result.add(r.asText()));
    return result;
  }

  private String oldPath(String path, JsonNode oldRows, List<String> newRows) {
    if (!path.startsWith("/items/")) return path;
    String[] parts = path.split("/", 4);
    int index = Integer.parseInt(parts[2]);
    if (index >= newRows.size()) return null;
    int oldIndex = toStrings(oldRows).indexOf(newRows.get(index));
    return oldIndex < 0 ? null : "/items/" + oldIndex + (parts.length > 3 ? "/" + parts[3] : "");
  }

  private ArrayNode updatedMetadata(
      Revision old, JsonNode payload, List<String> rows, List<String> reviewed) {
    JsonNode previous = json.read(old.payloadJson), oldRows = json.read(old.rowIdsJson);
    Map<String, JsonNode> sources = new HashMap<>();
    json.read(old.metadataJson).forEach(m -> sources.put(m.path("path").asText(), m));
    ArrayNode result = json.mapper.createArrayNode();
    List<String> paths = new ArrayList<>();
    payload
        .fieldNames()
        .forEachRemaining(
            k -> {
              if (!k.equals("items")) paths.add("/" + k);
            });
    for (int i = 0; i < payload.path("items").size(); i++) {
      final int index = i;
      payload
          .path("items")
          .get(i)
          .fieldNames()
          .forEachRemaining(k -> paths.add("/items/" + index + "/" + k));
    }
    for (String path : paths) {
      String oldPath = oldPath(path, oldRows, rows);
      JsonNode source = oldPath == null ? null : sources.get(oldPath);
      ObjectNode m = source == null ? json.mapper.createObjectNode() : source.deepCopy();
      m.put("path", path);
      boolean changed =
          oldPath == null
              || !previous.at(oldPath).equals(payload.at(path))
              || reviewed.contains(path);
      if (source == null) {
        m.putNull("raw_value");
        m.putArray("source_regions");
        m.putNull("ocr_score");
        m.putNull("confidence");
        m.putNull("confidence_method");
        m.putArray("review_flags");
      }
      if (changed) {
        m.put("value_origin", "human");
        m.putNull("confidence");
        m.putNull("confidence_method");
        m.putArray("review_flags").add("human_reviewed");
      } else if (!m.has("value_origin"))
        m.put("value_origin", payload.at(path).isNull() ? "absent" : "prediction");
      result.add(m);
    }
    return result;
  }

  private ArrayNode combinedIssues(
      String type,
      JsonNode payload,
      JsonNode metadata,
      JsonNode source,
      List<String> reviewed,
      JsonNode oldPayload,
      JsonNode oldRows,
      List<String> rows) {
    ArrayNode result = validator.issues(type, payload);
    for (JsonNode issue : source) {
      // Derived rules are recalculated from all operands in the new payload.
      if (Set.of("LINE_ARITHMETIC", "TOTAL_ARITHMETIC", "TOTAL_REQUIRED", "FIELD_MISSING",
              "INVALID_DATE", "INVALID_TIME", "TABLE_COMPLETENESS")
          .contains(issue.path("code").asText())) continue;
      boolean keep = true;
      ArrayNode mapped = json.mapper.createArrayNode();
      for (JsonNode p : issue.path("paths")) {
        String path = p.asText(), newPath = path;
        if (path.startsWith("/items/")) {
          String[] parts = path.split("/", 4);
          int index = Integer.parseInt(parts[2]);
          if (index >= oldRows.size()) {
            keep = false;
            break;
          }
          int newIndex = rows.indexOf(oldRows.get(index).asText());
          if (newIndex < 0) {
            keep = false;
            break;
          }
          newPath = "/items/" + newIndex + (parts.length > 3 ? "/" + parts[3] : "");
        }
        if (payload.at(newPath).isMissingNode()
            || !payload.at(newPath).equals(oldPayload.at(path))
            || reviewed.contains(newPath)) keep = false;
        mapped.add(newPath);
      }
      if ("PROFILE_UNSUPPORTED".equals(issue.path("code").asText())) keep = true;
      if (keep) {
        ObjectNode copy = issue.deepCopy();
        copy.set("paths", mapped);
        if (copy.path("code").asText().contains("AMBIGU")
            && mapped.toString().contains("/total_amount")) copy.put("severity", "blocking");
        merge(result, copy);
      }
    }
    for (JsonNode m : metadata)
      if (m.path("path").asText().equals("/total_amount"))
        for (JsonNode flag : m.path("review_flags"))
          if (flag.asText().toLowerCase(Locale.ROOT).contains("ambigu"))
            validator.add(
                result,
                "TOTAL_AMBIGUOUS",
                "blocking",
                "/total_amount",
                "Tổng tiền còn mơ hồ. Hãy sửa hoặc đánh dấu đã đối chiếu trường này rồi lưu.");
    return result;
  }

  private void merge(ArrayNode target, JsonNode issue) {
    for (JsonNode i : target) if (i.path("id").equals(issue.path("id"))) return;
    target.add(issue);
  }
}
