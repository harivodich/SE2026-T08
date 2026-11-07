package vn.vietdoc.common;

import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

@Component
public class Json {
  public final ObjectMapper mapper;

  public Json(ObjectMapper mapper) {
    this.mapper = mapper;
  }

  public String write(Object value) {
    try {
      return mapper.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalStateException("JSON serialization", e);
    }
  }

  public JsonNode read(String value) {
    try {
      return mapper.readTree(value);
    } catch (Exception e) {
      throw new IllegalStateException("Stored JSON invalid", e);
    }
  }

  public static String sha256(byte[] bytes) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  public static String sha256(String value) {
    return sha256(value.getBytes(StandardCharsets.UTF_8));
  }
}
