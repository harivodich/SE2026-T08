package vn.vietdoc.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class HomeController {
  @Value("${vietdoc.mode}")
  private String processingMode;

  @GetMapping({"/", "/index.html"})
  public String index(Model model) {
    model.addAttribute("processingMode", processingMode);
    return "index";
  }
}
