package vn.vietdoc.document;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import javax.imageio.ImageIO;
import javax.imageio.stream.ImageInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import vn.vietdoc.common.ApiException;
import vn.vietdoc.job.JobService.Claim;

/** Copies untrusted attempt files into an immutable Java-owned run directory. */
@Component
public class ArtifactPromoter {
  public record Promoted(String canonicalKey, String canonicalHash, int width, int height) {}
  private final Path attemptsRoot;
  private final Path committedRoot;
  private static final int MAX_OCR_BYTES = 8 * 1024 * 1024;
  private static final ObjectMapper OCR_MAPPER = new ObjectMapper(JsonFactory.builder()
      .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
      .streamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(32).build())
      .build());

  public ArtifactPromoter(PrivateStorage storage,
      @Value("${vietdoc.attempts-root:./runtime/ai-attempts}") String attemptsRoot) {
    this.attemptsRoot = Path.of(attemptsRoot).toAbsolutePath().normalize();
    this.committedRoot = storage.root().resolve("promoted");
  }

  public Promoted promote(Claim claim, JsonNode envelope) {
    String prefix = "attempts/" + claim.id() + "/" + claim.attemptId() + "/";
    Path attempt = attemptsRoot.resolve(claim.id()).resolve(claim.attemptId());
    Path staging = null;
    try {
      regularDirectory(attemptsRoot);
      regularDirectory(attemptsRoot.resolve(claim.id()));
      regularDirectory(attempt);
      Files.createDirectories(committedRoot);
      regularDirectory(committedRoot);
      Path stagingRoot = committedRoot.resolve(".staging");
      Files.createDirectories(stagingRoot);
      regularDirectory(stagingRoot);
      staging = Files.createTempDirectory(stagingRoot, claim.runId() + "-");
      String canonicalKey = envelope.path("canonical_page").path("asset_key").asText();
      String canonicalName = filename(canonicalKey, prefix);
      Set<String> names = new HashSet<>();
      long total = 0;
      Properties manifest = new Properties();
      manifest.setProperty("job_id", claim.id());
      manifest.setProperty("run_id", claim.runId());
      manifest.setProperty("attempt_id", claim.attemptId());
      int index = 0;
      for (JsonNode artifact : envelope.path("artifacts")) {
        String name = filename(artifact.path("asset_key").asText(), prefix);
        if (!names.add(name)) invalid();
        long expectedSize = artifact.path("size_bytes").asLong();
        if (expectedSize <= 0 || expectedSize > 50L * 1024 * 1024) invalid();
        total += expectedSize;
        if (total > 150L * 1024 * 1024) invalid();
        Path source = attempt.resolve(name);
        if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(source))
          invalid();
        String copiedHash = copyChecked(source, staging.resolve(name), expectedSize);
        if (!copiedHash.equals(artifact.path("sha256").asText())) invalid();
        manifest.setProperty("artifact." + index + ".name", name);
        manifest.setProperty("artifact." + index + ".sha256", copiedHash);
        manifest.setProperty("artifact." + index + ".kind", artifact.path("kind").asText());
        index++;
      }
      if (!names.contains(canonicalName)) invalid();
      JsonNode canonicalArtifact = null;
      JsonNode ocrArtifact = null;
      for (JsonNode artifact : envelope.path("artifacts"))
        if (artifact.path("asset_key").asText().equals(canonicalKey)) canonicalArtifact = artifact;
        else if ("ocr".equals(artifact.path("kind").asText())) ocrArtifact = artifact;
      if (canonicalArtifact == null || !"canonical_page".equals(canonicalArtifact.path("kind").asText())
          || !"image/png".equals(canonicalArtifact.path("media_type").asText())
          || !canonicalArtifact.path("sha256").asText().equals(envelope.path("canonical_page").path("sha256").asText()))
        invalid();
      int width = envelope.path("canonical_page").path("width").asInt();
      int height = envelope.path("canonical_page").path("height").asInt();
      if (width <= 0 || height <= 0 || (long) width * height > 20_000_000) invalid();
      verifyPng(staging.resolve(canonicalName), width, height);
      if (ocrArtifact == null || !"application/json".equals(ocrArtifact.path("media_type").asText())
          || ocrArtifact.path("size_bytes").asLong() > MAX_OCR_BYTES) invalid();
      verifyOcr(staging.resolve(filename(ocrArtifact.path("asset_key").asText(), prefix)),
          width, height, envelope.path("result").path("field_metadata"));
      manifest.setProperty("canonical_name", canonicalName);
      manifest.setProperty("canonical_hash", canonicalArtifact.path("sha256").asText());
      try (OutputStream out = Files.newOutputStream(staging.resolve("promotion.properties"),
          StandardOpenOption.CREATE_NEW)) {
        manifest.store(out, "VietDoc promoted run; orphan cleanup uses this manifest");
      }
      Path committed = committedRoot.resolve(claim.runId());
      if (Files.exists(committed, LinkOption.NOFOLLOW_LINKS)) invalid();
      Files.move(staging, committed, StandardCopyOption.ATOMIC_MOVE);
      staging = null;
      return new Promoted("promoted/" + claim.runId() + "/" + canonicalName,
          canonicalArtifact.path("sha256").asText(), width, height);
    } catch (ApiException e) {
      throw e;
    } catch (IOException e) {
      throw new ApiException(503, "STORAGE_UNAVAILABLE", "Không copy được compute artifact.");
    } finally {
      if (staging != null) removeStaging(staging);
    }
  }

  public byte[] readCanonical(String runId, Promoted asset) {
    if (asset == null || runId == null || !runId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}"))
      throw storageUnavailable();
    String prefix = "promoted/" + runId + "/";
    String name = safeFilename(asset.canonicalKey(), prefix);
    if (name == null) throw storageUnavailable();
    Path directory = committedRoot.resolve(runId);
    try {
      regularCommittedDirectory(committedRoot);
      regularCommittedDirectory(directory);
      Path path = directory.resolve(name);
      if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
        throw storageUnavailable();
      byte[] bytes;
      try (InputStream in = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
        bytes = in.readNBytes(50 * 1024 * 1024 + 1);
      }
      if (bytes.length > 50L * 1024 * 1024
          || !vn.vietdoc.common.Json.sha256(bytes).equals(asset.canonicalHash()))
        throw storageUnavailable();
      return bytes;
    } catch (IOException e) {
      throw storageUnavailable();
    }
  }

  private String filename(String key, String prefix) {
    String name = safeFilename(key, prefix);
    if (name == null) { invalid(); return ""; }
    return name;
  }

  private String safeFilename(String key, String prefix) {
    if (key == null || !key.startsWith(prefix)) return null;
    String name = key.substring(prefix.length());
    // The current Python AttemptWriter publishes flat, exclusive filenames.
    if (!name.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}") || name.equals("promotion.properties"))
      return null;
    return name;
  }

  private void regularDirectory(Path path) {
    if (!isRegularDirectory(path)) invalid();
  }

  private void regularCommittedDirectory(Path path) {
    if (!isRegularDirectory(path)) throw storageUnavailable();
  }

  private boolean isRegularDirectory(Path path) {
    for (Path part = path; part != null; part = part.getParent())
      if (Files.isSymbolicLink(part)) return false;
    return Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
  }

  private String copyChecked(Path source, Path target, long expectedSize) throws IOException {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      long copied = 0;
      try (InputStream in = Files.newInputStream(source, LinkOption.NOFOLLOW_LINKS);
          OutputStream out = Files.newOutputStream(target, StandardOpenOption.CREATE_NEW)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
          copied += count;
          if (copied > expectedSize) invalid();
          digest.update(buffer, 0, count);
          out.write(buffer, 0, count);
        }
      }
      if (copied != expectedSize) invalid();
      return HexFormat.of().formatHex(digest.digest());
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  private void verifyPng(Path file, int width, int height) {
    try (ImageInputStream stream = ImageIO.createImageInputStream(file.toFile())) {
      if (stream == null) { invalid(); return; }
      var readers = ImageIO.getImageReaders(stream);
      if (!readers.hasNext()) { invalid(); return; }
      var reader = readers.next();
      try {
        reader.setInput(stream);
        if (!"png".equalsIgnoreCase(reader.getFormatName()) || reader.getNumImages(true) != 1
            || reader.getWidth(0) != width || reader.getHeight(0) != height) invalid();
        BufferedImage decoded = reader.read(0);
        if (decoded == null || decoded.getWidth() != width || decoded.getHeight() != height)
          invalid();
      } finally { reader.dispose(); }
    } catch (ApiException e) { throw e; }
      catch (IOException | RuntimeException e) { invalid(); }
  }

  private void verifyOcr(Path file, int width, int height, JsonNode metadata) {
    try {
      byte[] bytes = Files.readAllBytes(file);
      if (bytes.length > MAX_OCR_BYTES) invalid();
      JsonNode ocr;
      try (JsonParser parser = OCR_MAPPER.createParser(bytes)) {
        ocr = OCR_MAPPER.readTree(parser);
        if (ocr == null || parser.nextToken() != null) invalid();
      }
      if (!ocr.isObject() || !ocr.path("page").isIntegralNumber()
          || !ocr.path("width").isIntegralNumber() || !ocr.path("height").isIntegralNumber()
          || ocr.path("page").asInt(-1) != 0
          || ocr.path("width").asInt(-1) != width
          || ocr.path("height").asInt(-1) != height
          || !ocr.path("blocks").isArray() || ocr.path("blocks").size() > 20_000) invalid();
      Set<String> ids = new HashSet<>();
      for (JsonNode block : ocr.path("blocks")) {
        String id = block.path("block_id").asText();
        if (!block.path("block_id").isTextual() || id.isBlank() || !ids.add(id)) invalid();
      }
      for (JsonNode field : metadata)
        for (JsonNode region : field.path("source_regions"))
          for (JsonNode id : region.path("ocr_block_ids"))
            if (!ids.contains(id.asText())) invalid();
    } catch (IOException e) { invalid(); }
  }

  private void removeStaging(Path staging) {
    try (var paths = Files.walk(staging)) {
      for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
    } catch (IOException ignored) { /* Orphan staging is retained for bounded reconciliation. */ }
  }

  private void invalid() {
    throw new ApiException(422, "MODEL_OUTPUT_INVALID", "Compute artifact không khớp khai báo hoặc path không an toàn.");
  }

  private ApiException storageUnavailable() {
    return new ApiException(503, "STORAGE_UNAVAILABLE", "Ảnh canonical không khả dụng.");
  }
}
