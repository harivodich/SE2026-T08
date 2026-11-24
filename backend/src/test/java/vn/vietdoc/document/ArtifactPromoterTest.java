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
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.imageio.ImageIO;
import javax.imageio.ImageReadParam;
import javax.imageio.ImageReader;
import javax.imageio.ImageTypeSpecifier;
import javax.imageio.metadata.IIOMetadata;
import javax.imageio.spi.IIORegistry;
import javax.imageio.spi.ImageReaderSpi;
import javax.imageio.stream.ImageInputStream;
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

  @Test
  void returnsStorageUnavailableWhenCommittedCanonicalIsCorruptedDeletedOrUnsafe() throws Exception {
    var promoted = promoter.promote(claim, envelope);
    Path committed = temporary.resolve("java/promoted").resolve(claim.runId()).resolve("canonical.png");

    Files.write(committed, new byte[] {9, 8, 7});
    ApiException corrupted = assertThrows(ApiException.class,
        () -> promoter.readCanonical(claim.runId(), promoted));
    assertEquals(503, corrupted.status);
    assertEquals("STORAGE_UNAVAILABLE", corrupted.code);

    Files.delete(committed);
    ApiException deleted = assertThrows(ApiException.class,
        () -> promoter.readCanonical(claim.runId(), promoted));
    assertEquals(503, deleted.status);
    assertEquals("STORAGE_UNAVAILABLE", deleted.code);

    var traversal = new ArtifactPromoter.Promoted(
        "promoted/" + claim.runId() + "/../canonical.png", promoted.canonicalHash(), 2, 3);
    ApiException unsafe = assertThrows(ApiException.class,
        () -> promoter.readCanonical(claim.runId(), traversal));
    assertEquals(503, unsafe.status);
    assertEquals("STORAGE_UNAVAILABLE", unsafe.code);
  }

  @Test
  void rejectsPngDecoderRuntimeExceptionAsModelOutputInvalid() {
    AtomicBoolean invoked = new AtomicBoolean();
    ImageReaderSpi throwingSpi = new ImageReaderSpi(
        "vietdoc-test", "1.0", new String[] {"png"}, new String[] {"png"},
        new String[] {"image/png"}, ImageReader.class.getName(),
        new Class<?>[] {ImageInputStream.class}, null,
        false, null, null, null, null, false, null, null, null, null) {
      @Override public boolean canDecodeInput(Object source) {
        return source instanceof ImageInputStream;
      }
      @Override public ImageReader createReaderInstance(Object extension) {
        return new ImageReader(this) {
          @Override public int getNumImages(boolean allowSearch) { return 1; }
          @Override public int getWidth(int imageIndex) { return 2; }
          @Override public int getHeight(int imageIndex) { return 3; }
          @Override public Iterator<ImageTypeSpecifier> getImageTypes(int imageIndex) {
            return List.<ImageTypeSpecifier>of().iterator();
          }
          @Override public IIOMetadata getStreamMetadata() { return null; }
          @Override public IIOMetadata getImageMetadata(int imageIndex) { return null; }
          @Override public BufferedImage read(int imageIndex, ImageReadParam param) {
            invoked.set(true);
            throw new IllegalArgumentException("Corrupt PNG decoder state");
          }
        };
      }
      @Override public String getDescription(Locale locale) { return "test throwing png reader"; }
    };
    IIORegistry registry = IIORegistry.getDefaultInstance();
    List<ImageReaderSpi> existing = new ArrayList<>();
    registry.getServiceProviders(ImageReaderSpi.class, false).forEachRemaining(existing::add);
    registry.registerServiceProvider(throwingSpi, ImageReaderSpi.class);
    try {
      for (ImageReaderSpi provider : existing)
        registry.setOrdering(ImageReaderSpi.class, throwingSpi, provider);
      ApiException failure = assertThrows(ApiException.class,
          () -> promoter.promote(claim, envelope));
      assertTrue(invoked.get());
      assertEquals(422, failure.status);
      assertEquals("MODEL_OUTPUT_INVALID", failure.code);
      assertFalse(Files.exists(temporary.resolve("java/promoted").resolve(claim.runId())));
    } finally {
      registry.deregisterServiceProvider(throwingSpi, ImageReaderSpi.class);
    }
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
