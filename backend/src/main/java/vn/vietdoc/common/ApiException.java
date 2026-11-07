package vn.vietdoc.common;

import java.util.Map;

public class ApiException extends RuntimeException {
  public final int status;
  public final String code;
  public final Map<String, Object> details;

  public ApiException(int status, String code, String message) {
    this(status, code, message, Map.of());
  }

  public ApiException(int status, String code, String message, Map<String, Object> details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  public static ApiException missing() {
    return new ApiException(
        404, "NOT_FOUND", "Không tìm thấy dữ liệu hoặc bạn không có quyền truy cập.");
  }
}
