package vn.vietdoc.auth;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;
import vn.vietdoc.common.*;

@Configuration
@org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication
public class SecurityConfig {
  @Bean
  ApplicationRunner seed(
      AuthService auth,
      @Value("${vietdoc.seed-username}") String user,
      @Value("${vietdoc.seed-password}") String password) {
    return args -> auth.seed(user, password);
  }

  @Bean
  SecurityFilterChain security(
      HttpSecurity http,
      AuthService auth,
      Json json)
      throws Exception {
    http.csrf(c -> c.csrfTokenRepository(
            new org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository()))
        .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
        .authorizeHttpRequests(
            a ->
                a.requestMatchers(
                        "/",
                        "/index.html",
                        "/app.js",
                        "/api.js",
                        "/domain.js",
                        "/styles.css",
                        "/api/v1/auth/session",
                        "/api/v1/auth/csrf",
                        "/health/**",
                        "/actuator/health/**",
                        "/error")
                    .permitAll()
                    .anyRequest()
                    .authenticated())
        .exceptionHandling(
            e ->
                e.authenticationEntryPoint(
                    (req, res, ex) -> {
                      res.setStatus(401);
                      res.setContentType("application/json;charset=UTF-8");
                      res.getWriter()
                          .write(
                              json.write(
                                  ErrorHandler.envelope(
                                      "UNAUTHENTICATED",
                                      "Phiên đăng nhập hết hạn. Hãy đăng nhập lại.",
                                      Map.of(),
                                      Objects.toString(req.getAttribute("request_id"), ""))));
                    }))
        .addFilterBefore(
            new OncePerRequestFilter() {
              @Override
              protected void doFilterInternal(
                  HttpServletRequest req, HttpServletResponse res, FilterChain chain)
                  throws ServletException, IOException {
                String requestId = UUID.randomUUID().toString();
                req.setAttribute("request_id", requestId);
                res.setHeader("X-Request-Id", requestId);
                if (req.getContentType() != null
                    && req.getContentType()
                        .toLowerCase(Locale.ROOT)
                        .startsWith("application/json")) {
                  byte[] body = req.getInputStream().readNBytes(1048577);
                  if (body.length > 1048576) {
                    res.setStatus(413);
                    res.setContentType("application/json;charset=UTF-8");
                    res.getWriter()
                        .write(
                            json.write(
                                ErrorHandler.envelope(
                                    "REQUEST_TOO_LARGE",
                                    "JSON request vượt giới hạn 1 MiB.",
                                    Map.of(),
                                    requestId)));
                    return;
                  }
                  req =
                      new HttpServletRequestWrapper(req) {
                        @Override
                        public ServletInputStream getInputStream() {
                          var bytes = new java.io.ByteArrayInputStream(body);
                          return new ServletInputStream() {
                            @Override
                            public int read() {
                              return bytes.read();
                            }

                            @Override
                            public boolean isFinished() {
                              return bytes.available() == 0;
                            }

                            @Override
                            public boolean isReady() {
                              return true;
                            }

                            @Override
                            public void setReadListener(ReadListener listener) {
                              throw new UnsupportedOperationException(
                                  "Only blocking request parsing is supported");
                            }
                          };
                        }

                        @Override
                        public java.io.BufferedReader getReader() {
                          return new java.io.BufferedReader(
                              new java.io.InputStreamReader(
                                  getInputStream(), java.nio.charset.StandardCharsets.UTF_8));
                        }
                      };
                }
                HttpSession session = req.getSession(false);
                if (session != null) {
                  String token = (String) session.getAttribute("vietdoc-token");
                  AuthService.Identity identity = auth.authenticate(token);
                  if (identity != null)
                    SecurityContextHolder.getContext()
                        .setAuthentication(
                            new UsernamePasswordAuthenticationToken(identity, null, List.of()));
                  else if (token != null) session.removeAttribute("vietdoc-token");
                }
                chain.doFilter(req, res);
              }
            },
            UsernamePasswordAuthenticationFilter.class);
    return http.build();
  }
}
