package vn.vietdoc.export;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.nio.charset.StandardCharsets;
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
public class ExportService {
  private final Store store;
  private final Json json;
  private final ContractValidator validator;
  private final DocumentService documents;

  public ExportService(
      Store store, Json json, ContractValidator validator, DocumentService documents) {
    this.store = store;
    this.json = json;
    this.validator = validator;
    this.documents = documents;
  }

  @Transactional
  public DocumentService.ExportView create(String id, String user, Requests.Export input) {
    Document d = store.owned(id, user, true);
    Revision r = store.revision(input.revisionId(), d);
    if (r.approvedAt == null)
      throw new ApiException(409, "UNAPPROVED_REVISION", "Chỉ xuất được revision đã duyệt.");
    List<ExportArtifact> existing =
        store
            .em()
            .createQuery(
                "select e from ExportArtifact e where e.revisionId=:r and e.exporterVersion=1",
                ExportArtifact.class)
            .setParameter("r", r.id)
            .getResultList();
    if (!existing.isEmpty()) return documents.exportView(existing.get(0));
    JsonNode payload = json.read(r.payloadJson);
    validator.business(d.documentType, payload);
    ObjectNode body = json.mapper.createObjectNode();
    body.put("export_version", 1);
    body.put("document_id", d.id);
    body.put("revision_id", r.id);
    body.put("document_type", d.documentType);
    body.put("schema_version", d.documentType + ".v1");
    body.put("language", "vi");
    body.set("payload", sorted(payload));
    validator.export(body);
    ExportArtifact e = new ExportArtifact();
    e.id = Store.id();
    e.documentId = d.id;
    e.revisionId = r.id;
    e.exporterVersion = 1;
    e.bodyJson = json.write(body) + "\n";
    e.sha256 = Json.sha256(e.bodyJson);
    e.createdAt = Instant.now();
    store.em().persist(e);
    store.audit(
        d, user, "EXPORT", Map.of("revision_id", r.id, "export_id", e.id, "sha256", e.sha256));
    return documents.exportView(e);
  }

  @Transactional(readOnly = true)
  public byte[] download(String id, String user) {
    ExportArtifact e = store.em().find(ExportArtifact.class, id);
    if (e == null) throw ApiException.missing();
    store.owned(e.documentId, user, false);
    return e.bodyJson.getBytes(StandardCharsets.UTF_8);
  }

  private JsonNode sorted(JsonNode value) {
    if (value.isObject()) {
      ObjectNode out = json.mapper.createObjectNode();
      List<String> keys = new ArrayList<>();
      value.fieldNames().forEachRemaining(keys::add);
      Collections.sort(keys);
      keys.forEach(k -> out.set(k, sorted(value.get(k))));
      return out;
    }
    if (value.isArray()) {
      ArrayNode out = json.mapper.createArrayNode();
      value.forEach(v -> out.add(sorted(v)));
      return out;
    }
    return value;
  }
}
