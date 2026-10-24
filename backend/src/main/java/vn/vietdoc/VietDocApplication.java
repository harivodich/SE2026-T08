package vn.vietdoc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;
import vn.vietdoc.document.PdfRenderMain;

@EnableScheduling
@SpringBootApplication(
    exclude =
        org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration
            .class)
public class VietDocApplication {
  public static void main(String[] args) {
    if (args.length == 4 && "--vietdoc-pdf-render".equals(args[0])) {
      try {
        PdfRenderMain.render(args[1], args[2], Long.parseLong(args[3]));
      } catch (IllegalArgumentException e) {
        System.exit(3);
      } catch (Exception e) {
        System.exit(2);
      }
      return;
    }
    SpringApplication.run(VietDocApplication.class, args);
  }
}
