package vn.vietdoc.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;
import vn.vietdoc.common.ApiException;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
  public record Credentials(
      @NotBlank @Size(max = 100) String username, @NotBlank @Size(max = 200) String password) {}

  private record Bucket(long expires, int attempts) {}

  private final Map<String, Bucket> buckets = new ConcurrentHashMap<>();
  private final AuthService auth;
  private final int tokenHours;

  public AuthController(AuthService auth, @Value("${vietdoc.token-hours}") int tokenHours) {
    this.auth = auth;
    this.tokenHours = tokenHours;
  }

  @PostMapping("/session")
  public Map<String, Object> login(
      @Valid @RequestBody Credentials input, HttpServletRequest request) {
    long now = System.currentTimeMillis();
    if (buckets.size() > 10000) buckets.entrySet().removeIf(e -> e.getValue().expires < now);
    String key = request.getRemoteAddr();
    Bucket b =
        buckets.compute(
            key,
            (k, old) ->
                old == null || old.expires < now
                    ? new Bucket(now + 60000, 1)
                    : new Bucket(old.expires, old.attempts + 1));
    if (b.attempts > 15 || buckets.size() > 20000)
      throw new ApiException(
          429, "LOGIN_RATE_LIMIT", "Bạn thử đăng nhập quá nhiều lần. Hãy đợi một phút.");
    Map<String, Object> result = auth.login(input.username, input.password);
    var session = request.getSession(true);
    request.changeSessionId();
    session.setMaxInactiveInterval(tokenHours * 60 * 60);
    session.setAttribute("vietdoc-token", result.get("access_token"));
    return Map.of("user", result.get("user"), "expires_at", result.get("expires_at"));
  }

  @GetMapping("/me")
  public AuthService.Identity me(@AuthenticationPrincipal AuthService.Identity user) {
    return user;
  }

  @GetMapping("/csrf")
  public Map<String, String> csrf(HttpServletRequest request) {
    CsrfToken token = (CsrfToken) request.getAttribute("_csrf");
    return Map.of("token", token.getToken());
  }

  @PostMapping("/logout")
  public Map<String, Boolean> logout(HttpServletRequest request) {
    var session = request.getSession(false);
    if (session != null) {
      String token = (String) session.getAttribute("vietdoc-token");
      if (token != null) auth.logout(token);
      session.invalidate();
    }
    return Map.of("ok", true);
  }
}
