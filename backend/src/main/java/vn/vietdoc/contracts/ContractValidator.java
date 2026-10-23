package vn.vietdoc.contracts;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import vn.vietdoc.common.*;

/** Validates the vocabulary used by the four versioned schemas; no network ref resolution. */
@Component
public class ContractValidator {
  private final Json json;
  private final Map<String, JsonNode> schemas = new HashMap<>();

  public ContractValidator(Json json) throws Exception {
    this.json = json;
    for (String name : List.of("business", "extraction-result", "export", "job-message")) {
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
