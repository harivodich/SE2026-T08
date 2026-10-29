package vn.vietdoc.common;

import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class ErrorHandler {
  private static final Logger log = LoggerFactory.getLogger(ErrorHandler.class);

  public static Map<String, Object> envelope(
      String code, String message, Map<String, Object> details, String requestId) {
    return Map.of(
        "error",
        Map.of("code", code, "message", message, "details", details, "request_id", requestId));
  }

  @ExceptionHandler(ApiException.class)
  ResponseEntity<?> api(ApiException e, HttpServletRequest request) {
    return ResponseEntity.status(e.status)
        .body(envelope(e.code, e.getMessage(), e.details, requestId(request)));
  }

  @ExceptionHandler(MaxUploadSizeExceededException.class)
  ResponseEntity<?> size(HttpServletRequest r) {
    return api(new ApiException(413, "FILE_TOO_LARGE", "File vượt giới hạn 20 MiB."), r);
  }

  @ExceptionHandler({
    HttpMessageNotReadableException.class,
    MethodArgumentNotValidException.class,
    MethodArgumentTypeMismatchException.class,
    org.springframework.web.bind.MissingServletRequestParameterException.class,
    org.springframework.web.multipart.support.MissingServletRequestPartException.class
  })
  ResponseEntity<?> malformed(Exception e, HttpServletRequest r) {
    return api(
        new ApiException(400, "INVALID_REQUEST", "Dữ liệu yêu cầu không đúng định dạng."), r);
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<?> unexpected(Exception e, HttpServletRequest r) {
    String id = requestId(r);
    log.error("request_id={} error_type={}", id, e.getClass().getSimpleName());
    return ResponseEntity.status(500)
        .body(
            envelope(
                "INTERNAL_ERROR",
                "Có lỗi xử lý. Hãy thử lại hoặc liên hệ người quản trị.",
                Map.of(),
                id));
  }

  private String requestId(HttpServletRequest r) {
    return Optional.ofNullable((String) r.getAttribute("request_id"))
        .orElseGet(() -> UUID.randomUUID().toString());
  }
}
