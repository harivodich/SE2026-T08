package vn.vietdoc.document;

import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.concurrent.*;
import javax.imageio.*;
import javax.imageio.stream.ImageInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import vn.vietdoc.common.*;

@Component
public class PrivateStorage {
  public record Asset(String contentType, String hash, long size, int width, int height) {}
  private record Dimension(int width, int height) {}
  private static final Semaphore PDF_SLOTS = new Semaphore(2, true);
  private static final Duration PDF_TIMEOUT = Duration.ofSeconds(15);

  private final Path root;
  private final long maxPixels;

  public PrivateStorage(
      @Value("${vietdoc.storage}") String root, @Value("${vietdoc.max-pixels}") long maxPixels)
      throws IOException {
    this.root = Path.of(root).toAbsolutePath().normalize();
    this.maxPixels = maxPixels;
    Files.createDirectories(this.root);
  }

  public Path original(String id) {
    return directory(id).resolve("original");
  }

  public Path page(String id) {
    return directory(id).resolve("page.png");
  }

  private Path directory(String id) {
    try {
      if (!java.util.UUID.fromString(id).toString().equals(id))
        throw new IllegalArgumentException();
    } catch (Exception e) {
      throw ApiException.missing();
    }
    return root.resolve(id);
  }

  public Asset put(String id, MultipartFile input) {
    if (input.isEmpty()) throw new ApiException(422, "INPUT_CORRUPT", "File rỗng.");
    if (input.getSize() > 20L * 1024 * 1024)
      throw new ApiException(413, "FILE_TOO_LARGE", "File vượt giới hạn 20 MiB.");
    Path dir = directory(id);
    try {
      Files.createDirectories(dir);
      Path file = original(id);
      try (InputStream in = input.getInputStream();
          OutputStream out = Files.newOutputStream(file, StandardOpenOption.CREATE_NEW)) {
        byte[] buffer = new byte[8192];
        long count = 0;
        int n;
        while ((n = in.read(buffer)) != -1) {
          count += n;
          if (count > 20L * 1024 * 1024)
            throw new ApiException(413, "FILE_TOO_LARGE", "File vượt giới hạn 20 MiB.");
          out.write(buffer, 0, n);
        }
      }
      byte[] bytes = Files.readAllBytes(file);
      int width, height;
      String contentType;
      if (bytes.length > 5
          && new String(bytes, 0, 5, java.nio.charset.StandardCharsets.US_ASCII).equals("%PDF-")) {
        contentType = "application/pdf";
        Dimension size = renderPdfIsolated(file, dir.resolve("page.pending.png"));
        width = size.width();
        height = size.height();
      } else {
        boolean png =
            bytes.length >= 8
                && bytes[0] == (byte) 137
                && bytes[1] == 80
                && bytes[2] == 78
                && bytes[3] == 71;
        boolean jpeg =
            bytes.length >= 3
                && bytes[0] == (byte) 255
                && bytes[1] == (byte) 216
                && bytes[2] == (byte) 255;
        if (!png && !jpeg)
          throw new ApiException(415, "UNSUPPORTED_MEDIA", "Chỉ nhận JPEG, PNG hoặc PDF.");
        contentType = png ? "image/png" : "image/jpeg";
        BufferedImage image;
        try (ImageInputStream stream = ImageIO.createImageInputStream(file.toFile())) {
          var readers = ImageIO.getImageReaders(stream);
          if (!readers.hasNext()) throw new IOException();
          var reader = readers.next();
          try {
            reader.setInput(stream);
            checkPixels(reader.getWidth(0), reader.getHeight(0));
            image = reader.read(0);
          } finally {
            reader.dispose();
          }
        }
        if (image == null) throw new IOException();
        checkPixels(image.getWidth(), image.getHeight());
        if (!ImageIO.write(image, "png", page(id).toFile())) throw new IOException();
        width = image.getWidth();
        height = image.getHeight();
      }
      return new Asset(contentType, Json.sha256(bytes), bytes.length, width, height);
    } catch (ApiException e) {
      remove(id);
      throw e;
    } catch (Exception e) {
      remove(id);
      throw new ApiException(
          422,
          "INPUT_CORRUPT",
          "Không giải mã được file. Hãy dùng ảnh rõ hoặc PDF một trang hợp lệ.");
    }
  }

  private Dimension renderPdfIsolated(Path input, Path pending) throws Exception {
    if (!PDF_SLOTS.tryAcquire())
      throw new ApiException(429, "PDF_RENDER_BUSY", "Renderer PDF đang bận. Hãy thử lại.");
    try {
      String java = Path.of(System.getProperty("java.home"), "bin",
          System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java").toString();
      String classPath = System.getProperty("surefire.test.class.path",
          System.getProperty("java.class.path"));
      var command = new java.util.ArrayList<String>();
      command.add(java);
      command.add("-Xms32m");
      command.add("-Xmx384m");
      command.add("-XX:MaxDirectMemorySize=64m");
      if (vn.vietdoc.VietDocApplication.class.getClassLoader().getClass().getName()
          .contains("LaunchedClassLoader")) {
        command.add("-jar");
        command.add(System.getProperty("java.class.path"));
      } else {
        command.add("-cp");
        command.add(classPath);
        command.add("vn.vietdoc.VietDocApplication");
      }
      command.add("--vietdoc-pdf-render");
      command.add(input.toString());
      command.add(pending.toString());
      command.add(Long.toString(maxPixels));
      Process process = new ProcessBuilder(command)
          .redirectErrorStream(true)
          .redirectOutput(ProcessBuilder.Redirect.DISCARD)
          .start();
      try {
        if (!process.waitFor(PDF_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS)) {
          process.destroyForcibly();
          process.waitFor(2, TimeUnit.SECONDS);
          throw new ApiException(422, "PDF_RENDER_TIMEOUT", "PDF xử lý quá lâu hoặc quá phức tạp.");
        }
      } catch (InterruptedException e) {
        process.destroyForcibly();
        Thread.currentThread().interrupt();
        throw new ApiException(503, "PDF_RENDER_INTERRUPTED", "Renderer PDF bị gián đoạn.");
      }
      if (process.exitValue() == 3)
        throw new ApiException(422, "PROFILE_UNSUPPORTED", "Chỉ nhận PDF không mã hóa, đúng một trang và trong giới hạn pixel.");
      if (process.exitValue() != 0 || !Files.isRegularFile(pending, LinkOption.NOFOLLOW_LINKS))
        throw new ApiException(422, "INPUT_CORRUPT", "Không giải mã được PDF trong giới hạn tài nguyên.");
      if (Files.size(pending) > 100L * 1024 * 1024)
        throw new ApiException(422, "PROFILE_UNSUPPORTED", "Ảnh PDF sau giải mã vượt giới hạn lưu trữ.");
      int width, height;
      try (ImageInputStream stream = ImageIO.createImageInputStream(pending.toFile())) {
        var readers = ImageIO.getImageReaders(stream);
        if (!readers.hasNext()) throw new IOException("Missing PNG reader");
        var reader = readers.next();
        try {
          reader.setInput(stream);
          width = reader.getWidth(0);
          height = reader.getHeight(0);
        } finally {
          reader.dispose();
        }
      }
      checkPixels(width, height);
      Files.move(pending, page(input.getParent().getFileName().toString()),
          StandardCopyOption.ATOMIC_MOVE);
      return new Dimension(width, height);
    } finally {
      PDF_SLOTS.release();
    }
  }

  private void checkPixels(long width, long height) {
    if (width <= 0
        || height <= 0
        || width > maxPixels
        || height > maxPixels
        || width * height > maxPixels)
      throw new ApiException(422, "PROFILE_UNSUPPORTED", "Ảnh vượt giới hạn 20 megapixel.");
  }

  public byte[] readPage(String id) {
    try {
      return Files.readAllBytes(page(id));
    } catch (IOException e) {
      throw new ApiException(503, "STORAGE_UNAVAILABLE", "Ảnh nguồn hiện không khả dụng.");
    }
  }

  public void remove(String id) {
    try {
      Files.deleteIfExists(directory(id).resolve("page.pending.png"));
      Files.deleteIfExists(page(id));
      Files.deleteIfExists(original(id));
      Files.deleteIfExists(directory(id));
    } catch (IOException ignored) {
    }
  }

  public Path root() {
    return root;
  }
}
