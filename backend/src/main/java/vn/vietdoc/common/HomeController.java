package vn.vietdoc.common;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class HomeController {
  @GetMapping({"/", "/index.html"})
  public String index() {
    return "index";
  }
}
