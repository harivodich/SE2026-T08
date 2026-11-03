package vn.vietdoc.auth;

import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.vietdoc.common.*;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.*;

@Service
public class AuthService {
  public record Identity(String id, String username) {}

  private final Store store;
  private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);
  private final SecureRandom random = new SecureRandom();
  private final int tokenHours;
  private final String dummyHash;

  public AuthService(Store store, @Value("${vietdoc.token-hours}") int tokenHours) {
    this.store = store;
    this.tokenHours = tokenHours;
    this.dummyHash = encoder.encode(Store.id());
  }

  @Transactional
  public void seed(String username, String password) {
    if (username.isBlank()) return;
    if (password.length() < 10)
      throw new IllegalStateException("SEED_PASSWORD must contain at least 10 characters");
    if (store
            .em()
            .createQuery("select count(u) from UserAccount u where u.username=:n", Long.class)
            .setParameter("n", username)
            .getSingleResult()
        > 0) return;
    UserAccount u = new UserAccount();
    u.id = Store.id();
    u.username = username;
    u.passwordHash = encoder.encode(password);
    u.createdAt = Instant.now();
    store.em().persist(u);
  }

  @Transactional
  public Map<String, Object> login(String username, String password) {
    List<UserAccount> matches =
        store
            .em()
            .createQuery("select u from UserAccount u where u.username=:n", UserAccount.class)
            .setParameter("n", username)
            .getResultList();
    String hash = matches.isEmpty() ? dummyHash : matches.get(0).passwordHash;
    if (!encoder.matches(password, hash) || matches.isEmpty())
      throw new ApiException(401, "INVALID_CREDENTIALS", "Tên đăng nhập hoặc mật khẩu không đúng.");
    UserAccount u = matches.get(0);
    byte[] bytes = new byte[32];
    random.nextBytes(bytes);
    String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    Session s = new Session();
    s.tokenHash = Json.sha256(token);
    s.userId = u.id;
    s.expiresAt = Instant.now().plus(Duration.ofHours(tokenHours));
    store.em().persist(s);
    return Map.of(
        "access_token",
        token,
        "token_type",
        "Bearer",
        "expires_at",
        s.expiresAt,
        "user",
        new Identity(u.id, u.username));
  }

  @Transactional(readOnly = true)
  public Identity authenticate(String token) {
    if (token == null || token.length() > 100) return null;
    Session s = store.em().find(Session.class, Json.sha256(token));
    if (s == null || !s.expiresAt.isAfter(Instant.now())) return null;
    UserAccount u = store.em().find(UserAccount.class, s.userId);
    return u == null ? null : new Identity(u.id, u.username);
  }

  @Transactional
  public void logout(String token) {
    Session s = store.em().find(Session.class, Json.sha256(token));
    if (s != null) store.em().remove(s);
  }

  @Transactional
  public void cleanup() {
    store
        .em()
        .createQuery("delete from Session s where s.expiresAt < :now")
        .setParameter("now", Instant.now())
        .executeUpdate();
  }
}
