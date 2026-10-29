package vn.vietdoc.common;

import java.util.Map;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class HealthController {
  private final DataSource database;
  private final String mode;

  public HealthController(DataSource database, @Value("${vietdoc.mode}") String mode) {
    this.database = database;
    this.mode = mode;
  }

  @GetMapping("/health/live")
  public Map<String, String> live() {
    return Map.of("status", "UP");
  }

  @GetMapping("/health/ready")
  public ResponseEntity<?> ready() {
    try (var connection = database.getConnection()) {
      return connection.isValid(2)
          ? ResponseEntity.ok(Map.of("status", "UP"))
          : ResponseEntity.status(503).body(Map.of("status", "DOWN"));
    } catch (Exception e) {
      return ResponseEntity.status(503).body(Map.of("status", "DOWN"));
    }
  }

  @GetMapping("/api/v1/config")
  public Map<String, Object> config() {
    return Map.of(
        "ai_mode", mode, "max_file_bytes", 20 * 1024 * 1024, "max_items", 30, "language", "vi");
  }

  @GetMapping(value = "/api/v1/openapi", produces = "application/json")
  public byte[] openapi() throws java.io.IOException {
    return new org.springframework.core.io.ClassPathResource("openapi.json")
        .getInputStream()
        .readAllBytes();
  }
}
