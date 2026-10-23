package vn.vietdoc.document;

import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import javax.imageio.*;
import javax.imageio.stream.ImageInputStream;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import vn.vietdoc.common.*;

@Component
public class PrivateStorage {
  public record Asset(String contentType, String hash, long size, int width, int height) {}

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
      BufferedImage image;
      String contentType;
      if (bytes.length > 5
          && new String(bytes, 0, 5, java.nio.charset.StandardCharsets.US_ASCII).equals("%PDF-")) {
        contentType = "application/pdf";
        try (var pdf = Loader.loadPDF(bytes)) {
          if (pdf.isEncrypted() || pdf.getNumberOfPages() != 1)
            throw new ApiException(
                422, "PROFILE_UNSUPPORTED", "Chỉ nhận PDF không mã hóa, đúng một trang.");
          var box = pdf.getPage(0).getCropBox();
          checkPixels((long) Math.ceil(box.getWidth() * 2), (long) Math.ceil(box.getHeight() * 2));
          image = new PDFRenderer(pdf).renderImageWithDPI(0, 144);
        }
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
      }
      if (image == null) throw new IOException();
      checkPixels(image.getWidth(), image.getHeight());
      if (!ImageIO.write(image, "png", page(id).toFile())) throw new IOException();
      return new Asset(
          contentType, Json.sha256(bytes), bytes.length, image.getWidth(), image.getHeight());
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
