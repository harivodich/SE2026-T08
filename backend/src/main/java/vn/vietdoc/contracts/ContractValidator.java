package vn.vietdoc.contracts;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import vn.vietdoc.common.*;

/** Validates the locally bundled shared schemas and owning business rules; no network refs. */
@Component
public class ContractValidator {
  private final Json json;
  private final Map<String, JsonNode> schemas = new HashMap<>();

  public ContractValidator(Json json) throws Exception {
    this.json = json;
    for (String name : List.of("business", "extraction-result", "export", "job-message",
        "compute-request", "compute-response", "compute-error")) {
      JsonNode schema =
          json.mapper.readTree(
              new ClassPathResource("contracts/" + name + ".schema.json").getInputStream());
      schemas.put(schema.path("$id").asText(), schema);
    }
  }

  public void type(String type) {
    if (!Set.of("receipt", "invoice").contains(type))
      invalid("/document_type", "Chỉ hỗ trợ receipt hoặc invoice.");
  }

  public BusinessPayloads.Payload business(String type, JsonNode payload) {
    type(type);
    JsonNode root = schemas.get("urn:vietdoc:business:v1");
    check(
        payload,
        root.path("$defs").path(type.equals("receipt") ? "Receipt" : "Invoice"),
        root,
        "",
        0);
    try {
      return type.equals("receipt")
          ? json.mapper.treeToValue(payload, BusinessPayloads.Receipt.class)
          : json.mapper.treeToValue(payload, BusinessPayloads.Invoice.class);
    } catch (Exception e) {
      throw new IllegalStateException("Validated business payload could not map to its DTO", e);
    }
  }

  public void extraction(
      String type, String runId, String jobId, String manifest, JsonNode result) {
    JsonNode root = schemas.get("urn:vietdoc:extraction-result:v1");
    check(result, root, root, "", 0);
    business(type, result.get("payload"));
    if (!type.equals(result.path("document_type").asText())
        || !runId.equals(result.path("run_id").asText())
        || !jobId.equals(result.path("job_id").asText())
        || !manifest.equals(result.path("provenance").path("pipeline_manifest_id").asText()))
      invalid("/", "Worker trả sai ID, loại chứng từ hoặc manifest.");
    if (result.path("field_metadata").size() > 200 || result.path("issues").size() > 200)
      invalid("/", "Quá nhiều metadata/issues.");
    Set<String> paths = new HashSet<>();
    for (JsonNode m : result.path("field_metadata")) {
      String p = m.path("path").asText();
      pointer(result.get("payload"), p);
      if (!paths.add(p)) invalid(p, "Metadata trùng path.");
      if (!m.path("confidence").isNull()
          && (m.path("confidence_method").isNull()
              || m.path("confidence_method").asText().isBlank()))
        invalid(p, "Confidence cần phương pháp hiệu chuẩn.");
      for (JsonNode region : m.path("source_regions")) {
        validateQuad(region.path("quad"), p);
        Set<String> blockIds = new HashSet<>();
        for (JsonNode blockId : region.path("ocr_block_ids"))
          if (blockId.asText().isBlank() || !blockIds.add(blockId.asText()))
            invalid(p, "OCR block ID rỗng hoặc trùng.");
      }
    }
    Set<String> ids = new HashSet<>();
    for (JsonNode issue : result.path("issues")) {
      if (!ids.add(issue.path("id").asText())) invalid("/issues", "Issue ID bị trùng.");
      for (JsonNode p : issue.path("paths")) pointer(result.get("payload"), p.asText());
    }
  }

  public void export(JsonNode envelope) {
    JsonNode root = schemas.get("urn:vietdoc:export:v1");
    check(envelope, root, root, "", 0);
  }

  public void computeRequest(JsonNode request) {
    JsonNode root = schemas.get("urn:vietdoc:compute-request:v1");
    check(request, root, root, "", 0);
  }

  public void computeResponse(JsonNode request, JsonNode response) {
    computeRequest(request);
    JsonNode root = schemas.get("urn:vietdoc:compute-response:v1");
    check(response, root, root, "", 0);
    String jobId = request.path("job_id").asText();
    String attemptId = request.path("attempt_id").asText();
    if (!attemptId.equals(response.path("attempt_id").asText()))
      invalid("/attempt_id", "Compute trả sai attempt ID.");
    JsonNode result = response.path("result");
    extraction(request.path("document_type").asText(), request.path("run_id").asText(),
        jobId, request.path("pipeline_manifest_id").asText(), result);
    if (!request.path("schema_version").asText().equals(result.path("schema_version").asText())
        || !request.path("language").asText().equals(result.path("language").asText()))
      invalid("/result", "Compute trả sai schema hoặc ngôn ngữ.");

    JsonNode canonical = response.path("canonical_page");
    if ((long) canonical.path("width").asInt() * canonical.path("height").asInt() > 20_000_000)
      invalid("/canonical_page", "Trang canonical vượt giới hạn pixel.");
    String canonicalKey = canonical.path("asset_key").asText();
    Set<String> keys = new HashSet<>();
    int canonicalCount = 0;
    int ocrCount = 0;
    for (JsonNode artifact : response.path("artifacts")) {
      String key = artifact.path("asset_key").asText();
      attemptKey(key, jobId, attemptId);
      if (!keys.add(key)) invalid("/artifacts", "Artifact key bị trùng.");
      String kind = artifact.path("kind").asText();
      if (kind.equals("canonical_page")) {
        canonicalCount++;
        if (!canonicalKey.equals(key)
            || !canonical.path("sha256").asText().equals(artifact.path("sha256").asText())
            || !artifact.path("media_type").asText().startsWith("image/"))
          invalid("/canonical_page", "Canonical page không khớp artifact.");
      }
      if (kind.equals("ocr")) ocrCount++;
    }
    attemptKey(canonicalKey, jobId, attemptId);
    if (canonicalCount != 1 || ocrCount != 1)
      invalid("/artifacts", "Cần đúng một canonical page và một OCR artifact.");
  }

  public void computeError(JsonNode request, JsonNode error) {
    computeRequest(request);
    JsonNode root = schemas.get("urn:vietdoc:compute-error:v1");
    check(error, root, root, "", 0);
    if (!error.path("attempt_id").isNull()
        && !request.path("attempt_id").asText().equals(error.path("attempt_id").asText()))
      invalid("/attempt_id", "Compute error trả sai attempt ID.");
  }

  private void attemptKey(String key, String jobId, String attemptId) {
    String prefix = "attempts/" + jobId + "/" + attemptId + "/";
    if (!key.startsWith(prefix) || key.length() == prefix.length())
      invalid("/artifacts/asset_key", "Artifact không thuộc attempt hiện hành.");
    for (String segment : key.substring(prefix.length()).split("/", -1))
      if (segment.isEmpty() || segment.equals(".") || segment.equals(".."))
        invalid("/artifacts/asset_key", "Artifact key có path segment không hợp lệ.");
  }

  public void rowIds(JsonNode payload, List<String> ids) {
    if (ids == null
        || ids.size() != payload.path("items").size()
        || new HashSet<>(ids).size() != ids.size())
      invalid("/row_ids", "Row IDs phải duy nhất và khớp số dòng hàng.");
    for (String id : ids) {
      try {
        if (!UUID.fromString(id).toString().equals(id)) throw new IllegalArgumentException();
      } catch (Exception e) {
        invalid("/row_ids", "Row ID phải là UUID.");
      }
    }
  }

  public void pointer(JsonNode payload, String path) {
    try {
      if (!path.startsWith("/") || payload.at(path).isMissingNode())
        invalid(path, "Path không tồn tại trong payload.");
    } catch (IllegalArgumentException e) {
      invalid("/", "JSON Pointer không hợp lệ.");
    }
  }

  public JsonNode empty(String type) {
    type(type);
    ObjectNode result = json.mapper.createObjectNode();
    JsonNode props =
        schemas
            .get("urn:vietdoc:business:v1")
            .path("$defs")
            .path(type.equals("receipt") ? "Receipt" : "Invoice")
            .path("properties");
    props
        .fieldNames()
        .forEachRemaining(
            k -> {
              if (k.equals("items")) result.putArray(k);
              else result.putNull(k);
            });
    return result;
  }

  public ArrayNode issues(String type, JsonNode payload) {
    ArrayNode issues = json.mapper.createArrayNode();
    if (payload.path("total_amount").isNull())
      add(
          issues,
          "TOTAL_REQUIRED",
          "blocking",
          "/total_amount",
          "Cần nhập tổng tiền theo chứng từ trước khi duyệt.");
    for (String field :
        type.equals("receipt")
            ? List.of("merchant_name", "transaction_date")
            : List.of("invoice_number", "seller_name", "issue_date")) {
      if (payload.path(field).isNull() || payload.path(field).asText().isBlank())
        add(
            issues,
            "FIELD_MISSING",
            "warning",
            "/" + field,
            "Chưa có giá trị cho " + field + ". Hãy đối chiếu nguồn.");
    }
    String dateField = type.equals("receipt") ? "transaction_date" : "issue_date";
    if (!payload.path(dateField).isNull()) {
      try {
        LocalDate.parse(payload.path(dateField).asText());
      } catch (Exception e) {
        add(issues, "INVALID_DATE", "blocking", "/" + dateField, "Ngày không tồn tại trong lịch.");
      }
    }
    if (type.equals("receipt") && !payload.path("transaction_time").isNull()) {
      try {
        LocalTime.parse(payload.path("transaction_time").asText());
      } catch (Exception e) {
        add(issues, "INVALID_TIME", "blocking", "/transaction_time", "Giờ không hợp lệ.");
      }
    }
    JsonNode items = payload.path("items");
    if (items.isEmpty())
      add(
          issues,
          "TABLE_COMPLETENESS",
          "warning",
          "/items",
          "Chưa có dòng hàng. Xác nhận chứng từ không có bảng hoặc đã nhập đầy đủ.");
    for (int i = 0; i < items.size(); i++) {
      JsonNode row = items.get(i);
      BigDecimal quantity = decimal(row.get("quantity")),
          price = decimal(row.get("unit_price")),
          total = decimal(row.get("line_total"));
      if (quantity != null
          && price != null
          && total != null
          && quantity.multiply(price).compareTo(total) != 0)
        add(
            issues,
            "LINE_ARITHMETIC",
            "warning",
            "/items/" + i + "/line_total",
            "Thành tiền khác số lượng × đơn giá; giữ số trên nguồn và đối chiếu.");
    }
    if (type.equals("invoice")) {
      BigDecimal subtotal = decimal(payload.get("subtotal")),
          tax = decimal(payload.get("tax_amount")),
          discount = decimal(payload.get("discount_amount")),
          total = decimal(payload.get("total_amount"));
      if (subtotal != null
          && tax != null
          && discount != null
          && total != null
          && subtotal.add(tax).subtract(discount).compareTo(total) != 0)
        add(
            issues,
            "TOTAL_ARITHMETIC",
            "warning",
            "/total_amount",
            "Tổng khác trước thuế + thuế − giảm giá. Đối chiếu quy ước chứng từ.");
    }
    return issues;
  }

  public void add(ArrayNode target, String code, String severity, String path, String message) {
    ObjectNode issue = target.addObject();
    issue.put("id", code + ":" + path);
    issue.put("code", code);
    issue.put("severity", severity);
    issue.putArray("paths").add(path);
    issue.put("message", message);
  }

  private BigDecimal decimal(JsonNode n) {
    return n == null || n.isNull() ? null : new BigDecimal(n.asText());
  }

  private void validateQuad(JsonNode quad, String path) {
    double area = 0;
    double sign = 0;
    for (int i = 0; i < 4; i++) {
      JsonNode a = quad.get(i), b = quad.get((i + 1) % 4), c = quad.get((i + 2) % 4);
      double ax = a.get(0).asDouble(), ay = a.get(1).asDouble();
      double bx = b.get(0).asDouble(), by = b.get(1).asDouble();
      double cx = c.get(0).asDouble(), cy = c.get(1).asDouble();
      if (!Double.isFinite(ax) || !Double.isFinite(ay) || !Double.isFinite(bx) ||
          !Double.isFinite(by) || !Double.isFinite(cx) || !Double.isFinite(cy))
        invalid(path, "Quad có tọa độ không hữu hạn.");
      area += ax * by - bx * ay;
      double cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx);
      if (Math.abs(cross) < 1e-8 || (sign != 0 && Math.signum(cross) != sign))
        invalid(path, "Quad phải là tứ giác lồi, không tự cắt và có diện tích.");
      sign = Math.signum(cross);
    }
    if (Math.abs(area) < 1e-8) invalid(path, "Quad không có diện tích.");
  }

  private void invalid(String path, String message) {
    throw new ApiException(422, "CONTRACT_INVALID", message, Map.of("path", path));
  }

  private void check(JsonNode value, JsonNode schema, JsonNode root, String path, int depth) {
    if (depth > 30) invalid(path, "Contract lồng quá sâu.");
    if (schema.has("$ref")) {
      String ref = schema.get("$ref").asText();
      int pos = ref.indexOf('#');
      String base = pos < 0 ? ref : ref.substring(0, pos);
      String fragment = pos < 0 ? "" : ref.substring(pos + 1);
      JsonNode refRoot = base.isEmpty() ? root : schemas.get(base);
      if (refRoot == null) throw new IllegalStateException("Unknown schema ref");
      check(value, fragment.isEmpty() ? refRoot : refRoot.at(fragment), refRoot, path, depth + 1);
      return;
    }
    if (schema.has("oneOf")) {
      int matches = 0;
      for (JsonNode option : schema.get("oneOf")) {
        try {
          check(value, option, root, path, depth + 1);
          matches++;
        } catch (ApiException ignored) {
        }
      }
      if (matches != 1) invalid(path, "Dữ liệu không khớp duy nhất một schema.");
    }
    if (schema.has("allOf"))
      for (JsonNode option : schema.get("allOf")) {
        if (option.has("if")) {
          boolean applies = true;
          try {
            check(value, option.get("if"), root, path, depth + 1);
          } catch (ApiException e) {
            applies = false;
          }
          if (applies && option.has("then"))
            check(value, option.get("then"), root, path, depth + 1);
        } else check(value, option, root, path, depth + 1);
      }
    if (value == null) invalid(path, "Thiếu giá trị.");
    if (schema.has("type")) {
      JsonNode types = schema.get("type");
      boolean valid = false;
      if (types.isArray()) {
        for (JsonNode t : types) valid |= isType(value, t.asText());
      } else valid = isType(value, types.asText());
      if (!valid) invalid(path, "Sai kiểu dữ liệu; tiền và số lượng phải là chuỗi hoặc null.");
    }
    if (schema.has("const") && !schema.get("const").equals(value))
      invalid(path, "Giá trị cố định không khớp.");
    if (schema.has("enum")) {
      boolean found = false;
      for (JsonNode v : schema.get("enum")) found |= v.equals(value);
      if (!found) invalid(path, "Giá trị ngoài danh sách cho phép.");
    }
    if (value.isObject()) {
      JsonNode props = schema.path("properties");
      for (JsonNode required : schema.path("required"))
        if (!value.has(required.asText()))
          invalid(
              path + "/" + required.asText(), "Thiếu field bắt buộc, kể cả khi giá trị là null.");
      Iterator<String> keys = value.fieldNames();
      while (keys.hasNext()) {
        String key = keys.next();
        if (!props.has(key)
            && schema.has("additionalProperties")
            && !schema.get("additionalProperties").asBoolean())
          invalid(path + "/" + key, "Field không được phép.");
        if (props.has(key))
          check(value.get(key), props.get(key), root, path + "/" + key, depth + 1);
      }
    }
    if (value.isArray()) {
      if (schema.has("minItems") && value.size() < schema.get("minItems").asInt()
          || schema.has("maxItems") && value.size() > schema.get("maxItems").asInt())
        invalid(path, "Số phần tử vượt giới hạn.");
      if (schema.has("items"))
        for (int i = 0; i < value.size(); i++)
          check(value.get(i), schema.get("items"), root, path + "/" + i, depth + 1);
    }
    if (value.isTextual()) {
      String text = value.asText();
      int length = text.codePointCount(0, text.length());
      if (schema.has("minLength") && length < schema.get("minLength").asInt()
          || schema.has("maxLength") && length > schema.get("maxLength").asInt())
        invalid(path, "Độ dài vượt giới hạn.");
      if (schema.has("pattern")
          && !java.util.regex.Pattern.compile(schema.get("pattern").asText()).matcher(text).find())
        invalid(path, "Giá trị không đúng định dạng.");
      if ("uuid".equals(schema.path("format").asText())) {
        try {
          if (!UUID.fromString(text).toString().equals(text)) throw new IllegalArgumentException();
        } catch (Exception e) {
          invalid(path, "ID phải là UUID.");
        }
      }
    }
    if (value.isNumber()) {
      double n = value.asDouble();
      if (!Double.isFinite(n)
          || schema.has("minimum") && n < schema.get("minimum").asDouble()
          || schema.has("maximum") && n > schema.get("maximum").asDouble())
        invalid(path, "Số ngoài giới hạn.");
    }
  }

  private boolean isType(JsonNode value, String type) {
    return switch (type) {
      case "object" -> value.isObject();
      case "array" -> value.isArray();
      case "string" -> value.isTextual();
      case "number" -> value.isNumber();
      case "integer" -> value.isIntegralNumber();
      case "null" -> value.isNull();
      case "boolean" -> value.isBoolean();
      default -> throw new IllegalStateException("Unsupported schema type");
    };
  }
}
