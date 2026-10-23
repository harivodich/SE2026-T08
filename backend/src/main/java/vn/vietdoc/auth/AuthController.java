package vn.vietdoc.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
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

  public AuthController(AuthService auth) {
    this.auth = auth;
  }

  @PostMapping("/token")
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
    return auth.login(input.username, input.password);
  }

  @GetMapping("/me")
  public AuthService.Identity me(@AuthenticationPrincipal AuthService.Identity user) {
    return user;
  }

  @PostMapping("/logout")
  public Map<String, Boolean> logout(@RequestHeader("Authorization") String header) {
    auth.logout(header.substring(7));
    return Map.of("ok", true);
  }
}
