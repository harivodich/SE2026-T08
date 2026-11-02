package vn.vietdoc.document;

import java.awt.image.BufferedImage;
import java.nio.file.*;
import javax.imageio.ImageIO;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.rendering.PDFRenderer;

/** Runs only in the bounded PDF child JVM, before Spring starts. */
public final class PdfRenderMain {
  private PdfRenderMain() {}

  public static void render(String input, String output, long maxPixels) throws Exception {
    byte[] bytes = Files.readAllBytes(Path.of(input));
    if (bytes.length > 20L * 1024 * 1024) throw new IllegalArgumentException("PDF too large");
    try (var pdf = Loader.loadPDF(bytes)) {
      if (pdf.isEncrypted() || pdf.getNumberOfPages() != 1)
        throw new IllegalArgumentException("PDF must be unencrypted and one page");
      var box = pdf.getPage(0).getCropBox();
      checkPixels((long) Math.ceil(box.getWidth() * 2),
          (long) Math.ceil(box.getHeight() * 2), maxPixels);
      BufferedImage image = new PDFRenderer(pdf).renderImageWithDPI(0, 144);
      checkPixels(image.getWidth(), image.getHeight(), maxPixels);
      if (!ImageIO.write(image, "png", Path.of(output).toFile()))
        throw new IllegalStateException("PNG writer unavailable");
    }
  }

  private static void checkPixels(long width, long height, long maxPixels) {
    if (width <= 0 || height <= 0 || width > maxPixels || height > maxPixels ||
        width * height > maxPixels) throw new IllegalArgumentException("PDF pixels exceed profile");
  }
}
