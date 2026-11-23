package vn.vietdoc.document;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.common.Json;
import vn.vietdoc.job.JobService;

class ArtifactPromoterTest {
  @TempDir Path temporary;
  private final ObjectMapper mapper = new ObjectMapper();
  private JobService.Claim claim;
  private ObjectNode envelope;
  private ArtifactPromoter promoter;
  private Path attempt;
  private byte[] png;

  @BeforeEach
  void setUp() throws Exception {
    JsonNode request = mapper.readTree(Files.readString(Path.of("..", "tests", "contract", "compute-request.json")));
    claim = new JobService.Claim(request.path("job_id").asText(),
        "55555555-5555-4555-8555-555555555555", request.path("run_id").asText(),
        "66666666-6666-4666-8666-666666666666", request.path("attempt_id").asText(),
        "receipt", request.path("input_sha256").asText(), "http",
        request.path("pipeline_manifest_id").asText(), Instant.now().plusSeconds(60));
    envelope = (ObjectNode) mapper.readTree(Files.readString(Path.of("..", "tests", "contract", "compute-response.json")));
    Path attemptsRoot = temporary.resolve("attempts");
    attempt = attemptsRoot.resolve(claim.id()).resolve(claim.attemptId());
    Files.createDirectories(attempt);
    promoter = new ArtifactPromoter(new PrivateStorage(temporary.resolve("java").toString(), 20_000_000), attemptsRoot.toString());
    var image = new BufferedImage(2, 3, BufferedImage.TYPE_INT_RGB);
    var encoded = new ByteArrayOutputStream();
    assertTrue(ImageIO.write(image, "png", encoded));
    png = encoded.toByteArray();
    put(0, png);
    put(1, "{\"page\":0,\"width\":2,\"height\":3,\"blocks\":[]}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    ((ObjectNode) envelope.path("canonical_page")).put("width", 2).put("height", 3)
        .put("sha256", Json.sha256(png));
  }

  @Test
  void copiesVerifiedBytesAndReadsOnlyCommittedCanonical() throws Exception {
    var promoted = promoter.promote(claim, envelope);
    assertArrayEquals(png, promoter.readCanonical(claim.runId(), promoted));
    assertEquals(2, promoted.width());
    assertTrue(Files.exists(temporary.resolve("java/promoted").resolve(claim.runId()).resolve("promotion.properties")));
    Files.write(attempt.resolve("canonical.png"), new byte[] {1, 2, 3});
    assertArrayEquals(png, promoter.readCanonical(claim.runId(), promoted));
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
  }

  @Test
  void rejectsChangedHashSizeAndFrameBeforePublishing() throws Exception {
    Files.write(attempt.resolve("ocr.json"), "changed".getBytes());
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    put(1, "{\"page\":0,\"width\":2,\"height\":3,\"blocks\":[]}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    ((ObjectNode) envelope.path("canonical_page")).put("width", 4);
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    assertFalse(Files.exists(temporary.resolve("java/promoted").resolve(claim.runId())));
  }

  @Test
  void rejectsOcrFrameAndReferencesToMissingBlocks() throws Exception {
    put(1, "{\"page\":0,\"width\":3,\"height\":3,\"blocks\":[]}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    put(1, "{\"page\":0,\"width\":2,\"height\":3,\"blocks\":[]}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    var metadata = ((ObjectNode) envelope.path("result")).putArray("field_metadata").addObject();
    metadata.putArray("source_regions").addObject().putArray("ocr_block_ids").add("missing-block");
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    assertFalse(Files.exists(temporary.resolve("java/promoted").resolve(claim.runId())));
  }

  @Test
  void rejectsTraversalForeignAttemptAndMissingFile() throws Exception {
    String foreign = "attempts/99999999-9999-4999-8999-999999999999/" + claim.attemptId() + "/ocr.json";
    ((ObjectNode) envelope.path("artifacts").get(1)).put("asset_key", foreign);
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    ((ObjectNode) envelope.path("artifacts").get(1)).put("asset_key",
        "attempts/" + claim.id() + "/" + claim.attemptId() + "/../ocr.json");
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
    ((ObjectNode) envelope.path("artifacts").get(1)).put("asset_key",
        "attempts/" + claim.id() + "/" + claim.attemptId() + "/ocr.json");
    Files.delete(attempt.resolve("ocr.json"));
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
  }

  @Test
  void rejectsCanonicalSymlinkEvenWithMatchingDeclaredBytes() throws Exception {
    Path outside = temporary.resolve("outside.png");
    Files.write(outside, png);
    Files.delete(attempt.resolve("canonical.png"));
    try { Files.createSymbolicLink(attempt.resolve("canonical.png"), outside); }
    catch (UnsupportedOperationException | java.nio.file.FileSystemException e) {
      Assumptions.abort("This host cannot create symlinks: " + e.getClass().getSimpleName());
    }
    assertEquals("MODEL_OUTPUT_INVALID", assertThrows(ApiException.class,
        () -> promoter.promote(claim, envelope)).code);
  }

  private void put(int index, byte[] bytes) throws Exception {
    ObjectNode artifact = (ObjectNode) envelope.path("artifacts").get(index);
    String key = artifact.path("asset_key").asText();
    String name = key.substring(key.lastIndexOf('/') + 1);
    Files.write(attempt.resolve(name), bytes);
    artifact.put("size_bytes", bytes.length);
    artifact.put("sha256", Json.sha256(bytes));
  }
}
